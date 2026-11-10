import base64
import io
import json
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

from PIL import Image

from landmarks import DEFAULT_BASE_URL, DEFAULT_MODEL, MAX_ERROR_BODY_BYTES, LandmarkError, parse_response, reported_usage, responses_url, suggest_landmarks


def response_for(points):
    return {"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps(points)}]},
    ]}


class LandmarkTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (2001, 1001), "orange")
        self.points = {"optic_disc": {"x": 0.6, "y": 0.4}, "macula": {"x": 0.4, "y": 0.5}}
        clock = patch("landmarks.perf_counter", return_value=100)
        self.clock = clock.start()
        self.addCleanup(clock.stop)

    def test_request_and_native_pixel_coordinates(self):
        with patch("landmarks.urlopen", return_value=io.BytesIO(json.dumps(response_for(self.points)).encode())) as call:
            result = suggest_landmarks(self.image, "sk-test-only")
        self.assertEqual(result, {"first": [1200, 400], "center": [800, 500], "model": DEFAULT_MODEL,
                                  "elapsed_seconds": 0, "usage": None})
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, DEFAULT_BASE_URL + "/responses")
        self.assertEqual(request.headers["Authorization"], "Bearer sk-test-only")
        self.assertEqual(call.call_args.kwargs["timeout"], 90)
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "gpt-6-sol")
        self.assertFalse(payload["store"])
        self.assertNotIn("reasoning", payload)
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertNotIn("sk-test-only", request.data.decode())
        encoded = payload["input"][0]["content"][1]["image_url"].split(",", 1)[1]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as preview:
            self.assertEqual(preview.size, (1600, 800))
            self.assertEqual(preview.format, "JPEG")
            self.assertEqual(preview.mode, "RGB")
            self.assertFalse(preview.getexif())
        self.assertEqual(self.image.size, (2001, 1001))

    def test_elapsed_and_usage_are_reported_without_double_counting(self):
        response = response_for(self.points)
        response["usage"] = {
            "input_tokens": 2000, "output_tokens": 300, "total_tokens": 2300,
            "input_tokens_details": {"cached_tokens": 500},
            "output_tokens_details": {"reasoning_tokens": 250},
        }
        self.clock.side_effect = [10.125, 12.875]
        with patch("landmarks.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            result = suggest_landmarks(self.image, "sk-test-only")
        self.assertEqual(result["elapsed_seconds"], 2.75)
        self.assertEqual(result["usage"], {
            "input_tokens": 2000, "output_tokens": 300, "total_tokens": 2300,
            "cached_input_tokens": 500, "reasoning_tokens": 250,
        })

    def test_missing_usage_is_not_estimated(self):
        for response in ({}, {"usage": None}, {"usage": {}}, {"usage": "unknown"}):
            self.assertIsNone(reported_usage(response))
        self.assertEqual(reported_usage({"usage": {"input_tokens": 5, "output_tokens": 7}}), {
            "input_tokens": 5, "output_tokens": 7, "total_tokens": None,
            "cached_input_tokens": None, "reasoning_tokens": None,
        })
        self.assertEqual(reported_usage({"usage": {
            "input_tokens": True, "output_tokens": -1, "total_tokens": "12",
            "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": [],
        }}), {
            "input_tokens": None, "output_tokens": None, "total_tokens": None,
            "cached_input_tokens": 0, "reasoning_tokens": None,
        })

    def test_billed_unusable_response_retains_usage(self):
        null_points = response_for({"optic_disc": None, "macula": None})
        invalid_points = response_for({"optic_disc": {"x": 2, "y": 0.4}, "macula": self.points["macula"]})
        refusal = {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]}
        incomplete = {"status": "incomplete", "output": []}
        for response in (null_points, invalid_points, refusal, incomplete):
            response["usage"] = {"input_tokens": 200, "output_tokens": 500, "total_tokens": 700}
            self.clock.side_effect = [10.125, 12.875]
            with self.subTest(response=response), patch("landmarks.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
                with self.assertRaises(LandmarkError) as caught:
                    suggest_landmarks(self.image, "sk-test-only")
            self.assertEqual(caught.exception.metadata, {
                "model": DEFAULT_MODEL, "elapsed_seconds": 2.75,
                "usage": {"input_tokens": 200, "output_tokens": 500, "total_tokens": 700,
                          "cached_input_tokens": None, "reasoning_tokens": None},
            })
            self.assertNotIn("sk-test-only", str(caught.exception.metadata))

    def test_custom_model_and_edges(self):
        self.points = {"optic_disc": {"x": 0, "y": 0}, "macula": {"x": 1, "y": 1}}
        with patch("landmarks.urlopen", return_value=io.BytesIO(json.dumps(response_for(self.points)).encode())) as call:
            result = suggest_landmarks(self.image, "sk-test-only", "gpt-6-sol-custom")
        self.assertEqual(result["center"], [2000, 1000])
        self.assertEqual(json.loads(call.call_args.args[0].data)["model"], "gpt-6-sol-custom")

    def test_custom_service_and_symbol_key(self):
        with patch("landmarks.urlopen", return_value=io.BytesIO(json.dumps(response_for(self.points)).encode())) as call:
            result = suggest_landmarks(self.image, "provider.test+key/=", "vendor/vision-model", "https://api.example.test/custom/v1/")
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/custom/v1/responses")
        self.assertEqual(request.headers["Authorization"], "Bearer provider.test+key/=")
        self.assertEqual(result["model"], "vendor/vision-model")
        self.assertNotIn("provider.test+key/=", str(result))

    def test_compatible_provider_without_reasoning_over_http(self):
        received = []
        response = response_for(self.points)

        class Provider(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append((self.path, payload))
                if "reasoning" in payload:
                    self.send_response(400)
                    data = {"error": {"message": "Unsupported reasoning parameter"}}
                else:
                    self.send_response(200)
                    data = response
                body = json.dumps(data).encode()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        with HTTPServer(("127.0.0.1", 0), Provider) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                result = suggest_landmarks(self.image, "local-test-key", "vendor/vision-model",
                                           f"http://127.0.0.1:{server.server_port}/v1")
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual((result["first"], result["center"]), ([1200, 400], [800, 500]))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "/v1/responses")
        self.assertNotIn("reasoning", received[0][1])
        self.assertTrue(received[0][1]["text"]["format"]["strict"])

    def test_base_url_normalization_and_validation(self):
        for supplied, expected in (
            ("https://api.example.test/v1", "https://api.example.test/v1/responses"),
            ("https://api.example.test/v1/", "https://api.example.test/v1/responses"),
            ("https://api.example.test/v1/responses", "https://api.example.test/v1/responses"),
            ("https://api.example.test/v1/responses/", "https://api.example.test/v1/responses"),
            ("http://127.0.0.1:8080/v1", "http://127.0.0.1:8080/v1/responses"),
        ):
            with self.subTest(supplied=supplied):
                self.assertEqual(responses_url(supplied), expected)
        with patch("landmarks.urlopen") as call:
            for supplied in (None, "", "api.example.test", "/v1", "file:///tmp/test", "ftp://host/v1", "https:///v1",
                             "https://user:secret@host/v1", "https://host/v1?key=secret", "https://host/v1?", "https://host/v1#fragment",
                             "https://host:bad/v1", "https://host:99999/v1", "https://[bad/v1", "https://host/white space",
                             "https://host/line\nbreak", "https://host\\other/v1"):
                with self.subTest(supplied=supplied), self.assertRaises(ValueError) as caught:
                    suggest_landmarks(self.image, "provider-key", base_url=supplied)
                self.assertNotIn("secret", str(caught.exception))
            call.assert_not_called()

    def test_redirect_never_forwards_credentials(self):
        received = []

        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()

            do_POST = do_GET

            def log_message(self, *_args):
                pass

        with HTTPServer(("127.0.0.1", 0), Destination) as destination:
            class Redirect(BaseHTTPRequestHandler):
                def do_POST(self):
                    self.rfile.read(int(self.headers["Content-Length"]))
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/responses")
                    self.end_headers()

                def log_message(self, *_args):
                    pass

            with HTTPServer(("127.0.0.1", 0), Redirect) as source:
                threads = [threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
                           for server in (source, destination)]
                for thread in threads:
                    thread.start()
                try:
                    with self.assertRaisesRegex(LandmarkError, "redirected"):
                        suggest_landmarks(self.image, "provider-secret", base_url=f"http://127.0.0.1:{source.server_port}/v1")
                    self.assertEqual(received, [])
                finally:
                    source.shutdown()
                    destination.shutdown()
                    for thread in threads:
                        thread.join()

    def test_invalid_settings_do_not_send_an_image(self):
        with patch("landmarks.urlopen") as call:
            for key in (None, "", "sk-test\nInjected: true", "key with spaces", "key\x00", "密钥", "x" * 513, 123):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    suggest_landmarks(self.image, key)
            for model in (None, "", "bad model", "x" * 101, 123):
                with self.subTest(model=model), self.assertRaises(ValueError):
                    suggest_landmarks(self.image, "sk-test-only", model)
            call.assert_not_called()

    def test_missing_null_and_invalid_points(self):
        cases = [
            {}, {"optic_disc": None, "macula": self.points["macula"]},
            {"optic_disc": self.points["optic_disc"], "macula": None},
            {"optic_disc": self.points["macula"], "macula": self.points["macula"]},
        ]
        for value in (-0.1, 1.1, float("inf"), float("nan"), True, "0.5", None):
            cases.append({"optic_disc": {"x": value, "y": 0.4}, "macula": self.points["macula"]})
        for points in cases:
            with self.subTest(points=points), self.assertRaises(LandmarkError):
                parse_response(response_for(points), self.image.size)

    def test_refusal_incomplete_and_malformed_outputs(self):
        responses = [
            None, [], {}, {"status": "incomplete", "output": []},
            {"status": "completed", "output": []},
            {"status": "completed", "output": [None]},
            {"status": "completed", "output": [{"type": "message", "content": None}]},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "private details"}]}]},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "private details"}]}]},
        ]
        for response in responses:
            with self.subTest(response=response), self.assertRaises(LandmarkError) as caught:
                parse_response(response, self.image.size)
            self.assertNotIn("private details", str(caught.exception))

    def test_provider_errors_are_sanitized(self):
        for code, status in ((400, 400), (401, 400), (403, 400), (404, 400), (429, 429), (500, 502)):
            error = HTTPError(DEFAULT_BASE_URL + "/responses", code, "sk-test-only", {}, io.BytesIO(b"sk-test-only private response"))
            self.clock.side_effect = [10.125, 12.875]
            with self.subTest(code=code), patch("landmarks.urlopen", side_effect=error):
                with self.assertRaises(LandmarkError) as caught:
                    suggest_landmarks(self.image, "sk-test-only")
                self.assertEqual(caught.exception.status, status)
                self.assertNotIn("sk-test-only", str(caught.exception))
                self.assertNotIn("OpenAI", str(caught.exception))
                self.assertEqual(caught.exception.metadata, {"model": DEFAULT_MODEL, "elapsed_seconds": 2.75, "usage": None})

    def test_http_error_retains_usage_without_private_details_or_retry(self):
        body = json.dumps({
            "error": {"message": "sk-test-only private image and upstream details"},
            "usage": {"input_tokens": 1200, "output_tokens": 80, "total_tokens": 1280,
                      "input_tokens_details": {"cached_tokens": 200},
                      "output_tokens_details": {"reasoning_tokens": 60}},
        }).encode()
        for code, status in ((400, 400), (429, 429), (500, 502)):
            error = HTTPError(DEFAULT_BASE_URL + "/responses", code, "private reason", {}, io.BytesIO(body))
            self.clock.side_effect = [10.125, 12.875]
            with self.subTest(code=code), patch("landmarks.urlopen", side_effect=error) as call:
                with self.assertRaises(LandmarkError) as caught:
                    suggest_landmarks(self.image, "sk-test-only")
            call.assert_called_once()
            self.assertEqual(caught.exception.status, status)
            self.assertEqual(caught.exception.metadata, {
                "model": DEFAULT_MODEL, "elapsed_seconds": 2.75,
                "usage": {"input_tokens": 1200, "output_tokens": 80, "total_tokens": 1280,
                          "cached_input_tokens": 200, "reasoning_tokens": 60},
            })
            exposed = str(caught.exception) + json.dumps(caught.exception.metadata)
            for private in ("sk-test-only", "private", "upstream"):
                self.assertNotIn(private, exposed)

    def test_http_error_usage_parsing_is_bounded_and_sanitized(self):
        class TrackedBody(io.BytesIO):
            def read(self, size=-1):
                self.read_size = size
                return super().read(size)

        bodies = (
            b"<html>private upstream error</html>", b"\xffprivate invalid encoding",
            b"<html>private" + b"x" * MAX_ERROR_BODY_BYTES,
            b'{"usage":{"input_tokens":1},"private":"' + b"x" * MAX_ERROR_BODY_BYTES + b'"}',
            b'{"error":{"usage":{"input_tokens":1},"message":"private"}}',
            b'{"usage":{"input_tokens":"private"}}',
            b"[" * 2000 + b"]" * 2000,
        )
        for body in bodies:
            stream = TrackedBody(body)
            error = HTTPError(DEFAULT_BASE_URL + "/responses", 500, "private reason", {}, stream)
            self.clock.side_effect = [10.125, 12.875]
            with self.subTest(size=len(body)), patch("landmarks.urlopen", side_effect=error) as call:
                with self.assertRaises(LandmarkError) as caught:
                    suggest_landmarks(self.image, "sk-test-only")
            call.assert_called_once()
            self.assertEqual(stream.read_size, MAX_ERROR_BODY_BYTES + 1)
            self.assertTrue(stream.closed)
            self.assertEqual(caught.exception.status, 502)
            self.assertEqual(caught.exception.metadata, {"model": DEFAULT_MODEL, "elapsed_seconds": 2.75, "usage": None})
            self.assertNotIn("private", str(caught.exception))

    def test_interrupted_http_error_body_keeps_sanitized_status(self):
        class InterruptedBody(io.BytesIO):
            def read(self, size=-1):
                raise IncompleteRead(b"private upstream fragment", 100)

        error = HTTPError(DEFAULT_BASE_URL + "/responses", 429, "private reason", {}, InterruptedBody())
        with patch("landmarks.urlopen", side_effect=error) as call:
            with self.assertRaisesRegex(LandmarkError, "usage limit") as caught:
                suggest_landmarks(self.image, "sk-test-only")
        call.assert_called_once()
        self.assertEqual(caught.exception.status, 429)
        self.assertIsNone(caught.exception.metadata["usage"])
        self.assertNotIn("private", str(caught.exception))

    def test_network_and_unreadable_response(self):
        for error in (TimeoutError("private connection detail"), URLError("private connection detail")):
            self.clock.side_effect = [10.125, 12.875]
            with patch("landmarks.urlopen", side_effect=error):
                with self.assertRaises(LandmarkError) as caught:
                    suggest_landmarks(self.image, "sk-test-only")
                self.assertEqual(caught.exception.status, 504)
                self.assertNotIn("private", str(caught.exception))
                self.assertEqual(caught.exception.metadata, {"model": DEFAULT_MODEL, "elapsed_seconds": 2.75, "usage": None})
        self.clock.side_effect = [10.125, 12.875]
        with patch("landmarks.urlopen", return_value=io.BytesIO(b"not JSON")):
            with self.assertRaisesRegex(LandmarkError, "unreadable response"):
                suggest_landmarks(self.image, "sk-test-only")

    def test_interrupted_and_nested_success_responses_over_http(self):
        received = []

        class Provider(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(self.path)
                self.rfile.read(int(self.headers["Content-Length"]))
                if self.path.startswith("/disconnect/"):
                    self.close_connection = True
                    return
                nested = self.path.startswith("/nested/")
                body = b"[" * 10000 + b'"private"' + b"]" * 10000 if nested else b'{"private":"fragment"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body) + (0 if nested else 100)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        with HTTPServer(("127.0.0.1", 0), Provider) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                opener = build_opener(ProxyHandler({}))
                for mode, status in (("truncated", 502), ("disconnect", 504), ("nested", 502)):
                    self.clock.side_effect = [10.125, 12.875]
                    with self.subTest(mode=mode), patch("landmarks.urlopen", side_effect=opener.open) as call:
                        with self.assertRaises(LandmarkError) as caught:
                            suggest_landmarks(self.image, "local-test-key",
                                              base_url=f"http://127.0.0.1:{server.server_port}/{mode}")
                        call.assert_called_once()
                        self.assertEqual(caught.exception.status, status)
                        self.assertEqual(caught.exception.metadata, {
                            "model": DEFAULT_MODEL, "elapsed_seconds": 2.75, "usage": None,
                        })
                        self.assertNotIn("private", str(caught.exception))
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(received, ["/truncated/responses", "/disconnect/responses", "/nested/responses"])


if __name__ == "__main__":
    unittest.main()
