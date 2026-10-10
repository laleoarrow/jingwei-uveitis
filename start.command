#!/bin/zsh
set -eu
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
    echo '首次使用请按 README.md 安装 Python 环境与依赖。'
    read -r '?按回车退出。'
    exit 1
fi
exec .venv/bin/python launch.py "$@"
