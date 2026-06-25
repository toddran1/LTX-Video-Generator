#!/usr/bin/env bash
set -euo pipefail

COMFY_PATH="${COMFY_PATH:-/workspace/ComfyUI}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models}"
COMFY_MODEL_ROOT="${COMFY_PATH}/models"
NETWORK_ROOT="${NETWORK_ROOT:-/workspace}"
WORKFLOW_ROOT="${WORKFLOW_ROOT:-${NETWORK_ROOT}/workflows}"
PYTHON_BIN="${PYTHON_BIN:-/opt/venvs/imagegen/bin/python}"

echo "[1/5] Preparing Wan 2.1 FLF2V start/end storage"
if [ ! -d "${COMFY_PATH}" ]; then
  echo "ComfyUI was not found at ${COMFY_PATH}. Run runpod/setup_ltx23.sh first."
  exit 1
fi

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "Python environment was not found at ${PYTHON_BIN}. Set PYTHON_BIN or run runpod/setup_ltx23.sh first."
  exit 1
fi

mkdir -p \
  "${WORKFLOW_ROOT}/source" \
  "${COMFY_MODEL_ROOT}/clip_vision" \
  "${COMFY_MODEL_ROOT}/diffusion_models/WanVideo" \
  "${COMFY_MODEL_ROOT}/loras" \
  "${COMFY_MODEL_ROOT}/text_encoders" \
  "${COMFY_MODEL_ROOT}/vae/WanVideo" \
  "${MODEL_ROOT}/clip_vision" \
  "${MODEL_ROOT}/diffusion_models/WanVideo" \
  "${MODEL_ROOT}/loras" \
  "${MODEL_ROOT}/text_encoders" \
  "${MODEL_ROOT}/vae/WanVideo"

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
  if [ -f "${dest}/${filename}" ] && [ ! -f "${dest}/${filename}.aria2" ]; then
    echo "Already downloaded: ${dest}/${filename}"
    return 0
  fi

  aria2c \
    --console-log-level=error \
    -c \
    -x 16 \
    -s 16 \
    -k 1M \
    -d "${dest}" \
    -o "${filename}" \
    "${url}"
}

expose_model() {
  local subdir="$1"
  local filename="$2"
  local source_path="${MODEL_ROOT}/${subdir}/${filename}"
  local target_dir="${COMFY_MODEL_ROOT}/${subdir}"
  local target_path="${target_dir}/${filename}"

  mkdir -p "${target_dir}"
  if [ "${MODEL_ROOT}" = "${COMFY_MODEL_ROOT}" ]; then
    return 0
  fi

  if [ ! -f "${source_path}" ]; then
    echo "Expected model is missing after download: ${source_path}"
    exit 1
  fi

  if [ -e "${target_path}" ] && [ ! -L "${target_path}" ]; then
    echo "Keeping existing ComfyUI model file: ${target_path}"
    return 0
  fi

  ln -sfn "${source_path}" "${target_path}"
  echo "Linked ${target_path} -> ${source_path}"
}

install_model() {
  local url="$1"
  local subdir="$2"
  local filename="$3"

  download_file "${url}" "${MODEL_ROOT}/${subdir}" "${filename}"
  expose_model "${subdir}" "${filename}"
}

echo "[2/5] Installing Wan FLF2V custom nodes"
install_custom_node \
  "https://github.com/kijai/ComfyUI-WanVideoWrapper" \
  "${COMFY_PATH}/custom_nodes/ComfyUI-WanVideoWrapper"

install_custom_node \
  "https://github.com/kijai/ComfyUI-KJNodes" \
  "${COMFY_PATH}/custom_nodes/ComfyUI-KJNodes"

install_custom_node \
  "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite" \
  "${COMFY_PATH}/custom_nodes/ComfyUI-VideoHelperSuite"

echo "[3/5] Downloading Wan 2.1 FLF2V models"
install_model \
  "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1-FLF2V-14B-720P_fp8_e4m3fn.safetensors" \
  "diffusion_models/WanVideo" \
  "Wan2_1-FLF2V-14B-720P_fp8_e4m3fn.safetensors"

install_model \
  "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors" \
  "vae/WanVideo" \
  "Wan2_1_VAE_bf16.safetensors"

install_model \
  "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-bf16.safetensors" \
  "text_encoders" \
  "umt5-xxl-enc-bf16.safetensors"

install_model \
  "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/open-clip-xlm-roberta-large-vit-huge-14_visual_fp16.safetensors" \
  "clip_vision" \
  "open-clip-xlm-roberta-large-vit-huge-14_visual_fp16.safetensors"

install_model \
  "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank32.safetensors" \
  "loras" \
  "Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank32.safetensors"

echo "[4/5] Syncing Wan FLF2V workflow files"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp -f \
  "${repo_root}/runpod/workflows/source/wanvideo_2_1_14B_FLF2V_720P_example_02.json" \
  "${WORKFLOW_ROOT}/source/wanvideo_2_1_14B_FLF2V_720P_example_02.json"
cp -f \
  "${repo_root}/runpod/workflows/api/wan2_1_flf2v_start_end_api.json" \
  "${WORKFLOW_ROOT}/wan2_1_flf2v_start_end_api.json"

echo "[5/5] Wan 2.1 FLF2V start/end setup complete"
cat <<EOF
ComfyUI:
  ${COMFY_PATH}

Models:
  ${MODEL_ROOT}

API workflow:
  ${WORKFLOW_ROOT}/wan2_1_flf2v_start_end_api.json

Notes:
  - This is the backend used by the LTX Text / Image tab's Start/End Image-to-Video mode.
  - Restart the UI after first install so ComfyUI reloads any newly installed custom nodes.
EOF
