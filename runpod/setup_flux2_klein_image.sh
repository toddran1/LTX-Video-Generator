#!/usr/bin/env bash
set -euo pipefail

NETWORK_ROOT="${NETWORK_ROOT:-/workspace}"
COMFY_PATH="${COMFY_PATH:-${NETWORK_ROOT}/ComfyUI}"
HF_HOME="${HF_HOME:-${NETWORK_ROOT}/hf-cache}"
HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"
VENV_PYTHON="${VENV_PYTHON:-/opt/venvs/imagegen/bin/python}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models}"
FLUX2_REPO="${FLUX2_REPO:-black-forest-labs/FLUX.2-klein-9B}"
TEXT_ENCODER_REPO="${TEXT_ENCODER_REPO:-ponpoke/flux2-klein-9b-uncensored-text-encoder}"
TEXT_ENCODER_FILE="${TEXT_ENCODER_FILE:-flux2-klein-9b-uncensored-q4_k_m.gguf}"

if [ -z "${HF_TOKEN}" ]; then
  cat >&2 <<'EOF'
HF_TOKEN is required for FLUX.2 Klein setup.

Before running this script:
1. Sign in to Hugging Face in a browser.
2. Accept access/terms for:
   - https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
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
  "${NETWORK_ROOT}/flux2-klein-9B"

export HF_HOME
export HF_TOKEN
export NETWORK_ROOT
export MODEL_ROOT
export FLUX2_REPO
export TEXT_ENCODER_REPO
export TEXT_ENCODER_FILE

"${VENV_PYTHON}" - <<'PY'
import os
import shutil
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError, RepositoryNotFoundError

flux_repo = os.environ["FLUX2_REPO"]
encoder_repo = os.environ["TEXT_ENCODER_REPO"]
encoder_file = os.environ["TEXT_ENCODER_FILE"]
network_root = Path(os.environ.get("NETWORK_ROOT", "/workspace"))
model_root = Path(os.environ.get("MODEL_ROOT", "/workspace/ComfyUI/models"))


def require_access(repo_id):
    try:
        files = HfApi().list_repo_files(repo_id)
        print(f"{repo_id}: access ok ({len(files)} files visible)")
        return files
    except (GatedRepoError, RepositoryNotFoundError, HfHubHTTPError) as error:
        raise SystemExit(
            f"Cannot access {repo_id}. Confirm your HF_TOKEN is valid and that the account "
            f"has accepted the model terms on Hugging Face.\n{error}"
        ) from error


flux_files = require_access(flux_repo)
require_access(encoder_repo)

print("Downloading FLUX.2 Klein repository files to /workspace/flux2-klein-9B ...")
snapshot_download(
    repo_id=flux_repo,
    local_dir=str(network_root / "flux2-klein-9B"),
    allow_patterns=[
        "*.safetensors",
        "*.json",
        "*.txt",
        "*.model",
        "*.jinja",
        "*.md",
    ],
)

print(f"Downloading ponpoke text encoder {encoder_file} ...")
encoder_path = hf_hub_download(
    repo_id=encoder_repo,
    filename=encoder_file,
    local_dir=str(model_root / "clip"),
)
print(f"text encoder: {encoder_path}")

preferred_diffusion = [
    path for path in flux_files
    if path.lower().endswith((".safetensors", ".gguf"))
    and not any(skip in path.lower() for skip in ["text", "encoder", "clip", "vae", "ae"])
]
if preferred_diffusion:
    source = network_root / "flux2-klein-9B" / preferred_diffusion[0]
    destination = model_root / "diffusion_models" / Path(preferred_diffusion[0]).name
    if source.exists() and not destination.exists():
        shutil.copy2(source, destination)
    print(f"candidate diffusion model: {destination}")
else:
    print("No obvious diffusion model file was auto-detected. Inspect /workspace/flux2-klein-9B.")

vae_candidates = [
    path for path in flux_files
    if path.lower().endswith(".safetensors") and any(term in path.lower() for term in ["vae", "ae"])
]
for candidate in vae_candidates[:2]:
    source = network_root / "flux2-klein-9B" / candidate
    destination = model_root / "vae" / Path(candidate).name
    if source.exists() and not destination.exists():
        shutil.copy2(source, destination)
    print(f"candidate vae: {destination}")

print()
print("Next step: open ComfyUI, verify the model filenames visible in loader nodes,")
print("then update runpod/model_manifest.json static_patches for flux2_klein_image_generation.")
PY
