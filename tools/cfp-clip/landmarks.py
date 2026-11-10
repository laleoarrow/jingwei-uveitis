"""Optional Responses API landmark suggestions; credentials are used for one request."""
from __future__ import annotations

import base64
import io
import json
import math
import re
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image

DEFAULT_MODEL = "gpt-6-sol"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
TIMEOUT_SECONDS = 90
POINT_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "x": {"type": "number", "minimum": 0, "maximum": 1},
        "y": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["x", "y"],
    "additionalProperties": False,
}
PROMPT = (
    "Locate two anatomical landmarks in this colour fundus photograph for a "
    "user-reviewed image crop: the centre of the optic disc and the macular "
    "centre (fovea). Identify the optic disc from the converging retinal vessels "
    "and disc boundary, not a bright lesion. Identify the fovea in the temporal "
    "macula using the vessel arcades and local anatomy; do not assume a fixed "
    "side or fixed distance. Return normalized x,y coordinates relative to the "
    "entire supplied image, including its black borders: (0,0) is the upper-left "
    "pixel centre and (1,1) the lower-right pixel centre. Return null for any "
    "landmark that cannot be located. Provide landmarks only, no diagnosis."
)


class LandmarkError(ValueError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status
        self.metadata: dict = {}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Send credentials only to the endpoint selected by the user.


urlopen = build_opener(NoRedirect).open


def responses_url(base_url: object) -> str:
    message = "Enter an HTTP(S) API base URL without credentials, a query or a fragment."
    if not isinstance(base_url, str) or not re.fullmatch(r"[\x21-\x7e]{1,2048}", base_url.strip()):
        raise ValueError(message)
    value = base_url.strip()
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or "?" in value or "#" in value or "\\" in value):
            raise ValueError(message)
        parsed.port  # Validate an explicitly supplied port.
    except ValueError:
        raise ValueError(message) from None
    endpoint = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    return endpoint if endpoint.endswith("/responses") else endpoint + "/responses"


def reported_usage(response: object) -> dict | None:
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return None
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    counts = {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_input_tokens": input_details.get("cached_tokens") if isinstance(input_details, dict) else None,
        "reasoning_tokens": output_details.get("reasoning_tokens") if isinstance(output_details, dict) else None,
    }
    counts = {name: value if type(value) is int and value >= 0 else None for name, value in counts.items()}
    return counts if any(value is not None for value in counts.values()) else None


def pixel_point(value: object, size: tuple[int, int]) -> list[float]:
    if value is None:
        raise LandmarkError("The model could not locate both landmarks. Please place the points manually.")
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        raise LandmarkError("The model returned invalid points. Please try again or place them manually.")
    coordinates = [value["x"], value["y"]]
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) or not 0 <= v <= 1 for v in coordinates):
        raise LandmarkError("The model returned points outside the image. Please place them manually.")
    return [coordinates[0] * (size[0] - 1), coordinates[1] * (size[1] - 1)]


def parse_response(response: object, size: tuple[int, int]) -> tuple[list[float], list[float]]:
    try:
        if not isinstance(response, dict) or response.get("status") != "completed":
            raise LandmarkError("The model did not finish locating the points. Please try again.")
        content = [part for item in response["output"] if item.get("type") == "message"
                   for part in item["content"]]
        if any(part.get("type") == "refusal" for part in content):
            raise LandmarkError("The model could not suggest points for this image. Please place them manually.")
        text = "".join(part["text"] for part in content if part.get("type") == "output_text")
        points = json.loads(text)
        if not isinstance(points, dict) or set(points) != {"optic_disc", "macula"}:
            raise ValueError("Unexpected landmark fields")
        first = pixel_point(points["optic_disc"], size)
        center = pixel_point(points["macula"], size)
        if first == center:
            raise LandmarkError("The model returned overlapping points. Please place them manually.")
        return first, center
    except LandmarkError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError):
        raise LandmarkError("The model returned an unreadable suggestion. Please try again or place the points manually.") from None


def suggest_landmarks(image: Image.Image, api_key: object, model: object = DEFAULT_MODEL,
                      base_url: object = DEFAULT_BASE_URL) -> dict:
    if not isinstance(api_key, str) or not re.fullmatch(r"[\x21-\x7e]{1,512}", api_key.strip()):
        raise ValueError("Enter a valid API key.")
    if not isinstance(model, str) or not re.fullmatch(r"[\x21-\x7e]{1,100}", model.strip()):
        raise ValueError("Enter a valid model name.")
    model = model.strip()
    endpoint = responses_url(base_url)
    preview = image.convert("RGB")
    preview.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    preview.save(buffer, format="JPEG", quality=92)
    payload = {
        "model": model,
        "store": False,
        "reasoning": {"effort": "medium"},
        "max_output_tokens": 4096,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": PROMPT},
            {"type": "input_image", "detail": "high",
             "image_url": "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")},
        ]}],
        "text": {"format": {
            "type": "json_schema", "name": "fundus_landmarks", "strict": True,
            "schema": {"type": "object", "properties": {
                "optic_disc": POINT_SCHEMA, "macula": POINT_SCHEMA,
            }, "required": ["optic_disc", "macula"], "additionalProperties": False},
        }},
    }
    request = Request(endpoint, json.dumps(payload).encode(), headers={
        "Authorization": "Bearer " + api_key.strip(), "Content-Type": "application/json",
    })
    started = perf_counter()
    result = None
    try:
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                result = json.load(response)
        except HTTPError as exc:
            if 300 <= exc.code < 400:
                raise LandmarkError("The API endpoint redirected this request. Enter the final API base URL.", 400) from None
            if exc.code in {401, 403}:
                raise LandmarkError("The API rejected this key or its permissions. Check API settings.", 400) from None
            if exc.code == 429:
                raise LandmarkError("The API reported a usage limit. Check your quota or try again later.", 429) from None
            if exc.code in {400, 404}:
                raise LandmarkError("The API could not process this image request. Check the base URL, model and access.", 400) from None
            raise LandmarkError("The API service is temporarily unavailable. Please try again later.") from None
        except (TimeoutError, URLError, OSError):
            raise LandmarkError("Could not reach the API in time. Check the base URL and your connection.", 504) from None
        except (ValueError, UnicodeError):
            raise LandmarkError("The API returned an unreadable response. Please try again.") from None
        finally:
            metadata = {"model": model, "elapsed_seconds": round(perf_counter() - started, 3),
                        "usage": reported_usage(result)}
        first, center = parse_response(result, image.size)
    except LandmarkError as exc:
        exc.metadata = metadata
        raise
    return {"first": first, "center": center, **metadata}
