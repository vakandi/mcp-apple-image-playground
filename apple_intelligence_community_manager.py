#!/usr/bin/env python3
"""
Community Manager Image Generation MCP Server
==============================================
Image generation MCP for community managers and content-creator AI agents.

Two engines:
  1. Apple Intelligence (on-device) — stylized: animation, illustration, sketch, emoji
  2. Pollinations.ai (cloud) — photorealistic: Flux model, free, no API key

Usage:
    mcp-cli call apple_intelligence list_styles
    mcp-cli call apple_intelligence generate_image --prompt "a sunset over mountains" --engine pollinations
    mcp-cli call apple_intelligence generate_social_pack --prompt "product launch" --platforms instagram_post,twitter_post

Requirements:
    pip install "mcp[cli]" pillow
    swiftc imagegen_helper.swift -o imagegen_helper \\
      -framework ImagePlayground -framework AppKit -framework Vision -framework CoreImage
"""
import json
import logging
import os
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from io import BytesIO

logger = logging.getLogger("apple_intelligence")

from mcp.server.fastmcp import FastMCP
from PIL import Image, ImageDraw, ImageFont, ImageFilter

mcp = FastMCP(
    "apple_intelligence",
    instructions=(
        "Image generation MCP for community managers. Two engines: "
        "apple_intelligence (on-device stylized art) and pollinations (cloud photorealistic). "
        "40+ platform presets, text overlay, watermark, smart crop, batch generation. "
        "All responses include 'success', 'path', and 'next_steps' fields. "
        "Always check 'success' before acting on results. "
        "Use 'list_engines' first to see what's available on this machine."
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# PATHS & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

HELPER_BINARY = Path(__file__).parent / "imagegen_helper"
HANDSHAKE_DIR = Path("/tmp/com.communitymanager.imagegen-helper")
APP_BUNDLE_DIR = HANDSHAKE_DIR / "ImageGenHelper.app"
DEFAULT_OUTPUT_DIR = Path.home() / "Pictures" / "AI-Generated"

APPLE_STYLES = ["animation", "illustration", "sketch", "emoji", "messages-background"]
FILTERS = [
    "blur", "sharpen", "brightness", "contrast", "saturation",
    "vignette", "sepia", "noir", "instant", "chrome",
]

# ═══════════════════════════════════════════════════════════════════════════════
# PLATFORM PRESETS — width x height, in pixels
# ═══════════════════════════════════════════════════════════════════════════════

PLATFORM_PRESETS = {
    # Instagram
    "instagram_post":       (1080, 1080),
    "instagram_portrait":   (1080, 1350),
    "instagram_landscape":  (1080, 566),
    "instagram_story":      (1080, 1920),
    "instagram_reel_cover": (1080, 1920),
    "instagram_carousel":   (1080, 1350),
    # Facebook
    "facebook_post":        (1200, 630),
    "facebook_cover":       (820, 312),
    "facebook_event":       (1920, 1005),
    "facebook_story":       (1080, 1920),
    "facebook_reel_cover":  (1080, 1920),
    # X / Twitter
    "twitter_post":         (1600, 900),
    "twitter_header":       (1500, 500),
    "twitter_card":         (1200, 628),
    # LinkedIn
    "linkedin_post":        (1200, 627),
    "linkedin_cover":       (1584, 396),
    "linkedin_article":     (744, 400),
    "linkedin_newsletter":  (1200, 627),
    # Pinterest
    "pinterest_pin":        (1000, 1500),
    "pinterest_standard":   (1000, 1000),
    "pinterest_long":       (1000, 2100),
    # YouTube
    "youtube_thumbnail":    (1280, 720),
    "youtube_banner":       (2560, 1440),
    "youtube_community":    (1200, 628),
    # TikTok
    "tiktok":               (1080, 1920),
    "tiktok_cover":         (1080, 1440),
    # Threads
    "threads_post":         (1080, 1080),
    "threads_portrait":     (1080, 1350),
    # Blog / Web
    "blog_header":          (1600, 800),
    "blog_inline":          (1200, 800),
    "blog_thumbnail":       (600, 400),
    "og_image":             (1200, 630),
    "email_header":         (600, 200),
    "email_hero":           (600, 400),
    # Thumbnails & Misc
    "square_thumbnail":     (600, 600),
    "discord_banner":       (960, 540),
    "twitch_banner":        (1200, 480),
    "spotify_playlist":     (300, 300),
    "app_icon_1024":        (1024, 1024),
    "app_icon_512":         (512, 512),
    "app_icon_180":         (180, 180),
    "logo_transparent":     (512, 512),
}

PLATFORM_BUNDLES = {
    "full_social": [
        "instagram_post", "instagram_portrait", "instagram_story",
        "facebook_post", "twitter_post", "linkedin_post",
        "pinterest_pin", "youtube_thumbnail", "tiktok",
    ],
    "instagram_set": [
        "instagram_post", "instagram_portrait", "instagram_story",
        "instagram_reel_cover", "instagram_carousel",
    ],
    "blog_set": [
        "blog_header", "blog_inline", "blog_thumbnail",
        "og_image", "square_thumbnail",
    ],
    "startup_kit": [
        "og_image", "twitter_post", "linkedin_post",
        "blog_header", "email_header",
    ],
    "short_form_video": [
        "tiktok", "instagram_reel_cover", "facebook_reel_cover",
        "instagram_story",
    ],
    "youtube_set": [
        "youtube_thumbnail", "youtube_banner", "youtube_community",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE HELPERS — structured for AI agents
# ═══════════════════════════════════════════════════════════════════════════════


def _ok(path: str, **extra) -> dict:
    """Build a success response with file info and next_steps."""
    p = Path(path)
    info: dict = {"success": True, "path": str(p)}
    if p.exists():
        sz = p.stat().st_size
        info["size_bytes"] = sz
        info["size_human"] = f"{sz / 1024:.1f} KB" if sz < 1_048_576 else f"{sz / 1_048_576:.1f} MB"
    info.update(extra)
    info["next_steps"] = _suggest_next(info)
    return info


def _fail(error: str, **extra) -> dict:
    """Build a failure response with actionable next_steps."""
    info: dict = {"success": False, "error": error}
    info.update(extra)
    info["next_steps"] = [f"Fix the error: {error}"]
    return info


def _check_absolute_path(absolute_path: str | None) -> str | None:
    """If absolute_path is set and file exists, return error dict. If set and free, return the path."""
    if absolute_path and Path(absolute_path).exists():
        raise FileExistsError(f"File already exists at {absolute_path}")
    return absolute_path


def _resolve_output_path(
    absolute_path: str | None,
    output_path: str | None,
    output_dir: str | None,
    file_prefix: str,
    suffix: str = ".png",
) -> Path:
    """Resolve final output path from absolute_path, output_path, or auto-generated default."""
    if absolute_path:
        p = Path(absolute_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    if output_path:
        return Path(output_path)
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return out_dir / f"{file_prefix}_{ts}{suffix}"


def _suggest_next(info: dict) -> list[str]:
    """Auto-generate next-step suggestions based on what was produced."""
    steps: list[str] = []
    p = info.get("path", "")
    if p:
        ext = Path(p).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg"):
            steps.append(f"Image saved to {p}")
            if "platforms" in info:
                steps.append(f"Ready to post: {list(info['platforms'].keys())}")
            if "text" in info:
                steps.append("Text overlay applied — image is posting-ready")
            else:
                steps.append("Consider adding text overlay with add_text_overlay()")
    return steps or ["Operation completed"]


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _run_helper(payload: dict, timeout: int = 180) -> dict:
    if not HELPER_BINARY.exists():
        return _fail(
            f"Swift helper not found at {HELPER_BINARY}. "
            "Compile with: swiftc imagegen_helper.swift -o imagegen_helper "
            "-framework ImagePlayground -framework AppKit -framework Vision -framework CoreImage"
        )

    mode = payload.get("mode", "")
    needs_foreground = mode in ("generate", "list-styles")

    if needs_foreground:
        return _run_helper_foreground(payload, timeout)

    try:
        proc = subprocess.run(
            [str(HELPER_BINARY), json.dumps(payload)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _fail("Helper timed out after 180s.")
    except FileNotFoundError:
        return _fail(f"Cannot execute {HELPER_BINARY}.")

    stdout = proc.stdout.strip()
    if not stdout:
        return _fail(f"No output from helper. stderr: {proc.stderr.strip()[:500]}")
    try:
        return json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError:
        return _fail(f"Bad JSON from helper: {stdout[:300]}")


def _ensure_app_bundle():
    macos_dir = APP_BUNDLE_DIR / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)
    binary_dest = macos_dir / "imagegen_helper"
    if binary_dest.exists() or binary_dest.is_symlink():
        binary_dest.unlink()
    binary_dest.symlink_to(HELPER_BINARY.resolve())

    plist = APP_BUNDLE_DIR / "Contents" / "Info.plist"
    plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.communitymanager.imagegen-helper</string>
    <key>CFBundleName</key>
    <string>ImageGenHelper</string>
    <key>CFBundleExecutable</key>
    <string>imagegen_helper</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>""")


def _run_helper_foreground(payload: dict, timeout: int = 180) -> dict:
    HANDSHAKE_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_app_bundle()

    try:
        subprocess.run(
            ["defaults", "write", "com.communitymanager.imagegen-helper", "AppleLanguages", "-array", "en"],
            capture_output=True, timeout=5,
        )
        subprocess.run(
            ["defaults", "write", "com.communitymanager.imagegen-helper", "AppleLocale", "en_US"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass

    import uuid
    request_id = uuid.uuid4().hex
    output_path = HANDSHAKE_DIR / f"resp_{request_id}.json"

    env = {
        **dict(os.environ),
        "IMAGE_HELPER_MODE": str(payload.get("mode", "generate")),
        "IMAGE_HELPER_PROMPT": str(payload.get("prompt", "") or ""),
        "IMAGE_HELPER_STYLE": str(payload.get("style", "illustration") or "illustration"),
        "IMAGE_HELPER_COUNT": str(payload.get("count", 1) or 1),
        "IMAGE_HELPER_DIR": str(payload.get("outputDir", "/tmp") or "/tmp"),
        "IMAGE_HELPER_PREFIX": str(payload.get("prefix", "aigen") or "aigen"),
        "IMAGE_HELPER_OUTPUT": str(output_path),
        "IMAGE_HELPER_INPUT_IMAGE": str(payload.get("inputImage") or ""),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
    }
    # Sanitize: subprocess requires all env values to be strings, no None
    env = {k: str(v) for k, v in env.items() if v is not None}

    try:
        cmd = ["open", "-a", str(APP_BUNDLE_DIR)]
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        return _fail(f"Failed to launch app bundle: {e}")

    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if output_path.exists():
            try:
                data = json.loads(output_path.read_text())
                output_path.unlink(missing_ok=True)
                if data.get("success"):
                    return data
                else:
                    return _fail(data.get("error", "Unknown helper error"))
            except (json.JSONDecodeError, KeyError):
                pass
        time.sleep(0.5)

    output_path.unlink(missing_ok=True)
    return _fail(f"Foreground generation timed out after {timeout}s.")

    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if output_path.exists():
            try:
                data = json.loads(output_path.read_text())
                output_path.unlink(missing_ok=True)
                return data
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.5)

    output_path.unlink(missing_ok=True)
    return _fail(f"Foreground generation timed out after {timeout}s. Apple Intelligence may be busy.")


def _generate_pollinations(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: int | None = None,
    model: str = "flux",
    output_path: str | None = None,
) -> dict:
    """Generate an image via Pollinations.ai (free, no API key)."""
    params = {
        "width": width, "height": height, "model": model,
        "nologo": "true", "enhance": "true",
    }
    if seed is not None:
        params["seed"] = seed

    encoded_prompt = urllib.parse.quote(prompt)
    query = urllib.parse.urlencode(params)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{query}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CommunityManagerMCP/2.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            img_data = resp.read()
    except Exception as e:
        return _fail(f"Pollinations request failed: {e}")

    if not img_data or len(img_data) < 1000:
        return _fail(f"Empty or too-small response from Pollinations ({len(img_data)} bytes)")

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(img_data)

    try:
        img = Image.open(BytesIO(img_data))
        return _ok(
            output_path or "pollinations_output",
            width=img.width, height=img.height, size_bytes=len(img_data),
        )
    except Exception:
        return _ok(output_path or "pollinations_output", size_bytes=len(img_data))


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
# MCP TOOLS — Discovery
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def list_engines() -> dict:
    """
    List available image generation engines. Call this FIRST to know what's available.
    Returns engine capabilities, availability status, and recommendations.
    """
    apple_ok = HELPER_BINARY.exists()
    return {
        "success": True,
        "engines": {
            "apple_intelligence": {
                "available": apple_ok,
                "type": "on-device",
                "styles": APPLE_STYLES if apple_ok else [],
                "description": "Stylized art (animation/illustration/sketch/emoji). Local, private.",
                "note": "Compile Swift helper to enable." if not apple_ok else None,
            },
            "pollinations": {
                "available": True,
                "type": "cloud",
                "styles": ["photorealistic", "any"],
                "description": "Photorealistic + artistic via Flux model. Free, no API key.",
            },
        },
        "recommendation": (
            "Use apple_intelligence for stylized brand art. "
            "Use pollinations for photorealistic scenes, product shots, people."
        ),
        "next_steps": [
            "Apple Intelligence available — use generate_image(engine='apple') for stylized art",
            "Pollinations available — use generate_image(engine='pollinations') for photorealistic",
            "Call list_styles() to see available Apple Intelligence styles",
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
    """List Apple Intelligence Image Playground styles available on this Mac."""
    result = _run_helper({"mode": "list-styles"})
    result["next_steps"] = [
        f"Use style parameter with generate_image(engine='apple', style='<style>')",
        "Available styles: " + ", ".join(result.get("styles", APPLE_STYLES)),
    ]
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOLS — Core Image Generation
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def generate_image(
    prompt: str,
    engine: str = "pollinations",
    style: str = "illustration",
    count: int = 1,
    width: int = 1024,
    height: int = 1024,
    seed: int | None = None,
    output_dir: str | None = None,
    file_prefix: str = "aigen",
    absolute_path: str | None = None,
    input_image: str | None = None,
) -> dict:
    """
    Generate images using Apple Intelligence or Pollinations.ai.

    Apple Intelligence: on-device stylized art (animation, illustration, sketch, emoji).
    NOT photorealistic — use engine='pollinations' for that.

    Pollinations.ai: cloud photorealistic via Flux model. Free, no API key.

    Args:
        prompt: Text description. Keep concrete and single-subject for Apple.
        engine: "apple" (stylized) or "pollinations" (photorealistic).
        style: Apple style (ignored for pollinations). One of: animation, illustration, sketch, emoji, messages-background.
        count: Number of variations (1-4, Apple only).
        width: Output width (Pollinations only, max ~2048).
        height: Output height (Pollinations only, max ~2048).
        seed: Optional seed for reproducibility (Pollinations only).
        output_dir: Save folder. Default: ~/Pictures/AI-Generated.
        file_prefix: Filename prefix.
        absolute_path: Full file path to force output location. ERROR if file exists.
        input_image: Path to an existing image to use as Apple Image Playground input (inpainting/transformation).
    """
    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    if engine == "apple":
        if style not in APPLE_STYLES:
            return _fail(f"Invalid style '{style}'. Must be one of: {APPLE_STYLES}")
        if forced:
            out_dir = str(Path(forced).parent)
            prefix = Path(forced).stem
        else:
            out_dir = str(Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR)
            prefix = file_prefix
        result = _run_helper({
            "mode": "generate", "prompt": prompt, "style": style,
            "count": count, "outputDir": out_dir, "prefix": prefix,
            "inputImage": input_image,
        })
        if result.get("success") and result.get("images"):
            img_path = result["images"][0].get("path", "")
            if forced and result["images"]:
                actual = Path(result["images"][0]["path"])
                if actual != Path(forced):
                    actual.rename(forced)
                    img_path = str(forced)
            return _ok(img_path, style=style, engine="apple", count=len(result["images"]))
        return result

    elif engine == "pollinations":
        if forced:
            save_path = str(forced)
        else:
            out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            slug = prompt[:40].lower().replace(" ", "_").replace("/", "_")
            filename = f"{file_prefix}_{slug}_{ts}.png"
            save_path = str(out_dir / filename)
        result = _generate_pollinations(prompt, width, height, seed, output_path=save_path)
        if result.get("success"):
            result["style"] = "photorealistic"
            result["engine"] = "pollinations"
        return result

    else:
        return _fail(f"Unknown engine '{engine}'. Use 'apple' or 'pollinations'.")


@mcp.tool()
def generate_social_pack(
    prompt: str,
    platforms: list[str],
    engine: str = "pollinations",
    style: str = "illustration",
    crop_mode: str = "center",
    bg_color: str = "#000000",
    output_dir: str | None = None,
    file_prefix: str = "post",
    absolute_path: str | None = None,
    input_image: str | None = None,
) -> dict:
    """
    Generate one master image, then produce ready-to-post crops for every platform.
    The main tool for "give me images for this social media post."

    Args:
        prompt: Image concept.
        platforms: Preset keys (e.g. ["instagram_post", "twitter_post"]).
        engine: "apple" (stylized), "pollinations" (photorealistic).
        style: Apple style (ignored for pollinations).
        crop_mode: "center" (crop+resize), "letterbox" (pad, no crop), or "smart" (face-aware).
        bg_color: Hex color for letterbox padding. Default: #000000.
        output_dir: Save folder.
        file_prefix: Filename prefix.
        absolute_path: Full file path for the master image. ERROR if file exists.
        input_image: Path to an existing image to use as Apple Image Playground input.
    """
    unknown = [p for p in platforms if p not in PLATFORM_PRESETS]
    if unknown:
        return _fail(f"Unknown platforms: {unknown}. Use list_presets() to see available presets.")
    if not platforms:
        return _fail("Need at least one platform. Use list_presets() to see options.")

    try:
        forced = _check_absolute_path(absolute_path)
    except FileExistsError as e:
        return _fail(str(e))

    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    sizes = [PLATFORM_PRESETS[p] for p in platforms]
    max_w = max(s[0] for s in sizes)
    max_h = max(s[1] for s in sizes)

    master_path: Path | None = None

    if engine == "apple" and HELPER_BINARY.exists():
        if forced:
            gen = _run_helper({
                "mode": "generate", "prompt": prompt, "style": style, "count": 1,
                "outputDir": str(forced.parent), "prefix": forced.stem,
                "inputImage": input_image,
            })
        else:
            gen = _run_helper({
                "mode": "generate", "prompt": prompt, "style": style, "count": 1,
                "outputDir": str(out_dir), "prefix": f"{file_prefix}_master",
                "inputImage": input_image,
            })
        if gen.get("success") and gen.get("images"):
            master_path = Path(gen["images"][0]["path"])
        else:
            return gen

    if master_path is None:
        save = str(forced) if forced else str(out_dir / f"{file_prefix}_master_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        gen = _generate_pollinations(prompt, max_w, max_h, output_path=save)
        if not gen.get("success"):
            return gen
        master_path = Path(save)

    # Crop to each platform
    master_img = Image.open(master_path).convert("RGB")
    platform_paths: dict[str, str] = {}

    for platform in platforms:
        size = PLATFORM_PRESETS[platform]
        try:
            if crop_mode == "letterbox":
                cropped = _letterbox(master_img, size, bg_color)
            elif crop_mode == "smart" and HELPER_BINARY.exists():
                tmp_in = f"/tmp/_smcrop_src_{platform}.png"
                master_img.save(tmp_in, "PNG")
                tmp_out = str(out_dir / f"{file_prefix}_{platform}_{size[0]}x{size[1]}.png")
                res = _run_helper({
                    "mode": "smart-crop", "inputPath": tmp_in,
                    "targetWidth": size[0], "targetHeight": size[1], "outputPath": tmp_out,
                })
                if res.get("success") and Path(tmp_out).exists():
                    platform_paths[platform] = tmp_out
                    continue
            cropped = _center_crop_resize(master_img, size)
            dest = out_dir / f"{file_prefix}_{platform}_{size[0]}x{size[1]}.png"
            cropped.save(dest, "PNG")
            platform_paths[platform] = str(dest)
        except Exception as e:
            platform_paths[platform] = f"ERROR: {e}"

    engine_used = "apple" if engine == "apple" and HELPER_BINARY.exists() else "pollinations"
    return _ok(
        str(master_path),
        engine=engine_used,
        platforms=platform_paths,
        platform_count=len(platforms),
    )


@mcp.tool()
def generate_bundle(
    prompt: str,
    bundle: str,
    engine: str = "pollinations",
    style: str = "illustration",
    crop_mode: str = "center",
    output_dir: str | None = None,
    file_prefix: str = "bundle",
    absolute_path: str | None = None,
    input_image: str | None = None,
) -> dict:
    """
    Generate images for a predefined bundle (e.g. "full_social", "blog_set").
    Use list_bundles() to see available bundles.

    Args:
        prompt: Image concept.
        bundle: Bundle name from list_bundles().
        engine: "apple" or "pollinations".
        style: Apple style.
        crop_mode: "center", "letterbox", or "smart".
        output_dir: Save folder.
        file_prefix: Filename prefix.
        absolute_path: Full file path for master image. ERROR if file exists.
        input_image: Path to an existing image for Apple Image Playground input.
    """
    if bundle not in PLATFORM_BUNDLES:
        return _fail(f"Unknown bundle '{bundle}'. Use list_bundles() to see available bundles.")
    return generate_social_pack(
        prompt=prompt, platforms=PLATFORM_BUNDLES[bundle],
        engine=engine, style=style, crop_mode=crop_mode,
        output_dir=output_dir, file_prefix=file_prefix,
        absolute_path=absolute_path, input_image=input_image,
    )


@mcp.tool()
def generate_batch(
    prompts: list[str],
    engine: str = "pollinations",
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
        engine: "apple" or "pollinations".
        style: Apple style.
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
                prompt=prompt, platforms=platforms, engine=engine,
                style=style, output_dir=str(out_dir), file_prefix=prefix,
            )
        elif engine == "apple" and HELPER_BINARY.exists():
            gen = _run_helper({
                "mode": "generate", "prompt": prompt, "style": style, "count": 1,
                "outputDir": str(out_dir), "prefix": prefix,
            })
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save = str(out_dir / f"{prefix}_{ts}.png")
            gen = _generate_pollinations(prompt, 1024, 1024, output_path=save)

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
    Apply a visual filter to an image. Uses Swift helper for Apple-native filters,
    or falls back to PIL-based filters.

    Filters: blur, sharpen, brightness, contrast, saturation, sepia, noir.

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

    if HELPER_BINARY.exists():
        result = _run_helper({
            "mode": "apply-filter", "inputPath": image_path,
            "filter": filter_name, "intensity": intensity, "outputPath": out,
        })
        if result.get("success"):
            return result

    # PIL fallback
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
        return _fail(f"PIL fallback not available for '{filter_name}'. Compile Swift helper for more filters.")

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
    Face-aware smart crop using Apple's Vision framework.
    Detects faces and centers the crop on them instead of the image center.
    Falls back to center crop if Swift helper is unavailable.

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

    if HELPER_BINARY.exists():
        result = _run_helper({
            "mode": "smart-crop", "inputPath": image_path,
            "targetWidth": target_width, "targetHeight": target_height,
            "outputPath": out,
        })
        if result.get("success"):
            return result

    # PIL fallback
    img = Image.open(image_path).convert("RGB")
    cropped = _center_crop_resize(img, (target_width, target_height))
    cropped.save(out, "PNG")
    return _ok(out, method="center_fallback", width=target_width, height=target_height)


@mcp.tool()
def detect_faces(image_path: str) -> dict:
    """
    Detect faces in an image using Apple's Vision framework.
    Returns face count and bounding boxes.
    """
    result = _run_helper({"mode": "detect-faces", "inputPath": image_path})
    if result.get("success"):
        result["next_steps"] = [
            f"Found {result.get('faceCount', 0)} face(s)",
            "Use smart_crop() to center-crop on detected faces",
        ]
    return result


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


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
