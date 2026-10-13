"""Local RETFound inference using the project's frozen single-image definitions."""

from __future__ import annotations

import argparse
import base64
import binascii
import gc
import hashlib
import importlib.util
import io
import math
import threading
import time
import uuid
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, UnidentifiedImageError

try:
    from .attribution import build_attribution
except ImportError:
    from attribution import build_attribution


ROOT = Path(__file__).resolve().parent
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
DEFAULT_PATHS = {
    "cfp": ROOT / "weights/CFP.pth",
    "oct": ROOT / "weights/OCT.pth",
}
# SHA-256 of the two supplied checkpoints, frozen when Figure 2 was integrated.
# Comparing contents, rather than paths, catches a replacement at the same path.
REFERENCE_SIGNATURES = {
    "cfp": "a4968a9cc8d6d498190edd0a9ed04e00b3e03d30ed5a20e0d24f15f34de23e60",
    "oct": "4145842ac43520167e147949687f9c82e0dcff8d7deb31f2692eea9ff61e51ff",
}
MODEL_NAMES = {
    "cfp": "RETFound_dinov2 / ViT-L/14",
    "oct": "RETFound_mae / ViT-L/16",
}


class InferenceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def available_devices() -> list[str]:
    import torch

    devices = ["cpu"]
    if torch.backends.mps.is_built() and torch.backends.mps.is_available():
        devices.append("mps")
    return devices


def resolve_device(requested: str) -> str:
    if requested == "auto":
        return "mps" if "mps" in available_devices() else "cpu"
    if requested == "cpu":
        return "cpu"
    if requested != "mps":
        raise InferenceError("Invalid processing device. Select Automatic, CPU, or Apple MPS.")
    if "mps" not in available_devices():
        raise InferenceError("Apple MPS is unavailable in this environment. Select CPU or Automatic.")
    return "mps"


def normalize_checkpoint_path(raw_path: str) -> str:
    raw_path = raw_path.strip()
    if len(raw_path) >= 2 and raw_path[0] == raw_path[-1] and raw_path[0] in {"'", '"'}:
        raw_path = raw_path[1:-1].strip()
    if not raw_path:
        return ""
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return str(path.resolve())


def validate_checkpoint_path(raw_path: str) -> Path:
    normalized = normalize_checkpoint_path(raw_path)
    if not normalized:
        raise InferenceError("No model weights configured. Set the checkpoint path in Settings before analysis.")
    path = Path(normalized)
    if path.suffix.lower() not in {".pth", ".pt"}:
        raise InferenceError("Model weights must be a .pth or .pt file.")
    if not path.is_file():
        raise InferenceError(f"Model weight file not found: {path}")
    return path


def decode_image(encoded: str) -> Image.Image:
    if len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise InferenceError("Image exceeds 20 MB. Reduce the file size and try again.", 413)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise InferenceError("Invalid image encoding. Select or drop the image again.") from None
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise InferenceError("Image is empty or exceeds 20 MB. Select another image.", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"PNG", "JPEG", "TIFF", "WEBP"}:
                    raise InferenceError("Only PNG, JPEG, TIFF, and WebP images are supported.")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise InferenceError("Image exceeds 40 million pixels. Resize it and try again.", 413)
                if max(image.size) > 32768 or max(image.size) > 64 * min(image.size):
                    raise InferenceError("Image dimensions or aspect ratio are too large. Crop to a single eye examination image.", 413)
                if getattr(image, "n_frames", 1) != 1:
                    raise InferenceError("Animated or multipage images are not supported. Export a single image for analysis.")
                image.load()
                # Historical ImageFolder inference decodes RGB without exif_transpose.
                # Preserve that behavior; both previews show the same pixel orientation.
                return image.convert("RGB")
    except InferenceError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise InferenceError("Image resolution is too large. Resize it and try again.", 413) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise InferenceError("Cannot read the image; the file may be damaged. Use a valid PNG, JPEG, TIFF, or WebP image.") from None


def png_preview(image: Image.Image, maximum: int = 1200) -> str:
    preview = image.copy()
    preview.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
    # Strip EXIF (including orientation) and metadata so browser display matches
    # the historical decoded pixels and does not embed source patient metadata.
    preview.info.clear()
    buffer = io.BytesIO()
    preview.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _fingerprint(path: Path) -> tuple:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cached_model_matches(cache, modality: str, path: str, device: str) -> bool:
    if not cache:
        return False
    try:
        normalized = normalize_checkpoint_path(path)
        if not normalized:
            return False
        resolved = Path(normalized)
        return (cache["modality"] == modality and cache["path"] == resolved
                and cache["device"] == device and cache["fingerprint"] == _fingerprint(resolved))
    except OSError:
        return False


class InferenceEngine:
    """One model at a time; settings changes share this lock with inference."""

    def __init__(self):
        self.lock = threading.RLock()
        self._cache = None
        self._activity = {"phase": "idle", "modality": None, "started": None}

    def activity(self) -> dict:
        snapshot = self._activity
        elapsed = time.perf_counter() - snapshot["started"] if snapshot["started"] is not None else 0
        return {"phase": snapshot["phase"], "modality": snapshot["modality"],
                "elapsed_seconds": round(elapsed, 3)}

    def _set_phase(self, phase: str):
        self._activity = {**self._activity, "phase": phase}

    @contextmanager
    def _track_activity(self, modality: str):
        self._activity = {"phase": "analyzing", "modality": modality, "started": time.perf_counter()}
        try:
            yield
        finally:
            self._activity = {"phase": "idle", "modality": None, "started": None}

    def clear(self):
        with self.lock:
            old_device = self._cache["device"] if self._cache else None
            self._cache = None
            gc.collect()
            if old_device == "mps":
                import torch

                torch.mps.empty_cache()

    def loaded(self, modality: str, path: str, device: str) -> bool:
        return cached_model_matches(self._cache, modality, path, device)

    def _load(self, modality: str, raw_path: str, device: str):
        import torch

        path = validate_checkpoint_path(raw_path)
        if self.loaded(modality, str(path), device):
            return self._cache
        self.clear()
        before = _fingerprint(path)
        signature = _sha256(path)
        try:
            with torch.serialization.safe_globals([argparse.Namespace]):
                checkpoint = torch.load(path, map_location="cpu", mmap=True, weights_only=True)
        except Exception as exc:
            raise InferenceError(
                "Cannot safely load model weights. Use a complete project RETFound checkpoint containing model and args, "
                f"and check that the file is intact. Error type: {type(exc).__name__}."
            ) from exc
        if not isinstance(checkpoint, dict) or "model" not in checkpoint or "args" not in checkpoint:
            raise InferenceError("Invalid checkpoint structure. A complete RETFound checkpoint containing model and args is required.")
        saved = checkpoint["args"]
        if isinstance(saved, argparse.Namespace):
            saved = vars(saved)
        if not isinstance(saved, dict):
            raise InferenceError("Invalid args configuration in the checkpoint.")
        expected = "RETFound_dinov2" if modality == "cfp" else "RETFound_mae"
        if saved.get("model") != expected:
            raise InferenceError(f"Checkpoint does not match the selected modality: {modality.upper()} requires {expected}.")
        if saved.get("nb_classes") != 2 or saved.get("input_size") != 224:
            raise InferenceError("Incompatible checkpoint configuration: 2 classes and 224 x 224 input are required.")
        if modality == "oct" and saved.get("global_pool") is not True:
            raise InferenceError("OCT weights must use the project's patch average pooling (global_pool=True).")
        specification = importlib.util.spec_from_file_location(
            "jingwei_retfound_models", ROOT / "vendor/models_vit.py"
        )
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        try:
            # Meta construction avoids allocating a second 1.2 GB random model.
            with torch.device("meta"):
                if modality == "cfp":
                    model = module.RETFound_dinov2(SimpleNamespace(**saved), num_classes=2, drop_path_rate=0.0)
                else:
                    model = module.RETFound_mae(img_size=224, num_classes=2, global_pool=True, drop_path_rate=0.0)
            model.load_state_dict(checkpoint["model"], strict=True, assign=True)
            model.eval().requires_grad_(False)
            model.to(device)
        except Exception as exc:
            raise InferenceError(
                "Checkpoint parameters do not match the model architecture, or the device cannot load the model. No prediction was made. "
                f"Error type: {type(exc).__name__}."
            ) from exc
        if before != _fingerprint(path):
            raise InferenceError("The checkpoint changed while loading. Finish replacing the file and try again.", 409)
        self._cache = {
            "model": model, "modality": modality, "path": path,
            "device": device, "fingerprint": before, "signature": signature,
        }
        return self._cache

    def predict(self, modality: str, encoded: str, path: str, requested_device: str,
                *, include_heatmap: bool = False) -> dict:
        import torch
        from torchvision import transforms

        started = time.perf_counter()
        image = decode_image(encoded)
        # Mirrors code/RETFound/util/datasets.py evaluation, including bicubic resize.
        crop = transforms.Compose([
            transforms.Resize(256, interpolation=transforms.InterpolationMode.BICUBIC),
            transforms.CenterCrop(224),
        ])(image)
        tensor = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
        ])(crop).unsqueeze(0)
        with self.lock, self._track_activity(modality):
            device = resolve_device(requested_device)
            loaded = self._load(modality, path, device)
            with torch.inference_mode():
                input_tensor = tensor.to(device)
                if modality == "oct":
                    # Project MAE returns [B, 1, C] after patch mean + fc_norm.
                    # Its historical timm head selected that singleton token.
                    # Explicit selection preserves this under current timm pooling APIs.
                    features = loaded["model"].forward_features(input_tensor)
                    logits = loaded["model"].head(features[:, 0, :])
                else:
                    logits = loaded["model"](input_tensor)
                logits = logits.float().cpu()
                if logits.shape != (1, 2) or not bool(torch.isfinite(logits).all()):
                    raise InferenceError("The model returned invalid classification outputs. No report was generated. Check the weights.", 500)
                score = float(logits[0, 1] - logits[0, 0])
                # Stable double-precision sigmoid keeps zero/50% consistent,
                # including margins too small for float32 softmax to distinguish.
                probability = (1 / (1 + math.exp(-score)) if score >= 0
                               else math.exp(score) / (1 + math.exp(score)))
            if not (math.isfinite(score) and math.isfinite(probability) and 0 <= probability <= 1):
                raise InferenceError("Prediction values are invalid. No report was generated.", 500)
            attribution = {"status": "disabled"}
            if include_heatmap:
                self._set_phase("heatmap")
                attribution = build_attribution(loaded["model"], tensor, crop, modality, device, logits,
                                                on_phase=self._set_phase)
            if loaded["fingerprint"] != _fingerprint(loaded["path"]):
                self.clear()
                raise InferenceError("The checkpoint changed during inference. Reload the weights before analyzing again.", 409)
            model_info = {
                "name": MODEL_NAMES[modality], "checkpoint": str(loaded["path"]),
                "signature": loaded["signature"], "device": device,
                "reference_compatible": loaded["signature"] == REFERENCE_SIGNATURES[modality],
            }
        return {
            "id": uuid.uuid4().hex, "modality": modality,
            "score": score, "probability": probability, "positive": score >= 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "image": {"width": image.width, "height": image.height,
                      "preview": png_preview(image),
                      "input_preview": attribution.get("input_preview") or png_preview(crop)},
            "model": model_info, "threshold": 0.5, "attribution": attribution,
        }
