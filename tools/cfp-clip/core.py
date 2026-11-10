"""Pixel-preserving circular crop adapted from the supplied cfp_clip draft."""
from __future__ import annotations

import io
import math
import warnings

from PIL import Image, ImageDraw, ImageOps

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".gif", ".webp"}
MAX_IMAGE_PIXELS = 50_000_000


def load_image(data: bytes) -> Image.Image:
    """Read the first frame, apply its EXIF orientation, and detach RGB pixels."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as opened:
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise ValueError("Images must contain no more than 50 million pixels.")
            return ImageOps.exif_transpose(opened).convert("RGB")


def validate_point(point: object, image: Image.Image) -> tuple[float, float]:
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        raise ValueError("Choose two points inside the image.")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in point):
        raise ValueError("Point coordinates must be finite numbers.")
    x, y = point
    if not (0 <= x < image.width and 0 <= y < image.height):
        raise ValueError("Choose two points inside the image.")
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("Point coordinates must be finite numbers.")
    return x, y


def make_circular_clip(image: Image.Image, first_point: tuple[float, float],
                       center_point: tuple[float, float]) -> Image.Image:
    """Use the draft's exact circle, rounding, boundary and masking rules."""
    first_point = validate_point(first_point, image)
    center_x, center_y = validate_point(center_point, image)
    radius = math.hypot(first_point[0] - center_x, first_point[1] - center_y) * 1.5
    if radius <= 0:
        raise ValueError("The two points must be different.")

    left = max(0, int(math.floor(center_x - radius)))
    top = max(0, int(math.floor(center_y - radius)))
    right = min(image.width, int(math.ceil(center_x + radius)))
    bottom = min(image.height, int(math.ceil(center_y + radius)))
    if left >= right or top >= bottom:
        raise ValueError("The crop does not intersect the image.")

    source = image.convert("RGB")
    cropped = source.crop((left, top, right, bottom))
    mask = Image.new("L", cropped.size, 0)
    ImageDraw.Draw(mask).ellipse(
        (center_x - radius - left, center_y - radius - top,
         center_x + radius - left, center_y + radius - top), fill=255,
    )
    clipped = Image.new("RGB", cropped.size, (0, 0, 0))
    clipped.paste(cropped, mask=mask)
    return clipped
