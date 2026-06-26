#!/usr/bin/env bash
# Baixa o bundle hand_landmarker.task (float16) se ainda nao existir.
set -euo pipefail

URL="https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
DEST_DIR="${HOME}/.local/share/handmouse"
DEST="${DEST_DIR}/hand_landmarker.task"

mkdir -p "${DEST_DIR}"

if [[ -f "${DEST}" ]]; then
  echo "modelo ja existe: ${DEST}"
  exit 0
fi

echo "baixando modelo -> ${DEST}"
curl -fL --progress-bar -o "${DEST}.tmp" "${URL}"
mv "${DEST}.tmp" "${DEST}"
echo "ok: ${DEST}"
