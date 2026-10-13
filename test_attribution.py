"""Real Captum IG on linear models, plus the optional web attribution contract."""

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

import attribution
from inference import InferenceEngine, _fingerprint


class ToyPatchEmbed(nn.Module):
    grid_size = (2, 2)
    patch_size = (112, 112)


class ToyModel(nn.Module):
    """A linear image readout with an analytically known input gradient."""

    def __init__(self, patch_average=False, positive_margin=True):
        super().__init__()
        self.patch_embed = ToyPatchEmbed()
        self.patch_average = patch_average
        self.head = nn.Linear(2, 2, bias=False)
        with torch.no_grad():
            self.head.weight.copy_(torch.tensor([[1., 0.], [3., 0.]]) if positive_margin
                                   else torch.tensor([[3., 0.], [1., 0.]]))
        self.eval().requires_grad_(False)

    def forward_features(self, images):
        value = images[:, 0].mean(dim=(-2, -1))
        return torch.stack((value, torch.ones_like(value)), dim=-1)[:, None, :]

    def forward(self, images):
        if self.patch_average:
            raise RuntimeError("MAE requires the explicit single-token adapter")
        return self.head(self.forward_features(images)[:, 0, :])


def png_pixels(uri):
    with Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))) as image:
        return np.asarray(image.convert("RGB")).copy()


class AttributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(2)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.previous_threads)

    def setUp(self):
        yy, xx = np.mgrid[:224, :224]
        pixels = np.stack((xx, yy, np.full_like(xx, 120)), axis=-1).astype(np.uint8)
        self.crop = Image.fromarray(pixels)
        self.tensor = torch.from_numpy(pixels.copy()).permute(2, 0, 1).float()[None] / 255
        # Linear fixtures need only two quadrature orders to check exactness and stability.
        self.fast_options = {"ig_steps": 2, "ig_max_steps": 4, "ig_batch_size": 2}
        options = patch.dict(attribution.IG_OPTIONS, self.fast_options)
        options.start()
        self.addCleanup(options.stop)

    def baseline(self, model, modality="cfp", tensor=None):
        with torch.inference_mode():
            forward = attribution.MAEForward(model) if modality == "oct" else model
            return forward(self.tensor if tensor is None else tensor)

    def raw_ig(self, model, tensor=None, **options):
        return attribution.ig_core().integrated_gradients(
            model, self.tensor if tensor is None else tensor, target="margin",
            **{**self.fast_options, **options})

    def test_target_is_positive_logit_margin_not_predicted_class(self):
        logits = torch.tensor([[4., 1.]], requires_grad=True)
        target = attribution.ig_core().LogitMarginTarget()(logits)
        self.assertEqual(target.item(), -3)
        target.backward()
        torch.testing.assert_close(logits.grad, torch.tensor([[-1., 1.]]))

    def test_linear_ig_matches_exact_signed_patch_sums_and_margin_difference(self):
        model = ToyModel()
        core = attribution.ig_core()
        logits, indices, maps, diagnostics = self.raw_ig(model)
        reference = core.attribution_baseline(self.tensor, "blur", 16.)
        # d(logit_1-logit_0)/d(red_pixel) = 2/(224*224).
        exact_pixels = (self.tensor - reference).double()[:, 0] * (2 / (224 * 224))
        exact_native = exact_pixels.reshape(1, 2, 112, 2, 112).sum(dim=(0, 2, 4)).numpy()
        native, pixels = maps[0]
        np.testing.assert_allclose(native, exact_native, rtol=1e-6, atol=1e-9)
        np.testing.assert_allclose(pixels, exact_pixels[0].numpy(), rtol=1e-6, atol=1e-12)
        self.assertTrue((native < 0).any())
        self.assertTrue((native > 0).any())
        self.assertEqual(pixels.shape, (224, 224))
        self.assertEqual(indices.tolist(), [-1])
        self.assertEqual(attribution.TARGET, "rvl_positive_margin")
        score_delta = diagnostics["input_score"][0] - diagnostics["baseline_score"][0]
        self.assertAlmostEqual(float(native.sum()), float(score_delta), places=6)
        self.assertTrue(diagnostics["converged"][0])
        self.assertTrue(diagnostics["map_stability_checked"][0])
        torch.testing.assert_close(logits, self.baseline(model))

    def test_negative_raw_attribution_remains_visible_in_blue(self):
        model = ToyModel(positive_margin=False)
        logits, _, maps, diagnostics = self.raw_ig(model, ig_baseline="mean")
        self.assertLess(float(logits[0, 1] - logits[0, 0]), 0)
        self.assertTrue((maps[0][0] < 0).all())
        self.assertTrue(diagnostics["converged"][0])
        heat, overlay, empty, parameters = attribution.render_maps(maps[0][1], self.crop)
        self.assertFalse(empty)
        self.assertTrue((png_pixels(heat)[..., 2] > png_pixels(heat)[..., 0]).any())
        self.assertFalse(np.array_equal(png_pixels(overlay), np.asarray(self.crop)))
        result = attribution.build_attribution(model, self.tensor, self.crop, "cfp", "cpu", logits)
        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["empty"])
        self.assertTrue((np.asarray(result["native_map"]) < 0).any())
        self.assertTrue((np.asarray(result["raw_pixel_map"]) < 0).any())
        self.assertEqual(result["display"], "signed")

    def test_blur_identity_gives_zero_attribution_without_false_hotspots(self):
        tensor = torch.full_like(self.tensor, .5)
        crop = Image.new("RGB", (224, 224), (128, 128, 128))
        model = ToyModel()
        result = attribution.build_attribution(model, tensor, crop, "cfp", "cpu", self.baseline(model, tensor=tensor))
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["empty"])
        np.testing.assert_array_equal(result["native_map"], np.zeros((2, 2)))
        np.testing.assert_array_equal(result["raw_pixel_map"], np.zeros((224, 224)))
        np.testing.assert_array_equal(png_pixels(result["heatmap"]), np.full((224, 224, 3), 255))
        np.testing.assert_array_equal(png_pixels(result["overlay"]), np.asarray(crop))
        self.assertEqual(result["diagnostics"]["attribution_sum"], 0)

    def test_ig_preserves_model_input_flags_and_repeats(self):
        model = ToyModel()
        model.head.weight.requires_grad_(True)
        model.head.weight.grad = torch.ones_like(model.head.weight)
        tensor = self.tensor.clone().requires_grad_(True)
        tensor.grad = torch.full_like(tensor, 2)
        baseline = self.baseline(model, tensor=tensor)
        before = {name: value.clone() for name, value in model.state_dict().items()}
        first = attribution.build_attribution(model, tensor, self.crop, "cfp", "cpu", baseline)
        second = attribution.build_attribution(model, tensor, self.crop, "cfp", "cpu", baseline)
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["method"], "integrated_gradients")
        self.assertEqual(first["target"], "rvl_positive_margin")
        self.assertEqual(first["display"], "signed")
        self.assertEqual(first["baseline"], "blur")
        self.assertEqual(first["pixel_size"], [224, 224])
        self.assertEqual(first["diagnostic_grid_size"], [2, 2])
        self.assertNotIn("grid_size", first)
        self.assertEqual(first["convergence_scope"], "native_patch")
        self.assertFalse(first["pixel_stability_checked"])
        self.assertEqual(first["heatmap"], second["heatmap"])
        self.assertTrue(model.head.weight.requires_grad)
        torch.testing.assert_close(model.head.weight.grad, torch.ones_like(model.head.weight))
        self.assertTrue(tensor.requires_grad)
        torch.testing.assert_close(tensor, self.tensor, rtol=0, atol=0)
        torch.testing.assert_close(tensor.grad, torch.full_like(tensor, 2))
        torch.testing.assert_close(self.baseline(model), baseline, rtol=0, atol=0)
        for layer in model.modules():
            self.assertFalse(layer._forward_hooks)
        for name, value in model.state_dict().items():
            torch.testing.assert_close(value, before[name], rtol=0, atol=0)

    def test_mae_explicit_forward_accepts_an_inference_tensor(self):
        model = ToyModel(patch_average=True)
        baseline = self.baseline(model, "oct")
        with torch.inference_mode():
            inference_tensor = self.tensor.clone()
        result = attribution.build_attribution(model, inference_tensor, self.crop, "oct", "cpu", baseline)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["method"], "integrated_gradients")
        self.assertFalse(result["empty"])
        np.testing.assert_array_equal(png_pixels(result["input_preview"]), np.asarray(self.crop))
        self.assertEqual(png_pixels(result["heatmap"]).shape, (224, 224, 3))
        self.assertEqual(png_pixels(result["overlay"]).shape, (224, 224, 3))
        torch.testing.assert_close(self.baseline(model, "oct"), baseline, rtol=0, atol=0)

    def test_pixel_rendering_smooths_signed_ig_and_keeps_raw_values_and_background(self):
        import cv2

        pixels = np.tile(np.linspace(-1, 1, 224), (224, 1))
        pixels[112, 111:113] = [-100., 100.]
        before = pixels.copy()
        background = np.asarray(self.crop).copy()
        heat, overlay, empty, parameters = attribution.render_maps(pixels, self.crop)
        heat, overlay = png_pixels(heat), png_pixels(overlay)
        self.assertFalse(empty)
        limit = np.percentile(np.abs(pixels), 99)
        smoothed = cv2.GaussianBlur(pixels, (0, 0), sigmaX=1., sigmaY=1.,
                                   borderType=cv2.BORDER_REFLECT_101)
        expected = attribution.ig_core().signed_overlay(
            background.astype(np.float32) / 255, np.clip(smoothed / limit, -1, 1), .5)
        np.testing.assert_array_equal(overlay, expected)
        np.testing.assert_array_equal(pixels, before)
        np.testing.assert_array_equal(np.asarray(self.crop), background)
        self.assertTrue((heat[..., 2] > heat[..., 0]).any())
        self.assertTrue((heat[..., 0] > heat[..., 2]).any())
        self.assertEqual(parameters["symmetric_limit"], limit)
        self.assertEqual(parameters["scale_source"], "raw_abs_p99")
        self.assertEqual(parameters["smoothing_sigma"], 1.)
        self.assertEqual(parameters["max_opacity"], .5)
        self.assertFalse(parameters["background_smoothing"])
        self.assertFalse(parameters["background_brightness_adjustment"])

    def test_nonzero_constant_maps_are_not_empty(self):
        for value in (-4., 4.):
            with self.subTest(value=value):
                heat, overlay, empty, _ = attribution.render_maps(np.full((224, 224), value), self.crop)
                self.assertFalse(empty)
                self.assertFalse(np.array_equal(png_pixels(overlay), np.asarray(self.crop)))
                expected_color = [0, 0, 255] if value < 0 else [255, 0, 0]
                np.testing.assert_array_equal(png_pixels(heat)[0, 0], expected_color)

    def test_sparse_nonzero_map_uses_explicit_maximum_fallback_when_p99_is_zero(self):
        pixels = np.zeros((224, 224))
        pixels[112, 112] = -2.
        _, overlay, empty, parameters = attribution.render_maps(pixels, self.crop)
        self.assertFalse(empty)
        self.assertEqual(parameters["raw_abs_p99"], 0)
        self.assertEqual(parameters["symmetric_limit"], 2.)
        self.assertEqual(parameters["scale_source"], "raw_abs_max_fallback")
        self.assertFalse(np.array_equal(png_pixels(overlay), np.asarray(self.crop)))

    def test_bad_alignment_empty_and_nonfinite_maps_are_rejected(self):
        for values in (np.ones((2, 2)), np.full((224, 224), np.nan), np.empty((0, 0)), np.ones(2)):
            with self.subTest(shape=values.shape), self.assertRaises(ValueError):
                attribution.render_maps(values, self.crop)

    def test_gradient_failure_restores_parameters_and_suppresses_map(self):
        model = ToyModel()
        model.head.weight.requires_grad_(True)
        original = model.forward

        def fail_with_grad(images):
            if torch.is_grad_enabled():
                raise RuntimeError("test gradient failure")
            return original(images)

        with patch.object(model, "forward", side_effect=fail_with_grad), self.assertLogs("jingwei", level="ERROR"):
            result = attribution.build_attribution(model, self.tensor, self.crop, "cfp", "cpu", self.baseline(model))
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("heatmap", result)
        self.assertNotIn("overlay", result)
        self.assertTrue(model.head.weight.requires_grad)
        self.assertIsNone(model.head.weight.grad)

    def test_mismatched_gradient_logits_are_not_presented_as_a_heatmap(self):
        model = ToyModel()
        with self.assertLogs("jingwei", level="ERROR"):
            result = attribution.build_attribution(model, self.tensor, self.crop, "cfp", "cpu", self.baseline(model) + 1)
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("heatmap", result)

    def test_unconverged_standard_ig_uses_real_adaptive_refinement(self):
        model = ToyModel()
        core = attribution.ig_core()
        raw = self.raw_ig(model)
        raw[3]["converged"][:] = False
        adaptive = core.adaptive_margin_integrated_gradients

        def inexpensive_refinement(*args, **kwargs):
            return adaptive(*args, **kwargs, initial_order=2, high_order=4)

        phases = []
        with patch.object(core, "integrated_gradients", return_value=raw), patch.object(
                core, "adaptive_margin_integrated_gradients", side_effect=inexpensive_refinement) as refine:
            result = attribution.build_attribution(model, self.tensor, self.crop, "cfp", "cpu", self.baseline(model),
                                                   on_phase=phases.append)
        refine.assert_called_once()
        self.assertEqual(phases, ["refining"])
        self.assertEqual(refine.call_args.kwargs["max_evaluations"], attribution.REFINEMENT_MAX_EVALUATIONS)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["diagnostics"]["converged"])
        self.assertIn("gradient_evaluations", result["diagnostics"])
        np.testing.assert_allclose(result["raw_pixel_map"], raw[2][0][1], rtol=1e-4, atol=1e-9)

    def test_adaptive_pixel_map_sums_final_leaves_after_refinement(self):
        class PiecewiseModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.patch_embed = ToyPatchEmbed()
                self.patch_embed.patch_size = (2, 2)
                self.register_buffer("weights", torch.tensor([[1., 1., -.5, -.5]]).repeat(4, 1))

            def forward(self, images):
                score = (torch.relu(images[:, 0] - .413) * self.weights).sum(dim=(-2, -1))
                return torch.stack((torch.zeros_like(score), score), dim=1)

        model = PiecewiseModel().eval()
        _, _, maps, diagnostics = attribution.ig_core().adaptive_margin_integrated_gradients(
            model, torch.ones(1, 3, 4, 4), ig_baseline="mean", ig_batch_size=2,
            initial_order=2, high_order=4, ig_rtol=1e-5, ig_atol=1e-5,
            max_evaluations=1024)
        self.assertTrue(diagnostics["converged"][0])
        self.assertGreater(diagnostics["integration_intervals"][0], 8)
        self.assertGreater(diagnostics["max_depth_reached"][0], 0)
        native, pixels = maps[0]
        expected = model.weights.numpy() * (1 - .413)
        np.testing.assert_allclose(pixels, expected, rtol=2e-5, atol=1e-5)
        np.testing.assert_allclose(native, pixels.reshape(2, 2, 2, 2).sum(axis=(1, 3)), rtol=0, atol=1e-12)
        self.assertTrue((pixels < 0).any())
        self.assertTrue((pixels > 0).any())

    def test_unconverged_refinement_never_presents_a_heatmap(self):
        model = ToyModel()
        core = attribution.ig_core()
        raw = self.raw_ig(model)
        raw[3]["converged"][:] = False
        with patch.object(core, "integrated_gradients", return_value=raw), patch.object(
                core, "adaptive_margin_integrated_gradients", return_value=raw), self.assertLogs("jingwei", level="WARNING"):
            result = attribution.build_attribution(model, self.tensor, self.crop, "cfp", "cpu", self.baseline(model))
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("heatmap", result)
        self.assertNotIn("overlay", result)

    def engine_fixture(self, folder):
        engine = InferenceEngine()
        stream = io.BytesIO()
        self.crop.save(stream, format="PNG")
        checkpoint = Path(folder) / "test.pth"
        checkpoint.write_bytes(b"test")
        loaded = {"model": ToyModel(), "path": checkpoint, "fingerprint": _fingerprint(checkpoint),
                  "signature": "test", "device": "cpu"}
        return engine, base64.b64encode(stream.getvalue()).decode(), checkpoint, loaded

    def test_optional_heatmap_skips_attribution_and_preserves_prediction(self):
        with tempfile.TemporaryDirectory() as folder:
            engine, encoded, checkpoint, loaded = self.engine_fixture(folder)
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
        with tempfile.TemporaryDirectory() as folder:
            engine, encoded, checkpoint, loaded = self.engine_fixture(folder)
            with patch.object(engine, "_load", return_value=loaded), patch.object(attribution, "ig_core", side_effect=RuntimeError("test attribution failure")), self.assertLogs("jingwei", level="ERROR"):
                result = engine.predict("cfp", encoded, str(checkpoint), "cpu", include_heatmap=True)
        self.assertTrue(np.isfinite(result["score"]))
        self.assertTrue(0 <= result["probability"] <= 1)
        self.assertEqual(result["positive"], result["score"] >= 0)
        self.assertEqual(result["attribution"]["status"], "unavailable")
        np.testing.assert_array_equal(png_pixels(result["image"]["input_preview"]),
                                      np.asarray(self.crop.resize((256, 256), Image.Resampling.BICUBIC).crop((16, 16, 240, 240))))


if __name__ == "__main__":
    unittest.main()
