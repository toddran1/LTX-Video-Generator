#!/usr/bin/env bash
set -euo pipefail

NETWORK_ROOT="${NETWORK_ROOT:-/workspace}"
COMFY_PATH="${COMFY_PATH:-${NETWORK_ROOT}/ComfyUI}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models}"
SPILL_ROOT="${SPILL_ROOT:-/root/comfy-models}"
HF_HOME="${HF_HOME:-${NETWORK_ROOT}/hf-cache}"
VENV_PYTHON="${VENV_PYTHON:-/opt/venvs/imagegen/bin/python}"

QWEN_UNET_REPO="${QWEN_UNET_REPO:-Comfy-Org/Qwen-Image-Edit_ComfyUI}"
QWEN_UNET_FILE="${QWEN_UNET_FILE:-split_files/diffusion_models/qwen_image_edit_2511_bf16.safetensors}"
QWEN_CLIP_REPO="${QWEN_CLIP_REPO:-Comfy-Org/HunyuanVideo_1.5_repackaged}"
QWEN_CLIP_FILE="${QWEN_CLIP_FILE:-split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors}"
QWEN_VAE_REPO="${QWEN_VAE_REPO:-Comfy-Org/Qwen-Image_ComfyUI}"
QWEN_VAE_FILE="${QWEN_VAE_FILE:-split_files/vae/qwen_image_vae.safetensors}"

if [ ! -x "${VENV_PYTHON}" ]; then
  echo "Python venv not found at ${VENV_PYTHON}. Install the runtime first." >&2
  exit 1
fi

mkdir -p \
  "${HF_HOME}" \
  "${MODEL_ROOT}/diffusion_models" \
  "${MODEL_ROOT}/text_encoders" \
  "${MODEL_ROOT}/vae" \
  "${SPILL_ROOT}/diffusion_models" \
  "${SPILL_ROOT}/text_encoders" \
  "${SPILL_ROOT}/vae"

export HF_HOME
export MODEL_ROOT
export SPILL_ROOT
export QWEN_UNET_REPO
export QWEN_UNET_FILE
export QWEN_CLIP_REPO
export QWEN_CLIP_FILE
export QWEN_VAE_REPO
export QWEN_VAE_FILE

"${VENV_PYTHON}" - <<'PY'
import os
from pathlib import Path

from huggingface_hub import hf_hub_download

model_root = Path(os.environ["MODEL_ROOT"])
spill_root = Path(os.environ["SPILL_ROOT"])


def install(repo_id, repo_file, spill_subdir, model_subdir, public_name):
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
    os.environ["QWEN_UNET_REPO"],
    os.environ["QWEN_UNET_FILE"],
    "diffusion_models",
    "diffusion_models",
    "qwen_image_edit_2511_bf16.safetensors",
)
install(
    os.environ["QWEN_CLIP_REPO"],
    os.environ["QWEN_CLIP_FILE"],
    "text_encoders",
    "text_encoders",
    "qwen_2.5_vl_7b_fp8_scaled.safetensors",
)
install(
    os.environ["QWEN_VAE_REPO"],
    os.environ["QWEN_VAE_FILE"],
    "vae",
    "vae",
    "qwen_image_vae.safetensors",
)

print()
print("Qwen multi-reference face blend files are installed.")
print("Restart ComfyUI after setup so it reloads available model names.")
PY
