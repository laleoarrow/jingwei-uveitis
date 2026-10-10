"""Crop-aligned RVL-margin attribution using the project's architecture workflow."""

from __future__ import annotations

import base64
import importlib.util
import io
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image
import torch


LOGGER = logging.getLogger("jingwei")
METHODS = {
    "cfp": "gradient_weighted_attention_rollout",
    "oct": "token_gradient_x_activation",
}
TARGET = "rvl_positive_margin"


@lru_cache(maxsize=1)
def architecture_core():
    path = Path(__file__).resolve().parent / "vendor/architecture_cam.py"
    spec = importlib.util.spec_from_file_location("jingwei_architecture_attribution", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MAEForward(torch.nn.Module):
    """Preserve the single-token head readout used by the prediction pass."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, images):
        return self.model.head(self.model.forward_features(images)[:, 0, :])


def _png(image: Image.Image) -> str:
    image = image.copy()
    image.info.clear()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def render_maps(normalized: np.ndarray, crop: Image.Image, empty: bool) -> tuple[str, str]:
    """JET color map and a fixed 50/50 blend, without composite renormalization."""
    if normalized.shape != (crop.height, crop.width) or not np.isfinite(normalized).all():
        raise ValueError("Attribution must be finite and aligned with the model input crop")
    if normalized.min() < 0 or normalized.max() > 1:
        raise ValueError("Normalized attribution is outside [0, 1]")
    rgb = np.asarray(crop.convert("RGB"), dtype=np.uint8)
    if empty:
        heat = np.zeros_like(rgb)
        overlay = rgb.copy()
    else:
        # Standard piecewise-linear JET, quantized to a 256-entry RGB lookup table.
        # No plotting or OpenCV dependency is needed for image-only display.
        ramp = np.linspace(0, 1, 256)
        lut = np.rint(255 * np.stack([
            np.clip(1.5 - np.abs(4 * ramp - 3), 0, 1),
            np.clip(1.5 - np.abs(4 * ramp - 2), 0, 1),
            np.clip(1.5 - np.abs(4 * ramp - 1), 0, 1),
        ], axis=-1)).astype(np.uint8)
        heat = lut[(normalized * 255).astype(np.uint8)]
        overlay = np.rint(.5 * rgb.astype(np.float32) + .5 * heat.astype(np.float32)).astype(np.uint8)
    return _png(Image.fromarray(heat)), _png(Image.fromarray(overlay))


def build_attribution(model, tensor: torch.Tensor, crop: Image.Image, modality: str,
                      device: str, expected_logits: torch.Tensor) -> dict:
    metadata = {"method": METHODS[modality], "target": TARGET}
    try:
        core = architecture_core()
        explained_model = MAEForward(model).eval() if modality == "oct" else model
        # Device transfer and cloning happen outside the prediction inference_mode:
        # an MPS tensor created inside inference_mode cannot carry input gradients.
        with torch.inference_mode(False), torch.enable_grad():
            gradient_input = tensor.detach().clone().to(device)
            with core.ArchitectureCAM(explained_model, "architecture") as camera:
                normalized = camera(gradient_input, targets=[core.LogitMarginTarget()])[0]
                actual_logits = camera.outputs.detach().float().cpu()
                if actual_logits.shape != expected_logits.shape or not torch.allclose(
                        actual_logits, expected_logits, rtol=1e-4, atol=1e-5):
                    raise ValueError("Prediction and attribution forwards produced inconsistent logits")
                grid = list(camera.raw_cam.shape[-2:])
                empty = not bool(np.any(camera.positive_native > 0))
        heatmap, overlay = render_maps(normalized, crop, empty)
        return {"status": "ready", **metadata, "heatmap": heatmap, "overlay": overlay,
                "input_preview": _png(crop), "grid_size": grid, "empty": empty}
    except Exception:
        # Keep the valid prediction; never substitute an invented attribution.
        LOGGER.exception("JingWei attribution failed for modality=%s", modality)
        return {"status": "unavailable", **metadata}
