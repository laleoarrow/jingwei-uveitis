"""Exercise a first install and an offline restart in an isolated checkout."""

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def stop(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        process.kill()
        process.wait(timeout=10)


def run_launcher(name, environment, timeout):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    command = (["cmd.exe", "/d", "/c", "start.bat"] if os.name == "nt"
               else ["bash", "start.command"])
    command += ["--no-browser", "--port", str(port)]
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == "nt" else {"start_new_session": True})
    log_path = ROOT / "runtime" / "launcher-smoke" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    print(f"{name}: starting launcher; log: {log_path}", flush=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, **options)
        try:
            while time.monotonic() - started < timeout:
                if process.poll() is not None:
                    raise RuntimeError(f"Launcher exited with code {process.returncode}")
                try:
                    with HTTP.open(url, timeout=2) as response:
                        page = response.read()
                except OSError:
                    time.sleep(1)
                    continue
                if b"JingWei" not in page:
                    raise RuntimeError("The launcher did not serve JingWei")
                with HTTP.open(url + "/api/health", timeout=20) as response:
                    health = json.load(response)
                if (health["status"] != "degraded" or not health["reference_available"]
                        or any(model["exists"] for model in health["models"].values())):
                    raise RuntimeError(f"Unexpected clean-install health: {health}")
                print(f"{name}: page and API ready in {time.monotonic() - started:.2f} s",
                      flush=True)
                return
            raise TimeoutError(f"Launcher did not become ready within {timeout} seconds")
        except BaseException:
            log.flush()
            print(log_path.read_text(encoding="utf-8", errors="replace")[-16000:], flush=True)
            raise
        finally:
            stop(process)


def main():
    if " " not in str(ROOT):
        raise SystemExit("Run this check in a disposable checkout whose path contains spaces.")
    for relative in (".venv", ".bootstrap", "runtime/settings.json", "weights/launcher-smoke.txt"):
        if (ROOT / relative).exists():
            raise SystemExit(f"A clean checkout is required; refusing to overwrite {relative}.")
    fixtures = {
        ROOT / "runtime/settings.json": json.dumps({
            "cfp_weight_path": str(ROOT / "weights/CFP.pth"),
            "oct_weight_path": str(ROOT / "weights/OCT.pth"),
            "institution": "Launcher smoke test", "device": "cpu",
        }).encode(),
        ROOT / "weights/launcher-smoke.txt": b"Preserve user weight files.\n",
    }
    for path, content in fixtures.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    environment = dict(os.environ, PYTHONUNBUFFERED="1")
    for name, timeout in (("first-install", 600), ("offline-restart", 90)):
        if name == "offline-restart":
            for key in list(environment):
                if key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
                    del environment[key]
            environment.update(UV_OFFLINE="1", PIP_NO_INDEX="1",
                               HTTP_PROXY="http://127.0.0.1:9",
                               HTTPS_PROXY="http://127.0.0.1:9",
                               ALL_PROXY="http://127.0.0.1:9",
                               NO_PROXY="127.0.0.1,localhost")
        run_launcher(name, environment, timeout)
        for path, content in fixtures.items():
            if path.read_bytes() != content:
                raise RuntimeError(f"Launcher modified user data: {path}")
    print("First install and offline restart passed; settings and weight files preserved.")


if __name__ == "__main__":
    main()
