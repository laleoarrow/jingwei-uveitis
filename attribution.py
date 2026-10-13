"""Signed pixel RVL-margin IG with display-only sigma-1 Gaussian smoothing."""

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
METHODS = {"cfp": "integrated_gradients", "oct": "integrated_gradients"}
TARGET = "rvl_positive_margin"
# Match generate_ig_heatmaps.py CLI, whose maximum overrides IG_DEFAULTS (256).
IG_OPTIONS = {"ig_max_steps": 512}
REFINEMENT_MAX_EVALUATIONS = 8192


@lru_cache(maxsize=1)
def ig_core():
    path = Path(__file__).resolve().parent / "vendor/integrated_gradients.py"
    spec = importlib.util.spec_from_file_location("jingwei_integrated_gradients", path)
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


def render_maps(raw_pixel: np.ndarray, crop: Image.Image) -> tuple[str, str, bool, dict]:
    """Preserve signed raw pixels; render only the derived display map."""
    rgb = np.asarray(crop.convert("RGB"), dtype=np.float32) / 255
    heat, overlay, parameters = ig_core().pixel_ig_display(rgb, raw_pixel)
    empty = not bool(np.any(np.asarray(raw_pixel) != 0))
    return _png(Image.fromarray(heat)), _png(Image.fromarray(overlay)), empty, parameters


def build_attribution(model, tensor: torch.Tensor, crop: Image.Image, modality: str,
                      device: str, expected_logits: torch.Tensor, *, on_phase=None) -> dict:
    metadata = {"method": METHODS[modality], "target": TARGET, "display": "signed",
                "baseline": "blur", "device": str(device), "convergence_scope": "native_patch",
                "pixel_stability_checked": False}
    try:
        core = ig_core()
        options = {**core.IG_DEFAULTS, **IG_OPTIONS}
        metadata["parameters"] = {**options, "refinement_max_evaluations": REFINEMENT_MAX_EVALUATIONS}
        explained_model = MAEForward(model).eval() if modality == "oct" else model
        # Clone outside inference_mode: attribution requires input gradients.
        with torch.inference_mode(False), torch.enable_grad(), core._fp32_backend():
            gradient_input = tensor.detach().clone().to(device)
            with torch.no_grad():
                actual_logits = explained_model(gradient_input).detach().float().cpu()
            if actual_logits.shape != expected_logits.shape or not torch.allclose(
                    actual_logits, expected_logits, rtol=1e-4, atol=1e-5):
                raise ValueError("Prediction and attribution forwards produced inconsistent logits")
            _, _, maps, diagnostics = core.integrated_gradients(
                explained_model, gradient_input, "margin", **options)
            metadata["integration"] = "gausslegendre"
            if not bool(diagnostics["converged"][0]):
                if on_phase is not None:
                    on_phase("refining")
                _, _, maps, diagnostics = core.adaptive_margin_integrated_gradients(
                    explained_model, gradient_input,
                    **{key: options[key] for key in ("ig_batch_size", "ig_baseline", "ig_blur_sigma",
                                                    "ig_rtol", "ig_atol")},
                    max_evaluations=REFINEMENT_MAX_EVALUATIONS)
                metadata["integration"] = "adaptive_gausslegendre"
            metadata["diagnostics"] = {key: value[0].tolist() for key, value in diagnostics.items()}
            if not bool(diagnostics["converged"][0]):
                LOGGER.warning("JingWei IG did not converge for modality=%s: %s", modality, metadata["diagnostics"])
                return {"status": "unavailable", "reason": "not_converged", **metadata}
            native, raw_pixel = maps[0]
        heatmap, overlay, empty, display_parameters = render_maps(raw_pixel, crop)
        return {"status": "ready", **metadata, "heatmap": heatmap, "overlay": overlay,
                "input_preview": _png(crop), "pixel_size": list(raw_pixel.shape),
                "diagnostic_grid_size": list(native.shape), "native_map": native.tolist(),
                "raw_pixel_map": raw_pixel.tolist(), "display_parameters": display_parameters,
                "empty": empty}
    except Exception:
        # Keep the valid prediction; never substitute an invented attribution.
        LOGGER.exception("JingWei attribution failed for modality=%s", modality)
        return {"status": "unavailable", **metadata}
