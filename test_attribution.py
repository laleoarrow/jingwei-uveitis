"""Small differentiable models exercise attribution without loading checkpoints."""

import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
import torch
from torch import nn
from torch.nn import functional as F

import attribution
from inference import InferenceEngine, _fingerprint


class ToyPatchEmbed(nn.Module):
    grid_size = (2, 2)

    def forward(self, images):
        patches = F.adaptive_avg_pool2d(images.mean(1, keepdim=True), self.grid_size)
        values = patches.flatten(2).transpose(1, 2)
        return torch.cat((values, torch.ones_like(values)), dim=-1)


class ToyAttention(nn.Module):
    def __init__(self):
        super().__init__()
        self.fused_attn = True
        self.attn_drop = nn.Identity()

    def forward(self, tokens):
        attention = (tokens @ tokens.transpose(-1, -2)).softmax(dim=-1)[:, None]
        if not self.fused_attn:
            attention = self.attn_drop(attention)
        return attention[:, 0] @ tokens


class ToyBlock(nn.Module):
    def __init__(self):
        super().__init__()
        self.attn = ToyAttention()

    def forward(self, tokens):
        return tokens + self.attn(tokens)


class ToyModel(nn.Module):
    num_prefix_tokens = 1

    def __init__(self, patch_average=False, positive_margin=True):
        super().__init__()
        self.global_pool = True if patch_average else "token"
        self.patch_embed = ToyPatchEmbed()
        self.blocks = nn.ModuleList([ToyBlock(), ToyBlock()])
        self.head = nn.Linear(2, 2, bias=False)
        with torch.no_grad():
            self.head.weight.copy_(torch.tensor([[1., 0.], [3., 0.]]) if positive_margin
                                   else torch.tensor([[3., 0.], [1., 0.]]))
        self.eval().requires_grad_(False)

    def forward_features(self, images):
        patches = self.patch_embed(images)
        tokens = torch.cat((torch.zeros_like(patches[:, :1]), patches), dim=1)
        for block in self.blocks:
            tokens = block(tokens)
        return tokens[:, 1:].mean(dim=1, keepdim=True) if self.global_pool is True else tokens[:, 0]

    def forward(self, images):
        if self.global_pool is True:
            raise RuntimeError("MAE requires the explicit single-token adapter")
        return self.head(self.forward_features(images))


def png_pixels(uri):
    with Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))) as image:
        return np.asarray(image.convert("RGB")).copy()


class AttributionTests(unittest.TestCase):
    def setUp(self):
        yy, xx = np.mgrid[:224, :224]
        pixels = np.stack((xx, yy, np.full_like(xx, 120)), axis=-1).astype(np.uint8)
        self.crop = Image.fromarray(pixels)
        self.tensor = torch.from_numpy(pixels.copy()).permute(2, 0, 1).float()[None] / 255

    def baseline(self, model, modality):
        with torch.inference_mode():
            return attribution.MAEForward(model)(self.tensor) if modality == "oct" else model(self.tensor)

    def test_target_is_positive_logit_margin_not_predicted_class(self):
        logits = torch.tensor([[4., 1.]], requires_grad=True)
        target = attribution.architecture_core().LogitMarginTarget()(logits)
        self.assertEqual(target.item(), -3)
        target.backward()
        torch.testing.assert_close(logits.grad, torch.tensor([[-1., 1.]]))

    def test_rollout_cleans_hooks_preserves_forward_and_repeats(self):
        model = ToyModel()
        baseline = self.baseline(model, "cfp")
        before = {name: value.clone() for name, value in model.state_dict().items()}
        first = attribution.build_attribution(model, self.tensor, self.crop, "cfp", "cpu", baseline)
        second = attribution.build_attribution(model, self.tensor, self.crop, "cfp", "cpu", baseline)
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["method"], "gradient_weighted_attention_rollout")
        self.assertEqual(first["target"], "rvl_positive_margin")
        self.assertEqual(first["grid_size"], [2, 2])
        self.assertEqual(first["heatmap"], second["heatmap"])
        torch.testing.assert_close(self.baseline(model, "cfp"), baseline, rtol=0, atol=0)
        for layer in model.modules():
            self.assertFalse(layer._forward_hooks)
        self.assertTrue(all(block.attn.fused_attn for block in model.blocks))
        self.assertTrue(all(not parameter.requires_grad and parameter.grad is None for parameter in model.parameters()))
        for name, value in model.state_dict().items():
            torch.testing.assert_close(value, before[name], rtol=0, atol=0)

    def test_mae_maps_align_with_input_and_use_fixed_half_blend(self):
        model = ToyModel(patch_average=True)
        baseline = self.baseline(model, "oct")
        # This recreates the problematic inference-tensor case from device transfer.
        with torch.inference_mode():
            inference_tensor = self.tensor.clone()
        result = attribution.build_attribution(model, inference_tensor, self.crop, "oct", "cpu", baseline)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["method"], "token_gradient_x_activation")
        self.assertFalse(result["empty"])
        heat = png_pixels(result["heatmap"])
        overlay = png_pixels(result["overlay"])
        np.testing.assert_array_equal(png_pixels(result["input_preview"]), np.asarray(self.crop))
        self.assertEqual(heat.shape, (224, 224, 3))
        np.testing.assert_array_equal(overlay, np.rint(.5 * np.asarray(self.crop).astype(np.float32) + .5 * heat).astype(np.uint8))
        self.assertFalse(model.blocks[-1]._forward_hooks)

    def test_negative_margin_has_no_invented_positive_attribution(self):
        model = ToyModel(patch_average=True, positive_margin=False)
        baseline = self.baseline(model, "oct")
        self.assertLess(float(baseline[0, 1] - baseline[0, 0]), 0)
        result = attribution.build_attribution(model, self.tensor, self.crop, "oct", "cpu", baseline)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["empty"])
        self.assertFalse(png_pixels(result["heatmap"]).any())
        np.testing.assert_array_equal(png_pixels(result["overlay"]), np.asarray(self.crop))

    def test_gradient_forward_failure_restores_hooks_and_attention_mode(self):
        model = ToyModel()
        with patch.object(model.head, "forward", side_effect=RuntimeError("test forward failure")), self.assertLogs("jingwei", level="ERROR"):
            result = attribution.build_attribution(model, self.tensor, self.crop, "cfp", "cpu", torch.zeros(1, 2))
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("heatmap", result)
        self.assertNotIn("overlay", result)
        self.assertTrue(all(block.attn.fused_attn for block in model.blocks))
        self.assertTrue(all(not layer._forward_hooks for layer in model.modules()))

    def test_mismatched_gradient_logits_are_not_presented_as_a_heatmap(self):
        model = ToyModel()
        with self.assertLogs("jingwei", level="ERROR"):
            result = attribution.build_attribution(model, self.tensor, self.crop, "cfp", "cpu", self.baseline(model, "cfp") + 1)
        self.assertEqual(result["status"], "unavailable")

    def test_bad_alignment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "aligned"):
            attribution.render_maps(np.ones((10, 10), dtype=np.float32), self.crop, False)

    def test_optional_heatmap_skips_attribution_and_preserves_prediction(self):
        engine = InferenceEngine()
        stream = io.BytesIO()
        self.crop.save(stream, format="PNG")
        encoded = base64.b64encode(stream.getvalue()).decode()
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / "test.pth"
            checkpoint.write_bytes(b"test")
            loaded = {"model": ToyModel(), "path": checkpoint, "fingerprint": _fingerprint(checkpoint),
                      "signature": "test", "device": "cpu"}
            with patch.object(engine, "_load", return_value=loaded), patch("inference.build_attribution", wraps=attribution.build_attribution) as build:
                default = engine.predict("cfp", encoded, str(checkpoint), "cpu")
                disabled = engine.predict("cfp", encoded, str(checkpoint), "cpu", include_heatmap=False)
                build.assert_not_called()
                self.assertEqual(default["attribution"], {"status": "disabled"})
                self.assertEqual(disabled["attribution"], {"status": "disabled"})
                enabled = engine.predict("cfp", encoded, str(checkpoint), "cpu", include_heatmap=True)
                build.assert_called_once()
                self.assertEqual(enabled["attribution"]["status"], "ready")
        for result in (default, disabled):
            for field in ("score", "probability", "positive", "threshold", "image", "model"):
                self.assertEqual(result[field], enabled[field])
        self.assertEqual(png_pixels(disabled["image"]["input_preview"]).shape, (224, 224, 3))

    def test_heatmap_failure_keeps_valid_prediction(self):
        model = ToyModel()
        engine = InferenceEngine()
        stream = io.BytesIO()
        self.crop.save(stream, format="PNG")
        encoded = base64.b64encode(stream.getvalue()).decode()
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / "test.pth"
            checkpoint.write_bytes(b"test")
            loaded = {"model": model, "path": checkpoint, "fingerprint": _fingerprint(checkpoint),
                      "signature": "test", "device": "cpu"}
            with patch.object(engine, "_load", return_value=loaded), patch.object(attribution, "architecture_core", side_effect=RuntimeError("test attribution failure")), self.assertLogs("jingwei", level="ERROR"):
                result = engine.predict("cfp", encoded, str(checkpoint), "cpu", include_heatmap=True)
        self.assertTrue(np.isfinite(result["score"]))
        self.assertTrue(0 <= result["probability"] <= 1)
        self.assertEqual(result["positive"], result["score"] >= 0)
        self.assertEqual(result["attribution"]["status"], "unavailable")
        np.testing.assert_array_equal(png_pixels(result["image"]["input_preview"]),
                                      np.asarray(self.crop.resize((256, 256), Image.Resampling.BICUBIC).crop((16, 16, 240, 240))))


if __name__ == "__main__":
    unittest.main()
