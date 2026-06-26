#!/usr/bin/env bash
# Instalacao idempotente do handmouse (Omarchy / Arch + Hyprland).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHARE_DIR="${HOME}/.local/share/handmouse"
VENV_DIR="${SHARE_DIR}/.venv"

echo "==> venv 3.12 em ${VENV_DIR}"
mkdir -p "${SHARE_DIR}"
uv venv --python 3.12 "${VENV_DIR}"

echo "==> instalando handmouse (editavel)"
uv pip install --python "${VENV_DIR}/bin/python" -e "${REPO_DIR}"

echo "==> baixando modelo"
bash "${REPO_DIR}/scripts/download-model.sh"

echo "==> regra udev (sudo)"
sudo cp "${REPO_DIR}/udev/99-uinput.rules" /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload
sudo udevadm trigger

echo "==> grupos input,video"
sudo usermod -aG input,video "${USER}"

echo "==> servico systemd (usuario)"
mkdir -p "${HOME}/.config/systemd/user"
cp "${REPO_DIR}/systemd/handmouse.service" "${HOME}/.config/systemd/user/handmouse.service"
systemctl --user daemon-reload

echo "==> selftest"
"${VENV_DIR}/bin/handmouse" selftest || echo "(selftest falhou; veja as mensagens acima)"

cat <<'EOF'

PRONTO.
  - Se voce acabou de entrar nos grupos input/video, FACA LOGOUT/LOGIN.
  - Habilite o servico:   systemctl --user enable --now handmouse.service
  - Ele sobe PAUSADO. Ative/pause com seu keybind (ex.: SUPER+M).
  - Adicione os binds no ~/.config/hypr/hyprland.conf (veja o README).
EOF
