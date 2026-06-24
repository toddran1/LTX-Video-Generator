#!/usr/bin/env bash
set -euo pipefail

COMFY_PATH="${COMFY_PATH:-/workspace/ComfyUI}"
VENV_PATH="${VENV_PATH:-/opt/venvs/imagegen}"
MODEL_ROOT="${MODEL_ROOT:-${COMFY_PATH}/models/insightface}"

echo "[1/3] Installing face swap Python dependencies"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    unzip
fi

"${VENV_PATH}/bin/python" -m pip install --upgrade pip wheel setuptools
"${VENV_PATH}/bin/python" -m pip install \
  cython \
  insightface \
  onnxruntime \
  opencv-python-headless \
  huggingface_hub

echo "[2/3] Downloading InsightFace/ReActor models"
mkdir -p "${MODEL_ROOT}"
MODEL_ROOT="${MODEL_ROOT}" "${VENV_PATH}/bin/python" - <<'PY'
import os
import shutil
import zipfile
from pathlib import Path

from huggingface_hub import hf_hub_download

model_root = Path(os.environ["MODEL_ROOT"])
model_root.mkdir(parents=True, exist_ok=True)

inswapper = hf_hub_download(
    repo_id="Gourieff/ReActor",
    repo_type="dataset",
    filename="inswapper_128.onnx",
    subfolder="models",
    local_dir=str(model_root),
    local_dir_use_symlinks=False,
)
print(f"Downloaded {inswapper}")
canonical_inswapper = model_root / "inswapper_128.onnx"
if Path(inswapper) != canonical_inswapper:
    shutil.copy2(inswapper, canonical_inswapper)
    print(f"Copied {inswapper} to {canonical_inswapper}")

buffalo_dir = model_root / "models" / "buffalo_l"
if not buffalo_dir.exists():
    buffalo_zip = hf_hub_download(
        repo_id="Gourieff/ReActor",
        repo_type="dataset",
        filename="buffalo_l.zip",
        subfolder="models",
        local_dir=str(model_root),
        local_dir_use_symlinks=False,
    )
    with zipfile.ZipFile(buffalo_zip) as archive:
        archive.extractall(model_root / "models")
    print(f"Extracted {buffalo_zip}")

buffalo_dir.mkdir(parents=True, exist_ok=True)
for filename in ("1k3d68.onnx", "2d106det.onnx", "det_10g.onnx", "genderage.onnx", "w600k_r50.onnx"):
    source = model_root / "models" / filename
    destination = buffalo_dir / filename
    if source.exists() and not destination.exists():
        shutil.copy2(source, destination)
        print(f"Copied {source} to {destination}")
PY

echo "[3/3] Verifying model files"
test -f "${MODEL_ROOT}/inswapper_128.onnx"
test -d "${MODEL_ROOT}/models/buffalo_l"

echo "InsightFace face swap setup complete."
