#!/usr/bin/env bash
set -euo pipefail

# Temporary helper script for first PyPI publish.
# Run:
#   export TWINE_PASSWORD='pypi-xxxxxxxxxxxxxxxx'
#   bash publish_pypi_temp.sh

if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  PYTHON="${VIRTUAL_ENV}/bin/python"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="$(command -v python3 || true)"
fi

if [[ -z "${PYTHON}" ]]; then
  echo "❌ Could not find a Python interpreter. Activate your venv first."
  exit 1
fi

if ! "${PYTHON}" -m pip --version >/dev/null 2>&1; then
  echo "⚠️ pip not available for ${PYTHON}; trying ensurepip..."
  "${PYTHON}" -m ensurepip --upgrade
fi

export TWINE_USERNAME="${TWINE_USERNAME:-__token__}"
export TWINE_PASSWORD="${TWINE_PASSWORD:-pypi-PASTE_YOUR_TOKEN_HERE}"

if [[ "${TWINE_PASSWORD}" == "pypi-PASTE_YOUR_TOKEN_HERE" ]]; then
  echo "❌ Set TWINE_PASSWORD to your PyPI API token first."
  echo "   Example: export TWINE_PASSWORD='pypi-xxxxxxxxxxxxxxxx'"
  exit 1
fi

# Build + validate
rm -rf dist build *.egg-info
"${PYTHON}" -m pip install --upgrade build twine
"${PYTHON}" -m build
"${PYTHON}" -m twine check dist/*

# Upload to PyPI
"${PYTHON}" -m twine upload dist/*

# Optional: quick install verification
# pipx install apk-distribution-pipeline
# apkdist --help
