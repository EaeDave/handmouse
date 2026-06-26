"""Config: dataclass com defaults + carga de TOML (~/.config/handmouse/config.toml).

Campos ausentes no TOML usam o default. Chaves desconhecidas no TOML sao
ignoradas. `model_path` tem o `~` expandido na carga.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

DEFAULT_CONFIG_PATH = "~/.config/handmouse/config.toml"


@dataclass
class Config:
    # captura
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    camera_fps: int = 30
    camera_mjpg: bool = True       # MJPG ajuda a manter 30fps (menos latencia)
    model_path: str = "~/.local/share/handmouse/hand_landmarker.task"

    # landmarks (indices MediaPipe)
    anchor_landmark: int = 9   # MIDDLE_FINGER_MCP (estavel durante a pinca)
    thumb_tip: int = 4
    index_tip: int = 8
    palm_ref_a: int = 0        # WRIST    } normalizam o
    palm_ref_b: int = 9        # MCP medio} tamanho da mao

    # movimento
    gain: float = 2500.0       # deslocamento normalizado -> pixels
    # aceleracao (ganho adaptativo: devagar = preciso, rapido = veloz)
    accel: bool = True
    accel_min: float = 0.4         # multiplicador em repouso (precisao)
    accel_max: float = 2.0         # multiplicador em movimento rapido (velocidade)
    accel_speed: float = 2.5       # vel. normalizada (un/s) p/ atingir accel_max

    # scroll por gesto
    scroll_enabled: bool = True
    scroll_dwell_ms: int = 220     # segurou a pose por este tempo -> entra em scroll
    scroll_gain: float = 60.0      # delta normalizado vertical -> passos de roda

    # One Euro Filter (coords normalizadas [0,1])
    oe_min_cutoff: float = 1.0
    oe_beta: float = 10.0
    oe_d_cutoff: float = 1.0

    # pinca (distancia normalizada pelo tamanho da mao)
    pinch_close_threshold: float = 0.35
    pinch_open_threshold: float = 0.55   # histerese: open > close
    pinch_debounce_ms: int = 60

    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    delegate: str = "cpu"          # "cpu" | "gpu" (GPU experimental; ver README)

    # --- deltas de comportamento (ver README) ---
    start_paused: bool = True       # D2: sobe pausado, SUPER+M ativa
    notify: bool = True             # D5: notify-send no toggle
    teleport_threshold: float = 0.25  # D4: salto impossivel (norm.) -> ignora frame
    idle_pause_s: int = 30          # D8: auto-pausa sem mao por N s (0 = desliga)
    # D9: gesto interruptor (pausa SUAVE -> cam segue ligada, cursor congela)
    gesture_toggle: str = "fist"    # "fist" | "off"
    gesture_dwell_ms: int = 400     # tempo segurando o punho p/ alternar


def load_config(path: str | os.PathLike | None = None) -> Config:
    cfg_path = Path(path).expanduser() if path else Path(DEFAULT_CONFIG_PATH).expanduser()
    data: dict = {}
    if cfg_path.is_file():
        with cfg_path.open("rb") as fh:
            data = tomllib.load(fh)
    known = {f.name for f in fields(Config)}
    overrides = {k: v for k, v in data.items() if k in known}
    cfg = replace(Config(), **overrides)
    cfg.model_path = os.path.expanduser(cfg.model_path)
    return cfg
