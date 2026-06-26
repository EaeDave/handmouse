import importlib
import sys
import types
from types import SimpleNamespace


def _stub(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


_ev = _stub("evdev")


class FakeUI:
    def __init__(self, *a, **k):
        self.writes = []
        self.syns = 0

    def write(self, ev_type, code, value):
        self.writes.append((ev_type, code, value))

    def syn(self):
        self.syns += 1

    def close(self):
        pass


_ev.UInput = FakeUI
_ev.ecodes = SimpleNamespace(EV_REL=0, EV_KEY=1, REL_X=0, REL_Y=1, BTN_LEFT=272, BTN_RIGHT=273)

output_mod = importlib.import_module("handmouse.output")
output_mod = importlib.reload(output_mod)
UinputMouse = output_mod.UinputMouse


def test_subpixel_accumulates_until_whole_pixel():
    m = UinputMouse()
    ui = m._ui
    m.move(0.4, 0.0)
    m.move(0.4, 0.0)
    assert ui.writes == []
    assert ui.syns == 0
    m.move(0.4, 0.0)
    assert ui.writes == [(0, 0, 1)]  # 1.2 px acumulado -> emite 1
    assert ui.syns == 1


def test_subpixel_keeps_fractional_remainder():
    m = UinputMouse()
    ui = m._ui
    m.move(1.7, 0.0)
    assert ui.writes == [(0, 0, 1)]
    assert ui.syns == 1
    m.move(0.4, 0.0)
    assert ui.writes == [(0, 0, 1), (0, 0, 1)]  # 0.7 restante + 0.4 = 1.1 -> emite +1
    assert ui.syns == 2


def test_negative_subpixel_also_accumulates():
    m = UinputMouse()
    ui = m._ui
    m.move(-0.6, 0.0)
    assert ui.writes == []
    m.move(-0.6, 0.0)
    assert ui.writes == [(0, 0, -1)]
    assert ui.syns == 1
