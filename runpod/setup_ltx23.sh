#!/usr/bin/env bash
set -euo pipefail

COMFY_PATH="${COMFY_PATH:-/workspace/ComfyUI}"
VENV_PATH="${VENV_PATH:-/opt/venvs/ltx23}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PIP_PROGRESS_BAR="${PIP_PROGRESS_BAR:-off}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/tmp/pip-cache-ltx23}"

echo "[1/5] Installing system packages"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    aria2 \
    ffmpeg \
    git \
    python3-venv
fi

echo "[2/5] Creating Python environment at ${VENV_PATH}"
mkdir -p "$(dirname "${VENV_PATH}")"
"${PYTHON_BIN}" -m venv "${VENV_PATH}"
# shellcheck source=/dev/null
source "${VENV_PATH}/bin/activate"
python -m pip install --upgrade pip wheel setuptools

echo "[3/5] Installing PyTorch and Python dependencies"
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
python -m pip install \
  accelerate \
  albumentations \
  av \
  diffusers \
  einops \
  gradio \
  onnx \
  onnxruntime-gpu \
  opencv-python-headless \
  Pillow \
  requests \
  spandrel \
  torchsde \
  tqdm

echo "[4/5] Installing ComfyUI and custom nodes"
if [ ! -d "${COMFY_PATH}/.git" ]; then
  git clone https://github.com/comfyanonymous/ComfyUI "${COMFY_PATH}"
fi
python -m pip install -r "${COMFY_PATH}/requirements.txt"

nodes_dir="${COMFY_PATH}/custom_nodes"
mkdir -p "${nodes_dir}"

install_node() {
  local url="$1"
  local name
  name="$(basename "${url%/}")"
  local path="${nodes_dir}/${name}"

  if [ ! -d "${path}/.git" ]; then
    git clone "${url}" "${path}"
  fi

  if [ -f "${path}/requirements.txt" ]; then
    python -m pip install -r "${path}/requirements.txt"
  fi
}

install_node "https://github.com/kijai/ComfyUI-KJNodes"
install_node "https://github.com/city96/ComfyUI-GGUF"
install_node "https://github.com/Lightricks/ComfyUI-LTXVideo"
install_node "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"
install_node "https://github.com/kijai/ComfyUI-MelBandRoFormer"

echo "[5/5] Downloading LTX 2.3 weights"
download_model() {
  local url="$1"
  local dest="$2"
  local filename="$3"

  mkdir -p "${dest}"
  if [ ! -f "${dest}/${filename}" ]; then
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

models_dir="${COMFY_PATH}/models"
download_model "https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/ltx-2.3-22b-dev-Q4_K_M.gguf" "${models_dir}/unet" "ltx-2.3-22b-dev-Q4_K_M.gguf"
download_model "https://huggingface.co/Dampfinchen/google-gemma-3-12b-it-qat-q4_0-gguf-small-fix/resolve/main/gemma-3-12b-it-q4_0_s.gguf" "${models_dir}/text_encoders" "gemma-3-12b-it-q4_0_s.gguf"
download_model "https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/text_encoders/ltx-2.3-22b-dev_embeddings_connectors.safetensors" "${models_dir}/text_encoders" "ltx-2.3-22b-dev_embeddings_connectors.safetensors"
download_model "https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/vae/ltx-2.3-22b-dev_video_vae.safetensors" "${models_dir}/vae" "ltx-2.3-22b-dev_video_vae.safetensors"
download_model "https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/vae/ltx-2.3-22b-dev_audio_vae.safetensors" "${models_dir}/vae" "ltx-2.3-22b-dev_audio_vae.safetensors"
download_model "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.0.safetensors" "${models_dir}/latent_upscale_models" "ltx-2.3-spatial-upscaler-x2-1.0.safetensors"
download_model "https://huggingface.co/Kijai/MelBandRoFormer_comfy/resolve/main/MelBandRoformer_fp16.safetensors" "${models_dir}/diffusion_models" "MelBandRoformer_fp16.safetensors"
download_model "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/taeltx2_3.safetensors" "${models_dir}/vae" "taeltx2_3.safetensors"
download_model "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-lora-384.safetensors" "${models_dir}/loras" "ltx-2.3-22b-distilled-lora-384.safetensors"

echo "Setup complete."
echo "ComfyUI: ${COMFY_PATH}"
echo "Virtualenv: ${VENV_PATH}"
