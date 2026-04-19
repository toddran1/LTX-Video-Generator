#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKFLOW_ROOT="${WORKFLOW_ROOT:-/workspace/workflows}"

mkdir -p "${WORKFLOW_ROOT}/source"

if [ -d "${REPO_ROOT}/runpod/workflows/source" ]; then
  cp -f "${REPO_ROOT}"/runpod/workflows/source/*.json "${WORKFLOW_ROOT}/source/" 2>/dev/null || true
fi

if [ -d "${REPO_ROOT}/runpod/workflows/api" ]; then
  cp -f "${REPO_ROOT}"/runpod/workflows/api/*.json "${WORKFLOW_ROOT}/" 2>/dev/null || true
fi

echo "Synced repo workflows into ${WORKFLOW_ROOT}"
