"""Image processing utilities — crop, overlay, filter, watermark, gradient, text."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .response import _ok, _fail, _check_absolute_path, DEFAULT_OUTPUT_DIR


# ═══════════════════════════════════════════════════════════════════════════════
# FONT UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for fp in candidates:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


# ═══════════════════════════════════════════════════════════════════════════════
# CROP & RESIZE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _center_crop_resize(src: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Center-crop to target aspect ratio, then resize."""
    tw, th = size
    target_ratio = tw / th
    w, h = src.size
    ratio = w / h
    if ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        src = src.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        src = src.crop((0, top, w, top + new_h))
    return src.resize(size, Image.LANCZOS)


def _letterbox(src: Image.Image, size: tuple[int, int], bg_color: str = "#000000") -> Image.Image:
    """Fit image inside target size with colored padding (no crop)."""
    tw, th = size
    canvas = Image.new("RGB", size, bg_color)
    src_copy = src.copy()
    src_copy.thumbnail((tw, th), Image.LANCZOS)
    w, h = src_copy.size
    x = (tw - w) // 2
    y = (th - h) // 2
    canvas.paste(src_copy, (x, y))
    return canvas
