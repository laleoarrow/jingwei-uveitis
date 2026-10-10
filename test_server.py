"""Boundary tests for local image handling and clinical result integrity."""

import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from PIL import Image

import server
from inference import (InferenceEngine, InferenceError, _fingerprint, available_devices,
                       decode_image, png_preview, resolve_device)


def image_payload(mode="RGB", size=(320, 240), image_format="PNG"):
    stream = io.BytesIO()
    Image.new(mode, size).save(stream, format=image_format)
    return base64.b64encode(stream.getvalue()).decode("ascii")


class DeviceTests(unittest.TestCase):
    def test_mps_requires_both_build_and_runtime_support(self):
        for built, available, expected in ((True, True, ["cpu", "mps"]),
                                           (True, False, ["cpu"]), (False, True, ["cpu"])):
            with patch("torch.backends.mps.is_built", return_value=built), patch("torch.backends.mps.is_available", return_value=available):
                self.assertEqual(available_devices(), expected)

    def test_automatic_selects_mps_and_explicit_cpu_stays_cpu(self):
        with patch("inference.available_devices", return_value=["cpu", "mps"]):
            self.assertEqual(resolve_device("auto"), "mps")
            self.assertEqual(resolve_device("mps"), "mps")
            self.assertEqual(resolve_device("cpu"), "cpu")

    def test_automatic_falls_back_to_cpu_and_explicit_unavailable_mps_fails(self):
        with patch("inference.available_devices", return_value=["cpu"]):
            self.assertEqual(resolve_device("auto"), "cpu")
            with self.assertRaisesRegex(InferenceError, "Apple MPS is unavailable"):
                resolve_device("mps")
        with self.assertRaisesRegex(InferenceError, "Invalid processing device"):
            resolve_device("cuda")


class ImageTests(unittest.TestCase):
    def test_grayscale_is_rgb_and_preview_is_decodable(self):
        image = decode_image(image_payload("L"))
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (320, 240))
        preview = png_preview(image)
        self.assertEqual(decode_image(preview.split(",", 1)[1]).size, image.size)

    def test_malformed_image_rejected(self):
        for payload in ("not base64!", base64.b64encode(b"not an image").decode()):
            with self.assertRaises(InferenceError):
                decode_image(payload)

    def test_multipage_tiff_rejected(self):
        stream = io.BytesIO()
        first = Image.new("RGB", (4, 4))
        first.save(stream, format="TIFF", save_all=True, append_images=[first.copy()])
        with self.assertRaisesRegex(InferenceError, "multipage"):
            decode_image(base64.b64encode(stream.getvalue()).decode())

    def test_score_zero_and_probability_half_have_the_same_decision(self):
        import torch

        engine = InferenceEngine()
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / "test.pth"
            checkpoint.write_bytes(b"test")
            for margin in (-1000, -1e-8, 0, 1e-8, 1000):
                loaded = {"model": lambda _x: torch.tensor([[0, margin]], dtype=torch.float32),
                          "path": checkpoint, "fingerprint": _fingerprint(checkpoint),
                          "signature": "test", "device": "cpu"}
                with patch.object(engine, "_load", return_value=loaded):
                    result = engine.predict("cfp", image_payload(), str(checkpoint), "cpu")
                self.assertEqual(result["positive"], margin >= 0)
                self.assertEqual(result["probability"] >= .5, margin >= 0)


class ServerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        paths = {modality: Path(directory.name).resolve() / (modality.upper() + ".pth")
                 for modality in ("cfp", "oct")}
        for path in paths.values():
            path.write_bytes(b"test fixture")
        defaults = patch.object(server, "DEFAULT_PATHS", paths)
        defaults.start()
        self.addCleanup(defaults.stop)
        self.client = TestClient(server.app, base_url="http://127.0.0.1:8765")

    def test_no_project_file_access(self):
        for path in ("/inference.py", "/runtime/settings.json", "/vendor/models_vit.py", "/AGENTS.md"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_health_reports_actual_and_available_devices(self):
        with tempfile.TemporaryDirectory() as folder:
            store = server.SettingsStore(Path(folder) / "settings.json")
            with patch.object(server, "settings_store", store), patch.object(server, "available_devices", return_value=["cpu"]), patch("inference.available_devices", return_value=["cpu"]):
                response = self.client.get("/api/health")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["device"], "cpu")
                self.assertEqual(response.json()["available_devices"], ["cpu"])

    def test_rejects_foreign_origin_and_host(self):
        for headers in ({"Origin": "https://example.com"}, {"Host": "foreign.test:8765"},
                        {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.client.get("/api/settings", headers=headers).status_code, 403)

    def test_homepage_accepts_top_level_navigation_from_another_origin(self):
        for path in ("/", "/index.html"):
            for origin in ("null", "https://example.com"):
                with self.subTest(path=path, origin=origin):
                    response = self.client.get(path, headers={
                        "Origin": origin, "Sec-Fetch-Site": "cross-site",
                        "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document",
                    })
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("<title>JingWei System</title>", response.text)
                    self.assertEqual(response.headers["x-frame-options"], "DENY")

    def test_navigation_exception_does_not_expose_api_or_allow_frames(self):
        headers = {"Origin": "null", "Sec-Fetch-Site": "cross-site",
                   "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        for path in ("/api/settings", "/api/health", "/styles.css"):
            self.assertEqual(self.client.get(path, headers=headers).status_code, 403)
        for override in ({"Sec-Fetch-Dest": "iframe"}, {"Sec-Fetch-Mode": "cors"},
                         {"Host": "foreign.test:8765"}):
            self.assertEqual(self.client.get("/", headers={**headers, **override}).status_code, 403)
        self.assertEqual(self.client.post("/", headers=headers, json={}).status_code, 403)

    def test_settings_roundtrip_is_atomic_and_does_not_touch_real_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            store = server.SettingsStore(Path(folder) / "settings.json")
            with patch.object(server, "settings_store", store):
                settings = self.client.get("/api/settings").json()
                settings.pop("llm_api_key_set")
                settings["institution"] = "Test institution"
                self.assertFalse(settings["include_heatmap"])
                settings["include_heatmap"] = True
                response = self.client.put("/api/settings", json=settings)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(server.SettingsStore(store.path).value.institution, "Test institution")
                self.assertTrue(server.SettingsStore(store.path).value.include_heatmap)
                self.assertTrue(self.client.get("/api/settings").json()["include_heatmap"])
                settings.pop("include_heatmap")
                self.assertTrue(self.client.put("/api/settings", json=settings).json()["include_heatmap"])
                settings["include_heatmap"] = False
                self.assertEqual(self.client.put("/api/settings", json=settings).status_code, 200)
                self.assertFalse(server.SettingsStore(store.path).value.include_heatmap)
                settings["cfp_weight_path"] = str(Path(folder) / "missing.pth")
                self.assertEqual(self.client.put("/api/settings", json=settings).status_code, 400)
                self.assertEqual(self.client.get("/api/settings").json()["institution"], "Test institution")

    def test_legacy_settings_default_to_no_heatmap(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            store = server.SettingsStore(path)
            path.write_text(store.value.model_dump_json(exclude={"include_heatmap"}), encoding="utf-8")
            legacy = server.SettingsStore(path)
            self.assertFalse(legacy.value.include_heatmap)
            with patch.object(server, "settings_store", legacy):
                self.assertFalse(self.client.get("/api/settings").json()["include_heatmap"])

    def test_non_model_settings_preserve_loaded_model(self):
        with tempfile.TemporaryDirectory() as folder:
            store = server.SettingsStore(Path(folder) / "settings.json")
            engine = InferenceEngine()
            cached = {"device": "cpu"}
            engine._cache = cached
            changes = ({}, {"include_heatmap": True}, {"include_heatmap": False},
                       {"institution": "New institution"},
                       {"llm_enabled": True, "llm_base_url": "https://example.invalid/v1",
                        "llm_model": "test-model", "llm_api_key": "test-key"})
            with patch.object(server, "settings_store", store), patch.object(server, "engine", engine), patch.object(engine, "clear", wraps=engine.clear) as clear:
                for change in changes:
                    response = self.client.put("/api/settings", json={**store.value.model_dump(), **change})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertIs(engine._cache, cached)
                clear.assert_not_called()

    def test_model_settings_change_clears_loaded_model(self):
        with tempfile.TemporaryDirectory() as folder:
            replacement = Path(folder) / "replacement.pth"
            replacement.write_bytes(b"test")
            store = server.SettingsStore(Path(folder) / "settings.json")
            store.value = store.value.model_copy(update={"device": "cpu"})
            engine = InferenceEngine()
            with patch.object(server, "settings_store", store), patch.object(server, "engine", engine), patch("inference.available_devices", return_value=["cpu"]):
                for change in ({"cfp_weight_path": str(replacement)},
                               {"oct_weight_path": str(replacement)}, {"device": "auto"}):
                    engine._cache = {"device": "cpu"}
                    with patch.object(engine, "clear", wraps=engine.clear) as clear:
                        response = self.client.put("/api/settings", json={**store.value.model_dump(), **change})
                        self.assertEqual(response.status_code, 200, response.text)
                        clear.assert_called_once_with()
                        self.assertIsNone(engine._cache)

    def test_prediction_uses_saved_heatmap_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            store = server.SettingsStore(Path(folder) / "settings.json")
            for enabled in (False, True):
                store.save(store.value.model_copy(update={"include_heatmap": enabled}))
                with patch.object(server, "settings_store", store), patch.object(server.engine, "predict", return_value={"score": 0}) as predict:
                    response = self.client.post("/api/predict", json={"modality": "cfp", "image_base64": "image"})
                    self.assertEqual(response.status_code, 200)
                    predict.assert_called_once_with("cfp", "image", store.value.cfp_weight_path,
                                                    store.value.device, include_heatmap=enabled)

    def test_reference_default_and_missing_group(self):
        result = self.client.get("/api/reference").json()
        self.assertEqual(result["cohort"], "internal_test")
        result = self.client.get("/api/reference?modality=oct&cohort=jilin").json()
        self.assertEqual(result["groups"][1]["n"], 0)
        self.assertEqual(self.client.get("/api/reference?modality=cfp&cohort=unknown").status_code, 400)

    def test_invalid_image_never_produces_a_prediction(self):
        response = self.client.post("/api/predict", json={
            "modality": "cfp", "image_base64": "invalid!", "filename": "image.png"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())
        self.assertEqual(response.json()["detail"], "Invalid image encoding. Select or drop the image again.")
        self.assertNotIn("probability", response.json())

    def test_tiff_preview_is_png_without_model_or_lock_access(self):
        engine = MagicMock()
        engine.lock.__enter__.side_effect = AssertionError("Preview must not acquire the model lock")
        engine.predict.side_effect = AssertionError("Preview must not predict")
        engine._load.side_effect = AssertionError("Preview must not load a model")
        with patch.object(server, "engine", engine), patch("inference.build_attribution") as attribution:
            response = self.client.post("/api/preview", json={
                "image_base64": image_payload("L", size=(1600, 800), image_format="TIFF")})
            self.assertEqual(response.status_code, 200, response.text)
            engine.assert_not_called()
            self.assertEqual(engine.mock_calls, [])
            attribution.assert_not_called()
        result = response.json()
        self.assertEqual(set(result), {"preview", "width", "height"})
        self.assertEqual((result["width"], result["height"]), (1600, 800))
        self.assertTrue(result["preview"].startswith("data:image/png;base64,"))
        self.assertEqual(decode_image(result["preview"].split(",", 1)[1]).size, (1200, 600))

    def test_preview_rejects_invalid_images_and_private_extra_fields(self):
        secret = "PRIVATE_IMAGE_SENTINEL"
        for encoded in (secret, base64.b64encode(secret.encode()).decode()):
            response = self.client.post("/api/preview", json={"image_base64": encoded})
            self.assertEqual(response.status_code, 400)
            self.assertNotIn(secret, response.text)
            self.assertNotIn(encoded, response.text)
        for name in ("filename", "modality", "patient_name"):
            response = self.client.post("/api/preview", json={
                "image_base64": image_payload(), name: secret})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(secret, response.text)

    def test_preview_reuses_image_size_limit(self):
        with patch("inference.MAX_IMAGE_BYTES", 1):
            response = self.client.post("/api/preview", json={"image_base64": image_payload()})
            self.assertEqual(response.status_code, 413)
            self.assertNotIn("preview", response.json())

    def test_invalid_request_never_echoes_image_or_patient_input(self):
        secret = "PRIVATE_SENTINEL"
        response = self.client.post("/api/predict", json={
            "modality": "wrong", "image_base64": secret, "patient_name": secret})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)

    def test_plain_form_and_excessive_payload_rejected(self):
        response = self.client.post("/api/settings", content="institution=x",
                                    headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(response.status_code, 415)
        with patch.object(server, "MAX_REQUEST_BYTES", 10):
            response = self.client.post("/api/predict", content=b"x" * 11,
                                        headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
