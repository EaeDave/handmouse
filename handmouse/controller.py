"""Laco principal: junta captura, tracking, filtro, gestos e saida uinput.

Modelo de concorrencia (Q1): a main thread so captura + submete frames; o trabalho
por-frame (filtro, mover, clicar) roda inline no result_callback do MediaPipe, que
e barato. A abertura/fechamento da camera e o tratamento de sinais ficam na main thread.

Deltas de comportamento implementados aqui:
  D1 relativo + clutch       -> reset de last_anchor ao perder a mao.
  D2 sobe pausado            -> paused = cfg.start_paused.
  D4 anti-teleporte          -> salto impossivel num frame e ignorado e re-ancorado.
  D5 notificacao no toggle    -> notify-send em cada troca de estado.
  D7 pausado solta a camera  -> camera so fica aberta enquanto ativo.
  D8 auto-pause por inatividade -> sem mao por cfg.idle_pause_s segundos -> pausa.
  D9 interruptor por gesto   -> punho alterna pausa SUAVE (cam segue ligada).
"""

from __future__ import annotations

import logging
import math
import signal
import subprocess
import time

from .capture import Camera, CameraError
from .config import Config, load_config
from .filter import Point2DFilter
from .gestures import EVENT_CLICK, FistToggle, PinchDetector, is_fist, others_curled, pinch_distance
from .output import UinputMouse
from .tracker import HandTracker

log = logging.getLogger("handmouse")


def _now_ms() -> int:
    return time.monotonic_ns() // 1_000_000


def _notify(enabled: bool, body: str) -> None:
    if not enabled:
        return
    try:
        subprocess.Popen(
            ["notify-send", "-a", "handmouse", "handmouse", body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # notify-send ausente: degrada para so-log


class Controller:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load_config()
        self.output = UinputMouse()
        self.filter = Point2DFilter(self.cfg.oe_min_cutoff, self.cfg.oe_beta, self.cfg.oe_d_cutoff)
        self.pinch = PinchDetector(self.cfg)
        self.suspended = False  # D9: pausa SUAVE via gesto (cam segue ligada)
        self.fist = FistToggle(self.cfg.gesture_dwell_ms) if self.cfg.gesture_toggle == "fist" else None
        self.tracker: HandTracker | None = None
        self.camera: Camera | None = None

        self.paused: bool = self.cfg.start_paused
        self.last_anchor: tuple[float, float] | None = None
        self.last_hand_ms: int = _now_ms()
        self._last_t: float = 0.0  # p/ aceleracao (dt entre frames)

        self._running = True
        self._toggle_requested = False
        self._cam_fail_streak = 0

    # ---- sinais (main thread): so setam flags ------------------------------
    def _on_toggle(self, *_):
        self._toggle_requested = True

    def _on_term(self, *_):
        self._running = False

    # ---- estado de pausa (main thread) -------------------------------------
    def _apply_pause(self, paused: bool, reason: str) -> None:
        if paused == self.paused:
            return
        self.paused = paused
        if paused:
            log.info("pausado (%s)", reason)
            _notify(self.cfg.notify, f"pausado ({reason})")
        else:
            self.last_hand_ms = _now_ms()  # D8: carencia ao reativar
            self.suspended = False         # reativar (keybind) limpa a suspensao por gesto
            if self.fist is not None:
                self.fist.reset()
            log.info("ativo")
            _notify(self.cfg.notify, "ativo")

    # ---- callback do MediaPipe (thread interna) ----------------------------
    def on_result(self, result, image, timestamp_ms: int) -> None:
        if self.paused:
            self.last_anchor = None
            return

        hands = getattr(result, "hand_landmarks", None)
        if not hands:
            # D1: mao sumiu -> reseta estado p/ nao "saltar" ao reaparecer
            self.last_anchor = None
            self.filter.reset()
            self.pinch.reset()
            if self.fist is not None:
                self.fist.reset()
            return

        lm = hands[0]
        self.last_hand_ms = _now_ms()

        # D9: punho mantido alterna a pausa SUAVE (cam fica ligada p/ ver o gesto de voltar)
        if self.fist is not None and self.fist.update(is_fist(lm), timestamp_ms):
            self.suspended = not self.suspended
            self.last_anchor = None
            self.filter.reset()
            self.pinch.reset()
            estado = "suspenso (gesto)" if self.suspended else "retomado (gesto)"
            log.info("%s", estado)
            _notify(self.cfg.notify, estado)
            return

        if self.suspended:
            self.last_anchor = None  # congela: nao move nem clica
            return

        anchor = lm[self.cfg.anchor_landmark]
        t = timestamp_ms / 1000.0
        fx, fy = self.filter.filter(anchor.x, anchor.y, t)

        if self.last_anchor is None:
            self.last_anchor = (fx, fy)  # 1o frame apos (re)aquisicao: sem movimento
            self._last_t = t
        else:
            dt = max(t - self._last_t, 1e-3)
            self._last_t = t
            dnx = fx - self.last_anchor[0]
            dny = fy - self.last_anchor[1]
            self.last_anchor = (fx, fy)
            thr = self.cfg.teleport_threshold
            if abs(dnx) <= thr and abs(dny) <= thr:  # D4: salto impossivel -> ignora
                g = self.cfg.gain * self._accel_mult(dnx, dny, dt)
                self.output.move(dnx * g, dny * g)  # float -> output faz o sub-pixel

        # clique: pinca polegar+indicador, mas NAO quando a mao fecha em punho (D9/A)
        d = pinch_distance(lm, self.cfg)
        if self.pinch.update(d, timestamp_ms) == EVENT_CLICK and not others_curled(lm):
            self.output.click()
            log.debug("click (d=%.3f)", d)

    def _accel_mult(self, dnx: float, dny: float, dt: float) -> float:
        # aceleracao: devagar -> accel_min (preciso); rapido -> accel_max (veloz)
        if not self.cfg.accel:
            return 1.0
        speed = math.hypot(dnx, dny) / dt
        if self.cfg.accel_speed <= 0:
            return self.cfg.accel_max
        ratio = min(speed / self.cfg.accel_speed, 1.0)
        return self.cfg.accel_min + (self.cfg.accel_max - self.cfg.accel_min) * ratio

    # ---- camera (main thread) ----------------------------------------------
    def _close_camera(self) -> None:
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.last_anchor = None
        self.filter.reset()

    def _open_camera(self) -> bool:
        try:
            self.camera = Camera(self.cfg.camera_index, self.cfg.frame_width, self.cfg.frame_height, self.cfg.camera_fps, self.cfg.camera_mjpg)
        except CameraError as exc:
            log.warning("%s", exc)
            return False
        self._cam_fail_streak = 0
        return True

    def _handle_read_failure(self) -> None:
        # D7/Q7: camera sumiu em uso (suspend/resume, app roubou) -> re-tenta vivo
        self._cam_fail_streak += 1
        if self._cam_fail_streak == 1:
            log.warning("falha ao ler a camera; tentando reabrir...")
        self._close_camera()
        time.sleep(min(2.0, 0.2 * self._cam_fail_streak))

    # ---- laco principal -----------------------------------------------------
    def run(self) -> None:
        signal.signal(signal.SIGUSR1, self._on_toggle)
        signal.signal(signal.SIGTERM, self._on_term)
        signal.signal(signal.SIGINT, self._on_term)

        self.tracker = HandTracker(
            self.cfg.model_path,
            self.on_result,
            num_hands=1,
            min_detection_confidence=self.cfg.min_detection_confidence,
            min_tracking_confidence=self.cfg.min_tracking_confidence,
            delegate=self.cfg.delegate,
        )
        estado = "pausado" if self.paused else "ativo"
        log.info("handmouse iniciado (%s)", estado)
        _notify(self.cfg.notify, f"iniciado ({estado})")

        try:
            while self._running:
                if self._toggle_requested:
                    self._toggle_requested = False
                    self._apply_pause(not self.paused, "atalho")

                if self.paused:
                    self._close_camera()  # D7: libera a webcam p/ outros apps
                    time.sleep(0.1)
                    continue

                if self.camera is None and not self._open_camera():
                    self._apply_pause(True, "camera ocupada")  # D7
                    continue

                frame = self.camera.read()
                if frame is None:
                    self._handle_read_failure()
                    continue
                self._cam_fail_streak = 0

                self.tracker.submit(frame, _now_ms())

                if self.cfg.idle_pause_s > 0 and (_now_ms() - self.last_hand_ms) > self.cfg.idle_pause_s * 1000:
                    self._apply_pause(True, "inatividade")  # D8
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        log.info("encerrando")
        if self.tracker is not None:
            self.tracker.close()  # primeiro: garante que nao ha mais callbacks
        self._close_camera()
        self.output.close()


def run_tune(cfg: Config | None = None) -> int:
    """Modo diagnostico: mostra ao vivo distancia de pinca, punho, velocidade e fps.
    Nao mexe no mouse (sem uinput). Requer a camera livre (pare o servico antes)."""
    cfg = cfg or load_config()
    state = {"last": None, "last_t": 0.0, "n": 0, "t0": time.monotonic()}

    def on_result(result, image, timestamp_ms):
        state["n"] += 1
        elapsed = time.monotonic() - state["t0"]
        fps = state["n"] / elapsed if elapsed > 0 else 0.0
        hands = getattr(result, "hand_landmarks", None)
        if not hands:
            msg = f"sem mao              | fps {fps:4.1f}"
        else:
            lm = hands[0]
            d = pinch_distance(lm, cfg)
            t = timestamp_ms / 1000.0
            a = lm[cfg.anchor_landmark]
            speed = 0.0
            if state["last"] is not None:
                dt = max(t - state["last_t"], 1e-3)
                speed = math.hypot(a.x - state["last"][0], a.y - state["last"][1]) / dt
            state["last"] = (a.x, a.y)
            state["last_t"] = t
            click = d < cfg.pinch_close_threshold and not others_curled(lm)
            msg = (
                f"pinch d={d:5.2f} (close<{cfg.pinch_close_threshold:.2f}) "
                f"{'CLICK' if click else '     '} "
                f"{'PUNHO' if is_fist(lm) else '     '} | vel={speed:4.1f}/s | fps {fps:4.1f}"
            )
        print("\r" + msg.ljust(78), end="", flush=True)

    camera = Camera(cfg.camera_index, cfg.frame_width, cfg.frame_height, cfg.camera_fps, cfg.camera_mjpg)
    tracker = HandTracker(
        cfg.model_path,
        on_result,
        num_hands=1,
        min_detection_confidence=cfg.min_detection_confidence,
        min_tracking_confidence=cfg.min_tracking_confidence,
        delegate=cfg.delegate,
    )
    print("handmouse tune — Ctrl+C p/ sair (nao mexe no mouse).")
    try:
        while True:
            frame = camera.read()
            if frame is None:
                time.sleep(0.05)
                continue
            tracker.submit(frame, _now_ms())
    except KeyboardInterrupt:
        pass
    finally:
        print()
        tracker.close()
        camera.release()
    return 0
