"""Optional result-only language assistance; numerical statements stay deterministic."""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlsplit, urlunsplit

import httpx


TIMEOUT_SECONDS = 12
MAX_TEXT_LENGTH = 500


def normalize_base_url(value: str) -> str:
    """Keep a configured API prefix, accepting a full chat-completions endpoint."""
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or any(character.isspace() for character in value)):
            raise ValueError
        _ = parsed.port
    except ValueError:
        raise ValueError("API Base URL must be a valid http(s) URL without credentials, query parameters, or fragments.") from None
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[:-len("/chat/completions")]
    if not path:
        path = "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def api_origin(base_url: str) -> tuple | None:
    if not base_url:
        return None
    parsed = urlsplit(normalize_base_url(base_url))
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


def numerical_sentence(result: dict) -> str:
    percentage = result["probability"] * 100
    value = f"{percentage:.1f}"
    approximate = float(value) in {0, 50, 100} and float(value) != percentage
    if percentage == 50:
        return "Predicted RVL probability is 50%, exactly at the 50% classification threshold."
    direction = "below" if percentage < 50 else "above"
    return f"Predicted RVL probability is {'approximately ' if approximate else ''}{value}%, {direction} the 50% classification threshold."


def template_text(result: dict) -> str:
    probability = result["probability"]
    # These four variants only change wording; 0.5 is the sole decision threshold.
    if probability < .2:
        suffix = "The model output favors an RVL-negative prediction."
    elif probability < .5:
        suffix = "The model output falls on the RVL-negative side of the decision threshold."
    elif probability < .8:
        suffix = "The model output falls on the RVL-positive side of the decision threshold."
    else:
        suffix = "The model output favors an RVL-positive prediction."
    return numerical_sentence(result) + " " + suffix


def _safe_suffix(value, result: dict) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) + len(numerical_sentence(result)) + 1 > MAX_TEXT_LENGTH:
        return None
    # The provider can phrase a direction, but cannot supply new numerical facts,
    # opposite classifications, clinical advice, or severity/risk categories.
    if re.search(r"\d|[%<>`\n]", text):
        return None
    if len(re.findall(r"[.!?]", text)) > 1:
        return None
    if re.search(r"diagnos|confirm|sever|\bmild\b|\bmoderate\b|risk|treat|recommend|\bshould\b", text, re.I):
        return None
    positive = result["probability"] >= .5
    expected, opposite = ("positive", "negative") if positive else ("negative", "positive")
    if "rvl" not in text.lower() or expected not in text.lower() or opposite in text.lower():
        return None
    return text


async def _request_suffix(result: dict, settings: dict) -> str | None:
    base_url = normalize_base_url(settings["llm_base_url"])
    if not base_url or not settings["llm_model"] or not settings["llm_api_key"]:
        return None
    direction = "RVL-positive" if result["probability"] >= .5 else "RVL-negative"
    system = (
        f"Write one short English sentence interpreting a fixed {direction} model prediction of "
        "FFA-assessed retinal vascular leakage (RVL) in uveitis. No image is supplied; do not describe "
        "visual findings or image quality. Describe only the direction of the model output, not a diagnosis. "
        "Its numerical probability and fixed classification threshold are printed separately; include no numbers. "
        "Include RVL and the matching positive/negative direction. "
        "No severity or risk classes, care/treatment/FFA advice, or defensive boilerplate. Plain text, one sentence."
    )
    # Explicitly allowlist result fields. Never serialize settings, image, patient,
    # institution, filename, or a full prediction response into the provider body.
    result_only = {key: result[key] for key in ("modality", "score", "probability")}
    payload = {"model": settings["llm_model"], "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(result_only, ensure_ascii=False, allow_nan=False)},
    ]}
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False, trust_env=False) as client:
        response = await client.post(
            base_url + "/chat/completions", json=payload,
            headers={"Authorization": "Bearer " + settings["llm_api_key"]},
        )
        if response.status_code != 200 or len(response.content) > 64 * 1024:
            return None
        body = response.json()
        try:
            return _safe_suffix(body["choices"][0]["message"]["content"], result)
        except (KeyError, IndexError, TypeError):
            return None


async def interpret_result(result: dict, settings: dict) -> dict:
    fallback = {"text": template_text(result), "source": "template", "fallback": False}
    if not settings["llm_enabled"]:
        return fallback
    try:
        suffix = await asyncio.wait_for(_request_suffix(result, settings), timeout=TIMEOUT_SECONDS)
    except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError):
        suffix = None
    if suffix is None:
        return {**fallback, "fallback": True}
    return {"text": numerical_sentence(result) + " " + suffix, "source": "llm", "fallback": False}
