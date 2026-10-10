"""Install JingWei in its own environment, then start the workbench."""

import argparse
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / '.venv'
PYTHON = ENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
REQUIREMENTS = ROOT / 'requirements.txt'
PENDING = ENV / '.jingwei-installing'


def requirements():
    return [line.strip() for line in REQUIREMENTS.read_text().splitlines()
            if line.strip() and not line.startswith('#')]


def ready():
    """Accept CPU wheel suffixes, but never mistake system Python for the app env."""
    if PENDING.exists() or sys.version_info[:2] != (3, 12) or Path(sys.prefix).resolve() != ENV.resolve():
        return False
    for requirement in requirements():
        name, expected = requirement.split('==')
        try:
            installed = importlib.metadata.version(name).split('+')[0]
        except importlib.metadata.PackageNotFoundError:
            return False
        if installed != expected:
            return False
    return True


def run(*command):
    subprocess.run([str(part) for part in command], cwd=ROOT, check=True)


def install(uv):
    if ENV.exists():
        # Repair missing packages in place; never clear an existing user environment.
        if not PYTHON.is_file():
            raise RuntimeError('The .venv folder is incomplete. Rename it to .venv-backup and run the launcher again.')
        check = subprocess.run([str(PYTHON), '-c',
                                'import sys; sys.exit(sys.version_info[:2] != (3, 12))'],
                               capture_output=True)
        if check.returncode:
            raise RuntimeError('The existing .venv needs Python 3.12. Rename it to .venv-backup and run the launcher again.')
    else:
        print('Creating the JingWei environment...', flush=True)
        run(uv, 'venv', '--python', sys.executable, ENV)

    print('Installing dependencies. The first download may take several minutes...', flush=True)
    retry = ['--reinstall'] if PENDING.exists() else []
    PENDING.touch()
    backend = [] if sys.platform == 'darwin' else ['--torch-backend', 'cpu']
    run(uv, 'pip', 'install', '--python', PYTHON, *backend, *retry, '-r', REQUIREMENTS)
    run(PYTHON, '-c', 'import torch, torchvision, timm, fastapi, uvicorn, numpy, scipy, PIL, httpx')
    PENDING.unlink()
    try:
        run(PYTHON, __file__, '--check')
    except subprocess.CalledProcessError:
        PENDING.touch()
        raise
    print('Setup complete.', flush=True)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--uv')
    args, launch_args = parser.parse_known_args()
    if args.check:
        return 0 if ready() else 1
    try:
        if not args.uv:
            raise RuntimeError('Run start.command or start.bat to set up JingWei.')
        install(args.uv)
        print('Starting JingWei...', flush=True)
        return subprocess.call([str(PYTHON), str(ROOT / 'launch.py'), *launch_args], cwd=ROOT)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'\nSetup stopped: {error}\nCheck the error above, then run the launcher again.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
