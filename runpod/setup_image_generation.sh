#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_QWEN_FACE_BLEND="${INSTALL_QWEN_FACE_BLEND:-1}"
INSTALL_KREA2="${INSTALL_KREA2:-1}"
INSTALL_FLUX2_KLEIN="${INSTALL_FLUX2_KLEIN:-0}"

echo "[1/4] Syncing API workflows from the repo"
bash "${SCRIPT_DIR}/sync_repo_workflows.sh"

if [ "${INSTALL_QWEN_FACE_BLEND}" = "1" ]; then
  echo "[2/4] Installing local Qwen multi-reference face blend stack"
  bash "${SCRIPT_DIR}/setup_qwen_face_blend_image.sh"
else
  echo "[2/4] Skipping Qwen multi-reference face blend stack"
fi

if [ "${INSTALL_KREA2}" = "1" ]; then
  echo "[3/4] Installing local Krea 2 multi-reference stack"
  bash "${SCRIPT_DIR}/setup_krea2_image.sh"
else
  echo "[3/4] Skipping local Krea 2 multi-reference stack"
fi

if [ "${INSTALL_FLUX2_KLEIN}" = "1" ]; then
  echo "[4/4] Installing local FLUX.2 Klein stack"
  bash "${SCRIPT_DIR}/setup_flux2_klein_image.sh"
else
  echo "[4/4] Skipping FLUX.2 Klein stack"
fi

echo
echo "Image generation setup complete."
echo "Start or restart the UI with: bash runpod/run_ui.sh"
