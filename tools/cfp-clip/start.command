#!/bin/bash
set -e
cd "$(dirname "$0")"
check_version='import sys; sys.exit(not ((3, 10) <= sys.version_info < (3, 14)))'
if [ ! -e .venv ] && [ ! -L .venv ]; then
  python=""
  for candidate in python3 python3.13 python3.12 python3.11 python3.10 python; do
    if "$candidate" -c "$check_version" >/dev/null 2>&1; then
      python="$candidate"
      break
    fi
  done
  if [ -z "$python" ]; then
    echo "Install Python 3.10-3.13, or use the standalone CFP Crop download."
    if [ -t 0 ]; then read -r -p "Press Enter to close."; fi
    exit 1
  fi
  "$python" -m venv .venv
fi
if ! .venv/bin/python -c "$check_version" >/dev/null 2>&1; then
  echo "The existing .venv must use Python 3.10-3.13. It has been left unchanged."
  echo "Move it aside and reopen this launcher, or use the standalone CFP Crop download."
  if [ -t 0 ]; then read -r -p "Press Enter to close."; fi
  exit 1
fi
if ! .venv/bin/python -c 'import PIL; assert PIL.__version__ == "11.3.0"' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python app.py "$@"
