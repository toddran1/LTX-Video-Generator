#!/usr/bin/env bash
set -euo pipefail

COMFY_PATH="${COMFY_PATH:-/Users/reginaldrandolph/Documents/coding projects/python/comfyUI/ComfyUI-local}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
WORKFLOW_SOURCE_URL="${WORKFLOW_SOURCE_URL:-https://huggingface.co/RuneXX/LTX-2.3-Workflows/resolve/main/Video-2-Video/LTX-2.3_-_V2V_ReTake_recreate_any_section_of_any_video.json}"
WORKFLOW_SOURCE_PATH="${WORKFLOW_SOURCE_PATH:-runpod/workflows/source/LTX-2.3_-_V2V_ReTake_recreate_any_section_of_any_video.json}"

if [ ! -d "${COMFY_PATH}" ]; then
  echo "ComfyUI was not found at: ${COMFY_PATH}" >&2
  echo "Set COMFY_PATH=/path/to/ComfyUI-local or create the local checkout first." >&2
  exit 1
fi

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

if [ ! -d "${COMFY_PATH}/venv" ]; then
  "${PYTHON_BIN}" -m venv "${COMFY_PATH}/venv"
fi

# shellcheck source=/dev/null
source "${COMFY_PATH}/venv/bin/activate"
python -m pip install --upgrade pip wheel setuptools

if [ -f "${COMFY_PATH}/requirements.txt" ]; then
  python -m pip install -r "${COMFY_PATH}/requirements.txt"
fi

nodes_dir="${COMFY_PATH}/custom_nodes"
mkdir -p "${nodes_dir}"

install_node() {
  local repo_url="$1"
  local name
  name="$(basename "${repo_url%.git}")"
  local dest="${nodes_dir}/${name}"

  if [ -d "${dest}/.git" ]; then
    git -C "${dest}" pull --ff-only
  else
    git clone "${repo_url}" "${dest}"
  fi

  if [ -f "${dest}/requirements.txt" ]; then
    python -m pip install -r "${dest}/requirements.txt"
  fi
}

install_node "https://github.com/kijai/ComfyUI-KJNodes.git"
install_node "https://github.com/city96/ComfyUI-GGUF.git"
install_node "https://github.com/Lightricks/ComfyUI-LTXVideo.git"
install_node "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"
install_node "https://github.com/kijai/ComfyUI-MelBandRoFormer.git"
install_node "https://github.com/kijai/ComfyUI-WanVideoWrapper.git"
install_node "https://github.com/yolain/ComfyUI-Easy-Use.git"
install_node "https://github.com/rgthree/rgthree-comfy.git"

mkdir -p "$(dirname "${REPO_ROOT}/${WORKFLOW_SOURCE_PATH}")"
if [ ! -f "${REPO_ROOT}/${WORKFLOW_SOURCE_PATH}" ]; then
  if command -v curl >/dev/null 2>&1; then
    curl -L "${WORKFLOW_SOURCE_URL}" -o "${REPO_ROOT}/${WORKFLOW_SOURCE_PATH}"
  else
    echo "curl is required to download the source workflow." >&2
    exit 1
  fi
fi

cat <<EOF
Local ComfyUI workflow editor is ready.

ComfyUI:
  ${COMFY_PATH}

Source workflow:
  ${REPO_ROOT}/${WORKFLOW_SOURCE_PATH}

Run ComfyUI:
  cd "${COMFY_PATH}"
  source venv/bin/activate
  python main.py --cpu --listen 127.0.0.1 --port 8188

After editing, export API JSON to:
  ${REPO_ROOT}/runpod/workflows/api/ltx23_v2v_retake_api.json
EOF
