"""Device virtual de mouse (uinput) em modo relativo via python-evdev."""

from __future__ import annotations

from evdev import UInput
from evdev import ecodes as e


class UinputError(RuntimeError):
    pass


_CAPS = {
    e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL],
    e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT],  # BTN_RIGHT declarado p/ facilitar a v2
}


class UinputMouse:
    def __init__(self):
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
        self._acc_wheel = 0.0
        self._left_down = False

    def move(self, dx: float, dy: float) -> None:
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

    def scroll(self, steps: float) -> None:
        self._acc_wheel += steps
        iw = int(self._acc_wheel)
        self._acc_wheel -= iw
        if iw:
            self._ui.write(e.EV_REL, e.REL_WHEEL, iw)
            self._ui.syn()

    def press_left(self) -> None:
        if self._left_down:
            return
        self._ui.write(e.EV_KEY, e.BTN_LEFT, 1)
        self._ui.syn()
        self._left_down = True

    def release_left(self) -> None:
        if not self._left_down:
            return
        self._ui.write(e.EV_KEY, e.BTN_LEFT, 0)
        self._ui.syn()
        self._left_down = False

    def click(self) -> None:
        self.press_left()
        self.release_left()

    def clear_motion(self) -> None:
        self._acc_x = 0.0
        self._acc_y = 0.0
        self._acc_wheel = 0.0

    def reset_state(self) -> None:
        self.clear_motion()
        self.release_left()

    def close(self) -> None:
        self.reset_state()
        if self._ui is not None:
            self._ui.close()
            self._ui = None
