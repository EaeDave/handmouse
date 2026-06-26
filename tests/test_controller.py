"""Testa deltas de comportamento no caminho real de Controller.on_result."""

import sys
import types
from types import SimpleNamespace


def _stub(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


# --- stubs de libs pesadas (antes de importar o controller) ---
_ev = _stub("evdev")


class _UInput:
    def __init__(self, *a, **k):
        pass

    def write(self, *a):
        pass

    def syn(self):
        pass

    def close(self):
        pass


_ev.UInput = _UInput
_ev.ecodes = SimpleNamespace(EV_REL=0, EV_KEY=1, REL_X=0, REL_Y=1, REL_WHEEL=8, BTN_LEFT=272, BTN_RIGHT=273)

_stub("cv2")
_mp = _stub("mediapipe")
_mpt = _stub("mediapipe.tasks")
_mpp = _stub("mediapipe.tasks.python")
_mpv = _stub("mediapipe.tasks.python.vision")
_mp.tasks = _mpt
_mpt.python = _mpp
_mpp.vision = _mpv

from handmouse.config import Config  # noqa: E402
from handmouse.controller import Controller  # noqa: E402


class FakeOut:
    def __init__(self):
        self.moves = []
        self.wheels = []
        self.presses = 0
        self.releases = 0
        self.clears = 0

    def move(self, dx, dy):
        self.moves.append((dx, dy))

    def scroll(self, steps):
        self.wheels.append(steps)

    def press_left(self):
        self.presses += 1

    def release_left(self):
        self.releases += 1

    def click(self):
        self.presses += 1
        self.releases += 1

    def clear_motion(self):
        self.clears += 1

    def reset_state(self):
        self.clears += 1

    def close(self):
        pass


class IdentFilter:
    def filter(self, x, y, t):
        return (x, y)

    def reset(self):
        pass


def _landmarks(anchor=(0.5, 0.5), thumb=(0.0, 0.0), index=(0.3, 0.0)):
    pts = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    pts[9] = SimpleNamespace(x=anchor[0], y=anchor[1])  # anchor + palm_ref_b
    pts[0] = SimpleNamespace(x=0.0, y=0.0)              # palm_ref_a (wrist)
    pts[4] = SimpleNamespace(x=thumb[0], y=thumb[1])
    pts[8] = SimpleNamespace(x=index[0], y=index[1])
    return pts


def _res(lm):
    return SimpleNamespace(hand_landmarks=([lm] if lm else []))


def _fresh(cfg=None):
    c = Controller(cfg or Config())
    c.cfg.notify = False
    c.cfg.accel = False
    c.output = FakeOut()
    c.filter = IdentFilter()
    c.paused = False
    return c


def _lm(anchor=(0.5, 0.5), thumb=(0.0, 0.0), index=(0.3, 0.0),
        index_ext=None, middle=True, ring=True, pinky=True):
    """Landmarks com pose controlavel.

    index_ext:
      None -> usa index tip passado (p/ pinca)
      True/False -> gera pose estendida/curvada p/ index finger
    """
    pts = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    pts[0] = SimpleNamespace(x=0.5, y=1.0)               # wrist / palm_ref_a
    pts[9] = SimpleNamespace(x=anchor[0], y=anchor[1])   # anchor + palm_ref_b
    pts[4] = SimpleNamespace(x=thumb[0], y=thumb[1])     # thumb tip
    pts[6] = SimpleNamespace(x=0.5, y=0.5)               # index pip
    if index_ext is None:
        pts[8] = SimpleNamespace(x=index[0], y=index[1])
    else:
        pts[8] = SimpleNamespace(x=0.5, y=(0.1 if index_ext else 0.6))
    for pip, tip, ext in [(10, 12, middle), (14, 16, ring), (18, 20, pinky)]:
        pts[pip] = SimpleNamespace(x=0.5, y=0.5)
        pts[tip] = SimpleNamespace(x=0.5, y=(0.1 if ext else 0.6))
    return pts


def test_first_frame_anchors_without_moving():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    assert c.output.moves == []
    assert c.last_anchor == (0.5, 0.5)


def test_normal_move_scales_delta_by_gain():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    c.on_result(_res(_landmarks(anchor=(0.52, 0.50))), None, 1100)
    dx, dy = c.output.moves[0]
    assert abs(dx - 50.0) < 1e-9
    assert dy == 0.0


def test_anti_teleport_ignores_impossible_jump():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    c.on_result(_res(_landmarks(anchor=(0.95, 0.50))), None, 1100)
    assert c.output.moves == []
    assert c.last_anchor == (0.95, 0.50)


def test_hand_loss_resets_anchor_and_output_state():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    c.on_result(_res(None), None, 1100)
    assert c.last_anchor is None
    assert c.output.clears >= 1


def test_reacquire_after_loss_does_not_jump():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    c.on_result(_res(None), None, 1100)
    c.on_result(_res(_landmarks(anchor=(0.1, 0.9))), None, 1200)
    assert c.output.moves == []


def test_paused_gates_all_output():
    c = _fresh()
    c.paused = True
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5), thumb=(0.5, 0.5), index=(0.5, 0.5))), None, 2000)
    assert c.output.moves == []
    assert c.output.presses == 0
    assert c.last_anchor is None


def test_pinch_press_then_release_for_simple_click():
    c = _fresh()
    c.on_result(_res(_lm(thumb=(0.5, 0.49), index=(0.5, 0.50))), None, 1000)
    assert c.output.presses == 1
    assert c.output.releases == 0
    c.on_result(_res(_lm(thumb=(0.0, 0.0), index=(0.9, 0.0))), None, 1100)
    assert c.output.releases == 1


def test_drag_keeps_button_down_while_moving_pinched():
    c = _fresh()
    c.on_result(_res(_lm(anchor=(0.5, 0.5), thumb=(0.5, 0.49), index=(0.5, 0.50))), None, 1000)
    c.on_result(_res(_lm(anchor=(0.52, 0.50), thumb=(0.5, 0.49), index=(0.5, 0.50))), None, 1100)
    assert c.output.presses == 1
    assert c.output.releases == 0
    assert c.output.moves  # arrastou com botao ainda pressionado


def test_open_pinch_no_press():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5), thumb=(0.0, 0.0), index=(0.9, 0.0))), None, 4000)
    assert c.output.presses == 0


def test_pinch_with_closed_other_fingers_suppressed():
    c = _fresh()
    fistish = _lm(thumb=(0.5, 0.58), index=(0.5, 0.6), middle=False, ring=False, pinky=False)
    c.on_result(_res(fistish), None, 0)
    assert c.output.presses == 0


def test_fist_hold_toggles_soft_suspend():
    c = _fresh()
    fist = _lm(thumb=(0.5, 0.58), index_ext=False, middle=False, ring=False, pinky=False)
    c.on_result(_res(fist), None, 0)
    c.on_result(_res(fist), None, 400)
    assert c.suspended is True
    c.on_result(_res(_lm(thumb=(0.5, 0.49), index=(0.5, 0.5))), None, 500)
    assert c.output.presses == 0
    assert c.output.moves == []
    c.on_result(_res(fist), None, 600)
    c.on_result(_res(fist), None, 1000)
    assert c.suspended is False


def test_keybind_reactivate_clears_soft_suspend():
    c = _fresh()
    c.suspended = True
    c.paused = True
    c._apply_pause(False, "atalho")
    assert c.suspended is False


def test_scroll_pose_after_dwell_emits_wheel_not_cursor_move():
    cfg = Config(scroll_dwell_ms=200, scroll_gain=40.0)
    c = _fresh(cfg)
    pose1 = _lm(anchor=(0.5, 0.50), index_ext=True, middle=True, ring=False, pinky=False)
    pose2 = _lm(anchor=(0.5, 0.45), index_ext=True, middle=True, ring=False, pinky=False)
    c.on_result(_res(pose1), None, 1000)  # inicia dwell
    c.on_result(_res(pose1), None, 1200)  # ativa scroll
    c.on_result(_res(pose2), None, 1300)  # move pra cima -> wheel positivo
    assert c.output.moves == []
    assert c.output.wheels and c.output.wheels[-1] > 0


def test_accel_mult_grows_with_speed_and_caps():
    cfg = Config()
    c = _fresh(cfg)
    c.cfg.accel = True
    c.cfg.accel_min = 0.4
    c.cfg.accel_max = 2.0
    c.cfg.accel_speed = 2.5
    slow = c._accel_mult(0.01, 0.0, 0.02)
    fast = c._accel_mult(0.10, 0.0, 0.02)
    assert 0.4 <= slow < fast
    assert fast == 2.0
