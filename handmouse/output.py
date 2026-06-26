"""Device virtual de mouse (uinput) em modo relativo via python-evdev."""

from __future__ import annotations

from evdev import UInput
from evdev import ecodes as e


class UinputError(RuntimeError):
    pass


_CAPS = {
    e.EV_REL: [e.REL_X, e.REL_Y],
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

    def move(self, dx: int, dy: int) -> None:
        moved = False
        if dx:
            self._ui.write(e.EV_REL, e.REL_X, int(dx))
            moved = True
        if dy:
            self._ui.write(e.EV_REL, e.REL_Y, int(dy))
            moved = True
        if moved:
            self._ui.syn()

    def click(self) -> None:
        self._ui.write(e.EV_KEY, e.BTN_LEFT, 1)
        self._ui.syn()
        self._ui.write(e.EV_KEY, e.BTN_LEFT, 0)
        self._ui.syn()

    def close(self) -> None:
        if self._ui is not None:
            self._ui.close()
            self._ui = None
