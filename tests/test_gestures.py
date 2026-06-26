from types import SimpleNamespace

from handmouse.config import Config
from handmouse.gestures import EVENT_CLICK, PinchDetector, pinch_distance


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
