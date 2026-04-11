#!/usr/bin/env bash
set -euo pipefail

VENV_PATH="${VENV_PATH:-/opt/venvs/ltx23}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ ! -f "${VENV_PATH}/bin/activate" ]; then
  echo "Virtualenv not found at ${VENV_PATH}. Run runpod/setup_ltx23.sh first." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "${VENV_PATH}/bin/activate"
python "${PROJECT_DIR}/runpod/app.py"
