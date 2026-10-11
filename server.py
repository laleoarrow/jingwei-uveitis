"""Same-origin, loopback-only HTTP interface for JingWei System."""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from . import interpretation, reference
    from .inference import (DEFAULT_PATHS, MAX_IMAGE_BYTES, MODEL_NAMES, ROOT,
                            InferenceEngine, InferenceError, available_devices, decode_image,
                            normalize_checkpoint_path, png_preview, resolve_device,
                            validate_checkpoint_path)
except ImportError:
    import interpretation
    import reference
    from inference import (DEFAULT_PATHS, MAX_IMAGE_BYTES, MODEL_NAMES, ROOT,
                           InferenceEngine, InferenceError, available_devices, decode_image,
                           normalize_checkpoint_path, png_preview, resolve_device,
                           validate_checkpoint_path)


LOGGER = logging.getLogger("jingwei")
SETTINGS_PATH = ROOT / "runtime/settings.json"
MAX_REQUEST_BYTES = 4 * ((MAX_IMAGE_BYTES + 2) // 3) + 8192
engine = InferenceEngine()


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cfp_weight_path: str = Field(max_length=4096)
    oct_weight_path: str = Field(max_length=4096)
    institution: str = Field(default="JingWei System", max_length=120)
    device: Literal["auto", "cpu", "mps"] = "auto"
    include_heatmap: bool = False
    llm_enabled: bool = False
    llm_base_url: str = Field(default="", max_length=2048)
    llm_model: str = Field(default="", max_length=200)
    llm_api_key: str = Field(default="", max_length=4096, repr=False)

    def public(self) -> dict:
        return {**self.model_dump(exclude={"llm_api_key"}), "llm_api_key_set": bool(self.llm_api_key)}


class SettingsUpdate(Settings):
    llm_clear_api_key: bool = False


class InterpretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modality: Literal["cfp", "oct"]
    score: float = Field(strict=True, allow_inf_nan=False)
    probability: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def consistent_probability(self):
        expected = 1 / (1 + math.exp(-self.score)) if self.score >= 0 else math.exp(self.score) / (1 + math.exp(self.score))
        if abs(expected - self.probability) > 1e-5 or (self.score >= 0) != (self.probability >= .5):
            raise ValueError("RVL Score and predicted probability are inconsistent.")
        return self


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_base64: str = Field(min_length=1)


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modality: Literal["cfp", "oct"]
    image_base64: str = Field(min_length=1)
    filename: str = Field(default="image", max_length=512)


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self.value = Settings(
            cfp_weight_path=str(DEFAULT_PATHS["cfp"]),
            oct_weight_path=str(DEFAULT_PATHS["oct"]),
        )
        if path.is_file():
            try:
                self.value = Settings.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"Cannot read JingWei settings. Check or remove the damaged file: {path}") from exc

    def save(self, settings: Settings):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                json.dump(settings.model_dump(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.value = settings


settings_store = SettingsStore(SETTINGS_PATH)
app = FastAPI(title="JingWei System", docs_url=None, redoc_url=None, openapi_url=None)


class LocalOnlyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))

        async def reject(message, code):
            await JSONResponse({"detail": message}, status_code=code)(scope, receive, send)

        try:
            host = headers.get(b"host", b"").decode("ascii")
            target = urlsplit("//" + host)
            if (target.hostname not in {"127.0.0.1", "localhost", "::1"}
                    or target.path or target.query or target.fragment or target.username or target.password):
                raise ValueError
            port = target.port or (443 if scope["scheme"] == "https" else 80)
            # Opening the public app shell from a link/file is not an API request.
            homepage_navigation = (
                scope["method"] == "GET" and scope["path"] in {"/", "/index.html"}
                and headers.get(b"sec-fetch-mode") == b"navigate"
                and headers.get(b"sec-fetch-dest") == b"document"
            )
            origin = headers.get(b"origin")
            if origin and not homepage_navigation:
                source = urlsplit(origin.decode("ascii"))
                source_port = source.port or (443 if source.scheme == "https" else 80)
                if (source.scheme != scope["scheme"] or source.hostname != target.hostname
                        or source_port != port or source.path or source.query or source.fragment
                        or source.username or source.password):
                    raise ValueError
            if headers.get(b"sec-fetch-site") == b"cross-site" and not homepage_navigation:
                raise ValueError
        except (ValueError, UnicodeError):
            await reject("Access is restricted to the local JingWei page. Open the application and try again.", 403)
            return

        if scope["method"] in {"POST", "PUT", "PATCH"}:
            if headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower() != b"application/json":
                await reject("Invalid request format. This endpoint accepts JSON only.", 415)
                return
            try:
                content_length = int(headers.get(b"content-length", b"0"))
                if content_length < 0:
                    raise ValueError
            except ValueError:
                await reject("Invalid request length.", 400)
                return
            if content_length > MAX_REQUEST_BYTES:
                await reject("Upload is too large. Image files must not exceed 20 MB.", 413)
                return
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                    await reject("Upload is too large. Image files must not exceed 20 MB.", 413)
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            replayed = False
            original_receive = receive

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()

            receive = replay

        async def add_headers(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                    (b"x-frame-options", b"DENY"),
                ])
            await send(message)

        await self.app(scope, receive, add_headers)


app.add_middleware(LocalOnlyMiddleware)


@app.exception_handler(InferenceError)
async def inference_error(_request, error: InferenceError):
    return JSONResponse({"detail": str(error)}, status_code=error.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_request, error: RequestValidationError):
    fields = sorted({".".join(str(part) for part in item["loc"]) for item in error.errors()})
    return JSONResponse({"detail": "Invalid request parameters. Check: " + ", ".join(fields)}, status_code=422)


@app.get("/api/settings")
def get_settings():
    with engine.lock:
        return settings_store.value.public()


@app.put("/api/settings")
def put_settings(settings: SettingsUpdate):
    with engine.lock:
        old = settings_store.value
        values = settings.model_dump(exclude={"llm_clear_api_key"})
        for name in ("include_heatmap", "llm_enabled", "llm_base_url", "llm_model"):
            if name not in settings.model_fields_set:
                values[name] = getattr(old, name)
        try:
            values["llm_base_url"] = interpretation.normalize_base_url(values["llm_base_url"])
            origin_changed = interpretation.api_origin(values["llm_base_url"]) != interpretation.api_origin(old.llm_base_url)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        typed_key = settings.llm_api_key.strip()
        values["llm_api_key"] = "" if settings.llm_clear_api_key else typed_key or ("" if origin_changed else old.llm_api_key)
        values["llm_model"] = values["llm_model"].strip()
        if values["llm_enabled"]:
            if origin_changed and old.llm_api_key and not typed_key:
                raise HTTPException(400, "Enter an API key for the new server after changing the API origin.")
            if not all(values[name] for name in ("llm_base_url", "llm_model", "llm_api_key")):
                raise HTTPException(400, "Enter an API Base URL, model name, and API key to enable language model interpretation.")
        for modality in ("cfp", "oct"):
            name = modality + "_weight_path"
            path = normalize_checkpoint_path(values[name])
            # An unused modality may still have its missing default path. It must
            # not prevent configuration of the other model or report settings.
            if path and path != normalize_checkpoint_path(getattr(old, name)):
                try:
                    validate_checkpoint_path(path)
                except InferenceError as exc:
                    raise InferenceError(f"{modality.upper()}: {exc}", exc.status_code) from None
            values[name] = path
        values["institution"] = settings.institution.strip()
        resolved = Settings.model_validate(values)
        resolve_device(resolved.device)
        try:
            settings_store.save(resolved)
        except OSError as exc:
            LOGGER.exception("Unable to save JingWei settings")
            raise HTTPException(500, "Cannot save settings. Check write access to the runtime directory.") from exc
        if (resolved.device != old.device or any(
                normalize_checkpoint_path(getattr(resolved, name)) != normalize_checkpoint_path(getattr(old, name))
                for name in ("cfp_weight_path", "oct_weight_path"))):
            engine.clear()
        return resolved.public()


@app.get("/api/health")
def health():
    with engine.lock:
        settings = settings_store.value
        try:
            device = resolve_device(settings.device)
        except InferenceError:
            device = "unavailable"
        models = {}
        for modality in ("cfp", "oct"):
            path = normalize_checkpoint_path(getattr(settings, modality + "_weight_path"))
            models[modality] = {"exists": bool(path) and Path(path).is_file(),
                                "loaded": engine.loaded(modality, path, device),
                                "name": MODEL_NAMES[modality]}
        available = reference.SOURCE.is_file()
        ready = all(item["exists"] for item in models.values()) and available and device != "unavailable"
        return {"status": "ok" if ready else "degraded", "models": models,
                "device": device, "available_devices": available_devices(), "reference_available": available}


@app.get("/api/reference")
def get_reference(modality: Literal["cfp", "oct"] = "cfp", cohort: str = "internal_test"):
    try:
        return reference.get_reference(modality, cohort)
    except FileNotFoundError as exc:
        raise HTTPException(503, "Figure 2 reference data is missing. Check the project source data file.") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/preview")
def preview(request: PreviewRequest):
    image = decode_image(request.image_base64)
    return {"preview": png_preview(image), "width": image.width, "height": image.height}


@app.post("/api/predict")
def predict(request: PredictRequest):
    try:
        with engine.lock:
            settings = settings_store.value
            path = getattr(settings, request.modality + "_weight_path")
            if not normalize_checkpoint_path(path):
                raise InferenceError(
                    f"No {request.modality.upper()} weights configured. "
                    "Set the checkpoint path for this modality in Settings before analysis."
                )
            return engine.predict(request.modality, request.image_base64,
                                  path, settings.device,
                                  include_heatmap=settings.include_heatmap)
    except InferenceError:
        raise
    except Exception as exc:
        LOGGER.exception("JingWei inference failed for modality=%s", request.modality)
        raise HTTPException(
            500, "Inference failed; no prediction was generated. Check the model and runtime environment. "
            f"Error type: {type(exc).__name__}. Details are available in the local terminal."
        ) from exc


@app.post("/api/interpret")
async def interpret(request: InterpretRequest):
    with engine.lock:
        settings = {name: getattr(settings_store.value, name) for name in
                    ("llm_enabled", "llm_base_url", "llm_model", "llm_api_key")}
    return await interpretation.interpret_result(request.model_dump(), settings)


# This mount exposes only frontend files, never checkpoints or patient data.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="frontend")
