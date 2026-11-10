"""Package only CFP Crop; never traverse or bundle the parent application."""
from __future__ import annotations

from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
NAME = f"JingWei-CFP-Crop-v{VERSION}"
SOURCE_FILES = (
    "app.py", "core.py", "landmarks.py", "README.md", "NOTICE.md", "LICENSE", "AGENTS.md",
    "requirements.txt", "start.command", "start.bat", "bootstrap.py", "scripts/start.ps1",
    "build_release.py", "static/index.html", "static/styles.css", "static/app.js",
    "static/jingwei-wordmark.svg", "tests/test_core.py", "tests/test_server.py",
    "tests/test_landmarks.py", "tests/test_launchers.py", "tests/test_bootstrap.py", "tests/test_build_release.py",
    "tests/browser.cjs", "tests/smoke_package.py",
)


def app_zip(dist: Path) -> Path:
    archive = dist / f"{NAME}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for relative in SOURCE_FILES:
            source = ROOT / relative
            entry = zipfile.ZipInfo.from_file(source, f"{NAME}/{relative}")
            entry.create_system = 3  # Preserve the macOS launcher's executable mode on Windows builds.
            entry.external_attr = (0o100755 if relative == "start.command" else 0o100644) << 16
            content = source.read_bytes()
            if relative == "start.command":
                content = content.replace(b"\r\n", b"\n")
            bundle.writestr(entry, content, compress_type=zipfile.ZIP_DEFLATED)
    return archive


def main() -> None:
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    print(app_zip(dist))


if __name__ == "__main__":
    main()
