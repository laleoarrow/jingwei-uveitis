"""Extract the release ZIP, install through its launcher, then restart offline."""
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener
import zipfile

from PIL import Image


HTTP = build_opener(ProxyHandler({}))
LOGS = Path(__file__).resolve().parents[1] / "build/launcher-smoke"


def stop(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        process.kill()
        process.wait(timeout=10)


def run_launcher(root, name, environment, timeout):
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
        with HTTP.open(Request(base + path, data=body, headers=headers), timeout=3) as response:
            assert response.status == 200, (path, response.status)
            return response.read()

    command = (["cmd.exe", "/d", "/c", "start.bat"] if os.name == "nt" else ["bash", "start.command"])
    command += ["--port", str(port), "--no-browser"]
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
               else {"start_new_session": True})
    log_path = LOGS / f"{name}.log"
    started = time.monotonic()
    print(f"{name}: starting extracted package; log: {log_path}", flush=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, **options)
        try:
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Launcher exited before startup: {process.returncode}")
                try:
                    config = json.loads(request("/api/config"))
                    break
                except OSError:
                    if time.monotonic() - started >= timeout:
                        raise TimeoutError(f"Package did not start within {timeout} seconds")
                    time.sleep(0.5)
            token = config["token"]
            assert isinstance(token, str) and token
            for asset in ("/", "/app.js", "/styles.css", "/jingwei-wordmark.svg"):
                assert request(asset), f"Empty packaged asset: {asset}"
            request("/api/reset", {"folder": "smoke"})
            source = io.BytesIO()
            Image.new("RGB", (20, 20), "white").save(source, format="PNG")
            record = json.loads(request("/api/images?name=smoke.png", source.getvalue()))
            with Image.open(io.BytesIO(request(f"/api/images/{record['id']}/source"))) as original:
                assert original.size == (20, 20)
            result = json.loads(request(f"/api/images/{record['id']}/crop", {"first": [10, 6], "center": [10, 10]}))
            assert (result["width"], result["height"]) == (12, 12)
            with zipfile.ZipFile(io.BytesIO(request("/api/export"))) as archive:
                assert archive.namelist() == ["smoke_clip/smoke.png"]
                with Image.open(io.BytesIO(archive.read(archive.namelist()[0]))) as cropped:
                    assert cropped.size == (12, 12)
                    assert cropped.getpixel((0, 0)) == (0, 0, 0)
                    assert cropped.getpixel((6, 6)) == (255, 255, 255)
            request("/api/shutdown", b"")
            process.wait(timeout=15)
            assert process.returncode == 0, f"Launcher exited with {process.returncode}"
            print(f"{name}: import, crop, export and clean shutdown passed in {time.monotonic() - started:.2f} s", flush=True)
        except BaseException:
            log.flush()
            print(log_path.read_text(encoding="utf-8", errors="replace")[-16000:], flush=True)
            raise
        finally:
            stop(process)
    if name == "offline-restart":
        assert "First-time setup" not in log_path.read_text(encoding="utf-8", errors="replace")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tests/smoke_package.py <release.zip>")
    archive = Path(sys.argv[1]).resolve()
    LOGS.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, CI="1", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    for key in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="JingWei Crop package ") as temporary:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(temporary)
        folders = list(Path(temporary).iterdir())
        assert len(folders) == 1 and folders[0].is_dir(), "Expected one application folder"
        root = folders[0]
        assert not (root / ".venv").exists() and not (root / ".bootstrap").exists()
        run_launcher(root, "first-install", environment, 600)
        python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        base_prefix = subprocess.check_output([str(python), "-c", "import sys; print(sys.base_prefix)"], text=True).strip()
        assert Path(base_prefix).resolve().is_relative_to((root / ".bootstrap/python").resolve()), "Expected local managed Python"
        marker = root / ".venv/keep.txt"
        marker.write_text("Preserve the existing environment.")
        for key in list(environment):
            if key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
                environment.pop(key)
        environment.update(UV_OFFLINE="1", PIP_NO_INDEX="1", HTTP_PROXY="http://127.0.0.1:9",
                           HTTPS_PROXY="http://127.0.0.1:9", ALL_PROXY="http://127.0.0.1:9",
                           NO_PROXY="127.0.0.1,localhost")
        run_launcher(root, "offline-restart", environment, 60)
        assert marker.read_text() == "Preserve the existing environment."
    print("Release ZIP passed: independent managed Python, first install, offline restart and crop/export.")


if __name__ == "__main__":
    main()
