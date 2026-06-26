# handmouse

Daemon que controla o mouse pelo movimento da mão via webcam, para **Omarchy
(Arch + Hyprland / Wayland)**. Move o cursor seguindo a mão e dispara **clique
esquerdo** num gesto de pinça (polegar + indicador).

---

<!-- business-readme:business-rules:start -->
## Como funciona (regras de comportamento)

- **Controle relativo, tipo trackpad com "clutch".** O cursor anda conforme o
  *deslocamento* da mão. Tirou a mão do quadro → o cursor **congela**; recolocou
  a mão em qualquer ponto → continua de onde parou, **sem pulo**. Dá pra
  "levantar e reposicionar" a mão como quem reposiciona um mouse na mesa.
- **Sobe pausado.** Ao logar, o serviço inicia **pausado** (não controla nada).
  Você ativa quando quiser com um atalho (ex.: `SUPER+M`).
- **Pausar libera a câmera.** Quando pausado, o handmouse **fecha a webcam** —
  então Teams/Zoom/Meet podem usá-la normalmente. Como o padrão é estar pausado,
  a câmera fica livre na maior parte do tempo. Ativou o handmouse mas a câmera já
  está em uso por outro app? Ele avisa **"câmera ocupada"** e continua pausado.
- **Interruptor por gesto (rock/ILY).** Com o serviço ativo, manter o gesto
  **polegar + indicador + mindinho para cima, médio + anelar para baixo** por
  ~0,5 s **suspende** o controle (cursor congela, cliques ignorados); repetir
  o gesto por ~0,5 s **retoma**. É diferente do `SUPER+M`: o gesto é pausa
  *suave* e a **câmera continua ligada** (precisa enxergar a mão pra ver o gesto
  de volta). Config: `toggle_gesture`/`toggle_dwell_ms`.
- **Fechar janela focada (punho).** Com o serviço ativo e não suspenso, fechar a mão em **punho**
  por ~1 s dispara `hyprctl dispatch killactive`. Durante esse dwell o cursor
  fica congelado para não trocar o foco por acidente.
- **Clique e arrastar = pinça.** Fechar polegar+indicador faz **botão esquerdo down**;
  abrir de novo faz **up**. Se você só fecha e abre rápido, vira clique normal. Se
  mantiver fechado e mover a mão, vira **drag**. A pinça **só conta com os outros
  dedos abertos** — fechar tudo (punho) não clica.
- **Scroll por gesto (V / dois dedos).** Indicador + médio **estendidos**, anelar +
  mindinho **fechados**. Segurou a pose por um dwell curto → entra em **modo scroll**;
  enquanto isso, o **movimento vertical** da mão vira roda do mouse e o cursor deixa
  de se mover. Saiu da pose → volta ao cursor normal.
- **Notificação no toggle.** Cada vez que ativa/pausa, aparece uma notificação
  (via `notify-send`/mako) dizendo o estado atual.
- **Sem teleporte.** Um "salto" fisicamente impossível do ponto rastreado (ex.:
  segunda mão entra no quadro, ou glitch de tracking) é ignorado — o cursor nunca
  voa para longe; no pior caso fica parado por um instante.
- **Auto-pausa por inatividade.** Sem detectar nenhuma mão por ~30 s, ele pausa
  sozinho e solta a câmera (rede de segurança para "esqueci ligado").
- **Sobrevive a suspend/resume.** Se a câmera some em uso, ele re-tenta sem
  morrer e retoma no mesmo estado quando ela volta.

> Suavização por **One Euro Filter**, com **sub-pixel accumulation** (movimento fino
> não se perde) e **aceleração adaptativa** (devagar = preciso, rápido = veloz).

<!-- business-readme:business-rules:end -->

<!-- business-readme:technical:start -->
---

## Instalação

Pré-requisitos: `uv` instalado; webcam funcionando.

```bash
bash scripts/install.sh
```

O script é idempotente e faz: venv Python **3.12** (MediaPipe não tem wheels para
3.13+), instala o pacote, baixa o modelo, aplica a regra udev (com `sudo`),
garante os grupos `input,video`, instala e recarrega o serviço de usuário, e roda
o `selftest`.

Depois:

```bash
# se você acabou de entrar nos grupos input/video, FAÇA LOGOUT/LOGIN antes
systemctl --user enable --now handmouse.service
```

### Passo a passo manual (equivalente)

```bash
uv venv --python 3.12 ~/.local/share/handmouse/.venv
uv pip install --python ~/.local/share/handmouse/.venv/bin/python -e .
bash scripts/download-model.sh
sudo cp udev/99-uinput.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger
sudo usermod -aG input,video "$USER"      # depois: logout/login
mkdir -p ~/.config/systemd/user && cp systemd/handmouse.service ~/.config/systemd/user/
~/.local/share/handmouse/.venv/bin/handmouse selftest
systemctl --user enable --now handmouse.service
```

---

## Keybinds do Hyprland

Já adicionados ao `~/.config/hypr/bindings.conf` (bloco `# handmouse:start` … `# handmouse:end`):

```conf
# SUPER+M: pausa/retoma (libera/pega a câmera). Sobe pausado: o 1o aperto ativa.
bindd = SUPER, M, Handmouse toggle (pause/resume), exec, systemctl --user kill -s SIGUSR1 handmouse.service
# SUPER CTRL+M: (re)liga o serviço, caso esteja parado
bindd = SUPER CTRL, M, Handmouse start, exec, systemctl --user start handmouse.service
```

> Nota: o "start" usa **SUPER CTRL+M** — o `SUPER SHIFT+M` já é o Spotify no Omarchy.

---

## Uso

```bash
handmouse run        # inicia o daemon (default)
handmouse selftest   # verifica: /dev/uinput gravável, câmera abre, modelo presente
handmouse tune       # mostra ao vivo pinch/punho/rock/scroll/velocidade/fps (não mexe no mouse)
```

Logs: `journalctl --user -u handmouse -f`. Nível: `HANDMOUSE_LOG=DEBUG`.

---

## Configuração

Opcional, em `~/.config/handmouse/config.toml`. Campos ausentes usam o default.

```toml
# captura
camera_index = 0
frame_width  = 640
frame_height = 480
camera_fps   = 30
camera_mjpg  = true   # tenta MJPG p/ segurar fps e baixar latência

# sensibilidade do movimento (norm. -> pixels)
gain = 2500.0
accel       = true
accel_min   = 0.4     # ganho efetivo ao mover devagar (precisão)
accel_max   = 2.0     # ganho efetivo ao mover rápido (velocidade)
accel_speed = 2.5     # vel. normalizada (un/s) p/ atingir accel_max

# scroll por gesto
scroll_enabled  = true
scroll_dwell_ms = 220
scroll_gain     = 60.0

# suavização (One Euro Filter)
oe_min_cutoff = 1.0   # menor = mais estável parado
oe_beta       = 10.0  # maior = menos lag em movimento rápido

# pinça (distância normalizada pelo tamanho da mão)
pinch_close_threshold = 0.18
pinch_open_threshold  = 0.55
pinch_debounce_ms     = 60

# tracking
delegate = "cpu"      # "cpu" | "gpu" (GPU é experimental; ver nota abaixo)

# comportamento
start_paused      = true   # sobe pausado
notify            = true   # notificação no toggle
teleport_threshold = 0.25  # salto impossível por frame -> ignorado
idle_pause_s      = 30     # auto-pausa sem mão por N s (0 = desliga)

# gesto interruptor (pausa suave: câmera fica ligada)
toggle_gesture       = "rock" # "rock" | "off"
toggle_dwell_ms      = 500    # rock/ILY segurado p/ alternar

# gesto de fechar janela focada
close_window_gesture  = "fist" # "fist" | "off"
close_window_dwell_ms = 1000   # segurança contra fechar sem querer
close_window_command  = "hyprctl dispatch killactive"
```

> **GPU / RTX 3060 (mapeado, experimental):** já existe o knob `delegate = "gpu"`
> e o `HandTracker` já encaminha isso para o MediaPipe Tasks delegate. O default
> continua **CPU** porque GPU em Linux desktop depende do stack EGL/OpenGL/driver e
> precisa validação na tua bancada. Quando formos ligar, a troca é de config; sem
> refactor no código.

---

## Troubleshooting

- **`selftest` falha em uinput** → você não está no grupo `input` ou a regra udev
  não foi aplicada. Rode `scripts/install.sh` e faça logout/login.
- **`selftest` falha na câmera** → outro app está usando a webcam, ou o
  `camera_index` está errado.
- **Cursor treme parado** → diminua `oe_min_cutoff`.
- **Cursor com lag ao mover rápido** → aumente `oe_beta`.
- **Cursor rápido/lento demais** → ajuste `gain`.
- **Clica fácil / sem fechar o dedo** → diminua `pinch_close_threshold` (ex.: 0.16); **demora pra clicar** → aumente levemente (ex.: 0.20).
- **Gesto rock não suspende, ou suspende sem querer** → ajuste `toggle_dwell_ms`, ou desligue com `toggle_gesture = "off"`.
- **Punho não fecha janela, ou fecha fácil demais** → ajuste `close_window_dwell_ms`, ou desligue com `close_window_gesture = "off"`.
- **Scroll entra fácil demais** → aumente `scroll_dwell_ms`.
- **Scroll fraco/forte demais** → ajuste `scroll_gain`.
- **Muito preciso mas lento / rápido mas arisco** → ajuste `accel_min`, `accel_max`, `accel_speed`.
- **Quer calibrar vendo números ao vivo** → pare o serviço e rode `handmouse tune`.

---

## Desenvolvimento

```bash
uv run --with pytest python -m pytest -q
```

Os testes cobrem a lógica pura (One Euro Filter, detecção de pinça/scroll/punho, config, output).
As partes de hardware (câmera, uinput no Wayland) são validadas via `selftest` e na
bancada.
<!-- business-readme:technical:end -->
