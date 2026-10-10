"""Result-only interpretation tests; every provider request is mocked."""

import asyncio
import json
import math
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

import interpretation
import server


def result(probability=.7):
    score = math.log(probability / (1 - probability)) if 0 < probability < 1 else (-1000 if probability == 0 else 1000)
    return {"modality": "cfp", "score": score, "probability": probability}


def provider_settings(**changes):
    return {"llm_enabled": True, "llm_base_url": "https://configured.example/v1",
            "llm_model": "test-model", "llm_api_key": "TEST_PRIVATE_API_KEY", **changes}


class SettingsAndRequestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = server.SettingsStore(Path(self.directory.name) / "settings.json")
        paths = {modality + "_weight_path": str(Path(self.directory.name).resolve() / (modality.upper() + ".pth"))
                 for modality in ("cfp", "oct")}
        for path in paths.values():
            Path(path).write_bytes(b"test fixture")
        self.store.value = self.store.value.model_copy(update=paths)
        self.patcher = patch.object(server, "settings_store", self.store)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = TestClient(server.app, base_url="http://127.0.0.1:8765")

    def update(self, **changes):
        fields = self.store.value.public()
        fields.pop("llm_api_key_set")
        return self.client.put("/api/settings", json={**fields, **changes})

    def test_key_never_returned_and_blank_or_omitted_preserve_it(self):
        saved = self.update(**provider_settings())
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()["llm_api_key_set"])
        self.assertNotIn("llm_api_key", saved.json())
        self.assertNotIn("TEST_PRIVATE_API_KEY", saved.text)
        for changes in ({"institution": "Another institution"}, {"llm_api_key": ""}):
            response = self.update(**changes)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.store.value.llm_api_key, "TEST_PRIVATE_API_KEY")
        public = self.client.get("/api/settings")
        self.assertNotIn("TEST_PRIVATE_API_KEY", public.text)
        self.assertNotIn("llm_api_key", public.json())
        self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode), 0o600)
        self.assertEqual(server.SettingsStore(self.store.path).value.llm_api_key, "TEST_PRIVATE_API_KEY")

    def test_explicit_clear_and_disabled_without_credentials(self):
        self.update(**provider_settings())
        response = self.update(llm_enabled=False, llm_clear_api_key=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["llm_api_key_set"])
        self.assertEqual(self.store.value.llm_api_key, "")
        self.assertNotIn("llm_clear_api_key", json.loads(self.store.path.read_text()))
        self.assertEqual(self.update(llm_enabled=False, llm_base_url="", llm_model="").status_code, 200)

    def test_cross_origin_cannot_silently_reuse_key(self):
        self.update(**provider_settings())
        for origin in ("https://other.example/v1", "http://configured.example/v1", "https://configured.example:444/v1"):
            response = self.update(llm_base_url=origin, llm_api_key="")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.store.value.llm_base_url, "https://configured.example/v1")
        response = self.update(llm_base_url="https://configured.example/api/v1")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["llm_api_key_set"])
        response = self.update(llm_base_url="https://other.example/v1", llm_enabled=False)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["llm_api_key_set"])
        self.assertEqual(self.update(llm_enabled=True).status_code, 400)
        self.assertEqual(self.update(llm_enabled=True, llm_api_key="NEW_SERVER_KEY").status_code, 200)

    def test_enabled_requires_configuration_and_rejects_unsafe_url(self):
        for changes in ({"llm_enabled": True}, {**provider_settings(), "llm_model": ""}):
            self.assertEqual(self.update(**changes).status_code, 400)
        for url in ("file:///tmp/key", "https://user:PRIVATE@configured.example/v1",
                    "https://configured.example/v1?api_key=PRIVATE", "https://configured.example/v1#PRIVATE",
                    "https://configured.example:99999/v1"):
            response = self.update(**provider_settings(llm_base_url=url))
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("PRIVATE", response.text)

    def test_template_api_at_boundary_and_no_external_call_when_disabled(self):
        with patch.object(interpretation.httpx, "AsyncClient") as client:
            for probability, label in ((.199, "negative"), (.2, "negative"), (.499999, "negative"),
                                       (.5, "positive"), (.799, "positive"), (.8, "positive")):
                response = self.client.post("/api/interpret", json=result(probability))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["source"], "template")
                self.assertFalse(response.json()["fallback"])
                self.assertIn("RVL-" + label, response.json()["text"])
                self.assertIn("50%", response.json()["text"])
            client.assert_not_called()

    def test_invalid_numeric_and_extra_private_fields_rejected(self):
        requests = [dict(result(), score=0), dict(result(), probability=1.1),
                    dict(result(), score=True), dict(result(), probability="0.7"),
                    dict(result(), score=-1e-8, probability=.5),
                    dict(result(), image_base64="PRIVATE_IMAGE"),
                    dict(result(), patient_name="PRIVATE_NAME"),
                    dict(result(), filename="PRIVATE_FILENAME"),
                    dict(result(), language="en"),
                    dict(result(), base_url="https://unconfigured.example")]
        for payload in requests:
            response = self.client.post("/api/interpret", json=payload)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertTrue(response.json()["detail"].startswith("Invalid request parameters."))
            self.assertNotIn("PRIVATE_", response.text)
        for nonfinite in ("NaN", "Infinity", "-Infinity"):
            response = self.client.post("/api/interpret", content='{"modality":"cfp","score":' + nonfinite + ',"probability":0.5}', headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 422)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def mocked(self, handler, payload=None, settings=None):
        real_client = httpx.AsyncClient
        def factory(**options):
            self.assertFalse(options["follow_redirects"])
            self.assertFalse(options["trust_env"])
            self.assertEqual(options["timeout"], interpretation.TIMEOUT_SECONDS)
            return real_client(transport=httpx.MockTransport(handler), **options)
        with patch.object(interpretation.httpx, "AsyncClient", side_effect=factory):
            return await interpretation.interpret_result(payload or result(), settings or provider_settings())

    async def test_outbound_body_is_allowlisted_and_numerical_sentence_is_fixed(self):
        received = []
        def handler(request):
            received.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "The model output favors an RVL-positive prediction."}}]})
        payload = {**result(), "patient_name": "PRIVATE_PATIENT", "image_base64": "PRIVATE_IMAGE", "filename": "PRIVATE_FILE"}
        response = await self.mocked(handler, payload)
        self.assertEqual(response["source"], "llm")
        self.assertFalse(response["fallback"])
        self.assertTrue(response["text"].startswith(interpretation.numerical_sentence(payload)))
        self.assertEqual(str(received[0].url), "https://configured.example/v1/chat/completions")
        self.assertEqual(received[0].headers["Authorization"], "Bearer TEST_PRIVATE_API_KEY")
        outbound = json.loads(received[0].content)
        self.assertEqual(set(outbound), {"model", "messages"})
        self.assertEqual(json.loads(outbound["messages"][1]["content"]), result())
        self.assertIn("No image is supplied", outbound["messages"][0]["content"])
        self.assertIn("one short English sentence", outbound["messages"][0]["content"])
        self.assertNotIn("PRIVATE", received[0].content.decode())
        self.assertNotIn("TEST_PRIVATE_API_KEY", json.dumps(response))

    async def test_negative_response_preserves_fixed_numerical_sentence(self):
        response = await self.mocked(lambda _request: httpx.Response(200, json={"choices": [{"message": {"content": "The model output favors an RVL-negative prediction."}}]}), result(.1))
        self.assertEqual(response["source"], "llm")
        self.assertTrue(response["text"].startswith("Predicted RVL probability is 10.0%, below the 50% classification threshold."))

    async def test_http_failure_redirect_and_malformed_reply_use_template(self):
        replies = [httpx.Response(503, text="PRIVATE_VENDOR_ERROR"),
                   httpx.Response(302, headers={"Location": "https://other.example"}),
                   httpx.Response(200, text="not json"), httpx.Response(200, json={}),
                   httpx.Response(200, json={"choices": []})]
        for reply in replies:
            response = await self.mocked(lambda _request: reply)
            self.assertEqual(response, {"text": interpretation.template_text(result()), "source": "template", "fallback": True})
            self.assertNotIn("PRIVATE", response["text"])

    async def test_empty_long_numeric_opposite_or_out_of_scope_reply_falls_back(self):
        for suffix in ("", "RVL-positive " + "x" * 500, "RVL-positive probability is 95%.",
                       "The model predicts RVL-negative output.", "This confirms RVL-positive diagnosis.",
                       "Severe RVL-positive disease requires treatment.", "RVL-positive. Another sentence."):
            response = await self.mocked(lambda _request: httpx.Response(200, json={"choices": [{"message": {"content": suffix}}]}))
            self.assertEqual(response["source"], "template")
            self.assertTrue(response["fallback"])

    async def test_provider_timeout_uses_template(self):
        def handler(request):
            raise httpx.ReadTimeout("PRIVATE_PROVIDER_DETAIL", request=request)
        response = await self.mocked(handler)
        self.assertTrue(response["fallback"])
        self.assertNotIn("PRIVATE", response["text"])
        async def slow(_request):
            await asyncio.sleep(.1)
            return httpx.Response(200, json={})
        with patch.object(interpretation, "TIMEOUT_SECONDS", .01):
            response = await self.mocked(slow)
        self.assertTrue(response["fallback"])

    def test_base_url_endpoint_normalization(self):
        for url in ("https://configured.example/v1", "https://configured.example/v1/",
                    "https://configured.example/v1/chat/completions", "https://configured.example"):
            self.assertEqual(interpretation.normalize_base_url(url), "https://configured.example/v1")


if __name__ == "__main__":
    unittest.main()
