#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_QWEN_FACE_BLEND="${INSTALL_QWEN_FACE_BLEND:-1}"
INSTALL_KREA2="${INSTALL_KREA2:-1}"
INSTALL_INSIGHTFACE_SWAP="${INSTALL_INSIGHTFACE_SWAP:-1}"
INSTALL_FLUX2_KLEIN="${INSTALL_FLUX2_KLEIN:-0}"
VENV_PYTHON="${VENV_PYTHON:-/opt/venvs/imagegen/bin/python}"

echo "[1/6] Syncing API workflows from the repo"
bash "${SCRIPT_DIR}/sync_repo_workflows.sh"

echo "[2/6] Installing shared video custom-node runtime compatibility packages"
if [ -x "${VENV_PYTHON}" ]; then
  "${VENV_PYTHON}" -m pip install \
    ftfy \
    imageio-ffmpeg \
    "kornia<0.8.0" \
    peft \
    pyloudnorm \
    rotary_embedding_torch
else
  echo "Skipping video compatibility packages because ${VENV_PYTHON} was not found."
fi

if [ "${INSTALL_INSIGHTFACE_SWAP}" = "1" ]; then
  echo "[3/6] Installing local InsightFace face swap stack"
  bash "${SCRIPT_DIR}/setup_insightface_swap.sh"
else
  echo "[3/6] Skipping local InsightFace face swap stack"
fi

if [ "${INSTALL_QWEN_FACE_BLEND}" = "1" ]; then
  echo "[4/6] Installing local Qwen multi-reference face blend stack"
  bash "${SCRIPT_DIR}/setup_qwen_face_blend_image.sh"
else
  echo "[4/6] Skipping Qwen multi-reference face blend stack"
fi

if [ "${INSTALL_KREA2}" = "1" ]; then
  echo "[5/6] Installing local Krea 2 multi-reference stack"
  bash "${SCRIPT_DIR}/setup_krea2_image.sh"
else
  echo "[5/6] Skipping local Krea 2 multi-reference stack"
fi

if [ "${INSTALL_FLUX2_KLEIN}" = "1" ]; then
  echo "[6/6] Installing local FLUX.2 Klein stack"
  bash "${SCRIPT_DIR}/setup_flux2_klein_image.sh"
else
  echo "[6/6] Skipping FLUX.2 Klein stack"
fi

echo
echo "Image generation setup complete."
echo "Start or restart the UI with: bash runpod/run_ui.sh"
