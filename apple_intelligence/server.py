"""MCP tool definitions for Apple Image Playground — fully on-device via Shortcuts."""
import logging
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from PIL import Image

from .engines import (
    generate_image as _generate_image,
    AVAILABLE_STYLES,
    _run_swift_helper,
)
from .platforms import PLATFORM_PRESETS, PLATFORM_BUNDLES
from .processing import (
    _hex_to_rgb,
    _get_font,
    _wrap_text,
    _center_crop_resize,
    _letterbox,
)
from .response import (
    _ok,
    _fail,
    _check_absolute_path,
    DEFAULT_OUTPUT_DIR,
)

logger = logging.getLogger("apple_intelligence")

mcp = FastMCP(
    "apple_image_playground",
    instructions=(
        "Apple Image Playground MCP — fully on-device image generation via macOS Shortcuts. "
        "Uses GenerateImageIntent for on-device styles (animation, illustration, sketch) "
        "and ChatGPT external styles (oil_painting, watercolor, vector, anime, print). "
        "40+ platform presets, text overlay, watermark, crop, batch generation. "
        "Zero API keys, zero cloud calls."
    ),
)


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOLS — Discovery
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool()
def list_engines() -> dict:
    """
    List available image generation engines. Apple Image Playground runs fully
    on-device via Shortcuts.app — no API keys, no cloud calls.
    """
    import subprocess
    shortcuts_ok = subprocess.run(
        ["shortcuts", "list"], capture_output=True, text=True, timeout=5,
    ).returncode == 0
    return {
        "success": True,
        "engines": {
            "shortcuts": {
                "available": shortcuts_ok,
                "type": "on-device",
                "styles": AVAILABLE_STYLES if shortcuts_ok else [],
                "description": (
                    "Image Playground via GenerateImageIntent. "
                    "On-device: animation, illustration, sketch. "
                    "ChatGPT external: oil_painting, watercolor, vector, anime, print."
                ),
            },
        },
        "next_steps": [
            "Use generate_image(prompt='...', style='illustration') to generate",
            "Use list_styles() to see all available styles",
        ],
    }


@mcp.tool()
def list_presets() -> dict:
    """List all 40+ social media / blog / web output size presets with dimensions."""
    return {
        "success": True,
        "presets": {k: f"{w}x{h}" for k, (w, h) in sorted(PLATFORM_PRESETS.items())},
        "next_steps": [
            "Use preset keys with generate_social_pack() or crop_image()",
            "Example: generate_social_pack(prompt='...', platforms=['instagram_post', 'twitter_post'])",
        ],
    }


@mcp.tool()
def list_bundles() -> dict:
    """List predefined bundles — groups of presets for common use cases."""
    return {
        "success": True,
        "bundles": dict(PLATFORM_BUNDLES),
        "next_steps": [
            "Use bundle keys with generate_bundle()",
            "Example: generate_bundle(prompt='...', bundle='full_social')",
        ],
    }


@mcp.tool()
def list_styles() -> dict:
    """List all available Apple Image Playground styles from the ImagePlayground API."""
    result = _run_swift_helper("list-styles")
    on_device = result.get("availableStyles", []) if result.get("success") else []
    chatgpt = ["oil_painting", "watercolor", "vector", "anime", "print"]
    return {
        "success": True,
        "on_device": on_device,
        "chatgpt_external": chatgpt,
        "styles": on_device + chatgpt,
        "next_steps": [
            "Use any style key with generate_image(prompt='...', style='<style>')",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOLS — Core Image Generation
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool()
def generate_image(
    prompt: str,
    style: str = "illustration",
    output_dir: str | None = None,
    file_prefix: str = "aigen",
    absolute_path: str | None = None,
) -> dict:
    """
    Generate an image using Apple Image Playground via Shortcuts.app.
    Fully on-device — no API keys, no cloud calls.

    Args:
        prompt: Text description of the image to generate.
        style: One of: animation, illustration, sketch, oil_painting, watercolor, vector, anime, print.
        output_dir: Save folder. Default: ~/Pictures/AI-Generated.
        file_prefix: Filename prefix.
        absolute_path: Full file path to force output location. ERROR if file exists.
    """
    if style not in AVAILABLE_STYLES:
        return _fail(f"Invalid style '{style}'. Use list_styles() to see available styles.")

    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    if forced:
        out_path = str(forced)
    else:
        out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = prompt[:40].lower().replace(" ", "_").replace("/", "_")
        out_path = str(out_dir / f"{file_prefix}_{slug}_{ts}.png")

    result = _generate_image(prompt=prompt, style=style, output_path=out_path)
    return result


@mcp.tool()
def generate_social_pack(
    prompt: str,
    platforms: list[str],
    style: str = "illustration",
    crop_mode: str = "center",
    bg_color: str = "#000000",
    output_dir: str | None = None,
    file_prefix: str = "post",
    absolute_path: str | None = None,
) -> dict:
    """
    Generate one master image via Image Playground, then crop to multiple platform sizes.

    Args:
        prompt: Image concept.
        platforms: Preset keys (e.g. ["instagram_post", "twitter_post"]).
        style: Image Playground style.
        crop_mode: "center" (crop+resize), "letterbox" (pad, no crop), or "smart" (face-aware).
        bg_color: Hex color for letterbox padding.
        output_dir: Save folder.
        file_prefix: Filename prefix.
        absolute_path: Full file path for the master image. ERROR if file exists.
    """
    unknown = [p for p in platforms if p not in PLATFORM_PRESETS]
    if unknown:
        return _fail(f"Unknown platforms: {unknown}. Use list_presets().")
    if not platforms:
        return _fail("Need at least one platform. Use list_presets().")
    if style not in AVAILABLE_STYLES:
        return _fail(f"Invalid style '{style}'. Use list_styles().")

    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    master_path: Path | None = None
    if forced:
        gen = _generate_image(prompt=prompt, style=style, output_path=str(forced))
        if gen.get("success") and gen.get("path"):
            master_path = Path(gen["path"])
        else:
            return gen
    else:
        master_file = out_dir / f"{file_prefix}_master_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        gen = _generate_image(prompt=prompt, style=style, output_path=str(master_file))
        if gen.get("success") and gen.get("path"):
            master_path = Path(gen["path"])
        else:
            return gen

    master_img = Image.open(master_path).convert("RGB")
    platform_paths: dict[str, str] = {}

    for platform in platforms:
        size = PLATFORM_PRESETS[platform]
        try:
            if crop_mode == "letterbox":
                cropped = _letterbox(master_img, size, bg_color)
            else:
                cropped = _center_crop_resize(master_img, size)
            dest = out_dir / f"{file_prefix}_{platform}_{size[0]}x{size[1]}.png"
            cropped.save(dest, "PNG")
            platform_paths[platform] = str(dest)
        except Exception as e:
            platform_paths[platform] = f"ERROR: {e}"

    return _ok(
        str(master_path),
        engine="shortcuts",
        style=style,
        platforms=platform_paths,
        platform_count=len(platforms),
    )


@mcp.tool()
def generate_bundle(
    prompt: str,
    bundle: str,
    style: str = "illustration",
    crop_mode: str = "center",
    output_dir: str | None = None,
    file_prefix: str = "bundle",
    absolute_path: str | None = None,
) -> dict:
    """
    Generate images for a predefined bundle (e.g. "full_social", "blog_set").
    Use list_bundles() to see available bundles.

    Args:
        prompt: Image concept.
        bundle: Bundle name from list_bundles().
        style: Image Playground style.
        crop_mode: "center" or "letterbox".
        output_dir: Save folder.
        file_prefix: Filename prefix.
        absolute_path: Full file path for master image. ERROR if file exists.
    """
    if bundle not in PLATFORM_BUNDLES:
        return _fail(f"Unknown bundle '{bundle}'. Use list_bundles().")
    return generate_social_pack(
        prompt=prompt, platforms=PLATFORM_BUNDLES[bundle],
        style=style, crop_mode=crop_mode,
        output_dir=output_dir, file_prefix=file_prefix,
        absolute_path=absolute_path,
    )


@mcp.tool()
def generate_batch(
    prompts: list[str],
    style: str = "illustration",
    platforms: list[str] | None = None,
    output_dir: str | None = None,
    prefix_template: str = "batch_{index}",
) -> dict:
    """
    Generate images for multiple prompts at once. Each prompt gets its own
    master image + optional platform crops.

    Args:
        prompts: List of image concepts.
        style: Image Playground style.
        platforms: Optional platform presets to crop each to.
        output_dir: Save folder.
        prefix_template: Filename prefix. {index} is replaced with 0,1,2...
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for i, prompt in enumerate(prompts):
        prefix = prefix_template.replace("{index}", str(i))
        if platforms:
            gen = generate_social_pack(
                prompt=prompt, platforms=platforms,
                style=style, output_dir=str(out_dir), file_prefix=prefix,
            )
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save = str(out_dir / f"{prefix}_{ts}.png")
            gen = _generate_image(prompt=prompt, style=style, output_path=save)

        results.append({"prompt": prompt, "result": gen})

    success_count = sum(1 for r in results if r["result"].get("success"))
    return {
        "success": True,
        "total": len(prompts),
        "succeeded": success_count,
        "failed": len(prompts) - success_count,
        "results": results,
        "next_steps": [
            f"Generated {success_count}/{len(prompts)} images",
            "Check individual results for file paths",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOLS — Post-Processing
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool()
def add_text_overlay(
    image_path: str,
    text: str,
    font_size: int = 48,
    font_color: str = "#FFFFFF",
    bg_color: str | None = None,
    position: str = "center",
    max_width_pct: float = 0.8,
    padding: int = 40,
    output_path: str | None = None,
    absolute_path: str | None = None,
) -> dict:
    """
    Overlay text on an image — for quotes, CTAs, headlines, announcements.
    Adds semi-transparent background behind text for readability.

    Args:
        image_path: Path to the source image.
        text: Text to overlay. Supports multi-line (use \\n or long text auto-wraps).
        font_size: Font size in pixels.
        font_color: Hex color for text (e.g. "#FFFFFF").
        bg_color: Semi-transparent background color (e.g. "#000000"). None = no bg.
        position: "center", "top", "bottom", "top-left", "bottom-right".
        max_width_pct: Max text width as fraction of image width (0.1-1.0).
        padding: Padding around text block in pixels.
        output_path: Where to save. Default: auto-named next to source.
        absolute_path: Full file path to force output location. ERROR if file exists.
    """
    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _get_font(font_size, bold=True)
    max_text_w = int(w * max_width_pct) - padding * 2
    lines = _wrap_text(text, font, max_text_w)

    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    line_h = max(line_heights) + 8
    total_h = line_h * len(lines) + padding * 2
    total_w = max(line_widths) + padding * 2

    if "top" in position:
        y = padding
    elif "bottom" in position:
        y = h - total_h - padding
    else:
        y = (h - total_h) // 2

    if "left" in position:
        x = padding
    elif "right" in position:
        x = w - total_w - padding
    else:
        x = (w - total_w) // 2

    if bg_color:
        rgb = _hex_to_rgb(bg_color)
        draw.rounded_rectangle(
            [x, y, x + total_w, y + total_h],
            radius=12, fill=(*rgb, 180),
        )

    tc = _hex_to_rgb(font_color)
    for i, line in enumerate(lines):
        lx = x + padding
        ly = y + padding + i * line_h
        draw.text((lx, ly), line, fill=(*tc, 255), font=font)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    out = str(forced) if forced else (output_path or str(Path(image_path).with_suffix("").as_posix() + "_text.png"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    result.save(out, "PNG")
    return _ok(out, text=text, position=position)


@mcp.tool()
def add_watermark(
    image_path: str,
    text: str = "",
    opacity: int = 80,
    position: str = "bottom-right",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    output_path: str | None = None,
    absolute_path: str | None = None,
) -> dict:
    """
    Add a text watermark to an image for brand protection.

    Args:
        image_path: Source image path.
        text: Watermark text (e.g. brand name, @handle).
        opacity: 0-255 (0=invisible, 255=fully opaque).
        position: "bottom-right", "bottom-left", "top-right", "top-left", "center".
        font_size: Watermark font size.
        font_color: Hex color.
        output_path: Where to save. Default: auto-named.
        absolute_path: Full file path to force output location. ERROR if file exists.
    """
    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _get_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    margin = 20
    positions = {
        "bottom-right": (w - tw - margin, h - th - margin),
        "bottom-left": (margin, h - th - margin),
        "top-right": (w - tw - margin, margin),
        "top-left": (margin, margin),
        "center": ((w - tw) // 2, (h - th) // 2),
    }
    pos = positions.get(position, positions["bottom-right"])
    tc = _hex_to_rgb(font_color)
    draw.text(pos, text, fill=(*tc, opacity), font=font)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    out = str(forced) if forced else (output_path or str(Path(image_path).with_suffix("").as_posix() + "_wm.png"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    result.save(out, "PNG")
    return _ok(out, watermark=text, position=position)


@mcp.tool()
def create_gradient(
    width: int = 1080,
    height: int = 1080,
    color_top: str = "#1a1a2e",
    color_bottom: str = "#16213e",
    direction: str = "vertical",
    output_path: str | None = None,
    absolute_path: str | None = None,
) -> dict:
    """
    Generate a gradient background image. Useful as a base for text posts
    or social media content that doesn't need a photo.

    Args:
        width: Image width.
        height: Image height.
        color_top: Start color (hex).
        color_bottom: End color (hex).
        direction: "vertical", "horizontal", "diagonal".
        output_path: Where to save.
        absolute_path: Full file path to force output location. ERROR if file exists.
    """
    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    r1, g1, b1 = _hex_to_rgb(color_top)
    r2, g2, b2 = _hex_to_rgb(color_bottom)

    for y in range(height):
        for x in range(width):
            if direction == "horizontal":
                ratio = x / width
            elif direction == "diagonal":
                ratio = (x / width + y / height) / 2
            else:
                ratio = y / height
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            draw.point((x, y), fill=(r, g, b))

    out = str(forced) if forced else (output_path or str(DEFAULT_OUTPUT_DIR / f"gradient_{width}x{height}.png"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return _ok(out, width=width, height=height)


@mcp.tool()
def create_text_post(
    text: str,
    width: int = 1080,
    height: int = 1080,
    bg_color: str = "#1a1a2e",
    font_color: str = "#FFFFFF",
    font_size: int = 48,
    gradient: bool = True,
    color_bottom: str = "#16213e",
    output_path: str | None = None,
    absolute_path: str | None = None,
) -> dict:
    """
    Create a ready-to-post text image (quote, announcement, tip).
    Generates a gradient or solid background with styled text.
    Perfect for Instagram carousel text slides or Twitter text posts.

    Args:
        text: The quote / message to display.
        width: Canvas width.
        height: Canvas height.
        bg_color: Background color (hex). Used as gradient start if gradient=True.
        font_color: Text color (hex).
        font_size: Font size in pixels.
        gradient: Use gradient background instead of solid.
        color_bottom: Gradient end color (only if gradient=True).
        output_path: Where to save.
        absolute_path: Full file path to force output location. ERROR if file exists.
    """
    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))
    if gradient:
        gen = create_gradient(width, height, bg_color, color_bottom, output_path="/tmp/_textbg.png")
        img = Image.open(gen["path"]).convert("RGBA")
    else:
        img = Image.new("RGBA", (width, height), _hex_to_rgb(bg_color) + (255,))

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _get_font(font_size, bold=True)
    max_w = int(width * 0.8) - 80
    lines = _wrap_text(text, font, max_w)

    line_h = font_size + 12
    total_h = line_h * len(lines)
    start_y = (height - total_h) // 2

    tc = _hex_to_rgb(font_color)
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (width - lw) // 2
        y = start_y + i * line_h
        draw.text((x, y), line, fill=(*tc, 255), font=font)

    result = Image.alpha_composite(img, overlay).convert("RGB")
    out = str(forced) if forced else (output_path or str(DEFAULT_OUTPUT_DIR / f"textpost_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    result.save(out, "PNG")
    return _ok(out, text=text, width=width, height=height)


@mcp.tool()
def apply_filter(
    image_path: str,
    filter_name: str,
    intensity: float = 0.5,
    output_path: str | None = None,
    absolute_path: str | None = None,
) -> dict:
    """
    Apply a visual filter to an image via PIL.
    Available: blur, sharpen, brightness, contrast, saturation, sepia, noir.

    Args:
        image_path: Source image path.
        filter_name: One of the filter names above.
        intensity: Strength 0.0-1.0.
        output_path: Where to save.
        absolute_path: Full file path to force output location. ERROR if file exists.
    """
    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    out = str(forced) if forced else (output_path or str(Path(image_path).with_suffix("").as_posix() + f"_{filter_name}.png"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(image_path).convert("RGB")
    if filter_name == "blur":
        img = img.filter(ImageFilter.GaussianBlur(radius=intensity * 20))
    elif filter_name == "sharpen":
        img = img.filter(ImageFilter.SHARPEN)
    elif filter_name == "brightness":
        from PIL import ImageEnhance
        img = ImageEnhance.Brightness(img).enhance(1.0 + intensity)
    elif filter_name == "contrast":
        from PIL import ImageEnhance
        img = ImageEnhance.Contrast(img).enhance(1.0 + intensity)
    elif filter_name == "saturation":
        from PIL import ImageEnhance
        img = ImageEnhance.Color(img).enhance(1.0 + intensity)
    elif filter_name == "sepia":
        gray = img.convert("L")
        sepia = Image.merge("RGB", [
            gray.point(lambda p: min(255, int(p * 1.2))),
            gray.point(lambda p: min(255, int(p * 1.0))),
            gray.point(lambda p: min(255, int(p * 0.8))),
        ])
        img = Image.blend(img, sepia, intensity)
    elif filter_name == "noir":
        gray = img.convert("L").convert("RGB")
        img = Image.blend(img, gray, intensity)
    else:
        return _fail(f"Unknown filter '{filter_name}'. Available: blur, sharpen, brightness, contrast, saturation, sepia, noir.")

    img.save(out, "PNG")
    return _ok(out, filter=filter_name, intensity=intensity)


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOLS — Crop & Utility
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool()
def smart_crop(
    image_path: str,
    target_width: int,
    target_height: int,
    output_path: str | None = None,
    absolute_path: str | None = None,
) -> dict:
    """
    Crop an image to exact dimensions using center-crop.

    Args:
        image_path: Source image path.
        target_width: Desired output width.
        target_height: Desired output height.
        output_path: Where to save.
        absolute_path: Full file path to force output location. ERROR if file exists.
    """
    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    out = str(forced) if forced else (output_path or str(
        Path(image_path).with_suffix("").as_posix()
        + f"_smart_{target_width}x{target_height}.png"
    ))
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(image_path).convert("RGB")
    cropped = _center_crop_resize(img, (target_width, target_height))
    cropped.save(out, "PNG")
    return _ok(out, method="center_crop", width=target_width, height=target_height)


@mcp.tool()
def crop_image(
    image_path: str,
    platforms: list[str],
    crop_mode: str = "center",
    bg_color: str = "#000000",
    output_dir: str | None = None,
    file_prefix: str = "crop",
    absolute_path: str | None = None,
) -> dict:
    """
    Take an existing image and crop it to multiple platform sizes.
    No generation — just reformatting an image you already have.

    Args:
        image_path: Path to existing image.
        platforms: Target platform presets (use list_presets() to see options).
        crop_mode: "center" or "letterbox".
        bg_color: Hex color for letterbox padding.
        output_dir: Save folder.
        file_prefix: Filename prefix.
        absolute_path: Full file path to force output location. ERROR if file exists.
    """
    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    unknown = [p for p in platforms if p not in PLATFORM_PRESETS]
    if unknown:
        return _fail(f"Unknown platforms: {unknown}. Use list_presets() to see available presets.")

    src = Image.open(image_path).convert("RGB")
    out_dir = Path(output_dir) if output_dir else Path(image_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}
    for platform in platforms:
        size = PLATFORM_PRESETS[platform]
        try:
            if crop_mode == "letterbox":
                cropped = _letterbox(src, size, bg_color)
            else:
                cropped = _center_crop_resize(src, size)
            dest = out_dir / f"{file_prefix}_{platform}_{size[0]}x{size[1]}.png"
            cropped.save(dest, "PNG")
            results[platform] = str(dest)
        except Exception as e:
            results[platform] = f"ERROR: {e}"

    return _ok(
        image_path,
        source=image_path,
        platforms=results,
        platform_count=len(platforms),
    )


@mcp.tool()
def resize_image(
    image_path: str,
    width: int | None = None,
    height: int | None = None,
    scale: float | None = None,
    output_path: str | None = None,
    absolute_path: str | None = None,
) -> dict:
    """
    Resize an image. Specify width/height or scale factor.

    Args:
        image_path: Source image.
        width: Target width (height auto-calculated if not set).
        height: Target height (width auto-calculated if not set).
        scale: Scale factor (e.g. 0.5 = half size, 2.0 = double).
        output_path: Where to save.
        absolute_path: Full file path to force output location. ERROR if file exists.
    """
    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    img = Image.open(image_path).convert("RGB")

    if scale:
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
    elif width and not height:
        new_h = int(img.height * (width / img.width))
        new_w = width
    elif height and not width:
        new_w = int(img.width * (height / img.height))
        new_h = height
    elif width and height:
        new_w, new_h = width, height
    else:
        return _fail("Specify width, height, or scale.")

    resized = img.resize((new_w, new_h), Image.LANCZOS)
    out = str(forced) if forced else (output_path or str(Path(image_path).with_suffix("").as_posix() + f"_{new_w}x{new_h}.png"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    resized.save(out, "PNG")
    return _ok(out, original_size=f"{img.width}x{img.height}", new_size=f"{new_w}x{new_h}")
