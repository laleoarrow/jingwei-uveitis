import base64
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from PIL import Image

from landmarks import API_URL, DEFAULT_MODEL, LandmarkError, parse_response, suggest_landmarks


def response_for(points):
    return {"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps(points)}]},
    ]}


class LandmarkTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (2001, 1001), "orange")
        self.points = {"optic_disc": {"x": 0.6, "y": 0.4}, "macula": {"x": 0.4, "y": 0.5}}

    def test_request_and_native_pixel_coordinates(self):
        with patch("landmarks.urlopen", return_value=io.BytesIO(json.dumps(response_for(self.points)).encode())) as call:
            result = suggest_landmarks(self.image, "sk-test-only")
        self.assertEqual(result, {"first": [1200, 400], "center": [800, 500], "model": DEFAULT_MODEL})
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, API_URL)
        self.assertEqual(request.headers["Authorization"], "Bearer sk-test-only")
        self.assertEqual(call.call_args.kwargs["timeout"], 90)
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "gpt-6-sol")
        self.assertFalse(payload["store"])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertNotIn("sk-test-only", request.data.decode())
        encoded = payload["input"][0]["content"][1]["image_url"].split(",", 1)[1]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as preview:
            self.assertEqual(preview.size, (1600, 800))
            self.assertEqual(preview.format, "JPEG")
            self.assertEqual(preview.mode, "RGB")
            self.assertFalse(preview.getexif())
        self.assertEqual(self.image.size, (2001, 1001))

    def test_custom_model_and_edges(self):
        self.points = {"optic_disc": {"x": 0, "y": 0}, "macula": {"x": 1, "y": 1}}
        with patch("landmarks.urlopen", return_value=io.BytesIO(json.dumps(response_for(self.points)).encode())) as call:
            result = suggest_landmarks(self.image, "sk-test-only", "gpt-6-sol-custom")
        self.assertEqual(result["center"], [2000, 1000])
        self.assertEqual(json.loads(call.call_args.args[0].data)["model"], "gpt-6-sol-custom")

    def test_invalid_settings_do_not_send_an_image(self):
        with patch("landmarks.urlopen") as call:
            for key in (None, "", "sk-test\nInjected: true", "x" * 257, 123):
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
            error = HTTPError(API_URL, code, "sk-test-only", {}, io.BytesIO(b"sk-test-only private response"))
            with self.subTest(code=code), patch("landmarks.urlopen", side_effect=error):
                with self.assertRaises(LandmarkError) as caught:
                    suggest_landmarks(self.image, "sk-test-only")
                self.assertEqual(caught.exception.status, status)
                self.assertNotIn("sk-test-only", str(caught.exception))

    def test_network_and_unreadable_response(self):
        for error in (TimeoutError("private connection detail"), URLError("private connection detail")):
            with patch("landmarks.urlopen", side_effect=error):
                with self.assertRaises(LandmarkError) as caught:
                    suggest_landmarks(self.image, "sk-test-only")
                self.assertEqual(caught.exception.status, 504)
                self.assertNotIn("private", str(caught.exception))
        with patch("landmarks.urlopen", return_value=io.BytesIO(b"not JSON")):
            with self.assertRaisesRegex(LandmarkError, "unreadable response"):
                suggest_landmarks(self.image, "sk-test-only")


if __name__ == "__main__":
    unittest.main()
