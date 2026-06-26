"""Device virtual de mouse (uinput) em modo relativo via python-evdev."""

from __future__ import annotations

import threading
import time

from evdev import UInput
from evdev import ecodes as e


class UinputError(RuntimeError):
    pass


_CAPS = {
    e.EV_REL: [e.REL_X, e.REL_Y],
    e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT],  # BTN_RIGHT declarado p/ facilitar a v2
}


class MotionSmoother:
    """Fake smoothness segura: aplica uma parte do delta na hora e espalha o resto
    em micro-passos ao longo de um pequeno horizonte temporal.

    Nao cria frames reais da camera; so evita o "degrau" grande entre amostras de 30 fps.
    """

    def __init__(self, enabled: bool = True, horizon_ms: int = 28, lead_ratio: float = 0.35):
        self.enabled = enabled
        self.horizon_s = max(horizon_ms, 0) / 1000.0
        self.lead_ratio = min(max(lead_ratio, 0.0), 1.0)
        self.pending_x = 0.0
        self.pending_y = 0.0
        self.remaining_s = 0.0

    def queue(self, dx: float, dy: float) -> tuple[float, float]:
        if not self.enabled:
            return dx, dy
        lead_x = dx * self.lead_ratio
        lead_y = dy * self.lead_ratio
        self.pending_x += dx - lead_x
        self.pending_y += dy - lead_y
        self.remaining_s = self.horizon_s
        return lead_x, lead_y

    def drain(self, dt: float) -> tuple[float, float]:
        if not self.enabled:
            return 0.0, 0.0
        if abs(self.pending_x) < 1e-9 and abs(self.pending_y) < 1e-9:
            self.pending_x = 0.0
            self.pending_y = 0.0
            self.remaining_s = 0.0
            return 0.0, 0.0
        if self.horizon_s <= 0 or self.remaining_s <= dt:
            out_x, out_y = self.pending_x, self.pending_y
            self.pending_x = 0.0
            self.pending_y = 0.0
            self.remaining_s = 0.0
            return out_x, out_y
        ratio = dt / self.remaining_s
        out_x = self.pending_x * ratio
        out_y = self.pending_y * ratio
        self.pending_x -= out_x
        self.pending_y -= out_y
        self.remaining_s -= dt
        return out_x, out_y

    def clear(self) -> None:
        self.pending_x = 0.0
        self.pending_y = 0.0
        self.remaining_s = 0.0


class UinputMouse:
    def __init__(
        self,
        fake_smoothness: bool = True,
        tick_hz: int = 200,
        horizon_ms: int = 28,
        lead_ratio: float = 0.35,
    ):
        try:
            self._ui = UInput(_CAPS, name="handmouse")
        except (PermissionError, OSError) as exc:
            raise UinputError(
                "nao consegui criar o device uinput (/dev/uinput). "
                "Rode scripts/install.sh e confirme que voce esta no grupo 'input' "
                "e que a regra udev foi aplicada. Detalhe: %s" % exc
            ) from exc
        self._acc_x = 0.0
        self._acc_y = 0.0
        self._lock = threading.Lock()
        self._tick_hz = max(int(tick_hz), 1)
        self._smooth = MotionSmoother(fake_smoothness, horizon_ms, lead_ratio)
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        if fake_smoothness:
            self._worker = threading.Thread(target=self._run_worker, name="handmouse-smoother", daemon=True)
            self._worker.start()

    def _emit_unlocked(self, dx: float, dy: float) -> None:
        # acumula a fracao de pixel entre frames -> movimento fino nao se perde (sub-pixel)
        self._acc_x += dx
        self._acc_y += dy
        ix = int(self._acc_x)  # trunca p/ zero, guarda o resto
        iy = int(self._acc_y)
        self._acc_x -= ix
        self._acc_y -= iy
        if ix:
            self._ui.write(e.EV_REL, e.REL_X, ix)
        if iy:
            self._ui.write(e.EV_REL, e.REL_Y, iy)
        if ix or iy:
            self._ui.syn()

    def _run_worker(self) -> None:
        last = time.monotonic()
        interval = 1.0 / self._tick_hz
        while not self._stop.wait(interval):
            now = time.monotonic()
            dt = now - last
            last = now
            with self._lock:
                dx, dy = self._smooth.drain(dt)
                if dx or dy:
                    self._emit_unlocked(dx, dy)

    def move(self, dx: float, dy: float) -> None:
        with self._lock:
            lead_x, lead_y = self._smooth.queue(dx, dy)
            self._emit_unlocked(lead_x, lead_y)

    def clear_motion(self) -> None:
        with self._lock:
            self._smooth.clear()
            self._acc_x = 0.0
            self._acc_y = 0.0

    def click(self) -> None:
        with self._lock:
            self._ui.write(e.EV_KEY, e.BTN_LEFT, 1)
            self._ui.syn()
            self._ui.write(e.EV_KEY, e.BTN_LEFT, 0)
            self._ui.syn()

    def close(self) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=0.2)
        if self._ui is not None:
            self._ui.close()
            self._ui = None
