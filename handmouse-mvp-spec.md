# handmouse — MVP Spec

> Daemon de controle do mouse por rastreamento de mão via webcam, para **Omarchy (Arch + Hyprland / Wayland)**.
> Este documento é a especificação de implementação. Um agente de código deve conseguir implementar o MVP completo a partir daqui, sem contexto adicional.

---

## 1. Objetivo

Um serviço de usuário (`systemd --user`) que:

1. Captura a webcam.
2. Rastreia uma mão em tempo real.
3. Move o cursor do mouse conforme o movimento da mão.
4. Dispara **clique esquerdo** num gesto de pinça (polegar + indicador).
5. Pode ser pausado/retomado.

O resultado precisa ser **usável**, não só "funcionar": cursor suave (sem tremor) e clique sem disparos duplos acidentais.

---

## 2. Restrições inegociáveis (decisões já tomadas — NÃO reavaliar)

Estas decisões vêm de pesquisa e evitam armadilhas conhecidas. O implementador **não deve** trocá-las.

| # | Decisão | Por quê |
|---|---------|---------|
| R1 | **Python 3.12** (fixo). | MediaPipe **não** publica wheels para Python 3.13+. O Arch/Omarchy roda 3.13/3.14 no sistema → usar venv isolado em 3.12. |
| R2 | **MediaPipe Tasks API** (`mediapipe.tasks.python.vision.HandLandmarker`), modo `LIVE_STREAM` com `detect_async` + `result_callback`. | A API legada `mp.solutions.hands` está deprecada. O modo LIVE_STREAM usa tracking entre frames → menor latência. |
| R3 | **Saída de input via `python-evdev` criando dispositivo uinput**, em **modo RELATIVO** (`REL_X`/`REL_Y` + `BTN_LEFT`). | No Wayland/Hyprland, injeção sintética (pyautogui/xdotool/pynput) **não funciona**. Um device uinput é tratado pelo `libinput` como mouse USB real e os eventos chegam ao compositor. Modo relativo evita a complexidade de calibração de dispositivos absolutos. |
| R4 | **One Euro Filter** na posição rastreada, antes de calcular o movimento. | Sem suavização adaptativa o cursor treme. Média móvel simples ou trava (lag) ou continua tremendo. |
| R5 | **Pinça com histerese (dois limiares) + debounce** para o clique. | Limiar único gera cliques múltiplos quando a distância oscila perto do corte. |

### Anti-requisitos (NÃO fazer)

- ❌ Não usar `pyautogui`, `xdotool`, `pynput` ou XTEST para mover/clicar (só X11; falham silenciosamente ou parcialmente no Wayland).
- ❌ Não usar `mp.solutions.hands` (API legada).
- ❌ Não usar Python 3.13+.
- ❌ Não usar eixos absolutos (`ABS_X`/`ABS_Y`) no MVP (fica para a v2).
- ❌ Não rodar processamento pesado dentro do `result_callback` a ponto de travá-lo.

---

## 3. Stack e dependências

- **Python 3.12**, ambiente criado com `uv`.
- Dependências PyPI: `mediapipe`, `opencv-python`, `evdev`.
- Sem dependência extra para o filtro: o **One Euro Filter é implementado no projeto** (é pequeno).
- Config em **TOML** lida com `tomllib` (stdlib do 3.11+ — sem dependência).
- Modelo: arquivo `hand_landmarker.task` (bundle float16), baixado uma vez.
  - URL: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`
  - Destino: `~/.local/share/handmouse/hand_landmarker.task`

---

## 4. Estrutura do repositório

```
handmouse/
├── pyproject.toml
├── README.md
├── handmouse/
│   ├── __init__.py
│   ├── __main__.py        # entrypoint CLI (run / selftest)
│   ├── config.py          # dataclass de config + defaults + load de TOML
│   ├── capture.py         # captura da webcam (OpenCV)
│   ├── tracker.py         # wrapper do MediaPipe HandLandmarker
│   ├── filter.py          # OneEuroFilter (1D) + Point2DFilter (x,y)
│   ├── gestures.py        # detecção de pinça com histerese
│   ├── output.py          # UinputMouse (device virtual relativo)
│   └── controller.py      # laço principal: junta tudo, trata pause e sinais
├── systemd/
│   └── handmouse.service
├── udev/
│   └── 99-uinput.rules
└── scripts/
    ├── install.sh
    └── download-model.sh
```

`pyproject.toml` deve declarar `requires-python = ">=3.12,<3.13"` e um console_script `handmouse = "handmouse.__main__:main"`.

---

## 5. Requisitos funcionais

- **FR1 — Captura:** abrir o dispositivo de webcam configurável (default índice `0`), resolução alvo 640×480, e **espelhar horizontalmente** cada frame (`cv2.flip(frame, 1)`) para que mover a mão à direita mova o cursor à direita.
- **FR2 — Tracking:** detectar 1 mão e obter os 21 landmarks normalizados (x,y ∈ [0,1]) via HandLandmarker em modo LIVE_STREAM. Se nenhuma mão for detectada no frame, não emitir movimento e resetar o estado de delta (ver §7.2).
- **FR3 — Cursor:** mover o cursor proporcionalmente ao deslocamento do **ponto âncora** da mão entre frames (modo relativo).
- **FR4 — Clique:** transição da mão para o estado "pinça fechada" dispara um clique esquerdo (press+release). Ver máquina de estados em §7.3.
- **FR5 — Pause/Resume:** sinal `SIGUSR1` alterna entre ativo e pausado. Pausado = não emite nenhum evento de mouse (tracking pode continuar rodando). Logar a troca de estado.
- **FR6 — Ciclo de vida:** `SIGTERM`/`SIGINT` encerram com limpeza: fechar o landmarker, liberar a câmera e destruir o device uinput.
- **FR7 — Selftest:** subcomando `handmouse selftest` que verifica, sem abrir a GUI/loop: (a) `/dev/uinput` gravável, (b) câmera abre, (c) modelo `.task` presente no caminho esperado. Sai com código ≠ 0 e mensagem clara se algo falhar.

---

## 6. Especificação dos módulos

### 6.1 `config.py`
- Dataclass `Config` com os campos abaixo e defaults.
- Carregar de `~/.config/handmouse/config.toml` se existir; senão usar defaults. Campos ausentes no TOML usam o default.

```
camera_index: int = 0
frame_width: int = 640
frame_height: int = 480
model_path: str = "~/.local/share/handmouse/hand_landmarker.task"  # expandir ~

# anchor / pinch landmarks (índices MediaPipe)
anchor_landmark: int = 9     # MIDDLE_FINGER_MCP (estável durante a pinça)
thumb_tip: int = 4
index_tip: int = 8
palm_ref_a: int = 0          # WRIST   } usados para normalizar
palm_ref_b: int = 9          # MCP médio} o tamanho da mão

# movimento
gain: float = 2500.0         # deslocamento normalizado -> pixels (tunar)

# One Euro Filter (operando em coords normalizadas [0,1])
oe_min_cutoff: float = 1.0   # menor = mais suave em repouso (menos tremor)
oe_beta: float = 10.0        # maior = menos lag em movimento rápido (tunar)
oe_d_cutoff: float = 1.0

# pinça (distância normalizada pelo tamanho da mão)
pinch_close_threshold: float = 0.35   # fecha o clique
pinch_open_threshold: float = 0.55    # solta (histerese: open > close)
pinch_debounce_ms: int = 60           # tempo mínimo entre trocas de estado

min_detection_confidence: float = 0.5
min_tracking_confidence: float = 0.5
```

### 6.2 `capture.py`
- Classe `Camera(index, width, height)` com `read() -> frame | None` e `release()`.
- Frame retornado já em **RGB** e **espelhado** (a conversão BGR→RGB é necessária para o MediaPipe; o flip horizontal é o de FR1).

### 6.3 `tracker.py`
- Classe `HandTracker(model_path, on_result, **opts)`.
- Cria o `HandLandmarker` com `running_mode=LIVE_STREAM`, `num_hands=1`, e `result_callback=on_result`.
- Método `submit(frame_rgb, timestamp_ms)` que monta `mp.Image` e chama `detect_async`.
  - **Importante:** `timestamp_ms` deve ser **monotonicamente crescente** entre chamadas; usar um relógio monotônico (ex.: `time.monotonic_ns() // 1_000_000`). Se cair, descartar o frame.
- `close()` libera o landmarker.

### 6.4 `filter.py`
- Implementar `OneEuroFilter` 1D conforme §7.1.
- `Point2DFilter` que aplica dois `OneEuroFilter` (x e y), compartilhando os mesmos parâmetros e o mesmo timestamp.

### 6.5 `gestures.py`
- Função `pinch_distance(landmarks, cfg) -> float`: distância euclidiana 2D entre `thumb_tip` e `index_tip`, dividida pelo "tamanho da mão" = distância entre `palm_ref_a` e `palm_ref_b`. Isso torna o gesto invariante à distância da câmera.
- Classe `PinchDetector(cfg)` que implementa a máquina de estados de §7.3 e expõe `update(distance, now_ms) -> Event | None`, onde `Event` ∈ {`CLICK`}.

### 6.6 `output.py`
- Classe `UinputMouse` que cria um device com:
  - `EV_REL`: `REL_X`, `REL_Y`
  - `EV_KEY`: `BTN_LEFT` (deixar `BTN_RIGHT` declarado para facilitar a v2)
  - nome do device: `"handmouse"`.
- Métodos: `move(dx, dy)`, `click()` (press+release de `BTN_LEFT` com `syn()` entre eles), `close()`.
- Se a criação falhar por permissão em `/dev/uinput`, levantar erro com mensagem orientando o usuário a rodar `scripts/install.sh` / verificar grupos.

### 6.7 `controller.py`
- Orquestra: instancia `Config`, `Camera`, `UinputMouse`, `Point2DFilter`, `PinchDetector`, `HandTracker`.
- Mantém estado compartilhado: `paused: bool`, `last_anchor: (x,y) | None`.
- Registra handlers: `SIGUSR1` → alterna `paused`; `SIGTERM`/`SIGINT` → encerra limpo.
- Laço principal: lê frame da câmera → `tracker.submit(...)`. (A baixa latência vem do modo async; o `detect_async` pode descartar frames se estiver ocupado — isso é esperado.)
- `on_result(result, image, timestamp_ms)`:
  1. Se `paused` ou nenhuma mão → resetar `last_anchor = None` e retornar.
  2. Pegar landmarks da mão 0. Calcular o ponto âncora (normalizado).
  3. Passar a âncora pelo `Point2DFilter` (usar `timestamp_ms`).
  4. Calcular delta vs `last_anchor` (ver §7.2); atualizar `last_anchor`.
  5. `output.move(delta_x_px, delta_y_px)`.
  6. Calcular `pinch_distance`, alimentar `PinchDetector.update(...)`; se retornar `CLICK`, `output.click()`.

### 6.8 `__main__.py`
- CLI mínimo: `handmouse run` (default) e `handmouse selftest`.
- `run`: inicia o controller. `selftest`: executa FR7.

---

## 7. Algoritmos (especificados para implementação direta)

### 7.1 One Euro Filter

Filtro passo-baixo adaptativo. Implementar exatamente assim (1D):

```
# alpha de um passa-baixa dado cutoff e período Te
alpha(cutoff, Te):
    tau = 1 / (2*pi*cutoff)
    return 1 / (1 + tau/Te)

estado: x_prev (último valor bruto), dx_prev (última derivada filtrada), t_prev

filter(x, t):
    if primeira amostra:
        inicializar x_hat = x, dx_prev = 0, t_prev = t; return x
    Te = max(t - t_prev, 1e-6)        # em segundos
    # derivada
    dx = (x - x_prev) / Te
    a_d = alpha(d_cutoff, Te)
    dx_hat = a_d*dx + (1 - a_d)*dx_prev
    # cutoff adaptativo
    cutoff = min_cutoff + beta*abs(dx_hat)
    a = alpha(cutoff, Te)
    x_hat = a*x + (1 - a)*x_hat_prev
    # atualizar estado (x_prev = x; dx_prev = dx_hat; x_hat_prev = x_hat; t_prev = t)
    return x_hat
```

`t` em **segundos** (converter `timestamp_ms`). Operar sobre coords normalizadas [0,1].
**Tuning** (expor em config): reduzir `min_cutoff` → mais estável parado; aumentar `beta` → menos lag ao mover rápido.

### 7.2 Movimento relativo do cursor

```
anchor_filtered = filter(anchor_norm, t)      # (x,y) em [0,1]
if last_anchor is None:
    last_anchor = anchor_filtered
    return                                     # sem movimento no 1º frame após (re)aquisição
dnx = anchor_filtered.x - last_anchor.x
dny = anchor_filtered.y - last_anchor.y
last_anchor = anchor_filtered
move(round(dnx * gain), round(dny * gain))
```

Resetar `last_anchor = None` sempre que a mão sumir (evita "salto" do cursor quando a mão reaparece em outro ponto).
O eixo X já está correto por causa do flip do frame (FR1). Verificar o sentido de Y na bancada; inverter no `move` se necessário (coord de imagem cresce para baixo, que coincide com a tela — em geral não precisa inverter).

### 7.3 Máquina de estados da pinça (clique)

Estados: `OPEN`, `CLOSED`. Distância `d` = `pinch_distance` (normalizada).

```
update(d, now_ms):
    if (now_ms - last_change_ms) < debounce_ms:
        return None                            # debounce
    if state == OPEN and d < close_threshold:
        state = CLOSED; last_change_ms = now_ms
        return CLICK                           # clique no momento em que fecha
    if state == CLOSED and d > open_threshold:
        state = OPEN; last_change_ms = now_ms
        return None
    return None
```

Como `open_threshold > close_threshold`, há histerese (zona morta entre 0.35 e 0.55) que impede cliques repetidos por oscilação.
Semântica MVP: **um clique discreto por pinça**. (v2: mapear pinça-segurada para botão pressionado → arrastar.)

---

## 8. Integração com o sistema

### 8.1 udev — `udev/99-uinput.rules`
```
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
```
Instalar em `/etc/udev/rules.d/` e recarregar (`udevadm control --reload && udevadm trigger`).

### 8.2 Grupos
Usuário precisa estar em `input` (uinput) e `video` (webcam):
```
sudo usermod -aG input,video $USER   # requer re-login
```

### 8.3 systemd — `systemd/handmouse.service` (serviço de USUÁRIO)
```
[Unit]
Description=handmouse - gesture mouse daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
ExecStart=%h/.local/share/handmouse/.venv/bin/handmouse run
Restart=on-failure
RestartSec=2

[Install]
WantedBy=graphical-session.target
```
Instalar em `~/.config/systemd/user/` e habilitar com `systemctl --user enable --now handmouse.service`.

### 8.4 Hyprland — pause/resume e toggle do serviço
Sugerir no README (não automatizar a edição do config do usuário):
```
# ~/.config/hypr/hyprland.conf
bind = SUPER, M, exec, systemctl --user kill -s SIGUSR1 handmouse.service   # pausa/retoma
bind = SUPER SHIFT, M, exec, systemctl --user start handmouse.service        # liga
```

### 8.5 Scripts
- `scripts/download-model.sh`: baixa o `.task` para `~/.local/share/handmouse/` se ausente.
- `scripts/install.sh`: cria venv 3.12 com `uv`, instala o pacote, baixa o modelo, copia a regra udev (com `sudo`), adiciona grupos, instala e habilita o serviço. Deve ser idempotente e imprimir avisos claros (ex.: "faça logout/login para os grupos valerem").

---

## 9. Setup (ordem de execução)

```bash
uv venv --python 3.12 ~/.local/share/handmouse/.venv
~/.local/share/handmouse/.venv/bin/pip install -e .
bash scripts/download-model.sh
sudo cp udev/99-uinput.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger
sudo usermod -aG input,video "$USER"      # depois faça logout/login
mkdir -p ~/.config/systemd/user && cp systemd/handmouse.service ~/.config/systemd/user/
~/.local/share/handmouse/.venv/bin/handmouse selftest
systemctl --user enable --now handmouse.service
```

---

## 10. Critérios de aceite (Definition of Done)

1. `handmouse selftest` passa (uinput gravável, câmera abre, modelo presente) e falha com mensagem útil quando alguma condição não é satisfeita.
2. Com o serviço ativo no Hyprland, **mover a mão move o cursor** de forma suave (sem tremor perceptível com a mão parada; sem lag perceptível em movimento normal após tuning de `gain`/`beta`/`min_cutoff`).
3. **Pinça polegar+indicador gera um clique esquerdo** verificável (ex.: clica um botão numa janela de teste), sem cliques duplos espúrios.
4. `SIGUSR1` (via keybind) **pausa e retoma**; pausado não move nem clica.
5. `SIGTERM`/`SIGINT` encerram **sem deixar device uinput órfão** nem travar a câmera.
6. O serviço sobe via `systemctl --user` e reinicia em falha.
7. Quando a mão sai do quadro e volta, o cursor **não dá salto** (estado de delta resetado).
8. Uso de CPU razoável em laptop típico (alvo: tracking fluido ~20–30 FPS em CPU).

---

## 11. Fora de escopo (v2 — não implementar agora)

- Botão direito, scroll e arrastar (pinça-segurada → botão pressionado).
- Modo de posicionamento **absoluto** (device tipo touchscreen com `ABS_X/ABS_Y` + matriz de calibração; tratamento de multi-monitor e aspect ratio).
- Aceleração de GPU para o MediaPipe.
- Pausa por gesto (ex.: mão aberta) como alternativa ao keybind.
- GUI/HUD de estado.
- Calibração de zona ativa (mapear só o centro do quadro para a tela inteira).

---

## 12. Notas para o implementador

- O `result_callback` roda na thread interna do MediaPipe — manter o trabalho ali enxuto; emitir eventos uinput é barato, OK.
- `detect_async` pode **descartar** frames sob carga; isso é normal e desejável (mantém latência baixa). Não tentar garantir 1 resultado por frame.
- Ao errar o sentido de algum eixo na bancada, ajustar apenas no `output.move`/no sinal do delta — não reintroduzir flips na captura.
- Manter os parâmetros de tuning (`gain`, `oe_min_cutoff`, `oe_beta`, limiares de pinça) **somente** na config, para iterar sem editar código.
