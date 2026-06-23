#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -n "${VENV_PATH:-}" ]; then
  selected_venv="${VENV_PATH}"
elif [ -f "/opt/venvs/imagegen/bin/activate" ]; then
  selected_venv="/opt/venvs/imagegen"
else
  selected_venv="/opt/venvs/ltx23"
fi

if [ ! -f "${selected_venv}/bin/activate" ]; then
  echo "Virtualenv not found at ${selected_venv}. Run runpod/setup_ltx23.sh first." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "${selected_venv}/bin/activate"
python "${PROJECT_DIR}/runpod/app.py"
