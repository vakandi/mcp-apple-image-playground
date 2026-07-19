"""Structured response helpers for AI agents."""
from pathlib import Path
from datetime import datetime

DEFAULT_OUTPUT_DIR = Path.home() / "Pictures" / "AI-Generated"


def _ok(path: str, **extra) -> dict:
    """Build a success response with file info and next_steps."""
    p = Path(path)
    info: dict = {"success": True, "path": str(p)}
    if p.exists():
        sz = p.stat().st_size
        info["size_bytes"] = sz
        info["size_human"] = (
            f"{sz / 1024:.1f} KB" if sz < 1_048_576 else f"{sz / 1_048_576:.1f} MB"
        )
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
    """If absolute_path is set and file exists, raise. If set and free, return it."""
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
