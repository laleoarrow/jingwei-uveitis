import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
from time import perf_counter
import unittest
from unittest.mock import patch
from urllib.parse import quote
import zipfile

from PIL import Image

from app import ClipServer, MAX_UPLOAD_BYTES
from core import make_circular_clip


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.static = tempfile.TemporaryDirectory()
        Path(cls.static.name, "index.html").write_text("<title>CFP Clip</title>")
        cls.server = ClipServer(static_root=Path(cls.static.name))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()
        cls.static.cleanup()

    def request(self, method, path, body=None, *, headers=None, token=True, server=None):
        actual = {"X-Clip-Token": self.token if token is True else token} if token else {}
        actual.update(headers or {})
        if isinstance(body, dict):
            body = json.dumps(body)
            actual["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", (server or self.server).server_port, timeout=5)
        connection.request(method, path, body=body, headers=actual)
        response = connection.getresponse()
        data = response.read()
        result = response.status, dict(response.headers), data
        connection.close()
        return result

    def setUp(self):
        self.token = json.loads(self.request("GET", "/api/config", token=False)[2])["token"]
        self.session = self.server.sessions[self.token]
        self.request("POST", "/api/reset", {"folder": "study"})

    def tearDown(self):
        for token in list(self.server.sessions):
            self.server.close_session(token)

    def image_bytes(self, size=(40, 30), format="PNG"):
        image = Image.new("RGB", size)
        image.putdata([(x % 256, y % 256, (x + y) % 256) for y in range(size[1]) for x in range(size[0])])
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return image, buffer.getvalue()

    def import_image(self, name="fundus.png", data=None):
        data = data if data is not None else self.image_bytes()[1]
        status, _, body = self.request("POST", f"/api/images?name={quote(name)}", data)
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def test_crop_export_is_exact_and_sources_are_unchanged(self):
        image, original = self.image_bytes()
        record = self.import_image("眼底 image.png", original)
        identifier = record["id"]
        self.import_image("not-cropped.png")
        points = {"first": [12.25, 10.5], "center": [22.5, 15.25]}
        status, _, body = self.request("POST", f"/api/images/{identifier}/crop", points)
        self.assertEqual(status, 200, body)
        expected = make_circular_clip(image, points["first"], points["center"])
        self.assertEqual(json.loads(body)["width"], expected.width)
        status, headers, body = self.request("GET", "/api/export")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(body)) as bundle:
            self.assertEqual(bundle.namelist(), ["study_clip/眼底 image.png"])
            with Image.open(io.BytesIO(bundle.read(bundle.namelist()[0]))) as result:
                self.assertEqual(result.tobytes(), expected.tobytes())
        with Image.open(self.session.records[identifier]["source"]) as unchanged:
            self.assertEqual(unchanged.tobytes(), image.tobytes())
        self.assertEqual(original, self.image_bytes()[1])

    def test_auth_host_origin_and_static_paths(self):
        self.assertEqual(self.request("GET", "/", token=False)[0], 200)
        config = self.request("GET", "/api/config", token=False)
        self.assertNotEqual(json.loads(config[2])["token"], self.token)
        self.assertEqual(self.request("POST", "/api/reset", {}, token=False)[0], 403)
        self.assertEqual(self.request("GET", "/api/config", headers={"Host": "attacker.invalid"})[0], 403)
        self.assertEqual(self.request("GET", "/api/config", headers={"Origin": "https://attacker.invalid"})[0], 403)
        self.assertEqual(self.request("GET", "/api/config", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        for path in ("/../app.py", "/app.py", "/static/../app.py", "/%2e%2e/app.py"):
            self.assertEqual(self.request("GET", path)[0], 404)

    def test_file_validation_duplicates_and_bad_upload(self):
        for name in ("../outside.png", "a/b.png", "a\\b.png", "CON.png", "a.txt", "foo.png "):
            self.assertEqual(self.request("POST", f"/api/images?name={quote(name)}", self.image_bytes()[1])[0], 400)
        self.import_image("A.PNG")
        self.assertEqual(self.request("POST", "/api/images?name=a.png", self.image_bytes()[1])[0], 400)
        self.assertEqual(self.request("POST", "/api/images?name=bad.png", b"not-an-image")[0], 400)
        self.assertEqual(self.request("POST", "/api/images?name=large.png", b"", headers={"Content-Length": str(MAX_UPLOAD_BYTES + 1)})[0], 400)

    def test_no_accidental_export_for_source_name(self):
        self.import_image("source.png")
        self.assertEqual(self.request("GET", "/api/export")[0], 400)

    def test_unknown_image_invalid_points_and_reset(self):
        record = self.import_image()
        identifier = record["id"]
        self.assertEqual(self.request("GET", "/api/images/missing/preview")[0], 404)
        self.assertEqual(self.request("GET", f"/api/images/{identifier}/crop")[0], 404)
        self.assertEqual(self.request("POST", f"/api/images/{identifier}/crop", {"first": [0, 0], "center": [999, 999]})[0], 400)
        workspace = self.session.records[identifier]["source"].parent
        self.request("POST", "/api/reset", {"folder": "next"})
        self.assertFalse(workspace.exists())
        self.assertEqual(self.session.records, {})

    def test_tiff_crop_preview_works_in_browser(self):
        record = self.import_image("image.tiff", self.image_bytes(format="TIFF")[1])
        base = f"/api/images/{record['id']}"
        self.assertEqual(self.request("POST", base + "/crop", {"first": [12, 12], "center": [20, 15]})[0], 200)
        status, headers, data = self.request("GET", base + "/crop")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertEqual(Image.open(io.BytesIO(data)).format, "PNG")

    def test_source_for_zoom_preserves_native_pixels(self):
        image = Image.new("RGB", (2001, 1001), "orange")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        record = self.import_image(data=buffer.getvalue())
        base = f"/api/images/{record['id']}"
        status, headers, data = self.request("GET", base + "/source")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        with Image.open(io.BytesIO(data)) as source:
            self.assertEqual(source.size, image.size)
            self.assertEqual(source.tobytes(), image.tobytes())
        self.assertEqual(self.request("GET", base + "/source", token=False)[0], 403)

    def test_landmark_endpoint_does_not_keep_crop_or_credentials(self):
        record = self.import_image()
        base = f"/api/images/{record['id']}"
        response = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": '{"optic_disc":{"x":0.6,"y":0.4},"macula":{"x":0.4,"y":0.5}}'},
        ]}]}
        settings = {"api_key": "sk-test-only", "base_url": "https://api.example.test/v1"}
        with patch("landmarks.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as call, \
                patch("landmarks.perf_counter", side_effect=[10, 12.5]):
            self.assertEqual(self.request("POST", base + "/landmarks", settings, token=False)[0], 403)
            call.assert_not_called()
            status, _, body = self.request("POST", base + "/landmarks", settings)
        self.assertEqual(status, 200, body)
        self.assertEqual(call.call_args.args[0].full_url, "https://api.example.test/v1/responses")
        self.assertEqual(json.loads(body), {"first": [23.4, 11.600000000000001], "center": [15.600000000000001, 14.5],
                                           "model": "gpt-6-sol", "elapsed_seconds": 2.5, "usage": None})
        self.assertEqual(self.request("GET", base + "/crop")[0], 404)
        self.assertEqual(self.request("GET", "/api/export")[0], 400)
        self.assertNotIn("sk-test-only", str(self.session.records))
        self.assertNotIn(b"sk-test-only", self.request("GET", "/api/config")[2])
        self.assertEqual(self.request("POST", base + "/landmarks", {})[0], 400)

    def test_landmark_failure_retains_reported_usage(self):
        record = self.import_image()
        response = {"status": "incomplete", "output": [], "usage": {
            "input_tokens": 1200, "output_tokens": 4096, "total_tokens": 5296,
            "output_tokens_details": {"reasoning_tokens": 4096},
        }}
        with patch("landmarks.urlopen", return_value=io.BytesIO(json.dumps(response).encode())), \
                patch("landmarks.perf_counter", side_effect=[10, 16.25]):
            status, _, body = self.request("POST", f"/api/images/{record['id']}/landmarks", {"api_key": "sk-test-only"})
        self.assertEqual(status, 502)
        result = json.loads(body)
        self.assertIn("did not finish", result["error"])
        self.assertEqual(result["elapsed_seconds"], 6.25)
        self.assertEqual(result["model"], "gpt-6-sol")
        self.assertEqual(result["usage"], {"input_tokens": 1200, "output_tokens": 4096, "total_tokens": 5296,
                                          "cached_input_tokens": None, "reasoning_tokens": 4096})
        self.assertNotIn(b"sk-test-only", body)

    def test_sessions_isolate_import_reset_crop_and_export(self):
        record = self.import_image("tab-A.png")
        points = {"first": [12, 12], "center": [20, 15]}
        self.assertEqual(self.request("POST", f"/api/images/{record['id']}/crop", points)[0], 200)
        second = json.loads(self.request("GET", "/api/config", token=False)[2])["token"]
        self.assertNotEqual(second, self.token)
        self.assertNotEqual(self.session.workspace.name, self.server.sessions[second].workspace.name)
        self.assertEqual(self.request("GET", f"/api/images/{record['id']}/source", token=second)[0], 404)
        self.assertEqual(self.request("POST", f"/api/images/{record['id']}/crop", points, token=second)[0], 404)
        self.assertEqual(self.request("GET", "/api/export", token=second)[0], 400)
        second_record = json.loads(self.request("POST", "/api/images?name=tab-A.png", self.image_bytes()[1], token=second)[2])
        self.assertEqual(self.request("GET", f"/api/images/{second_record['id']}/source")[0], 404)
        self.assertEqual(self.request("POST", "/api/reset", {"folder": "tab-B"}, token=second)[0], 200)
        status, _, data = self.request("GET", "/api/export")
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            self.assertEqual(bundle.namelist(), ["study_clip/tab-A.png"])
            expected = make_circular_clip(self.image_bytes()[0], points["first"], points["center"])
            with Image.open(io.BytesIO(bundle.read(bundle.namelist()[0]))) as cropped:
                self.assertEqual(cropped.tobytes(), expected.tobytes())

    def test_close_session_releases_only_its_workspace_and_allows_reload(self):
        self.import_image()
        workspace = Path(self.session.workspace.name)
        second = json.loads(self.request("GET", "/api/config", token=False)[2])["token"]
        second_workspace = Path(self.server.sessions[second].workspace.name)
        self.assertEqual(self.request("POST", "/api/close-session", {})[0], 200)
        self.assertFalse(workspace.exists())
        self.assertTrue(second_workspace.exists())
        self.assertEqual(self.request("POST", "/api/reset", {})[0], 403)
        self.assertEqual(self.request("POST", "/api/reset", {}, token=second)[0], 200)
        self.assertEqual(self.request("POST", "/api/close-session", {}, token=second)[0], 200)
        self.assertFalse(second_workspace.exists())
        self.assertTrue(self.thread.is_alive())
        self.assertEqual(self.request("GET", "/api/config", token=False)[0], 200)

    def test_quit_one_tab_preserves_another_tab(self):
        second = json.loads(self.request("GET", "/api/config", token=False)[2])["token"]
        self.assertEqual(self.request("POST", "/api/shutdown", {})[0], 200)
        self.assertTrue(self.thread.is_alive())
        self.assertEqual(self.request("POST", "/api/reset", {}, token=second)[0], 200)
        self.assertEqual(self.request("GET", "/api/export")[0], 403)

    def test_slow_landmarks_do_not_block_another_tab(self):
        record = self.import_image()
        started = threading.Event()
        release = threading.Event()
        responses = []

        def slow_suggestion(*_args):
            started.set()
            release.wait(timeout=4)
            return {"first": [12, 12], "center": [20, 15], "model": "test"}

        with patch("app.suggest_landmarks", side_effect=slow_suggestion):
            thread = threading.Thread(target=lambda: responses.append(self.request(
                "POST", f"/api/images/{record['id']}/landmarks", {"api_key": "test"})))
            thread.start()
            try:
                self.assertTrue(started.wait(timeout=2))
                before = perf_counter()
                second = json.loads(self.request("GET", "/api/config", token=False)[2])["token"]
                self.assertEqual(self.request("POST", "/api/reset", {}, token=second)[0], 200)
                self.assertLess(perf_counter() - before, 1)
                self.assertFalse(release.is_set())
            finally:
                release.set()
                thread.join(timeout=3)
        self.assertEqual(responses[0][0], 200)

    def test_partial_body_times_out_without_blocking_other_tabs(self):
        with patch("app.SOCKET_TIMEOUT_SECONDS", 0.25):
            connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
            try:
                connection.putrequest("POST", "/api/images?name=partial.png")
                connection.putheader("X-Clip-Token", self.token)
                connection.putheader("Content-Length", "100")
                connection.endheaders()
                connection.send(b"partial")
                second = json.loads(self.request("GET", "/api/config", token=False)[2])["token"]
                self.assertEqual(self.request("POST", "/api/reset", {}, token=second)[0], 200)
                response = connection.getresponse()
                self.assertEqual(response.status, 408)
                self.assertIn("timed out", json.loads(response.read())["error"])
            finally:
                connection.close()
        self.assertEqual(self.request("POST", "/api/reset", {})[0], 200)

    def test_json_body_limit_uses_kilobytes(self):
        status, _, body = self.request("POST", "/api/reset", b"", headers={"Content-Length": str(64 * 1024 + 1)})
        self.assertEqual(status, 400)
        self.assertIn("64 KB", json.loads(body)["error"])

    def test_shutdown_cleans_temporary_images(self):
        with ClipServer(static_root=Path(self.static.name)) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            token = json.loads(self.request("GET", "/api/config", token=False, server=server)[2])["token"]
            workspace = Path(server.sessions[token].workspace.name)
            (workspace / "temporary.png").write_bytes(b"temporary")
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("POST", "/api/shutdown", body="", headers={"X-Clip-Token": token})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            connection.close()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        self.assertFalse(workspace.exists())


if __name__ == "__main__":
    unittest.main()
