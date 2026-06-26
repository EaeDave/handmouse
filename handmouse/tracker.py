"""Wrapper do MediaPipe HandLandmarker em modo LIVE_STREAM (async + callback)."""

from __future__ import annotations

import os

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision


class HandTracker:
    def __init__(
        self,
        model_path: str,
        on_result,
        num_hands: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        delegate: str = "cpu",
    ):
        model_path = os.path.expanduser(model_path)
        deleg = (
            mp_python.BaseOptions.Delegate.GPU
            if str(delegate).lower() == "gpu"
            else mp_python.BaseOptions.Delegate.CPU
        )
        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path, delegate=deleg),
            running_mode=vision.RunningMode.LIVE_STREAM,
            num_hands=num_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            result_callback=on_result,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_ts = -1

    def submit(self, frame_rgb, timestamp_ms: int) -> None:
        # detect_async exige timestamps monotonicamente crescentes; descarta repetidos.
        if timestamp_ms <= self._last_ts:
            return
        self._last_ts = timestamp_ms
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        self._landmarker.detect_async(image, timestamp_ms)

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()  # junta a thread interna -> sem callbacks apos isto
            self._landmarker = None
