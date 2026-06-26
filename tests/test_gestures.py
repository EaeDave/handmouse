from types import SimpleNamespace

from handmouse.config import Config
from handmouse.gestures import EVENT_CLICK, FistToggle, PinchDetector, is_fist, others_curled, pinch_distance


def _landmarks(thumb, index, ref_a=(0.0, 0.0), ref_b=(0.0, 0.1)):
    cfg = Config()
    pts = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    pts[cfg.thumb_tip] = SimpleNamespace(x=thumb[0], y=thumb[1])
    pts[cfg.index_tip] = SimpleNamespace(x=index[0], y=index[1])
    pts[cfg.palm_ref_a] = SimpleNamespace(x=ref_a[0], y=ref_a[1])
    pts[cfg.palm_ref_b] = SimpleNamespace(x=ref_b[0], y=ref_b[1])
    return pts, cfg


def test_pinch_distance_ratio():
    pts, cfg = _landmarks(thumb=(0.0, 0.0), index=(0.0, 0.05), ref_b=(0.0, 0.1))
    assert abs(pinch_distance(pts, cfg) - 0.5) < 1e-9  # 0.05 / 0.10


def test_pinch_distance_invariant_to_hand_scale():
    p1, cfg = _landmarks((0, 0), (0, 0.05), ref_b=(0, 0.1))   # ratio 0.5
    p2, _ = _landmarks((0, 0), (0, 0.10), ref_b=(0, 0.2))     # mao 2x maior, ratio 0.5
    assert abs(pinch_distance(p1, cfg) - pinch_distance(p2, cfg)) < 1e-9


def test_click_fires_when_closing():
    d = PinchDetector(Config())
    assert d.update(0.30, 1000) == EVENT_CLICK
    assert d.state == "CLOSED"


def test_no_repeat_click_while_closed():
    d = PinchDetector(Config())
    d.update(0.30, 1000)
    assert d.update(0.30, 1100) is None


def test_hysteresis_midzone_keeps_closed():
    d = PinchDetector(Config())
    d.update(0.30, 1000)
    assert d.update(0.45, 1100) is None  # entre close(.35) e open(.55)
    assert d.state == "CLOSED"


def test_reopen_then_second_click():
    d = PinchDetector(Config())
    assert d.update(0.30, 1000) == EVENT_CLICK
    assert d.update(0.60, 1200) is None  # > open -> OPEN
    assert d.state == "OPEN"
    assert d.update(0.30, 1400) == EVENT_CLICK


def test_debounce_blocks_fast_toggle():
    d = PinchDetector(Config())  # debounce 60 ms
    assert d.update(0.30, 1000) == EVENT_CLICK
    assert d.update(0.60, 1030) is None  # dentro do debounce -> bloqueado
    assert d.state == "CLOSED"
    assert d.update(0.60, 1100) is None  # passado o debounce -> abre
    assert d.state == "OPEN"


def _hand(index=True, middle=True, ring=True, pinky=True):
    """Mao sintetica: wrist embaixo; ponta esticada = longe do pulso, curvada = perto."""
    pts = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    pts[0] = SimpleNamespace(x=0.5, y=1.0)  # wrist
    for pip, tip, ext in [(6, 8, index), (10, 12, middle), (14, 16, ring), (18, 20, pinky)]:
        pts[pip] = SimpleNamespace(x=0.5, y=0.5)
        pts[tip] = SimpleNamespace(x=0.5, y=(0.1 if ext else 0.6))
    return pts


def _partial_finger_hand():
    """Dedos levemente dobrados, mas longe de 'completamente fechados'."""
    pts = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    pts[0] = SimpleNamespace(x=0.5, y=1.0)
    for pip, tip in [(6, 8), (10, 12), (14, 16), (18, 20)]:
        pts[pip] = SimpleNamespace(x=0.5, y=0.5)
        pts[tip] = SimpleNamespace(x=0.5, y=0.54)  # ratio ~0.92 -> ainda NAO fechado
    return pts


def test_is_fist_all_curled():
    assert is_fist(_hand(index=False, middle=False, ring=False, pinky=False)) is True


def test_is_fist_false_for_pinch_pose():
    # pinca: indicador dobrado, mas medio/anelar/mindinho esticados
    assert is_fist(_hand(index=False, middle=True, ring=True, pinky=True)) is False


def test_is_fist_false_open_hand():
    assert is_fist(_hand()) is False


def test_is_fist_false_when_only_partially_closed():
    assert is_fist(_partial_finger_hand()) is False
    assert others_curled(_partial_finger_hand()) is False


def test_others_curled_needs_all_three():
    assert others_curled(_hand(middle=False, ring=False, pinky=False)) is True
    assert others_curled(_hand(middle=False, ring=False, pinky=True)) is False
    assert others_curled(_hand()) is False


def test_fist_toggle_dwell_edge_trigger():
    ft = FistToggle(400)
    assert ft.update(True, 0) is False
    assert ft.update(True, 399) is False
    assert ft.update(True, 400) is True    # dispara 1x apos o dwell
    assert ft.update(True, 800) is False   # segurando: nao re-dispara
    assert ft.update(False, 850) is False  # soltou -> rearma
    assert ft.update(True, 900) is False
    assert ft.update(True, 1300) is True   # novo punho -> dispara de novo


def test_fist_toggle_reset():
    ft = FistToggle(400)
    ft.update(True, 0)
    ft.update(True, 400)
    ft.reset()
    assert ft.update(True, 100) is False   # dwell reiniciado
