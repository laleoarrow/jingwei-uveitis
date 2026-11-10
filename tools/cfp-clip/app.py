"""Independent, loopback-only browser application for JingWei CFP Crop."""
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import secrets
import shutil
import sys
import tempfile
import threading
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PIL import Image, UnidentifiedImageError

from core import SUPPORTED_SUFFIXES, load_image, make_circular_clip
from landmarks import DEFAULT_MODEL, LandmarkError, suggest_landmarks

MAX_UPLOAD_BYTES = 64 * 1024 * 1024
STATIC_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "static"
STATIC_FILES = {"index.html", "styles.css", "app.js", "jingwei-wordmark.svg"}


def safe_name(value: object) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > 240
            or value in {".", ".."} or value[-1:] in {".", " "}
            or any(ord(char) < 32 or char in '/\\:*?"<>|' for char in value)):
        raise ValueError("Use a filename without path separators or reserved characters.")
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise ValueError("This filename is reserved on Windows.")
    return value


class ClipServer(HTTPServer):
    def __init__(self, port: int = 0, static_root: Path = STATIC_ROOT):
        self.token = secrets.token_urlsafe(32)
        self.static_root = static_root
        self.workspace = tempfile.TemporaryDirectory(prefix="jingwei-cfp-crop-")
        self.records: dict[str, dict] = {}
        self.folder = "images"
        super().__init__(("127.0.0.1", port), ClipHandler)

    def reset(self, folder: str) -> None:
        folder = safe_name(folder)
        for path in Path(self.workspace.name).iterdir():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        self.records.clear()
        self.folder = folder

    def server_close(self) -> None:
        super().server_close()
        self.workspace.cleanup()


class ClipHandler(BaseHTTPRequestHandler):
    server: ClipServer

    def log_message(self, *_args) -> None:
        pass  # Do not put image names or patient information in console logs.

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        super().end_headers()

    def send_bytes(self, data: bytes, content_type: str, status: int = 200, **headers) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, data: dict, status: int = 200) -> None:
        self.send_bytes(json.dumps(data, allow_nan=False).encode(), "application/json; charset=utf-8", status)

    def send_file(self, path: Path, content_type: str, attachment: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        if attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
        self.end_headers()
        with path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile)

    def read_body(self, maximum: int = MAX_UPLOAD_BYTES) -> bytes:
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        if not 0 <= size <= maximum:
            self.close_connection = True
            raise ValueError(f"Request must be no larger than {maximum // 1024 // 1024} MB.")
        body = self.rfile.read(size)
        if len(body) != size:
            raise ValueError("The image transfer was interrupted.")
        return body

    def read_json(self) -> dict:
        value = json.loads(self.read_body(64 * 1024))
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object.")
        return value

    def allowed(self, path: str) -> bool:
        port = self.server.server_port
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if (host not in {f"127.0.0.1:{port}", f"localhost:{port}"}
                or (origin is not None and origin != f"http://{host}")
                or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            self.send_json({"error": "Only requests from this local application are accepted."}, 403)
            return False
        if path.startswith("/api/") and path != "/api/config":
            if not secrets.compare_digest(self.headers.get("X-Clip-Token", ""), self.server.token):
                self.send_json({"error": "Reload the application to start a local session."}, 403)
                return False
        return True

    def do_GET(self) -> None:
        self.dispatch("GET")

    def do_POST(self) -> None:
        self.dispatch("POST")

    def dispatch(self, method: str) -> None:
        request = urlsplit(self.path)
        if not self.allowed(request.path):
            return
        try:
            self.route(method, request.path, parse_qs(request.query))
        except LandmarkError as exc:
            self.send_json({"error": str(exc)}, exc.status)
        except (ValueError, KeyError, UnidentifiedImageError, Image.DecompressionBombError,
                Image.DecompressionBombWarning, OSError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else "This image could not be read or saved. Please choose a supported image."
            self.send_json({"error": message}, 400)

    def route(self, method: str, path: str, query: dict) -> None:
        if method == "GET" and path == "/api/config":
            self.send_json({"token": self.server.token, "supported_suffixes": sorted(SUPPORTED_SUFFIXES)})
        elif method == "POST" and path == "/api/reset":
            self.server.reset(self.read_json().get("folder", "images"))
            self.send_json({"ok": True})
        elif method == "POST" and path == "/api/images":
            self.import_image(query)
        elif path.startswith("/api/images/"):
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[2] not in self.server.records:
                self.send_json({"error": "Image not found in this session."}, 404)
                return
            record = self.server.records[parts[2]]
            if method == "GET" and parts[3] == "source":
                self.send_file(record["source"], "image/png")
            elif method == "POST" and parts[3] == "landmarks":
                settings = self.read_json()
                with Image.open(record["source"]) as image:
                    suggestion = suggest_landmarks(image, settings.get("api_key"), settings.get("model", DEFAULT_MODEL))
                self.send_json(suggestion)
            elif method == "GET" and parts[3] in {"preview", "crop"}:
                source = record["source"] if parts[3] == "preview" else record["output"]
                if not source.exists():
                    self.send_json({"error": "This image has not been cropped yet."}, 404)
                    return
                with Image.open(source) as opened:
                    preview = opened.convert("RGB")
                preview.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                preview.save(buffer, format="PNG")
                self.send_bytes(buffer.getvalue(), "image/png")
            elif method == "POST" and parts[3] == "crop":
                points = self.read_json()
                with Image.open(record["source"]) as image:
                    clipped = make_circular_clip(image, points.get("first"), points.get("center"))
                staging = record["output"].with_suffix(".tmp")
                try:
                    clipped.save(staging, format=Image.registered_extensions()[record["output"].suffix.lower()])
                    staging.replace(record["output"])
                finally:
                    staging.unlink(missing_ok=True)
                self.send_json({"width": clipped.width, "height": clipped.height, "filename": record["name"]})
            else:
                self.send_json({"error": "Unknown operation."}, 404)
        elif method == "GET" and path == "/api/export":
            completed = [record for record in self.server.records.values() if record["output"].exists()]
            if not completed:
                raise ValueError("Crop at least one image before downloading.")
            archive = Path(self.server.workspace.name) / "export.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                for record in completed:
                    bundle.write(record["output"], f"{self.server.folder}_clip/{record['name']}")
            self.send_file(archive, "application/zip", "JingWei-CFP-Crop.zip")
        elif method == "POST" and path == "/api/shutdown":
            self.read_body(64 * 1024)
            self.send_json({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        elif method == "GET" and (path == "/" or path.lstrip("/") in STATIC_FILES):
            name = "index.html" if path == "/" else path.lstrip("/")
            self.send_file(self.server.static_root / name, mimetypes.guess_type(name)[0] or "application/octet-stream")
        else:
            self.send_json({"error": "Not found."}, 404)

    def import_image(self, query: dict) -> None:
        name = safe_name(query.get("name", [""])[0])
        if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError("Choose a JPG, PNG, BMP, TIFF, GIF or WebP image.")
        if any(record["name"].casefold() == name.casefold() for record in self.server.records.values()):
            raise ValueError("An image with this filename is already in the session.")
        image = load_image(self.read_body())
        identifier = secrets.token_hex(12)
        directory = Path(self.server.workspace.name) / identifier
        directory.mkdir()
        source = directory / "source.image"
        image.save(source, format="PNG")
        self.server.records[identifier] = {"id": identifier, "name": name, "source": source, "output": directory / name}
        self.send_json({"id": identifier, "name": name, "width": image.width, "height": image.height})


def main() -> int:
    parser = argparse.ArgumentParser(description="JingWei CFP Crop — independent local cropping tool")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    with ClipServer(args.port) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        if sys.stdout is not None:
            print(f"JingWei CFP Crop: {url}\nKeep this window open. Press Ctrl+C to quit.", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
