"""Frozen architecture attribution core; provenance is recorded in NOTICE.md."""
from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import torch
import torch.nn.functional as F


class LogitMarginTarget:
    """Explain the binary logit margin, without a softmax or class switching."""

    def __call__(self, logits):
        if logits.shape[-1] != 2:
            raise ValueError("Logit margin requires exactly two model outputs")
        return logits[..., 1] - logits[..., 0]


class TokenHook:
    """Retain a target layer's token activations and their output gradients."""

    def __init__(self, layer: torch.nn.Module):
        self.activation: torch.Tensor | None = None
        self.gradient: torch.Tensor | None = None
        self.handle = layer.register_forward_hook(self._forward_hook)

    def _forward_hook(self, _module, _inputs, output):
        if not isinstance(output, torch.Tensor):
            raise TypeError(f"Expected tensor target-layer output, got {type(output)!r}")
        self.activation = output
        self.gradient = None
        output.register_hook(self._gradient_hook)

    def _gradient_hook(self, gradient):
        self.gradient = gradient

    def close(self):
        self.handle.remove()
        self.activation = None
        self.gradient = None


class AttentionHook(TokenHook):
    """Capture attention probabilities; restore the attention backend on close."""

    def __init__(self, attention):
        self.attention = attention
        self.original_fused_attn = attention.fused_attn
        super().__init__(attention.attn_drop)
        attention.fused_attn = False

    def close(self):
        super().close()
        self.attention.fused_attn = self.original_fused_attn


def attention_hooks(model_or_wrapper) -> list[AttentionHook]:
    model = getattr(model_or_wrapper, "model", model_or_wrapper)
    hooks = []
    try:
        for block in model.blocks:
            hooks.append(AttentionHook(block.attn))
    except Exception:
        for hook in hooks:
            hook.close()
        raise
    return hooks


def uses_patch_average_pool(model) -> bool:
    model = getattr(model, "model", model)
    if bool(getattr(model, "ret_global_pool", False)):
        return True
    # The single-modality RETFound MAE subclass stores a boolean here. timm's
    # DINOv2 model instead stores the string "token".
    pool = getattr(model, "global_pool", None)
    return pool is True or pool == "avg"


def grad_attention_rollout(
    hooks: list[AttentionHook],
    model_or_wrapper,
    output_size: tuple[int, int],
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Propagate positive, class-conditioned attention through all blocks."""
    model = getattr(model_or_wrapper, "model", model_or_wrapper)
    if not hooks:
        raise ValueError("Gradient attention rollout needs at least one block")
    first = hooks[0].activation
    if first is None:
        raise RuntimeError("Attention hooks did not receive activations")
    batch, _heads, token_count, _ = first.shape
    identity = torch.eye(token_count, device=first.device, dtype=torch.float32)
    identity = identity.unsqueeze(0).expand(batch, -1, -1)
    rollout = identity

    for hook in hooks:
        if hook.activation is None or hook.gradient is None:
            raise RuntimeError("Attention hook did not receive activations and gradients")
        attention = hook.activation.detach().float()
        gradient = hook.gradient.detach().float()
        if not torch.isfinite(attention).all() or not torch.isfinite(gradient).all():
            raise ValueError("Non-finite attention or gradient")
        transition = (attention * gradient).clamp(min=0).mean(dim=1)
        # Residual connections are represented by the identity path. Row
        # normalization prevents arbitrary scale accumulation over 24 blocks.
        transition = transition + identity
        transition = transition / transition.sum(dim=-1, keepdim=True).clamp_min(1e-12)
        rollout = torch.bmm(transition, rollout)

    prefix = int(getattr(model, "num_prefix_tokens", 1))
    if uses_patch_average_pool(model):
        # RETFound MAE averages every final patch token before fc_norm/head.
        relevance = rollout[:, prefix:, prefix:].mean(dim=1)
    else:
        # DINOv2 classification is read from the final CLS token.
        relevance = rollout[:, 0, prefix:]

    grid = tuple(int(x) for x in model.patch_embed.grid_size)
    if math.prod(grid) != relevance.shape[1]:
        raise ValueError(
            f"Patch grid {grid} does not match {relevance.shape[1]} rollout tokens"
        )
    low_resolution = relevance.reshape(batch, 1, *grid)
    upsampled = F.interpolate(
        low_resolution, size=output_size, mode="bilinear", align_corners=False
    )[:, 0]
    return [
        (low_resolution[row, 0].cpu().numpy(), upsampled[row].cpu().numpy())
        for row in range(batch)
    ]


def target_layer(model_or_wrapper):
    model = getattr(model_or_wrapper, "model", model_or_wrapper)
    if not hasattr(model, "blocks"):
        raise ValueError(f"Model has no ViT blocks: {type(model)!r}")
    return model.blocks[-1].norm1


def final_patch_layer(model_or_wrapper):
    model = getattr(model_or_wrapper, "model", model_or_wrapper)
    return model.blocks[-1]


def cam_from_tokens(
    hook: TokenHook,
    model_or_wrapper,
    method: str,
    output_size: tuple[int, int],
    positive_only: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    if hook.activation is None or hook.gradient is None:
        raise RuntimeError("CAM hook did not receive activations and gradients")
    model = getattr(model_or_wrapper, "model", model_or_wrapper)
    prefix = int(getattr(model, "num_prefix_tokens", 1))
    activation = hook.activation.detach().float()[:, prefix:, :]
    gradient = hook.gradient.detach().float()[:, prefix:, :]
    if not torch.isfinite(activation).all() or not torch.isfinite(gradient).all():
        raise ValueError("Non-finite token activation or gradient")

    if method == "hirescam":
        token_cam = (activation * gradient).sum(dim=-1)
    elif method == "gradcam":
        channel_weight = gradient.mean(dim=1, keepdim=True)
        token_cam = (activation * channel_weight).sum(dim=-1)
    else:
        raise ValueError(method)
    if positive_only:
        token_cam = token_cam.relu()

    grid = tuple(int(x) for x in model.patch_embed.grid_size)
    if math.prod(grid) != token_cam.shape[1]:
        raise ValueError(
            f"Patch grid {grid} does not match {token_cam.shape[1]} spatial tokens"
        )
    low_resolution = token_cam.reshape(-1, 1, *grid)
    upsampled = F.interpolate(
        low_resolution, size=output_size, mode="bilinear", align_corners=False
    )[:, 0]
    return (
        low_resolution[0, 0].cpu().numpy(),
        upsampled[0].cpu().numpy(),
    )


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


def explain_single_batch(
    model,
    images: torch.Tensor,
    target: str | torch.Tensor,
    method: str,
    positive_only: bool = True,
) -> tuple[torch.Tensor, torch.Tensor, list[tuple[np.ndarray, np.ndarray]]]:
    if model.training:
        raise ValueError("Explanations require model.eval()")
    if method not in {"architecture", "gradrollout", "hirescam", "gradcam"}:
        raise ValueError(f"Unknown explanation method: {method}")
    images = images.detach().requires_grad_(True)
    patch_average = uses_patch_average_pool(model)
    use_rollout = method == "gradrollout" or (
        method == "architecture" and not patch_average
    )
    if use_rollout and not positive_only:
        raise ValueError("Signed attribution is only defined here for token CAMs")
    rollout_hooks = attention_hooks(model) if use_rollout else []
    if rollout_hooks:
        hook = None
    elif method == "architecture":
        hook = TokenHook(final_patch_layer(model))
    else:
        hook = TokenHook(target_layer(model))
    try:
        logits = model(images)
        if isinstance(target, str) and target == "margin":
            scores = LogitMarginTarget()(logits)
            indices = torch.full((len(logits),), -1, dtype=torch.long, device=logits.device)
        else:
            indices = target_indices(logits, target)
            scores = logits.gather(1, indices[:, None])
        if not torch.isfinite(logits).all():
            raise ValueError("Non-finite logits")
        scores.sum().backward()
        if rollout_hooks:
            return (
                logits.detach().cpu(),
                indices.detach().cpu(),
                grad_attention_rollout(
                    rollout_hooks, model, tuple(images.shape[-2:])
                ),
            )
        results = []
        # The hook contains a batch; split it without another forward/backward.
        assert hook is not None
        activation, gradient = hook.activation, hook.gradient
        assert activation is not None and gradient is not None
        for row in range(images.shape[0]):
            row_hook = SimpleNamespace(
                activation=activation[row : row + 1],
                gradient=gradient[row : row + 1],
            )
            token_method = "hirescam" if method == "architecture" else method
            results.append(cam_from_tokens(
                row_hook, model, token_method, tuple(images.shape[-2:]), positive_only
            ))
        return logits.detach().cpu(), indices.detach().cpu(), results
    finally:
        if hook is not None:
            hook.close()
        for rollout_hook in rollout_hooks:
            rollout_hook.close()


def normalize_cam(cam: np.ndarray) -> np.ndarray:
    if not np.isfinite(cam).all():
        raise ValueError("Non-finite attribution map")
    cam = np.maximum(cam.astype(np.float32), 0)
    maximum = float(cam.max())
    return cam / maximum if maximum > 0 else np.zeros_like(cam)


class ArchitectureCAM:
    def __init__(self, model, method):
        self.model = model
        self.method = method
        self.rollout = method == 'gradrollout' or (
            method == 'architecture' and not uses_patch_average_pool(model)
        )
        # Input gradients are required through ALL blocks for rollout. The
        # last-norm-only gradient shortcut used by Grad-CAM++ is insufficient.
        self.model.requires_grad_(False)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __call__(self, input_tensor, targets=None, eigen_smooth=False, aug_smooth=False):
        if eigen_smooth or aug_smooth:
            raise ValueError('Architecture attribution does not implement smoothing')
        if targets is None:
            target = 'predicted'
        else:
            if len(targets) != len(input_tensor):
                raise ValueError('Expected one target per input image')
            if all(isinstance(t, LogitMarginTarget) for t in targets):
                target = 'margin'
            elif any(isinstance(t, LogitMarginTarget) for t in targets):
                raise ValueError('Cannot mix class and margin targets within a batch')
            else:
                target = torch.tensor([t.category for t in targets], dtype=torch.long,
                                      device=input_tensor.device)
        self.outputs, self.target_indices, maps = explain_single_batch(
            self.model, input_tensor, target, self.method, positive_only=self.rollout
        )
        self.raw_cam = np.stack([low for low, _ in maps])
        self.positive_native = np.maximum(self.raw_cam, 0)
        resized = F.interpolate(
            torch.from_numpy(self.positive_native)[:, None],
            size=input_tensor.shape[-2:], mode='bilinear', align_corners=False,
        )[:, 0].numpy()
        return np.stack([normalize_cam(cam) for cam in resized])
