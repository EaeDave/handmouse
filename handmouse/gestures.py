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
