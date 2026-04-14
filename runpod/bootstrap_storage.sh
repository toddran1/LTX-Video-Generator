#!/usr/bin/env bash
set -euo pipefail

NETWORK_ROOT="${NETWORK_ROOT:-/workspace}"
COMFY_PATH="${COMFY_PATH:-/workspace/ComfyUI}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${NETWORK_ROOT}/outputs}"

echo "Preparing network storage layout under ${NETWORK_ROOT}"
mkdir -p \
  "${NETWORK_ROOT}/models" \
  "${NETWORK_ROOT}/hf-cache" \
  "${NETWORK_ROOT}/ComfyUI" \
  "${OUTPUT_ROOT}" \
  "${NETWORK_ROOT}/tmp"

echo "Export these values before setup when this volume is mounted:"
cat <<EOF
export NETWORK_ROOT=${NETWORK_ROOT}
export COMFY_PATH=${COMFY_PATH}
export MODEL_ROOT=${COMFY_PATH}/models
export HF_HOME=${NETWORK_ROOT}/hf-cache
export HUGGINGFACE_HUB_CACHE=${NETWORK_ROOT}/hf-cache/hub
export TRANSFORMERS_CACHE=${NETWORK_ROOT}/hf-cache/transformers
export TMPDIR=${NETWORK_ROOT}/tmp
EOF

if [ -d "${COMFY_PATH}" ]; then
  mkdir -p "${COMFY_PATH}/output"
  if [ ! -L "${COMFY_PATH}/output/network" ]; then
    ln -sfn "${OUTPUT_ROOT}" "${COMFY_PATH}/output/network"
  fi
fi

echo "Storage layout ready."
