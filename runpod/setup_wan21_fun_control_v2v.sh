#!/usr/bin/env bash
set -euo pipefail

COMFY_PATH="${COMFY_PATH:-/workspace/ComfyUI}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models}"
NETWORK_ROOT="${NETWORK_ROOT:-/workspace}"
WORKFLOW_ROOT="${WORKFLOW_ROOT:-${NETWORK_ROOT}/workflows}"
PYTHON_BIN="${PYTHON_BIN:-/opt/venvs/ltx23/bin/python}"

echo "[1/5] Preparing Wan 2.1 Fun Control storage"
if [ ! -d "${COMFY_PATH}" ]; then
  echo "ComfyUI was not found at ${COMFY_PATH}. Run runpod/setup_ltx23.sh first."
  exit 1
fi

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "Python environment was not found at ${PYTHON_BIN}. Run runpod/setup_ltx23.sh first."
  exit 1
fi

mkdir -p \
  "${WORKFLOW_ROOT}/source" \
  "${WORKFLOW_ROOT}" \
  "${MODEL_ROOT}/clip_vision" \
  "${MODEL_ROOT}/diffusion_models" \
  "${MODEL_ROOT}/text_encoders" \
  "${MODEL_ROOT}/vae"

install_custom_node() {
  local repo_url="$1"
  local dest="$2"

  if [ -d "${dest}/.git" ]; then
    echo "Custom node already installed: ${dest}"
    git -C "${dest}" pull --ff-only
  else
    git clone "${repo_url}" "${dest}"
  fi

  if [ -f "${dest}/requirements.txt" ]; then
    "${PYTHON_BIN}" -m pip install -r "${dest}/requirements.txt"
  fi
}

download_file() {
  local url="$1"
  local dest="$2"
  local filename="$3"

  mkdir -p "${dest}"
  if [ ! -f "${dest}/${filename}" ] || [ -f "${dest}/${filename}.aria2" ]; then
    aria2c \
      --console-log-level=error \
      -c \
      -x 16 \
      -s 16 \
      -k 1M \
      -d "${dest}" \
      -o "${filename}" \
      "${url}"
  else
    echo "Already downloaded: ${dest}/${filename}"
  fi
}

echo "[2/5] Installing Wan V2V custom nodes"
install_custom_node \
  "https://github.com/Fannovel16/comfyui_controlnet_aux.git" \
  "${COMFY_PATH}/custom_nodes/comfyui_controlnet_aux"

if [ ! -d "${COMFY_PATH}/custom_nodes/ComfyUI-VideoHelperSuite/.git" ]; then
  install_custom_node \
    "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite" \
    "${COMFY_PATH}/custom_nodes/ComfyUI-VideoHelperSuite"
fi

echo "[3/5] Downloading Wan 2.1 Fun Control models"
download_file \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_fun_control_1.3B_bf16.safetensors" \
  "${MODEL_ROOT}/diffusion_models" \
  "wan2.1_fun_control_1.3B_bf16.safetensors"

download_file \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
  "${MODEL_ROOT}/text_encoders" \
  "umt5_xxl_fp8_e4m3fn_scaled.safetensors"

download_file \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors" \
  "${MODEL_ROOT}/vae" \
  "wan_2.1_vae.safetensors"

download_file \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors" \
  "${MODEL_ROOT}/clip_vision" \
  "clip_vision_h.safetensors"

echo "[4/5] Syncing Wan workflow files"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp -f \
  "${repo_root}/runpod/workflows/source/wan2_1_fun_control_v2v_custom_nodes.json" \
  "${WORKFLOW_ROOT}/source/wan2_1_fun_control_v2v_custom_nodes.json"
cp -f \
  "${repo_root}/runpod/workflows/api/wan2_1_fun_control_v2v_api.json" \
  "${WORKFLOW_ROOT}/wan2_1_fun_control_v2v_api.json"

echo "[5/5] Wan 2.1 Fun Control V2V setup complete"
cat <<EOF
ComfyUI:
  ${COMFY_PATH}

Models:
  ${MODEL_ROOT}

API workflow:
  ${WORKFLOW_ROOT}/wan2_1_fun_control_v2v_api.json

Notes:
  - First run may download DWpose/OpenPose detector assets for comfyui_controlnet_aux.
  - This initial workflow caps each generation to 81 loaded frames. Longer 60s inputs
    need chunking/stitching before they are practical at 720p.
EOF
