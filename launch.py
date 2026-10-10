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
    parser = argparse.ArgumentParser(description="JingWei System 本机临床工作台")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            print(f"端口 {args.port} 已被使用。若 JingWei 已运行，请打开 {url}；否则用 --port 8766。")
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
    print(f"JingWei System: {url}\n关闭此窗口或按 Ctrl+C 停止服务。")
    uvicorn.run("server:app", host="127.0.0.1", port=args.port,
                app_dir=str(Path(__file__).resolve().parent), access_log=False)


if __name__ == "__main__":
    main()
