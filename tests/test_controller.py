"""Testa os deltas de comportamento no caminho real de Controller.on_result.

As libs pesadas (evdev/cv2/mediapipe) sao stubadas para importar o controller sem
elas; o filtro One Euro e trocado por um passthrough (sua matematica e coberta em
test_filter). Assim isolamos a logica de movimento/teleporte/clique/pausa.
"""

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
_ev.ecodes = SimpleNamespace(EV_REL=0, EV_KEY=1, REL_X=0, REL_Y=1, BTN_LEFT=272, BTN_RIGHT=273)

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
        self.clicks = 0

    def move(self, dx, dy):
        self.moves.append((dx, dy))

    def click(self):
        self.clicks += 1

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
    c.cfg.notify = False  # nao dispara notificacoes reais nos testes
    c.output = FakeOut()
    c.filter = IdentFilter()
    c.paused = False
    return c


def test_first_frame_anchors_without_moving():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    assert c.output.moves == []
    assert c.last_anchor == (0.5, 0.5)


def test_normal_move_scales_delta_by_gain():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    c.on_result(_res(_landmarks(anchor=(0.52, 0.50))), None, 1100)
    assert c.output.moves == [(50, 0)]  # 0.02 * 2500 = 50


def test_anti_teleport_ignores_impossible_jump():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    c.on_result(_res(_landmarks(anchor=(0.95, 0.50))), None, 1100)  # delta 0.45 > 0.25
    assert c.output.moves == []
    assert c.last_anchor == (0.95, 0.50)  # re-ancorado mesmo sem mover


def test_hand_loss_resets_anchor():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    c.on_result(_res(None), None, 1100)
    assert c.last_anchor is None


def test_reacquire_after_loss_does_not_jump():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5))), None, 1000)
    c.on_result(_res(None), None, 1100)
    c.on_result(_res(_landmarks(anchor=(0.1, 0.9))), None, 1200)
    assert c.output.moves == []  # 1o frame da re-aquisicao nao move


def test_paused_gates_all_output():
    c = _fresh()
    c.paused = True
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5), thumb=(0.5, 0.5), index=(0.5, 0.5))), None, 2000)
    assert c.output.moves == []
    assert c.output.clicks == 0
    assert c.last_anchor is None


def test_closed_pinch_fires_click():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5), thumb=(0.5, 0.5), index=(0.5, 0.5))), None, 3000)
    assert c.output.clicks == 1


def test_open_pinch_no_click():
    c = _fresh()
    c.on_result(_res(_landmarks(anchor=(0.5, 0.5), thumb=(0.0, 0.0), index=(0.9, 0.0))), None, 4000)
    assert c.output.clicks == 0


def _lm(anchor=(0.5, 0.5), thumb=(0.0, 0.0), index=(0.3, 0.0),
        middle=True, ring=True, pinky=True):
    """Como _landmarks, mas tambem posiciona pip/tip de cada dedo p/ deteccao de punho."""
    pts = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    pts[0] = SimpleNamespace(x=0.5, y=1.0)               # wrist / palm_ref_a
    pts[9] = SimpleNamespace(x=anchor[0], y=anchor[1])   # anchor + palm_ref_b
    pts[4] = SimpleNamespace(x=thumb[0], y=thumb[1])     # thumb tip
    pts[6] = SimpleNamespace(x=0.5, y=0.5)               # index pip
    pts[8] = SimpleNamespace(x=index[0], y=index[1])     # index tip (pinca)
    for pip, tip, ext in [(10, 12, middle), (14, 16, ring), (18, 20, pinky)]:
        pts[pip] = SimpleNamespace(x=0.5, y=0.5)
        pts[tip] = SimpleNamespace(x=0.5, y=(0.1 if ext else 0.6))
    return pts


def test_pinch_click_with_open_fingers_fires():
    c = _fresh()
    c.on_result(_res(_lm(thumb=(0.5, 0.45), index=(0.5, 0.5))), None, 1000)
    assert c.output.clicks == 1


def test_fist_pose_suppresses_click():
    c = _fresh()
    fist = _lm(thumb=(0.5, 0.58), index=(0.5, 0.6), middle=False, ring=False, pinky=False)
    c.on_result(_res(fist), None, 0)
    assert c.output.clicks == 0       # punho nao clica mesmo com polegar+indicador juntos
    assert c.suspended is False        # dwell ainda nao atingido


def test_fist_hold_toggles_soft_suspend():
    c = _fresh()
    fist = _lm(thumb=(0.5, 0.58), index=(0.5, 0.6), middle=False, ring=False, pinky=False)
    c.on_result(_res(fist), None, 0)      # inicia dwell
    c.on_result(_res(fist), None, 400)    # >= dwell -> suspende
    assert c.suspended is True
    # suspenso: pinca normal nao move nem clica
    c.on_result(_res(_lm(thumb=(0.5, 0.45), index=(0.5, 0.5))), None, 500)
    assert c.output.clicks == 0
    assert c.output.moves == []
    # novo punho retoma
    c.on_result(_res(fist), None, 600)
    c.on_result(_res(fist), None, 1000)
    assert c.suspended is False


def test_keybind_reactivate_clears_soft_suspend():
    c = _fresh()
    c.suspended = True
    c.paused = True
    c._apply_pause(False, "atalho")
    assert c.suspended is False
