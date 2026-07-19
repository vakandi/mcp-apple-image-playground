<p align="center">
  <img src="assets/banners/banner.png" alt="Apple Image MCP — On-device AI image generation for macOS" width="100%">
</p>

<p align="center">
  <strong>On-device AI image generation for macOS. 17 tools. Zero API keys.</strong><br>
  Apple Intelligence (<code>ImageCreator</code>) + Pollinations.ai (photorealistic) in a single MCP server.<br>
  Auto-crops for 40+ social media platforms. Built for AI agents.
</p>

<p align="center">
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-compatible-blue" alt="MCP"></a>
  <a href="https://www.apple.com/macos/"><img src="https://img.shields.io/badge/macOS-15.4%2B-black?logo=apple" alt="macOS"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://github.com/vakandi/apple-image-mcp/releases"><img src="https://img.shields.io/badge/version-1.0.0-orange" alt="Version"></a>
</p>

---

## Why this exists

Other Apple Intelligence MCP servers expose one tool: `generate_image`. That's it.

**apple-image-mcp** gives your AI agent a full image pipeline:

- **Dual engine** — Apple on-device stylized art + Pollinations photorealistic (Flux model, free, no API key)
- **17 tools** — generate, crop, batch, watermark, text overlay, filters, social packs
- **40+ platform presets** — Instagram, TikTok, LinkedIn, YouTube, Pinterest, blog headers — all one prompt away
- **Zero config** — runs locally on any Apple Silicon Mac with Apple Intelligence enabled

---

## Quick Start

```bash
# 1. Compile the Swift helper (one-time)
swiftc imagegen_helper.swift -o imagegen_helper \
  -framework ImagePlayground -framework AppKit

# 2. Install Python deps
pip install "mcp[cli]" pillow

# 3. Add to your MCP client (Claude Desktop example)
# Edit ~/Library/Application Support/Claude/claude_desktop_config.json:
```

```json
{
  "mcpServers": {
    "apple_image": {
      "command": "python3",
      "args": ["/absolute/path/to/apple_intelligence_community_manager.py"]
    }
  }
}
```

```bash
# 4. Restart Claude Desktop — 17 tools appear instantly
```

---

## Available Tools

### Image Generation

| Tool | Description |
|------|-------------|
| `generate_image` | Generate from text prompt. Engine: `apple` or `pollinations` |
| `generate_social_pack` | One prompt → multiple platform-sized crops (Instagram, Twitter, LinkedIn…) |
| `generate_bundle` | Generate for a predefined bundle (e.g. `full_social`, `blog_set`) |
| `generate_batch` | Generate multiple images from a list of prompts |

### Image Processing

| Tool | Description |
|------|-------------|
| `add_text_overlay` | Add text with custom font, position, color, shadow |
| `add_watermark` | Brand watermark with opacity control |
| `create_gradient` | Generate gradient backgrounds (vertical, horizontal, diagonal) |
| `create_text_post` | Ready-to-post text image (quote, announcement, tip) |
| `apply_filter` | Blur, sharpen, brightness, contrast, sepia, noir |
| `smart_crop` | Face-aware crop using Apple's Vision framework |
| `crop_image` | Crop existing image to multiple platform sizes |
| `resize_image` | Resize to exact dimensions or scale factor |

### Discovery

| Tool | Description |
|------|-------------|
| `list_engines` | Check which engines are available (Apple + Pollinations) |
| `list_styles` | Show available Apple Intelligence styles on this machine |
| `list_presets` | All 40+ platform presets with exact dimensions |
| `list_bundles` | Predefined bundles (full_social, instagram_set, blog_set…) |
| `detect_faces` | Detect faces using Apple's Vision framework |

---

## Engine Details

### Apple Intelligence (On-Device)

- **Styles**: `illustration`, `sketch`, `animation` (also `emoji`, `messages-background` — may timeout on some macOS versions)
- **Requires**: macOS 15.4+ with Apple Intelligence enabled, Apple Silicon Mac
- **Privacy**: Runs entirely on your machine. No images leave your device.
- **Speed**: ~3-5 seconds per image

### Pollinations.ai (Cloud)

- **Model**: Flux — photorealistic, high quality
- **Requires**: Internet connection. **No API key needed.**
- **Privacy**: Input prompt sent to Pollinations API. Output images are public URLs (regenerate to get new ones).
- **Speed**: ~5-10 seconds per image

---

## Platform Presets

One prompt → perfectly sized for every platform:

```
Instagram:   post (1080×1080) · portrait (1080×1350) · story (1080×1920) · reel cover
Twitter/X:   post (1200×675)  · header (1500×500)  · card (1200×628)
LinkedIn:     post (1200×628)  · article (744×400)  · banner (1584×396)
YouTube:      thumbnail (1280×720) · channel art (2560×1440) · short (1080×1920)
Pinterest:    pin (1000×1500)  · story (1080×1920)
Blog:         header (1200×630) · hero (1920×1080) · thumbnail (400×300)
Facebook:     post (1200×630)  · cover (820×312)   · story (1080×1920)
TikTok:       video cover (1080×1920)
```

Full list: call `list_platform_presets` on the running server.

---

## Example Agent Calls

### Generate a social media pack

```python
generate_social_pack(
    prompt="a cozy coffee shop in autumn, warm colors",
    platforms=["instagram_post", "twitter_post", "linkedin_post"],
    engine="apple",
    style="illustration"
)
# → 3 images, each cropped to the perfect platform size
```

### Generate a photorealistic product shot

```python
generate_image(
    prompt="minimalist product photography of a ceramic mug on marble",
    engine="pollinations",
    width=1080,
    height=1080
)
# → photorealistic image, no API key needed
```

### Generate a bundle for your blog

```python
generate_bundle(
    prompt="a rocket launching into a starry sky",
    bundle="blog_set",
    engine="pollinations"
)
# → 5 images: blog_header, blog_inline, blog_thumbnail, og_image, square_thumbnail
```

### Create a text post for social

```python
create_text_post(
    text="50% OFF everything this weekend",
    width=1080,
    height=1080,
    bg_color="#1a1a2e",
    font_color="#FFFFFF",
    gradient=True
)
# → ready-to-post text image with gradient background
```

### Add text overlay to an image

```python
add_text_overlay(
    image_path="/path/to/image.png",
    text="50% OFF",
    position="center",
    font_size=72,
    font_color="#FF0000",
    bg_color="#000000"
)
```

---

## Requirements

| Requirement | Details |
|-------------|---------|
| **macOS** | 15.4+ (Sequoia) or 26+ (Tahoe) |
| **Hardware** | Apple Silicon Mac (M1, M2, M3, M4, M5) |
| **Apple Intelligence** | Enabled in System Settings → Apple Intelligence & Siri |
| **Image Playground** | Open once to download models (one-time, ~2GB) |
| **Xcode CLI** | `xcode-select --install` |
| **Python** | 3.10+ |
| **Pip** | `pip install "mcp[cli]" pillow` |

### Non-Apple-Silicon Macs

Apple Intelligence is required for the `apple_intelligence` engine, but **Pollinations works on any machine** with Python and internet. You can use the server with only the `pollinations` engine on Intel Macs.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APPLE_IMAGE_OUTPUT_DIR` | `~/Pictures/AI-Generated` | Where generated images are saved |
| `APPLE_IMAGE_DEFAULT_ENGINE` | `apple_intelligence` | Default engine (`apple_intelligence` or `pollinations`) |
| `APPLE_IMAGE_DEFAULT_STYLE` | `illustration` | Default Apple style |
| `POLLINATIONS_DEFAULT_MODEL` | `flux` | Pollinations model to use |

### OpenCode / Claude Code Integration

```bash
# Quick add via CLI
claude mcp add apple_image \
  --scope user \
  --env "APPLE_IMAGE_OUTPUT_DIR=$HOME/Pictures/AI-Generated" \
  -- python3 /absolute/path/to/apple_intelligence_community_manager.py
```

---

## Troubleshooting

### `ImagePlayground.ImageCreator.Error.creationFailed`

This is a known macOS issue, especially on beta builds. Fixes:

1. Open **Image Playground.app** and generate one image manually
2. Confirm Apple Intelligence is enabled in System Settings
3. Ensure Image Playground models are fully downloaded

### Dock icon flashes during generation

Expected behavior. Apple's `ImageCreator` requires the app to run in the foreground. The helper temporarily sets a Dock icon, generates, then exits. The icon disappears automatically.

### Pollinations returns errors

Pollinations is a free service — occasional rate limits or downtime happen. The server retries automatically. For production workflows, use the Apple engine as primary.

---

## Architecture

```
┌──────────────────┐     ┌──────────────────────────┐     ┌─────────────────┐
│  MCP Client      │────▶│  apple_image MCP Server  │────▶│  Apple          │
│  (Claude, Cursor │◀────│  (Python + FastMCP)       │◀────│  ImageCreator   │
│   OpenCode, etc.)│     │                          │     │  (on-device)    │
└──────────────────┘     │  ┌──────────────────────┐ │     └─────────────────┘
                         │  │  Pollinations API    │─│────▶ Pollinations.ai
                         │  └──────────────────────┘ │     (cloud, free)
                         └──────────────────────────┘
```

The Swift helper binary (`imagegen_helper`) is a thin wrapper around Apple's `ImagePlayground.ImageCreator` API. The Python MCP server calls it as a subprocess, receives generated images via file polling, then processes them (crop, resize, overlay, etc.) using Pillow.

---

## Project Structure

```
apple-image-mcp/
├── apple_intelligence/                  # Python package
│   ├── __init__.py                     # Package entry point
│   ├── server.py                       # 17 MCP tool definitions
│   ├── engines.py                      # Apple Intelligence + Pollinations engines
│   ├── processing.py                   # Image crop, resize, font utilities
│   ├── platforms.py                    # 40+ platform presets & bundles
│   └── response.py                     # Structured response helpers
├── apple_intelligence_community_manager.py  # MCP server entry point
├── imagegen_helper.swift               # Swift → ImageCreator bridge
├── imagegen_helper                     # Compiled arm64 binary
├── assets/banners/banner.png           # Repo banner (generated with this MCP)
├── README.md
├── LICENSE
└── .gitignore
```

---

## Contributing

Contributions welcome. Please open an issue first to discuss what you'd like to change.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [Apple ImagePlayground API](https://developer.apple.com/documentation/imageplayground) — the on-device image generation framework
- [Pollinations.ai](https://pollinations.ai) — free, open photorealistic image generation
- [FastMCP](https://github.com/jlowin/fastmcp) — the MCP server framework
- [Pillow](https://python-pillow.org) — image processing
