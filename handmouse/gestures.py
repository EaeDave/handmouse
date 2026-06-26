"""Deteccao de pinca, scroll por gesto e punho com dwell.

`pinch_distance` normaliza pela "largura da mao" (wrist <-> MCP medio) para ficar
invariante a distancia da camera.
"""

from __future__ import annotations

import math

EVENT_PRESS = "PRESS"
EVENT_RELEASE = "RELEASE"

_STATE_OPEN = "OPEN"
_STATE_CLOSED = "CLOSED"


def pinch_distance(landmarks, cfg) -> float:
    thumb = landmarks[cfg.thumb_tip]
    index = landmarks[cfg.index_tip]
    ref_a = landmarks[cfg.palm_ref_a]
    ref_b = landmarks[cfg.palm_ref_b]

    pinch = math.hypot(thumb.x - index.x, thumb.y - index.y)
    hand = math.hypot(ref_a.x - ref_b.x, ref_a.y - ref_b.y)
    if hand < 1e-6:
        return math.inf
    return pinch / hand


class PinchDetector:
    """Maquina OPEN/CLOSED para botao esquerdo.

    - CLOSE  -> EVENT_PRESS   (botao down; se abrir rapido vira clique normal)
    - OPEN   -> EVENT_RELEASE (solta; se estava movendo vira drag)
    """

    def __init__(self, cfg):
        self.close_threshold = cfg.pinch_close_threshold
        self.open_threshold = cfg.pinch_open_threshold
        self.debounce_ms = cfg.pinch_debounce_ms
        self.state = _STATE_OPEN
        self.last_change_ms: int | None = None

    def update(self, distance: float, now_ms: int) -> str | None:
        if self.last_change_ms is not None and (now_ms - self.last_change_ms) < self.debounce_ms:
            return None
        if self.state == _STATE_OPEN and distance < self.close_threshold:
            self.state = _STATE_CLOSED
            self.last_change_ms = now_ms
            return EVENT_PRESS
        if self.state == _STATE_CLOSED and distance > self.open_threshold:
            self.state = _STATE_OPEN
            self.last_change_ms = now_ms
            return EVENT_RELEASE
        return None

    def reset(self) -> None:
        self.state = _STATE_OPEN
        self.last_change_ms = None


# --- dedos / poses -----------------------------------------------------------
_WRIST = 0
_INDEX = (6, 8)
_MIDDLE = (10, 12)
_RING = (14, 16)
_PINKY = (18, 20)
_CLOSED_RATIO = 0.85  # tip precisa estar BEM mais perto do pulso que a PIP
_OPEN_RATIO = 1.15    # tip precisa estar claramente mais longe do pulso que a PIP


def _tip_pip_ratio(landmarks, pip: int, tip: int) -> float:
    w = landmarks[_WRIST]
    d_tip = math.hypot(landmarks[tip].x - w.x, landmarks[tip].y - w.y)
    d_pip = math.hypot(landmarks[pip].x - w.x, landmarks[pip].y - w.y)
    if d_pip < 1e-6:
        return 1.0
    return d_tip / d_pip


def _curled(landmarks, pip: int, tip: int) -> bool:
    return _tip_pip_ratio(landmarks, pip, tip) < _CLOSED_RATIO


def _extended(landmarks, pip: int, tip: int) -> bool:
    return _tip_pip_ratio(landmarks, pip, tip) > _OPEN_RATIO


def others_curled(landmarks) -> bool:
    """Medio + anelar + mindinho claramente curvados (mao indo p/ punho)."""
    return (
        _curled(landmarks, *_MIDDLE)
        and _curled(landmarks, *_RING)
        and _curled(landmarks, *_PINKY)
    )


def is_fist(landmarks) -> bool:
    """Punho: indicador + medio + anelar + mindinho todos claramente curvados.

    Polegar fica fora do criterio porque sua pose varia muito entre pessoas/cameras.
    """
    return _curled(landmarks, *_INDEX) and others_curled(landmarks)


def is_scroll_pose(landmarks) -> bool:
    """Pose de scroll: indicador + medio estendidos; anelar + mindinho curvados.

    Thumb ignorado. A ideia e uma pose tipo 'V' / dois dedos.
    """
    return (
        _extended(landmarks, *_INDEX)
        and _extended(landmarks, *_MIDDLE)
        and _curled(landmarks, *_RING)
        and _curled(landmarks, *_PINKY)
    )


class PoseHold:
    """Ativa uma pose apos dwell; desativa imediatamente quando a pose quebra."""

    def __init__(self, dwell_ms: int):
        self.dwell_ms = dwell_ms
        self._since: int | None = None
        self.active = False

    def update(self, pose_now: bool, now_ms: int) -> bool:
        if not pose_now:
            self._since = None
            self.active = False
            return False
        if self.active:
            return True
        if self._since is None:
            self._since = now_ms
            return False
        if (now_ms - self._since) >= self.dwell_ms:
            self.active = True
            return True
        return False

    def reset(self) -> None:
        self._since = None
        self.active = False


class FistToggle:
    """Edge-trigger com dwell: punho mantido >= dwell_ms dispara 1 vez; rearma so
    quando a mao deixa de ser punho (evita flip-flop enquanto segura)."""

    def __init__(self, dwell_ms: int):
        self.dwell_ms = dwell_ms
        self._fist_since: int | None = None
        self._fired = False

    def update(self, fist_now: bool, now_ms: int) -> bool:
        if not fist_now:
            self._fist_since = None
            self._fired = False
            return False
        if self._fist_since is None:
            self._fist_since = now_ms
        if not self._fired and (now_ms - self._fist_since) >= self.dwell_ms:
            self._fired = True
            return True
        return False

    def reset(self) -> None:
        self._fist_since = None
        self._fired = False
