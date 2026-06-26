"""Captura da webcam (OpenCV/V4L2). read() devolve frame RGB ja espelhado."""

from __future__ import annotations

import cv2


class CameraError(RuntimeError):
    pass


class Camera:
    def __init__(self, index: int, width: int, height: int):
        self._cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            self._cap.release()
            raise CameraError(
                f"nao foi possivel abrir a webcam (indice {index}); "
                "pode estar em uso por outro app ou ausente"
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self):
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        frame = cv2.flip(frame, 1)                       # FR1: espelha horizontal
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)    # MediaPipe espera RGB

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
