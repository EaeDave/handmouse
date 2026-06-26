"""Captura da webcam. Dois backends:

- "v4l2"     : OpenCV abrindo /dev/videoN direto (exclusivo).
- "pipewire" : consome via PipeWire (gst-launch pipewiresrc -> frames RGB crus por
               um fd dedicado). Permite compartilhar a camera com Teams/Discord/etc,
               desde que esses apps tambem usem PipeWire para a camera.

Ambos os backends entregam `read() -> frame RGB ja espelhado | None`.
"""

from __future__ import annotations

import os
import select
import shutil
import subprocess
import time

import cv2


class CameraError(RuntimeError):
    pass


class V4l2Camera:
    """OpenCV/V4L2 direto (exclusivo na camera)."""

    def __init__(self, cfg):
        self._cap = cv2.VideoCapture(cfg.camera_index, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            self._cap.release()
            raise CameraError(
                f"nao foi possivel abrir a webcam (indice {cfg.camera_index}); "
                "pode estar em uso por outro app ou ausente"
            )
        if cfg.camera_mjpg:
            self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.frame_width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.frame_height)
        self._cap.set(cv2.CAP_PROP_FPS, cfg.camera_fps)

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


class PipewireCamera:
    """Consome a camera via PipeWire usando gst-launch como subprocesso.

    Os frames RGB saem por um fd dedicado (nao stdout, p/ nao misturar com os logs
    de texto do gst). Cada frame tem width*height*3 bytes.
    """

    def __init__(self, cfg, read_timeout: float = 2.5):
        self._w = cfg.frame_width
        self._h = cfg.frame_height
        self._frame_bytes = self._w * self._h * 3
        self._read_timeout = read_timeout
        self._proc = None
        self._rfd = None

        if shutil.which("gst-launch-1.0") is None:
            raise CameraError(
                'gst-launch-1.0 ausente: instale gstreamer + gst-plugin-pipewire, '
                'ou use capture_backend = "v4l2".'
            )

        rfd, wfd = os.pipe()
        caps = f"video/x-raw,format=RGB,width={self._w},height={self._h}"
        pipeline = ["gst-launch-1.0", "pipewiresrc"]
        if cfg.pipewire_target:
            pipeline.append(f"target-object={cfg.pipewire_target}")
        pipeline += [
            "!", "videoconvert",
            "!", "videoscale",
            "!", caps,
            "!", "videoflip", "method=horizontal-flip",   # FR1: espelha horizontal
            "!", "queue", "leaky=downstream", "max-size-buffers=2",
            "!", "fdsink", f"fd={wfd}", "sync=false",
        ]
        try:
            self._proc = subprocess.Popen(
                pipeline,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                pass_fds=(wfd,),
            )
        except OSError as exc:
            os.close(rfd)
            os.close(wfd)
            raise CameraError(f"falha ao iniciar pipewiresrc: {exc}") from exc
        os.close(wfd)          # o pai fica so com a ponta de leitura
        self._rfd = rfd

    def read(self):
        if self._rfd is None:
            return None
        import numpy as np

        need = self._frame_bytes
        got = 0
        chunks = []
        deadline = time.monotonic() + self._read_timeout
        while got < need:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None  # pipeline travou/morreu -> controller reabre
            ready, _, _ = select.select([self._rfd], [], [], remaining)
            if not ready:
                return None
            block = os.read(self._rfd, need - got)
            if not block:
                return None  # EOF (gst morreu)
            chunks.append(block)
            got += len(block)
        buf = b"".join(chunks)
        return np.frombuffer(buf, dtype=np.uint8).reshape(self._h, self._w, 3).copy()

    def release(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        if self._rfd is not None:
            try:
                os.close(self._rfd)
            except OSError:
                pass
            self._rfd = None


def open_camera(cfg):
    """Factory: devolve o backend de captura conforme cfg.capture_backend."""
    backend = (getattr(cfg, "capture_backend", "v4l2") or "v4l2").lower()
    if backend == "pipewire":
        return PipewireCamera(cfg)
    return V4l2Camera(cfg)
