#!/usr/bin/env bash
set -euo pipefail

COMFY_PATH="${COMFY_PATH:-/workspace/ComfyUI}"
VENV_PATH="${VENV_PATH:-/opt/venvs/ltx23}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models}"
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
  ftfy \
  gradio \
  huggingface_hub \
  imageio-ffmpeg \
  "kornia<0.8.0" \
  onnx \
  onnxruntime-gpu \
  opencv-python-headless \
  peft \
  Pillow \
  pyloudnorm \
  requests \
  rotary_embedding_torch \
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
python -m pip install \
  ftfy \
  imageio-ffmpeg \
  "kornia<0.8.0" \
  peft \
  pyloudnorm \
  rotary_embedding_torch

echo "[5/5] Downloading LTX 2.3 weights"
model_dirs=(
  diffusion_models
  latent_upscale_models
  loras
  text_encoders
  unet
  vae
)

if [ "${MODEL_ROOT}" != "${COMFY_PATH}/models" ]; then
  echo "Using external model root: ${MODEL_ROOT}"
  mkdir -p "${MODEL_ROOT}" "${COMFY_PATH}/models"
  for model_dir in "${model_dirs[@]}"; do
    mkdir -p "${MODEL_ROOT}/${model_dir}"
    if [ -d "${COMFY_PATH}/models/${model_dir}" ] && [ ! -L "${COMFY_PATH}/models/${model_dir}" ]; then
      find "${COMFY_PATH}/models/${model_dir}" -maxdepth 1 -type f -exec mv -n {} "${MODEL_ROOT}/${model_dir}/" \;
      rmdir "${COMFY_PATH}/models/${model_dir}" 2>/dev/null || true
    fi
    ln -sfn "${MODEL_ROOT}/${model_dir}" "${COMFY_PATH}/models/${model_dir}"
  done
fi

download_model() {
  local url="$1"
  local dest="$2"
  local filename="$3"

  mkdir -p "${dest}"
  if [ -f "${dest}/${filename}" ] && [ ! -f "${dest}/${filename}.aria2" ]; then
    if [[ "${filename}" == *.gguf ]]; then
      if ! DEST="${dest}" FILENAME="${filename}" python - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["DEST"]) / os.environ["FILENAME"]
with path.open("rb") as handle:
    raise SystemExit(0 if handle.read(4) == b"GGUF" else 1)
PY
      then
        mv "${dest}/${filename}" "${dest}/${filename}.corrupt.$(date +%s)"
      else
        return 0
      fi
    else
      return 0
    fi
  fi

  if [[ "${url}" == https://huggingface.co/*/resolve/* ]]; then
    URL="${url}" DEST="${dest}" FILENAME="${filename}" python - <<'PY'
import os
from pathlib import Path
from urllib.parse import urlparse

from huggingface_hub import hf_hub_download

url = os.environ["URL"]
dest = Path(os.environ["DEST"])
filename = os.environ["FILENAME"]

path = urlparse(url).path.strip("/").split("/")
if len(path) < 5 or path[2] != "resolve":
    raise SystemExit(f"Unsupported Hugging Face URL: {url}")

repo_id = "/".join(path[:2])
relative_path = "/".join(path[4:])
subfolder, _, repo_filename = relative_path.rpartition("/")
if filename != repo_filename:
    raise SystemExit(
        f"Filename mismatch for {url}: expected {repo_filename}, got {filename}"
    )

downloaded = hf_hub_download(
    repo_id=repo_id,
    filename=repo_filename,
    subfolder=subfolder or None,
    local_dir=str(dest),
    local_dir_use_symlinks=False,
    resume_download=True,
    token=os.environ.get("HF_TOKEN"),
)
canonical = dest / filename
if Path(downloaded) != canonical and not canonical.exists():
    try:
        canonical.symlink_to(Path(downloaded).relative_to(dest))
    except OSError:
        import shutil

        shutil.copy2(downloaded, canonical)
print(f"Downloaded {downloaded}")
PY
    rm -f "${dest}/${filename}.aria2"
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
