"""Package only CFP Crop; never traverse or bundle the parent application."""
from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "0.1.0"
NAME = f"JingWei-CFP-Crop-v{VERSION}"
SOURCE_FILES = (
    "app.py", "core.py", "README.md", "NOTICE.md", "LICENSE", "AGENTS.md",
    "requirements.txt", "requirements-build.txt", "start.command", "start.bat",
    "build_release.py", "static/index.html", "static/styles.css", "static/app.js",
    "static/jingwei-wordmark.svg", "tests/test_core.py", "tests/test_server.py",
    "tests/smoke_package.py",
)


def source_zip(dist: Path) -> Path:
    archive = dist / f"{NAME}-source.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for relative in SOURCE_FILES:
            bundle.write(ROOT / relative, f"{NAME}/{relative}")
    return archive


def native_zip(dist: Path) -> Path:
    system = platform.system()
    if system not in {"Darwin", "Windows"}:
        raise SystemExit("Build native packages on macOS or Windows; use the source ZIP on Linux.")
    native_name = "JingWei CFP Crop" if system == "Darwin" else "JingWei-CFP-Crop"
    output = ROOT / "build" / "native"
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--onedir" if system == "Darwin" else "--onefile",
        "--name", native_name, "--add-data", f"{ROOT / 'static'}:static",
        "--distpath", str(output), "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build"), str(ROOT / "app.py"),
    ], check=True, cwd=ROOT)
    platform_label = "macOS" if system == "Darwin" else "Windows"
    label = f"{NAME}-{platform_label}-{platform.machine().lower()}"
    stage = ROOT / "build" / label
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    if system == "Darwin":
        shutil.copytree(output / f"{native_name}.app", stage / f"{native_name}.app", symlinks=True)
    else:
        shutil.copy2(output / f"{native_name}.exe", stage)
    for filename in ("README.md", "NOTICE.md", "LICENSE"):
        shutil.copy2(ROOT / filename, stage)
    notices = stage / "third-party-licenses"
    notices.mkdir()
    for package in ("Pillow", "pyinstaller"):
        distribution = metadata.distribution(package)
        for item in distribution.files or ():
            if "license" in str(item).lower() or "copying" in str(item).lower():
                path = Path(distribution.locate_file(item))
                if path.is_file() and path.suffix not in {".py", ".pyc"}:
                    shutil.copy2(path, notices / f"{package}-{path.name}")
    for candidate in (Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE.txt"):
        if candidate.exists():
            shutil.copy2(candidate, notices / "Python-LICENSE.txt")
            break
    archive = dist / f"{label}.zip"
    if system == "Darwin":
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(stage), str(archive)], check=True)
    else:
        shutil.make_archive(str(archive.with_suffix("")), "zip", root_dir=stage.parent, base_dir=stage.name)
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true", help="Also build a native app for this OS")
    args = parser.parse_args()
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    print(source_zip(dist))
    if args.native:
        print(native_zip(dist))


if __name__ == "__main__":
    main()
