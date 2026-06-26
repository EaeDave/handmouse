"""CLI: `handmouse run` (default) e `handmouse selftest`."""

from __future__ import annotations

import argparse
import logging
import os
import sys


def _selftest() -> int:
    """FR7: verifica uinput gravavel, camera abre e modelo presente."""
    from .capture import CameraError, open_camera
    from .config import load_config
    from .output import UinputError, UinputMouse

    cfg = load_config()
    ok = True

    if os.path.isfile(cfg.model_path):
        print(f"[ok]      modelo presente: {cfg.model_path}")
    else:
        print(f"[FALHOU]  modelo ausente: {cfg.model_path}  -> rode scripts/download-model.sh")
        ok = False

    try:
        m = UinputMouse()
        m.close()
        print("[ok]      /dev/uinput gravavel")
    except UinputError as exc:
        print(f"[FALHOU]  uinput: {exc}")
        ok = False

    try:
        c = open_camera(cfg)
        frame = c.read()
        c.release()
        if frame is None:
            raise CameraError("abriu mas nao recebeu frame")
        print(f"[ok]      camera ok (backend={cfg.capture_backend}, indice {cfg.camera_index})")
    except CameraError as exc:
        print(f"[FALHOU]  camera: {exc}")
        ok = False

    print("selftest:", "OK" if ok else "FALHOU")
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="handmouse", description="mouse por gesto de mao (webcam)")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("run", help="inicia o daemon (default)")
    sub.add_parser("selftest", help="verifica uinput, camera e modelo e sai")
    sub.add_parser("tune", help="mostra valores ao vivo p/ calibrar (nao mexe no mouse)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.environ.get("HANDMOUSE_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if (args.cmd or "run") == "selftest":
        return _selftest()

    if args.cmd == "tune":
        from .controller import run_tune

        return run_tune()

    from .controller import Controller

    try:
        Controller().run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
