#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETWORK_ROOT="${NETWORK_ROOT:-/workspace}"
COMFY_PATH="${COMFY_PATH:-${NETWORK_ROOT}/ComfyUI}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models}"
SPILL_ROOT="${SPILL_ROOT:-/root/comfy-models}"
HF_HOME="${HF_HOME:-${NETWORK_ROOT}/hf-cache}"
VENV_PYTHON="${VENV_PYTHON:-/opt/venvs/imagegen/bin/python}"

KREA_REPO="${KREA_REPO:-Comfy-Org/Krea-2}"
KREA_UNET_FILE="${KREA_UNET_FILE:-diffusion_models/krea2_turbo_fp8_scaled.safetensors}"
KREA_CLIP_FILE="${KREA_CLIP_FILE:-text_encoders/qwen3vl_4b_fp8_scaled.safetensors}"
KREA_VAE_FILE="${KREA_VAE_FILE:-vae/qwen_image_vae.safetensors}"

REPO_NODE_DIR="${SCRIPT_DIR}/custom_nodes/ComfyUI-LTXImageNodes"
DEST_NODE_DIR="${COMFY_PATH}/custom_nodes/ComfyUI-LTXImageNodes"

if [ ! -x "${VENV_PYTHON}" ]; then
  echo "Python venv not found at ${VENV_PYTHON}. Install the image runtime first." >&2
  exit 1
fi

mkdir -p \
  "${HF_HOME}" \
  "${MODEL_ROOT}/diffusion_models" \
  "${MODEL_ROOT}/text_encoders" \
  "${MODEL_ROOT}/vae" \
  "${SPILL_ROOT}/diffusion_models" \
  "${SPILL_ROOT}/text_encoders" \
  "${SPILL_ROOT}/vae" \
  "${COMFY_PATH}/custom_nodes"

mkdir -p "${DEST_NODE_DIR}"
cp -f "${REPO_NODE_DIR}/__init__.py" "${DEST_NODE_DIR}/__init__.py"

export HF_HOME
export MODEL_ROOT
export SPILL_ROOT
export KREA_REPO
export KREA_UNET_FILE
export KREA_CLIP_FILE
export KREA_VAE_FILE

"${VENV_PYTHON}" - <<'PY'
import os
from pathlib import Path

from huggingface_hub import hf_hub_download

model_root = Path(os.environ["MODEL_ROOT"])
spill_root = Path(os.environ["SPILL_ROOT"])
repo_id = os.environ["KREA_REPO"]


def install(repo_file, spill_subdir, model_subdir, public_name):
    target_dir = spill_root / spill_subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {public_name} from {repo_id}:{repo_file} ...")
    downloaded = Path(
        hf_hub_download(
            repo_id=repo_id,
            filename=repo_file,
            local_dir=str(target_dir),
        )
    )

    link_path = model_root / model_subdir / public_name
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    link_path.symlink_to(downloaded)
    print(f"{public_name}: {link_path} -> {downloaded}")


install(
    os.environ["KREA_UNET_FILE"],
    "diffusion_models",
    "diffusion_models",
    "krea2_turbo_fp8_scaled.safetensors",
)
install(
    os.environ["KREA_CLIP_FILE"],
    "text_encoders",
    "text_encoders",
    "qwen3vl_4b_fp8_scaled.safetensors",
)
install(
    os.environ["KREA_VAE_FILE"],
    "vae",
    "vae",
    "qwen_image_vae.safetensors",
)

print()
print("Krea 2 local multi-reference files are installed.")
print("Restart ComfyUI after setup so it reloads the custom node and model names.")
PY
