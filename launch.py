"""Start JingWei locally and open the workbench when the server is ready."""

import argparse
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="JingWei offline assessment workbench")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            print(f"Port {args.port} is in use. If JingWei is running, open {url}; otherwise use --port 8766.")
            return

    def open_when_ready():
        for _ in range(100):
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        webbrowser.open(url)
                        return
            except OSError:
                time.sleep(.3)

    if not args.no_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    print(f"JingWei System: {url}\nKeep this window open. Press Ctrl+C to stop.")
    uvicorn.run("server:app", host="127.0.0.1", port=args.port,
                app_dir=str(Path(__file__).resolve().parent), access_log=False)


if __name__ == "__main__":
    main()
