#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

on_exit() {
    status=$?
    if [[ $status -ne 0 && $status -ne 130 ]]; then
        echo
        echo 'JingWei could not start. See the error above and Troubleshooting in README.md.'
        if [[ -t 0 ]]; then read -r -p 'Press Enter to close.'; fi
    fi
    exit "$status"
}
trap on_exit EXIT

# A configured environment starts without downloading or installing anything.
if [[ -x .venv/bin/python ]] && .venv/bin/python scripts/bootstrap.py --check; then
    .venv/bin/python launch.py "$@"
    exit $?
fi

echo 'First-time setup: preparing Python and dependencies. Keep this window open.'
export UV_UNMANAGED_INSTALL="$PWD/.bootstrap/bin"
export UV_PYTHON_INSTALL_DIR="$PWD/.bootstrap/python"
export UV_CACHE_DIR="$PWD/.bootstrap/cache"
export UV_PYTHON_INSTALL_BIN=0
export UV_PYTHON_INSTALL_REGISTRY=0
export UV_NO_CONFIG=1
uv_tool="$UV_UNMANAGED_INSTALL/uv"
if [[ ! -x "$uv_tool" ]]; then
    mkdir -p .bootstrap
    curl --fail --location --show-error --retry 2 --connect-timeout 15 --max-time 180 \
        https://astral.sh/uv/0.13.0/install.sh -o .bootstrap/install-uv.sh
    sh .bootstrap/install-uv.sh
    rm .bootstrap/install-uv.sh
fi
echo 'Preparing Python 3.12...'
"$uv_tool" python install 3.12
bootstrap_python=$("$uv_tool" python find --managed-python --no-project --system 3.12)
"$bootstrap_python" scripts/bootstrap.py --uv "$uv_tool" "$@"
