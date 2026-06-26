"""Deteccao de pinca (polegar+indicador) com histerese + debounce.

`pinch_distance` normaliza pela "largura da mao" (wrist <-> MCP medio) para ficar
invariante a distancia da camera.
"""

from __future__ import annotations

import math

EVENT_CLICK = "CLICK"

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
    """Maquina de estados OPEN/CLOSED. update() retorna EVENT_CLICK ao fechar."""

    def __init__(self, cfg):
        self.close_threshold = cfg.pinch_close_threshold
        self.open_threshold = cfg.pinch_open_threshold
        self.debounce_ms = cfg.pinch_debounce_ms
        self.state = _STATE_OPEN
        self.last_change_ms: int | None = None

    def update(self, distance: float, now_ms: int) -> str | None:
        if self.last_change_ms is not None and (now_ms - self.last_change_ms) < self.debounce_ms:
            return None  # debounce: ignora trocas rapidas demais
        if self.state == _STATE_OPEN and distance < self.close_threshold:
            self.state = _STATE_CLOSED
            self.last_change_ms = now_ms
            return EVENT_CLICK  # clique no instante em que fecha
        if self.state == _STATE_CLOSED and distance > self.open_threshold:
            self.state = _STATE_OPEN
            self.last_change_ms = now_ms
            return None
        return None

    def reset(self) -> None:
        self.state = _STATE_OPEN
        self.last_change_ms = None


# --- deteccao de dedos curvados / punho (toggle de gesto) ---
_WRIST = 0
# (pip, tip) por dedo
_INDEX = (6, 8)
_MIDDLE = (10, 12)
_RING = (14, 16)
_PINKY = (18, 20)


def _curled(landmarks, pip: int, tip: int) -> bool:
    """Dedo curvado: ponta mais perto do pulso que a junta PIP (robusto a orientacao)."""
    w = landmarks[_WRIST]
    d_tip = math.hypot(landmarks[tip].x - w.x, landmarks[tip].y - w.y)
    d_pip = math.hypot(landmarks[pip].x - w.x, landmarks[pip].y - w.y)
    return d_tip < d_pip


def others_curled(landmarks) -> bool:
    """Medio + anelar + mindinho curvados (mao indo p/ punho)."""
    return (
        _curled(landmarks, *_MIDDLE)
        and _curled(landmarks, *_RING)
        and _curled(landmarks, *_PINKY)
    )


def is_fist(landmarks) -> bool:
    """Punho: indicador + medio + anelar + mindinho todos curvados (polegar ignorado)."""
    return _curled(landmarks, *_INDEX) and others_curled(landmarks)


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
