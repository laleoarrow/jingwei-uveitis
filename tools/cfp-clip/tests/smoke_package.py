"""Exercise a frozen executable from an empty directory, without source imports."""
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
import zipfile

from PIL import Image


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tests/smoke_package.py <absolute executable>")
    executable = Path(sys.argv[1]).resolve()
    if not executable.is_file():
        raise SystemExit("Provide an existing executable using its absolute path.")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    token = ""

    def request(path, body=None):
        headers = {"X-Clip-Token": token} if token else {}
        if isinstance(body, dict):
            headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode()
        with urlopen(Request(base + path, data=body, headers=headers), timeout=2) as response:
            assert response.status == 200, (path, response.status)
            return response.read()

    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="cfp-crop-package-smoke-") as empty_directory:
        process = subprocess.Popen(
            [str(executable), "--port", str(port), "--no-browser"],
            cwd=empty_directory, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Executable exited before startup: " + process.communicate()[0].decode(errors="replace"))
                try:
                    config = json.loads(request("/api/config"))
                    break
                except (URLError, TimeoutError, ConnectionError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Packaged application did not start within 20 seconds.")
                    time.sleep(0.2)
            token = config["token"]
            assert isinstance(token, str) and token
            for asset in ("/", "/app.js", "/styles.css", "/jingwei-wordmark.svg"):
                assert request(asset), f"Empty packaged asset: {asset}"
            request("/api/reset", {"folder": "smoke"})
            source = io.BytesIO()
            Image.new("RGB", (20, 20), "white").save(source, format="PNG")
            record = json.loads(request("/api/images?name=smoke.png", source.getvalue()))
            result = json.loads(request(f"/api/images/{record['id']}/crop", {"first": [10, 6], "center": [10, 10]}))
            assert (result["width"], result["height"]) == (12, 12)
            with zipfile.ZipFile(io.BytesIO(request("/api/export"))) as archive:
                assert archive.namelist() == ["smoke_clip/smoke.png"]
                with Image.open(io.BytesIO(archive.read(archive.namelist()[0]))) as cropped:
                    assert cropped.size == (12, 12)
                    assert cropped.getpixel((0, 0)) == (0, 0, 0)
                    assert cropped.getpixel((6, 6)) == (255, 255, 255)
            request("/api/shutdown", b"")
            output, _ = process.communicate(timeout=10)
            assert process.returncode == 0, output.decode(errors="replace")
            print("Packaged application passed: assets, import, crop, ZIP export and clean shutdown.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    main()
