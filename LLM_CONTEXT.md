<!-- business-readme:context:start -->
# LLM Context

## Current business rule map
- Controle relativo/clutch: `handmouse/controller.py::Controller.on_result`; coberto por `tests/test_controller.py` (ancoragem, perda/reentrada da mão, anti-teleporte).
- Clique/drag por pinça: `handmouse/gestures.py::PinchDetector` + `Controller.on_result`; punho não clica porque `others_curled()` suprime press.
- Pausa dura por `SIGUSR1`: `Controller._on_toggle`, `Controller._apply_pause`, loop principal; libera câmera quando pausado.
- Pausa suave por gesto: rock/ILY (polegar + indicador + mindinho estendidos; médio + anelar curvados) mantido por `Config.toggle_dwell_ms` alterna `Controller.suspended`; câmera segue ligada.
- Fechar janela focada: quando não está suspenso, punho mantido por `Config.close_window_dwell_ms` chama `Config.close_window_command` via `Controller._close_window`; durante o dwell, cursor/cliques congelam para preservar o foco.
- Scroll: pose em V com dwell entra em modo de roda vertical; implementado em `PoseHold`, `is_scroll_pose()` e `Controller.on_result`.

## Technical map for future LLMs
- CLI: `handmouse/__main__.py` (`run`, `selftest`, `tune`).
- Config: `handmouse/config.py`, defaults carregados de `~/.config/handmouse/config.toml` por `load_config()`; chaves desconhecidas são ignoradas.
- Entrada de vídeo/tracking: `handmouse/capture.py` e `handmouse/tracker.py` (MediaPipe Tasks, `num_hands=1`).
- Saída: `handmouse/output.py` cria device `uinput` relativo com botão esquerdo e roda.
- Testes: `uv run --with pytest python -m pytest -q` cobre lógica pura e controller com stubs para libs pesadas.
- Integração desktop alvo: Omarchy/Hyprland/Wayland; fechamento de janela usa `hyprctl dispatch killactive` por padrão.

## Conflicts and unknowns
- O gesto rock/ILY depende de o rastreador diferenciar polegar, indicador e mindinho estendidos de médio/anelar curvados. Se a câmera confundir a pose, calibre com `handmouse tune`, aumente `toggle_dwell_ms` ou use `toggle_gesture = "off"`.
- `Controller._close_window()` executa o comando com timeout de 1 s; sucesso real depende de `hyprctl` estar no PATH e do compositor aceitar `killactive`.

## History
- 2026-06-26: Alteradas regras de gesto conforme pedido do usuário: punho deixou de ser interruptor e virou fechamento de janela focada com dwell de 2500 ms; mão aberta virou interruptor de pausa suave com dwell de 1500 ms. Fontes inspecionadas/atualizadas: `README.md`, `handmouse/gestures.py`, `handmouse/controller.py`, `handmouse/config.py`, `tests/test_gestures.py`, `tests/test_controller.py`, `tests/test_config.py`.
- 2026-06-26: Interruptor de pausa suave mudou de mão aberta para gesto rock/ILY; dwell de punho para fechar janela caiu de 2500 ms para 2000 ms. Fontes inspecionadas/atualizadas: `README.md`, `LLM_CONTEXT.md`, `handmouse/gestures.py`, `handmouse/controller.py`, `handmouse/config.py`, `tests/test_gestures.py`, `tests/test_controller.py`, `tests/test_config.py`.
- 2026-06-26: Dwell do gesto rock/ILY reduzido de 1500 ms para 800 ms para suspender/retomar mais rápido sem ficar instantâneo. Fontes atualizadas: `README.md`, `handmouse/config.py`, `tests/test_config.py`, `tests/test_controller.py`, config local.
- 2026-06-26: Dwell do gesto rock/ILY reduzido de 800 ms para 500 ms, e dwell do punho para fechar janela reduzido de 2000 ms para 1000 ms. Fontes atualizadas: `README.md`, `handmouse/config.py`, `tests/test_config.py`, `tests/test_controller.py`, config local.
- 2026-06-26: Default de pinça ajustado para `pinch_close_threshold = 0.18`, espelhando config local, para detectar pinça levemente mais cedo sem ficar agressivo. Fontes atualizadas: `README.md`, `handmouse/config.py`, `tests/test_config.py`, `tests/test_gestures.py`, config local.
<!-- business-readme:context:end -->
