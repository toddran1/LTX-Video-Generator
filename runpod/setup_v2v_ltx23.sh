#!/usr/bin/env bash
set -euo pipefail

COMFY_PATH="${COMFY_PATH:-/workspace/ComfyUI}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models}"
NETWORK_ROOT="${NETWORK_ROOT:-/workspace}"
WORKFLOW_ROOT="${WORKFLOW_ROOT:-${NETWORK_ROOT}/workflows}"
PYTHON_BIN="${PYTHON_BIN:-/opt/venvs/ltx23/bin/python}"

echo "[1/5] Preparing LTX 2.3 video-to-video workflow storage"
mkdir -p \
  "${WORKFLOW_ROOT}/source" \
  "${MODEL_ROOT}/diffusion_models" \
  "${MODEL_ROOT}/text_encoders"

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
  fi
}

echo "[2/5] Installing required V2V custom nodes"
install_custom_node \
  "https://github.com/kijai/ComfyUI-WanVideoWrapper.git" \
  "${COMFY_PATH}/custom_nodes/ComfyUI-WanVideoWrapper"

echo "[3/5] Downloading community LTX 2.3 V2V source workflow"
download_file \
  "https://huggingface.co/RuneXX/LTX-2.3-Workflows/resolve/main/Video-2-Video/LTX-2.3_-_V2V_ReTake_recreate_any_section_of_any_video.json" \
  "${WORKFLOW_ROOT}/source" \
  "LTX-2.3_-_V2V_ReTake_recreate_any_section_of_any_video.json"

echo "[4/5] Downloading additional LTX 2.3 V2V model files"
download_file \
  "https://huggingface.co/QuantStack/LTX-2.3-GGUF/resolve/main/LTX-2.3-distilled/LTX-2.3-distilled-Q4_K_S.gguf" \
  "${MODEL_ROOT}/diffusion_models" \
  "LTX-2.3-distilled-Q4_K_S.gguf"

download_file \
  "https://huggingface.co/unsloth/gemma-3-12b-it-GGUF/resolve/main/gemma-3-12b-it-Q2_K.gguf" \
  "${MODEL_ROOT}/text_encoders" \
  "gemma-3-12b-it-Q2_K.gguf"

download_file \
  "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/text_encoders/ltx-2.3_text_projection_bf16.safetensors" \
  "${MODEL_ROOT}/text_encoders" \
  "ltx-2.3_text_projection_bf16.safetensors"

echo "[5/5] Next step"
cat <<EOF
Downloaded the source workflow to:
  ${WORKFLOW_ROOT}/source/LTX-2.3_-_V2V_ReTake_recreate_any_section_of_any_video.json

This is a ComfyUI editor workflow. Open it in ComfyUI, export it as API JSON,
and save the API JSON here:
  ${WORKFLOW_ROOT}/ltx23_v2v_retake_api.json

The app backend is already configured to read that API JSON path.
EOF
