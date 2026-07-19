"""Apple Intelligence and Pollinations.ai image generation engines."""
import json
import logging
import os
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PIL import Image
from io import BytesIO

from .response import _fail, _ok

logger = logging.getLogger("apple_intelligence")

HELPER_BINARY = Path(__file__).parent.parent / "imagegen_helper"
HANDSHAKE_DIR = Path("/tmp/com.communitymanager.imagegen-helper")
APP_BUNDLE_DIR = HANDSHAKE_DIR / "ImageGenHelper.app"


def _ensure_app_bundle():
    """Create a macOS .app bundle wrapper so `open -a` can launch the helper."""
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


def _run_helper(payload: dict, timeout: int = 180) -> dict:
    """Execute the Swift helper binary with the given payload."""
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


def _run_helper_foreground(payload: dict, timeout: int = 180) -> dict:
    """Launch helper via `open -a` for foreground process status (required by Apple Image Playground)."""
    HANDSHAKE_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_app_bundle()

    # Force English locale
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
