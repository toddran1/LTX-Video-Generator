#!/usr/bin/env bash
set -euo pipefail

NETWORK_ROOT="${NETWORK_ROOT:-/workspace}"
COMFY_PATH="${COMFY_PATH:-${NETWORK_ROOT}/ComfyUI}"
HF_HOME="${HF_HOME:-${NETWORK_ROOT}/hf-cache}"
HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"
VENV_PYTHON="${VENV_PYTHON:-/opt/venvs/imagegen/bin/python}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models}"
FLUX2_DIFFUSION_REPO="${FLUX2_DIFFUSION_REPO:-black-forest-labs/FLUX.2-klein-9B}"
FLUX2_DIFFUSION_FILE="${FLUX2_DIFFUSION_FILE:-flux-2-klein-9b.safetensors}"
FLUX2_VAE_REPO="${FLUX2_VAE_REPO:-Comfy-Org/flux2-klein}"
FLUX2_VAE_FILE="${FLUX2_VAE_FILE:-split_files/vae/flux2-vae.safetensors}"
TEXT_ENCODER_REPO="${TEXT_ENCODER_REPO:-ponpoke/flux2-klein-9b-uncensored-text-encoder}"
TEXT_ENCODER_FILE="${TEXT_ENCODER_FILE:-flux2-klein-9b-uncensored-q4_k_m.gguf}"
GGUF_NODE_REPO="${GGUF_NODE_REPO:-https://github.com/city96/ComfyUI-GGUF.git}"

if [ -z "${HF_TOKEN}" ]; then
  cat >&2 <<'EOF'
HF_TOKEN is required for FLUX.2 Klein setup.

Before running this script:
1. Sign in to Hugging Face in a browser.
2. Accept access/terms for:
   - the configured FLUX.2 Klein diffusion repo
   - https://huggingface.co/ponpoke/flux2-klein-9b-uncensored-text-encoder
3. Create a read token at https://huggingface.co/settings/tokens
4. Re-run, for example:
   HF_TOKEN=hf_xxx bash runpod/setup_flux2_klein_image.sh

Codex cannot accept gated model terms on your behalf.
EOF
  exit 1
fi

if [ ! -x "${VENV_PYTHON}" ]; then
  echo "Python venv not found at ${VENV_PYTHON}. Install the image runtime first." >&2
  exit 1
fi

mkdir -p \
  "${HF_HOME}" \
  "${MODEL_ROOT}/diffusion_models" \
  "${MODEL_ROOT}/clip" \
  "${MODEL_ROOT}/vae" \
  "${NETWORK_ROOT}/flux2-klein-9B" \
  "${COMFY_PATH}/custom_nodes"

if [ ! -d "${COMFY_PATH}/custom_nodes/ComfyUI-GGUF" ]; then
  git clone "${GGUF_NODE_REPO}" "${COMFY_PATH}/custom_nodes/ComfyUI-GGUF"
fi

"${VENV_PYTHON}" -m pip install -r "${COMFY_PATH}/custom_nodes/ComfyUI-GGUF/requirements.txt"

export HF_HOME
export HF_TOKEN
export NETWORK_ROOT
export MODEL_ROOT
export FLUX2_DIFFUSION_REPO
export FLUX2_DIFFUSION_FILE
export FLUX2_VAE_REPO
export FLUX2_VAE_FILE
export TEXT_ENCODER_REPO
export TEXT_ENCODER_FILE

"${VENV_PYTHON}" - <<'PY'
import os
import shutil
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError, RepositoryNotFoundError

flux_repo = os.environ["FLUX2_DIFFUSION_REPO"]
flux_file = os.environ["FLUX2_DIFFUSION_FILE"]
vae_repo = os.environ["FLUX2_VAE_REPO"]
vae_file = os.environ["FLUX2_VAE_FILE"]
encoder_repo = os.environ["TEXT_ENCODER_REPO"]
encoder_file = os.environ["TEXT_ENCODER_FILE"]
model_root = Path(os.environ.get("MODEL_ROOT", "/workspace/ComfyUI/models"))
token = os.environ["HF_TOKEN"]


def require_access(repo_id):
    try:
        files = HfApi().list_repo_files(repo_id, token=token)
        print(f"{repo_id}: access ok ({len(files)} files visible)")
        return files
    except (GatedRepoError, RepositoryNotFoundError, HfHubHTTPError) as error:
        raise SystemExit(
            f"Cannot access {repo_id}. Confirm your HF_TOKEN is valid and that the account "
            f"has accepted the model terms on Hugging Face.\n{error}"
        ) from error


require_access(flux_repo)
require_access(vae_repo)
require_access(encoder_repo)


def link_or_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


print(f"Downloading FLUX.2 Klein diffusion model {flux_file} ...")
diffusion_path = Path(hf_hub_download(
    repo_id=flux_repo,
    filename=flux_file,
    local_dir=str(model_root / "diffusion_models"),
    token=token,
))
print(f"diffusion model: {diffusion_path}")

print(f"Downloading ponpoke text encoder {encoder_file} ...")
encoder_path = hf_hub_download(
    repo_id=encoder_repo,
    filename=encoder_file,
    local_dir=str(model_root / "clip"),
    token=token,
)
print(f"text encoder: {encoder_path}")

print(f"Downloading FLUX.2 VAE {vae_file} ...")
vae_path = hf_hub_download(
    repo_id=vae_repo,
    filename=vae_file,
    token=token,
)
vae_destination = model_root / "vae" / Path(vae_file).name
link_or_copy(vae_path, vae_destination)
print(f"vae: {vae_destination}")

print()
print("FLUX.2 Klein local image generation files are installed.")
print("Restart ComfyUI so it picks up ComfyUI-GGUF and the new model files.")
PY
