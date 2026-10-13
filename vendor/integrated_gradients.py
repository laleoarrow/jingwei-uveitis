"""IG extracted from BDRV generate_ig_heatmaps.py (1248f82).

See NOTICE.md for source fingerprint, CPU transports and pixel-map extension.
No dependency on the BDRV checkout is required at runtime.
"""
from __future__ import annotations

from contextlib import contextmanager
import math

import numpy as np
import torch


def signed_overlay(rgb: np.ndarray, signed_mask: np.ndarray, image_weight: float) -> np.ndarray:
    """Blend red positive and blue negative evidence with zero transparent.

    The input map shares one maximum absolute scale for both signs. Its opacity
    scales with attribution magnitude. Use the raw native maps for quantitative
    comparison, since per-image display normalization changes magnitudes.
    """
    rgb = np.asarray(rgb, dtype=np.float32)
    signed_mask = np.asarray(signed_mask, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[-1] != 3 or signed_mask.shape != rgb.shape[:2]:
        raise ValueError("Signed display requires an RGB image and a matching 2D map")
    if not np.isfinite(rgb).all() or not np.isfinite(signed_mask).all():
        raise ValueError("Non-finite signed overlay input")
    if not 0 <= image_weight <= 1 or np.any(np.abs(signed_mask) > 1 + 1e-6):
        raise ValueError("Signed overlay expects image_weight in [0,1] and map in [-1,1]")
    colors = np.zeros_like(rgb)
    colors[..., 0] = signed_mask > 0
    colors[..., 2] = signed_mask < 0
    opacity = (1 - image_weight) * np.abs(signed_mask)[..., None]
    overlay = rgb * (1 - opacity) + colors * opacity
    return np.rint(np.clip(overlay, 0, 1) * 255).astype(np.uint8)


def pixel_ig_display(rgb: np.ndarray, raw_pixel_ig: np.ndarray):
    """Render signed pixel IG with sigma-1 smoothing and the raw absolute P99.

    Return uint8 ``(heatmap, overlay, display_parameters)``. Smoothing and
    saturation are display-only; neither the source IG nor RGB is modified.
    A nonzero sparse map whose P99 is zero uses its maximum absolute value.
    """
    import cv2
    from matplotlib import colormaps
    from matplotlib.colors import Normalize

    rgb = np.asarray(rgb, dtype=np.float32)
    raw = np.asarray(raw_pixel_ig, dtype=np.float64)
    if (rgb.ndim != 3 or rgb.shape[-1] != 3 or raw.ndim != 2 or not raw.size
            or raw.shape != rgb.shape[:2] or not np.isfinite(raw).all()
            or not np.isfinite(rgb).all() or np.any((rgb < 0) | (rgb > 1))):
        raise ValueError('Pixel IG must be finite and aligned with the RGB model input')
    percentile = float(np.percentile(np.abs(raw), 99))
    maximum = float(np.abs(raw).max())
    fallback = percentile == 0 and maximum > 0
    limit = maximum if fallback else percentile
    smoothed = cv2.GaussianBlur(raw, (0, 0), sigmaX=1., sigmaY=1.,
                                borderType=cv2.BORDER_REFLECT_101)
    mask = np.clip(smoothed / limit, -1, 1).astype(np.float32) if limit else np.zeros_like(raw, dtype=np.float32)
    heat = (np.rint(colormaps['bwr'](Normalize(-limit, limit, clip=True)(smoothed))[..., :3] * 255).astype(np.uint8)
            if limit else np.full(rgb.shape, 255, dtype=np.uint8))
    overlay = signed_overlay(rgb, mask, .5)
    parameters = dict(smoothing_sigma=1., smoothing_unit='model_input_pixel',
                      smoothing_border='BORDER_REFLECT_101', smoothing_applied_to='signed_pixel_ig',
                      percentile=99, raw_abs_p99=percentile, symmetric_limit=limit,
                      scale_source='raw_abs_max_fallback' if fallback else 'raw_abs_p99',
                      colormap='bwr', max_opacity=.5, gamma=1.,
                      background_smoothing=False, background_brightness_adjustment=False,
                      raw_values_modified=False)
    return heat, overlay, parameters


IG_DEFAULTS = dict(ig_steps=32, ig_max_steps=256, ig_batch_size=4,
                   ig_baseline='blur', ig_blur_sigma=16.0,
                   ig_rtol=0.01, ig_atol=1e-4)


@contextmanager
def frozen_parameters(model):
    """Avoid parameter-gradient allocation and restore every original flag."""
    parameters = list(model.parameters())
    flags = [parameter.requires_grad for parameter in parameters]
    try:
        for parameter in parameters:
            parameter.requires_grad_(False)
        yield
    finally:
        for parameter, flag in zip(parameters, flags):
            parameter.requires_grad_(flag)


def attribution_baseline(images: torch.Tensor, kind='blur', blur_sigma=16.0):
    """A detached reference in the same ImageNet-normalized input coordinates."""
    if kind == 'mean':
        return torch.zeros_like(images)
    if kind != 'blur':
        raise ValueError(f'Unknown IG reference: {kind}')
    if not math.isfinite(blur_sigma) or blur_sigma <= 0:
        raise ValueError('IG blur sigma must be finite and positive')
    # Reflection padding avoids a dark artificial border. Normalization is
    # affine, so blurring normalized RGB equals normalizing blurred RGB.
    from torchvision.transforms.functional import gaussian_blur
    radius = min(int(math.ceil(3 * blur_sigma)), min(images.shape[-2:]) - 1)
    if radius < 1:
        raise ValueError('A blurred reference needs image dimensions >= 2')
    reference = gaussian_blur(images.detach(), 2 * radius + 1, blur_sigma)
    # A constant channel is exactly unchanged by Gaussian blur. Enforce that
    # identity: convolution rounding otherwise creates tiny artificial IG that
    # per-image normalization can amplify to full-strength hotspots.
    constant = images.amin(dim=(-2, -1), keepdim=True) == images.amax(dim=(-2, -1), keepdim=True)
    return torch.where(constant, images.detach(), reference).detach()


def _patch_grid(model_or_wrapper, images):
    model = getattr(model_or_wrapper, 'model', model_or_wrapper)
    grid = tuple(int(v) for v in model.patch_embed.grid_size)
    patch = tuple(int(v) for v in model.patch_embed.patch_size)
    if len(grid) != 2 or len(patch) != 2 or tuple(images.shape[-2:]) != tuple(
        g * p for g, p in zip(grid, patch)
    ):
        raise ValueError('IG requires a fixed, non-overlapping native patch grid')
    projection = getattr(model.patch_embed, 'proj', None)
    if isinstance(projection, torch.nn.Conv2d) and (
        tuple(projection.kernel_size) != patch or tuple(projection.stride) != patch
        or tuple(projection.padding) != (0, 0) or tuple(projection.dilation) != (1, 1)
    ):
        raise ValueError('IG patch aggregation requires non-overlapping patch embedding')
    return grid, patch


def _target_scores(logits, target):
    if logits.ndim != 2 or not torch.isfinite(logits).all():
        raise ValueError('Expected finite [B, classes] logits')
    if isinstance(target, str) and target == 'margin':
        return LogitMarginTarget()(logits), torch.full(
            (len(logits),), -1, dtype=torch.long, device=logits.device
        )
    indices = target_indices(logits, target)
    return logits.gather(1, indices[:, None])[:, 0], indices


def _integrate_one(model, image, baseline, target, steps, internal_batch_size):
    from captum.attr import IntegratedGradients

    def forward(inputs):
        scores, _ = _target_scores(model(inputs), target)
        # A disconnected constant output has exactly zero input attribution.
        return scores + inputs.flatten(1)[:, 0] * 0

    attribution = IntegratedGradients(forward).attribute(
        image, baselines=baseline, n_steps=steps, method='gausslegendre',
        internal_batch_size=internal_batch_size,
    )
    if not torch.isfinite(attribution).all():
        raise ValueError('Non-finite Integrated Gradients attribution')
    # Promote only the subsequent patch sums; Captum uses the input dtype and
    # float32 quadrature weights, so this is not double-precision integration.
    # MPS has no float64: transfer before the unchanged double-precision sums.
    return attribution.detach().cpu().double()


@torch.enable_grad()
def integrated_gradients(model, images, target='margin', **options):
    """Return signed native patch and raw pixel IG, with native-grid diagnostics.

    Each maps item is ``(native_patch_ig, raw_pixel_ig)``; the latter sums only
    channels, without spatial pooling, resizing or smoothing. Convergence and
    map-stability checks concern the native patch grid, not individual pixels.

    Parameters remain frozen only during this call. Input targets are fixed at
    the endpoint, including ``predicted``; they never switch along the path.
    Integration batches bound the number of simultaneous ViT graphs regardless
    of the external image batch. Raw values are never rescaled to force closure.
    """
    if model.training:
        raise ValueError('Explanations require model.eval()')
    unknown = set(options) - set(IG_DEFAULTS)
    if unknown:
        raise ValueError(f'Unknown IG options: {sorted(unknown)}')
    settings = {**IG_DEFAULTS, **options}
    steps, maximum = settings['ig_steps'], settings['ig_max_steps']
    internal_batch = settings['ig_batch_size']
    if any(not isinstance(v, int) or isinstance(v, bool) for v in (steps, maximum, internal_batch)):
        raise ValueError('IG integration steps and batch size must be integers')
    if steps < 2 or maximum < steps or internal_batch < 1:
        raise ValueError('IG requires max_steps >= steps >= 2 and batch_size >= 1')
    rtol, atol = settings['ig_rtol'], settings['ig_atol']
    if any(not math.isfinite(v) or v < 0 for v in (rtol, atol)):
        raise ValueError('IG error tolerances must be finite and nonnegative')
    images = images.detach()
    if images.ndim != 4 or len(images) == 0 or not images.is_floating_point() or not torch.isfinite(images).all():
        raise ValueError('IG expects a nonempty, finite floating [B,C,H,W] input')
    grid, patch = _patch_grid(model, images)
    baseline = attribution_baseline(images, settings['ig_baseline'], settings['ig_blur_sigma'])
    maps, diagnostics = [], {key: [] for key in (
        'baseline_logits', 'baseline_score', 'input_score', 'attribution_sum',
        'completeness_error', 'completeness_relative_error', 'converged', 'steps_used',
        'map_relative_change', 'map_stability_checked'
    )}
    with frozen_parameters(model):
        with torch.no_grad():
            logits = model(images)
            scores, indices = _target_scores(logits, target)
            baseline_logits = model(baseline)
            fixed_target = 'margin' if isinstance(target, str) and target == 'margin' else indices
            baseline_scores, _ = _target_scores(baseline_logits, fixed_target)
        for row in range(len(images)):
            row_target = 'margin' if isinstance(fixed_target, str) else str(int(indices[row]))
            score_delta = float(scores[row].cpu().double() - baseline_scores[row].cpu().double())
            current_steps = steps
            previous_native = None
            while True:
                attribution = _integrate_one(model, images[row:row + 1], baseline[row:row + 1],
                                             row_target, current_steps, internal_batch)
                native = attribution.reshape(1, images.shape[1], grid[0], patch[0],
                                             grid[1], patch[1]).sum(dim=(1, 3, 5))[0]
                attribution_sum = float(native.sum())
                error = attribution_sum - score_delta
                # Closure alone can hide cancelling integration errors. Adaptive
                # runs also compare successive signed native maps before stopping.
                checked = previous_native is not None
                map_change = (float((native - previous_native).abs().sum()) /
                              max(float(native.abs().sum()), float(previous_native.abs().sum()),
                                  np.finfo(np.float64).tiny)) if checked else 0.0
                stable = map_change <= rtol if checked else maximum == steps
                converged = abs(error) <= atol + rtol * abs(score_delta) and stable
                if converged or current_steps >= maximum:
                    break
                previous_native = native
                current_steps = min(current_steps * 2, maximum)
            pixels = attribution.sum(dim=1)[0]
            maps.append((native.cpu().numpy(), pixels.cpu().numpy()))
            values = dict(baseline_logits=baseline_logits[row].cpu().numpy(),
                          baseline_score=float(baseline_scores[row]), input_score=float(scores[row]),
                          attribution_sum=attribution_sum, completeness_error=error,
                          completeness_relative_error=abs(error) / max(abs(score_delta), np.finfo(np.float32).tiny),
                          converged=converged, steps_used=current_steps,
                          map_relative_change=map_change, map_stability_checked=checked)
            for key, value in values.items():
                diagnostics[key].append(value)
    return logits.detach().cpu(), indices.detach().cpu(), maps, {
        key: np.asarray(value) for key, value in diagnostics.items()
    }


class LogitMarginTarget:
    """Explain the binary logit margin, without a softmax or class switching."""

    def __call__(self, logits):
        if logits.shape[-1] != 2:
            raise ValueError("Logit margin requires exactly two model outputs")
        return logits[..., 1] - logits[..., 0]


def target_indices(logits: torch.Tensor, target: str | torch.Tensor) -> torch.Tensor:
    if logits.ndim != 2 or not torch.isfinite(logits).all():
        raise ValueError("Expected finite [B, classes] logits")
    if isinstance(target, torch.Tensor):
        if target.shape != (logits.shape[0],) or target.dtype != torch.long:
            raise ValueError("Per-image targets must be a long tensor of shape [B]")
        indices = target.to(logits.device)
        if ((indices < 0) | (indices >= logits.shape[1])).any():
            raise ValueError("Target class outside model output range")
        return indices
    if target == "predicted":
        return logits.argmax(dim=1)
    index = int(target)
    if not 0 <= index < logits.shape[1]:
        raise ValueError(f"Target class {index} is outside [0, {logits.shape[1]})")
    return torch.full(
        (logits.shape[0],), index, dtype=torch.long, device=logits.device
    )


@contextmanager
def _fp32_backend():
    previous = (torch.backends.cuda.matmul.allow_tf32,
                torch.backends.cudnn.allow_tf32, torch.backends.cudnn.benchmark)
    try:
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        yield
    finally:
        (torch.backends.cuda.matmul.allow_tf32,
         torch.backends.cudnn.allow_tf32, torch.backends.cudnn.benchmark) = previous


def _scores(model, images):
    logits = model(images)
    scores, _ = _target_scores(logits, "margin")
    return logits, scores


@torch.enable_grad()
def adaptive_margin_integrated_gradients(
    model, images, *, ig_batch_size=4, ig_blur_sigma=16., ig_baseline="blur",
    ig_rtol=.01, ig_atol=1e-4, initial_order=16, high_order=32,
    max_evaluations=8192, max_depth=18,
):
    """Return native-patch and raw pixel margin IG from an adaptive partition.

    The return tuple is ``(logits_cpu, margin_indices, maps, diagnostics)``.
    Each maps item is ``(native_patch_ig, raw_pixel_ig)``. Pixel IG sums the
    high-order channel sums from all final retained leaves, never a last call
    or an interpolated patch map. Convergence checks remain native-grid checks.
    ``steps_used`` counts retained high-order nodes; ``gradient_evaluations``
    includes both orders and discarded parent intervals. The latter never
    exceeds ``max_evaluations``. A spent budget/depth limit preserves the measured
    errors and returns ``converged=False``; raw vectors are never rescaled.

    Global stopping requires the sum of absolute local closure errors within
    ``atol + rtol * abs(input_margin - reference_margin)`` and the sum of native
    high/low-order L1 differences within ``rtol * L1(total_native)``. Cached
    midpoint scores also detect observed turning excursions hidden by equal
    endpoints. TF32/backend settings and every parameter flag are restored.
    """
    if model.training:
        raise ValueError("Explanations require model.eval()")
    integers = (ig_batch_size, initial_order, high_order, max_evaluations, max_depth)
    if any(not isinstance(value, int) or isinstance(value, bool) for value in integers):
        raise ValueError("Quadrature orders, budgets, depth and batch size must be integers")
    if ig_batch_size < 1 or initial_order < 2 or high_order <= initial_order or max_depth < 0:
        raise ValueError("Require batch_size >= 1, high_order > initial_order >= 2 and depth >= 0")
    pair_cost = initial_order + high_order
    if max_evaluations < pair_cost:
        raise ValueError("The evaluation budget must cover at least one high/low-order pair")
    if any(not math.isfinite(value) or value < 0 for value in (ig_rtol, ig_atol)):
        raise ValueError("Error tolerances must be finite and nonnegative")
    images = images.detach()
    if (images.ndim != 4 or len(images) == 0 or not images.is_floating_point()
            or not torch.isfinite(images).all()):
        raise ValueError("Expected nonempty, finite floating [B,C,H,W] input")
    grid, patch = _patch_grid(model, images)
    fields = (
        "baseline_logits", "baseline_score", "input_score", "attribution_sum",
        "completeness_error", "completeness_relative_error", "converged", "steps_used",
        "map_relative_change", "map_stability_checked", "gradient_evaluations",
        "integration_intervals", "local_closure_error_bound", "vector_error_bound",
        "midpoint_excursion_bound", "endpoint_evaluations", "max_depth_reached",
        "evaluation_budget_exhausted", "depth_limit_exhausted",
    )
    diagnostics = {name: [] for name in fields}
    maps = []
    tiny = np.finfo(np.float64).tiny

    with _fp32_backend(), frozen_parameters(model):
        baseline = attribution_baseline(images, ig_baseline, ig_blur_sigma)
        with torch.no_grad():
            logits, input_scores = _scores(model, images)
            baseline_logits, baseline_scores = _scores(model, baseline)
        for row in range(len(images)):
            image, reference = images[row:row + 1], baseline[row:row + 1]
            difference = image - reference
            input_score = float(input_scores[row])
            baseline_score = float(baseline_scores[row])
            score_delta = input_score - baseline_score
            closure_budget = ig_atol + ig_rtol * abs(score_delta)
            # The exact mathematical endpoints are the original input and
            # reference. Interior endpoints use the same straight input path
            # as the quadrature; shared boundary values are evaluated once.
            score_cache = {0.: baseline_score, 1.: input_score}
            evaluations = 0

            def endpoint(alpha):
                if alpha not in score_cache:
                    with torch.no_grad():
                        _, value = _scores(model, reference + image.new_tensor(alpha) * difference)
                    score_cache[alpha] = float(value[0])
                return score_cache[alpha]

            def integral(left, right, order):
                nonlocal evaluations
                start = reference if left == 0. else reference + left * difference
                end = image if right == 1. else reference + right * difference
                # Captum already multiplies by end - start; summing segment
                # attributions must not multiply by the segment width again.
                attribution = _integrate_one(model, end, start, 'margin', order, ig_batch_size)
                evaluations += order
                native = attribution.reshape(1, image.shape[1], grid[0], patch[0],
                                              grid[1], patch[1]).sum(dim=(1, 3, 5))[0]
                return native, attribution.sum(dim=1)[0]

            def interval(left, right, depth):
                low, _ = integral(left, right, initial_order)
                high, high_pixels = integral(left, right, high_order)
                first, last = endpoint(left), endpoint(right)
                middle_score = endpoint((left + right) / 2)
                delta = last - first
                signed_sum = float(high.sum())
                closure = signed_sum - delta
                # A midpoint outside the endpoint range reveals an observed
                # turning feature, even if its net endpoint difference is zero.
                excursion = max(0., abs(middle_score - first) + abs(last - middle_score) - abs(delta))
                return dict(left=left, right=right, depth=depth, high=high, high_pixels=high_pixels,
                            endpoint_delta=delta, signed_sum=signed_sum, closure_error=closure,
                            vector_error=float((high - low).abs().sum()),
                            midpoint_score=middle_score, midpoint_excursion=excursion)

            # A generic initial partition; no patient-specific alpha values.
            count = min(8, max_evaluations // pair_cost)
            edges = np.linspace(0., 1., count + 1).tolist()
            leaves = [interval(left, right, 0) for left, right in zip(edges, edges[1:])]
            budget_exhausted = depth_exhausted = False
            while True:
                native = torch.stack([leaf["high"] for leaf in leaves]).sum(0)
                attribution_sum = float(native.sum())
                error = attribution_sum - score_delta
                native_l1 = float(native.abs().sum())
                closure_bound = math.fsum(abs(leaf["closure_error"]) for leaf in leaves)
                vector_bound = math.fsum(leaf["vector_error"] for leaf in leaves)
                excursion_bound = math.fsum(leaf["midpoint_excursion"] for leaf in leaves)
                map_change = vector_bound / max(native_l1, tiny)
                converged = (closure_bound <= closure_budget and abs(error) <= closure_budget
                             and map_change <= ig_rtol and excursion_bound <= closure_budget)
                if converged:
                    break
                candidates = [leaf for leaf in leaves if leaf["depth"] < max_depth]
                if not candidates:
                    depth_exhausted = True
                    break
                if evaluations + 2 * pair_cost > max_evaluations:
                    budget_exhausted = True
                    break
                vector_budget = ig_rtol * native_l1

                def priority(leaf):
                    return max(abs(leaf["closure_error"]) / max(closure_budget, tiny),
                               leaf["vector_error"] / max(vector_budget, tiny),
                               leaf["midpoint_excursion"] / max(closure_budget, tiny))

                worst = max(candidates, key=priority)
                middle = (worst["left"] + worst["right"]) / 2
                depth = worst["depth"] + 1
                children = (interval(worst["left"], middle, depth),
                            interval(middle, worst["right"], depth))
                leaves = [leaf for leaf in leaves if leaf is not worst] + list(children)
            leaves.sort(key=lambda leaf: leaf["left"])
            pixels = torch.stack([leaf['high_pixels'] for leaf in leaves]).sum(0)
            maps.append((native.cpu().numpy(), pixels.cpu().numpy()))
            values = dict(
                baseline_logits=baseline_logits[row].detach().cpu().numpy(),
                baseline_score=baseline_score, input_score=input_score,
                attribution_sum=attribution_sum, completeness_error=error,
                completeness_relative_error=abs(error) / max(abs(score_delta), tiny),
                converged=converged, steps_used=high_order * len(leaves),
                map_relative_change=map_change, map_stability_checked=True,
                gradient_evaluations=evaluations, integration_intervals=len(leaves),
                local_closure_error_bound=closure_bound, vector_error_bound=vector_bound,
                midpoint_excursion_bound=excursion_bound,
                endpoint_evaluations=len(score_cache) - 2,
                max_depth_reached=max(leaf["depth"] for leaf in leaves),
                evaluation_budget_exhausted=budget_exhausted, depth_limit_exhausted=depth_exhausted,
            )
            for name, value in values.items():
                diagnostics[name].append(value)
    return (logits.detach().cpu(), torch.full((len(images),), -1, dtype=torch.long),
            maps, {name: np.asarray(values) for name, values in diagnostics.items()})
