"""Prepare JingWei Crop's own environment, then open the application."""
import argparse
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".venv"
PYTHON = ENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REQUIREMENTS = ROOT / "requirements.txt"
PENDING = ENV / ".cfp-crop-installing"


def ready():
    if (PENDING.exists() or not (3, 10) <= sys.version_info[:2] < (3, 14)
            or Path(sys.prefix).resolve() != ENV.resolve()):
        return False
    for line in REQUIREMENTS.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, expected = line.strip().split("==")
        try:
            if importlib.metadata.version(name) != expected:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False
    return True


def run(*command):
    subprocess.run([str(part) for part in command], cwd=ROOT, check=True)


def install(uv):
    if ENV.exists():
        if not PYTHON.is_file():
            raise RuntimeError("The .venv folder is incomplete. Rename it to .venv-backup and reopen the launcher.")
        check = subprocess.run([str(PYTHON), "-c",
                                "import sys; sys.exit(not ((3, 10) <= sys.version_info[:2] < (3, 14)))"],
                               capture_output=True)
        if check.returncode:
            raise RuntimeError("The existing .venv needs Python 3.10–3.13. Rename it to .venv-backup and reopen the launcher.")
    else:
        print("Creating the JingWei Crop environment...", flush=True)
        run(uv, "venv", "--python", sys.executable, ENV)

    print("Installing image-processing dependencies...", flush=True)
    retry = ["--reinstall"] if PENDING.exists() else []
    PENDING.touch()
    run(uv, "pip", "install", "--python", PYTHON, *retry, "-r", REQUIREMENTS)
    run(PYTHON, "-c", "from PIL import Image")
    PENDING.unlink()
    try:
        run(PYTHON, __file__, "--check")
    except subprocess.CalledProcessError:
        PENDING.touch()
        raise
    print("Setup complete.", flush=True)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--uv")
    args, launch_args = parser.parse_known_args()
    if args.check:
        return 0 if ready() else 1
    try:
        if not args.uv:
            raise RuntimeError("Run start.command or start.bat to set up JingWei Crop.")
        install(args.uv)
        print("Starting JingWei Crop...", flush=True)
        return subprocess.call([str(PYTHON), str(ROOT / "app.py"), *launch_args], cwd=ROOT)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nSetup stopped: {error}\nCheck the error above, then reopen the launcher.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
