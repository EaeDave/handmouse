from types import SimpleNamespace

from handmouse.config import Config
from handmouse.gestures import (
    EVENT_PRESS,
    EVENT_RELEASE,
    HoldTrigger,
    PinchDetector,
    PoseHold,
    is_fist,
    is_rock_pose,
    is_scroll_pose,
    others_curled,
    pinch_distance,
)


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
    assert abs(pinch_distance(pts, cfg) - 0.5) < 1e-9


def test_pinch_distance_invariant_to_hand_scale():
    p1, cfg = _landmarks((0, 0), (0, 0.05), ref_b=(0, 0.1))
    p2, _ = _landmarks((0, 0), (0, 0.10), ref_b=(0, 0.2))
    assert abs(pinch_distance(p1, cfg) - pinch_distance(p2, cfg)) < 1e-9


def test_press_fires_when_closing():
    d = PinchDetector(Config())
    assert d.update(0.17, 1000) == EVENT_PRESS
    assert d.state == "CLOSED"


def test_release_fires_when_opening_again():
    d = PinchDetector(Config())
    d.update(0.17, 1000)
    assert d.update(0.60, 1200) == EVENT_RELEASE
    assert d.state == "OPEN"


def test_no_repeat_press_while_closed():
    d = PinchDetector(Config())
    d.update(0.17, 1000)
    assert d.update(0.17, 1100) is None


def test_hysteresis_midzone_keeps_closed():
    d = PinchDetector(Config())
    d.update(0.17, 1000)
    assert d.update(0.45, 1100) is None
    assert d.state == "CLOSED"


def test_debounce_blocks_fast_toggle():
    d = PinchDetector(Config())
    assert d.update(0.17, 1000) == EVENT_PRESS
    assert d.update(0.60, 1030) is None
    assert d.state == "CLOSED"
    assert d.update(0.60, 1100) == EVENT_RELEASE
    assert d.state == "OPEN"


def _hand(thumb=True, index=True, middle=True, ring=True, pinky=True):
    pts = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    pts[0] = SimpleNamespace(x=0.5, y=1.0)
    pts[3] = SimpleNamespace(x=0.35, y=0.5)
    pts[4] = SimpleNamespace(x=(0.10 if thumb else 0.45), y=(0.10 if thumb else 0.75))
    for pip, tip, ext in [(6, 8, index), (10, 12, middle), (14, 16, ring), (18, 20, pinky)]:
        pts[pip] = SimpleNamespace(x=0.5, y=0.5)
        pts[tip] = SimpleNamespace(x=0.5, y=(0.1 if ext else 0.6))
    return pts


def _partial_finger_hand():
    pts = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    pts[0] = SimpleNamespace(x=0.5, y=1.0)
    for pip, tip in [(6, 8), (10, 12), (14, 16), (18, 20)]:
        pts[pip] = SimpleNamespace(x=0.5, y=0.5)
        pts[tip] = SimpleNamespace(x=0.5, y=0.54)
    pts[3] = SimpleNamespace(x=0.35, y=0.5)
    pts[4] = SimpleNamespace(x=0.40, y=0.55)
    return pts


def test_is_fist_all_curled():
    assert is_fist(_hand(index=False, middle=False, ring=False, pinky=False)) is True


def test_is_fist_false_for_pinch_pose():
    assert is_fist(_hand(index=False, middle=True, ring=True, pinky=True)) is False


def test_is_fist_false_open_hand():
    assert is_fist(_hand()) is False


def test_is_fist_false_when_only_partially_closed():
    assert is_fist(_partial_finger_hand()) is False


def test_is_rock_pose_requires_thumb_index_pinky_up_middle_ring_down():
    assert is_rock_pose(_hand(thumb=True, index=True, middle=False, ring=False, pinky=True)) is True
    assert is_rock_pose(_hand(thumb=False, index=True, middle=False, ring=False, pinky=True)) is False
    assert is_rock_pose(_hand(thumb=True, index=False, middle=False, ring=False, pinky=True)) is False
    assert is_rock_pose(_hand(thumb=True, index=True, middle=True, ring=False, pinky=True)) is False
    assert is_rock_pose(_hand(thumb=True, index=True, middle=False, ring=False, pinky=False)) is False


def test_scroll_pose_requires_two_extended_and_two_curled():
    assert is_scroll_pose(_hand(index=True, middle=True, ring=False, pinky=False)) is True
    assert is_scroll_pose(_hand(index=True, middle=True, ring=True, pinky=False)) is False
    assert is_scroll_pose(_hand(index=False, middle=True, ring=False, pinky=False)) is False


def test_others_curled_needs_all_three():
    assert others_curled(_hand(middle=False, ring=False, pinky=False)) is True
    assert others_curled(_hand(middle=False, ring=False, pinky=True)) is False
    assert others_curled(_hand()) is False


def test_pose_hold_dwell():
    h = PoseHold(200)
    assert h.update(True, 0) is False
    assert h.update(True, 199) is False
    assert h.update(True, 200) is True
    assert h.update(True, 400) is True
    assert h.update(False, 401) is False
    assert h.active is False


def test_hold_trigger_dwell_edge_trigger():
    hold = HoldTrigger(400)
    assert hold.update(True, 0) is False
    assert hold.update(True, 399) is False
    assert hold.update(True, 400) is True
    assert hold.update(True, 800) is False
    assert hold.update(False, 850) is False
    assert hold.update(True, 900) is False
    assert hold.update(True, 1300) is True


def test_hold_trigger_reset():
    hold = HoldTrigger(400)
    hold.update(True, 0)
    hold.update(True, 400)
    hold.reset()
    assert hold.update(True, 100) is False
