#!/usr/bin/env bash
set -euo pipefail

COMFY_PATH="${COMFY_PATH:-/workspace/ComfyUI}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models}"
NETWORK_ROOT="${NETWORK_ROOT:-/workspace}"
WORKFLOW_ROOT="${WORKFLOW_ROOT:-${NETWORK_ROOT}/workflows}"
PYTHON_BIN="${PYTHON_BIN:-/opt/venvs/ltx23/bin/python}"

echo "[1/5] Preparing Wan 2.1 VACE storage"
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
  "${MODEL_ROOT}/diffusion_models" \
  "${MODEL_ROOT}/unet" \
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

echo "[2/5] Installing VACE custom nodes"
install_custom_node \
  "https://github.com/Fannovel16/comfyui_controlnet_aux.git" \
  "${COMFY_PATH}/custom_nodes/comfyui_controlnet_aux"

install_custom_node \
  "https://github.com/kijai/ComfyUI-KJNodes.git" \
  "${COMFY_PATH}/custom_nodes/ComfyUI-KJNodes"

if [ ! -d "${COMFY_PATH}/custom_nodes/ComfyUI-VideoHelperSuite/.git" ]; then
  install_custom_node \
    "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite" \
    "${COMFY_PATH}/custom_nodes/ComfyUI-VideoHelperSuite"
fi

echo "[3/5] Downloading Wan 2.1 VACE models"
download_file \
  "https://huggingface.co/QuantStack/Wan2.1_14B_VACE-GGUF/resolve/main/Wan2.1_14B_VACE-Q4_K_M.gguf" \
  "${MODEL_ROOT}/unet" \
  "Wan2.1_14B_VACE-Q4_K_M.gguf"

download_file \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
  "${MODEL_ROOT}/text_encoders" \
  "umt5_xxl_fp8_e4m3fn_scaled.safetensors"

download_file \
  "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors" \
  "${MODEL_ROOT}/vae" \
  "wan_2.1_vae.safetensors"

echo "[4/5] Syncing VACE workflow files"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp -f \
  "${repo_root}/runpod/workflows/source/Wan2.1_VACE_control_pose.json" \
  "${WORKFLOW_ROOT}/source/Wan2.1_VACE_control_pose.json"
cp -f \
  "${repo_root}/runpod/workflows/api/wan2_1_vace_v2v_api.json" \
  "${WORKFLOW_ROOT}/wan2_1_vace_v2v_api.json"
cp -f \
  "${repo_root}/runpod/workflows/api/wan2_1_vace_depth_restyle_api.json" \
  "${WORKFLOW_ROOT}/wan2_1_vace_depth_restyle_api.json"

echo "[5/5] Wan 2.1 VACE V2V setup complete"
cat <<EOF
ComfyUI:
  ${COMFY_PATH}

Models:
  ${MODEL_ROOT}

API workflow:
  ${WORKFLOW_ROOT}/wan2_1_vace_v2v_api.json
  ${WORKFLOW_ROOT}/wan2_1_vace_depth_restyle_api.json

Notes:
  - VACE uses a 14B editing model. This setup installs the Q4_K_M GGUF
    quantization so it can fit alongside the existing test models.
  - The depth restyle workflow is the first-choice style/theme workflow.
  - The pose workflow is for motion/character experiments where body motion is
    more important than scene structure.
  - These workflows cap each generation to 161 loaded frames. Longer 60s inputs
    need chunking/stitching before they are practical at 720p.
EOF
