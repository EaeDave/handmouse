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
MotionSmoother = output_mod.MotionSmoother
UinputMouse = output_mod.UinputMouse


def test_motion_smoother_splits_delta_into_lead_and_tail():
    s = MotionSmoother(enabled=True, horizon_ms=20, lead_ratio=0.25)
    lead_x, lead_y = s.queue(8.0, 0.0)
    assert (lead_x, lead_y) == (2.0, 0.0)
    assert s.pending_x == 6.0
    assert s.remaining_s == 0.02
    assert s.drain(0.01) == (3.0, 0.0)
    assert s.drain(0.01) == (3.0, 0.0)


def test_motion_smoother_disabled_passthrough():
    s = MotionSmoother(enabled=False, horizon_ms=20, lead_ratio=0.25)
    assert s.queue(5.0, -2.0) == (5.0, -2.0)
    assert s.drain(0.1) == (0.0, 0.0)


def test_subpixel_accumulates_until_whole_pixel():
    m = UinputMouse(fake_smoothness=False)
    ui = m._ui
    m.move(0.4, 0.0)
    m.move(0.4, 0.0)
    assert ui.writes == []
    assert ui.syns == 0
    m.move(0.4, 0.0)
    assert ui.writes == [(0, 0, 1)]  # 1.2 px acumulado -> emite 1
    assert ui.syns == 1
    m.close()


def test_subpixel_keeps_fractional_remainder():
    m = UinputMouse(fake_smoothness=False)
    ui = m._ui
    m.move(1.7, 0.0)
    assert ui.writes == [(0, 0, 1)]
    assert ui.syns == 1
    m.move(0.4, 0.0)
    assert ui.writes == [(0, 0, 1), (0, 0, 1)]  # 0.7 restante + 0.4 = 1.1 -> emite +1
    assert ui.syns == 2
    m.close()


def test_negative_subpixel_also_accumulates():
    m = UinputMouse(fake_smoothness=False)
    ui = m._ui
    m.move(-0.6, 0.0)
    assert ui.writes == []
    m.move(-0.6, 0.0)
    assert ui.writes == [(0, 0, -1)]
    assert ui.syns == 1
    m.close()
