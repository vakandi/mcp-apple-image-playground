"""Apple Image Playground generation engine via compiled Swift binary."""
import json
import logging
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from PIL import Image

from .response import _fail, _ok

logger = logging.getLogger("apple_intelligence")

_BINARY_DIR = Path(__file__).resolve().parent.parent
_BINARY_PATH = _BINARY_DIR / "imagegen_helper"

_APP_BUNDLE_DIR = Path("/tmp/com.communitymanager.imagegen-helper")
_APP_BUNDLE_PATH = _APP_BUNDLE_DIR / "ImageGenHelper.app"

STYLE_MAP = {
    "animation": "animation",
    "illustration": "illustration",
    "sketch": "sketch",
    "emoji": "emoji",
    "messages_background": "messages-background",
}

CHATGPT_STYLES = {
    "oil_painting": "oil_painting",
    "watercolor": "watercolor",
    "vector": "vector",
    "anime": "anime",
    "print": "print",
}

AVAILABLE_STYLES = list(STYLE_MAP.keys())

_POLL_INTERVAL = 0.5


def _ensure_app_bundle() -> bool:
    """Create the .app bundle with a symlink to the compiled binary.

    The .app bundle is required because ImagePlayground's ImageCreator needs
    a proper GUI app context. Running the binary directly causes SIGSEGV.
    Using `open -a` on the .app bundle gives it the foreground status it needs.

    Returns True if the bundle is ready, False on error.
    """
    if not _BINARY_PATH.exists():
        logger.error("Swift binary not found at %s — run: swiftc imagegen_helper.swift -o imagegen_helper "
                     "-framework ImagePlayground -framework AppKit -framework Vision -framework CoreImage",
                     _BINARY_PATH)
        return False

    macos_dir = _APP_BUNDLE_PATH / "Contents" / "MacOS"
    try:
        macos_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error("Failed to create .app bundle dirs: %s", e)
        return False

    binary_link = macos_dir / "imagegen_helper"
    try:
        if binary_link.exists() or binary_link.is_symlink():
            binary_link.unlink()
        binary_link.symlink_to(_BINARY_PATH.resolve())
    except OSError as e:
        logger.error("Failed to symlink binary into .app bundle: %s", e)
        return False

    plist_path = _APP_BUNDLE_PATH / "Contents" / "Info.plist"
    if not plist_path.exists():
        plist_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            '  <key>CFBundleIdentifier</key>\n'
            '  <string>com.communitymanager.imagegen-helper</string>\n'
            '  <key>CFBundleName</key>\n'
            '  <string>ImageGenHelper</string>\n'
            '  <key>CFBundleExecutable</key>\n'
            '  <string>imagegen_helper</string>\n'
            '  <key>CFBundlePackageType</key>\n'
            '  <string>APPL</string>\n'
            '  <key>LSUIElement</key>\n'
            '  <false/>\n'
            '</dict>\n</plist>\n',
            encoding="utf-8",
        )

    return True


def _run_swift_helper(mode: str, env_overrides: dict | None = None, timeout: int = 120) -> dict:
    """Launch the Swift helper via `open -a` and wait for its JSON response.

    The helper writes a JSON response file to /tmp/com.communitymanager.imagegen-helper/resp_<uuid>.json.
    We poll for it until it appears or we timeout.

    Args:
        mode: "list-styles" or "generate"
        env_overrides: Additional env vars to pass (IMAGE_HELPER_PROMPT, etc.)
        timeout: Max seconds to wait for the response file

    Returns:
        Parsed JSON dict from the helper, or an error dict.
    """
    if not _ensure_app_bundle():
        return {"success": False, "error": f"Swift binary not found at {_BINARY_PATH}"}

    response_id = uuid.uuid4().hex[:12]
    response_path = _APP_BUNDLE_DIR / f"resp_{response_id}.json"

    env = os.environ.copy()
    env["IMAGE_HELPER_MODE"] = mode
    env["IMAGE_HELPER_OUTPUT"] = str(response_path)
    env["LANG"] = "en_US.UTF-8"
    env["LC_ALL"] = "en_US.UTF-8"
    if env_overrides:
        env.update(env_overrides)

    try:
        proc = subprocess.run(
            ["open", "-a", str(_APP_BUNDLE_PATH)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        if proc.returncode != 0:
            logger.warning("open -a returned %d: %s", proc.returncode, proc.stderr[:200])
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "open -a timed out after 10s"}
    except Exception as e:
        return {"success": False, "error": f"Failed to launch .app bundle: {e}"}

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if response_path.exists():
            try:
                data = json.loads(response_path.read_text(encoding="utf-8"))
                try:
                    response_path.unlink()
                except OSError:
                    pass
                return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read response file: %s", e)
                break
        time.sleep(_POLL_INTERVAL)

    try:
        response_path.unlink()
    except OSError:
        pass
    return {"success": False, "error": f"Timed out waiting for {mode} response ({timeout}s)"}


def generate_image(
    prompt: str,
    style: str | None = None,
    output_path: str | None = None,
    timeout: int = 600,
) -> dict:
    if style and style in CHATGPT_STYLES:
        return generate_chatgpt_image(prompt, style=style, output_path=output_path, timeout=timeout)

    if output_path is None:
        output_path = str(
            Path(tempfile.gettempdir()) / f"imgplayground_{uuid.uuid4().hex[:8]}.png"
        )

    output_dir = str(Path(output_path).parent)
    prefix = Path(output_path).stem.rsplit("_", 1)[0] if "_" in Path(output_path).stem else "aigen"

    style_id = STYLE_MAP.get(style, "illustration") if style else "illustration"

    env = {
        "IMAGE_HELPER_PROMPT": prompt,
        "IMAGE_HELPER_STYLE": style_id,
        "IMAGE_HELPER_COUNT": "1",
        "IMAGE_HELPER_DIR": output_dir,
        "IMAGE_HELPER_PREFIX": prefix,
    }

    result = _run_swift_helper("generate", env_overrides=env, timeout=timeout)

    if not result.get("success"):
        return _fail(result.get("error", "Unknown generation error"))

    images = result.get("images", [])
    if not images:
        return _fail("Generation succeeded but returned no images")

    generated_path = images[0].get("path", "")
    if not generated_path or not Path(generated_path).exists():
        return _fail(f"Generated image not found at {generated_path}")

    # If caller wanted a specific output path, copy/move there
    dest = Path(output_path)
    if generated_path != output_path:
        import shutil
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_path, str(dest))

    size_bytes = dest.stat().st_size
    try:
        img = Image.open(str(dest))
        return _ok(
            str(dest),
            width=img.width, height=img.height, size_bytes=size_bytes,
            style=style or "default",
        )
    except Exception:
        return _ok(str(dest), size_bytes=size_bytes)


def generate_chatgpt_image(
    prompt: str,
    style: str = "oil_painting",
    output_path: str | None = None,
    timeout: int = 120,
) -> dict:
    if output_path is None:
        output_path = str(
            Path(tempfile.gettempdir()) / f"chatgpt_{uuid.uuid4().hex[:8]}.png"
        )

    output_dir = str(Path(output_path).parent)
    prefix = Path(output_path).stem.rsplit("_", 1)[0] if "_" in Path(output_path).stem else "chatgpt"

    env = {
        "IMAGE_HELPER_PROMPT": prompt,
        "IMAGE_HELPER_DIR": output_dir,
        "IMAGE_HELPER_PREFIX": prefix,
    }

    result = _run_swift_helper("generate-chatgpt", env_overrides=env, timeout=timeout)

    if not result.get("success"):
        return _fail(result.get("error", "ChatGPT generation error"))

    images = result.get("images", [])
    if not images:
        return _fail("ChatGPT generation succeeded but returned no images")

    generated_path = images[0].get("path", "")
    if not generated_path or not Path(generated_path).exists():
        return _fail(f"Generated image not found at {generated_path}")

    dest = Path(output_path)
    if generated_path != output_path:
        import shutil
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_path, str(dest))

    size_bytes = dest.stat().st_size
    try:
        img = Image.open(str(dest))
        return _ok(
            str(dest),
            width=img.width, height=img.height, size_bytes=size_bytes,
            style=style,
        )
    except Exception:
        return _ok(str(dest), size_bytes=size_bytes)
