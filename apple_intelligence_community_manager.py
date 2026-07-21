#!/usr/bin/env python3
"""
Community Manager Image Generation MCP Server
==============================================
Image generation MCP for community managers and content-creator AI agents.

Engine: Apple Intelligence via Shortcuts.app (GenerateImageIntent)
  - On-device styles: animation, illustration, sketch
  - ChatGPT external styles: oil_painting, watercolor, vector, anime, print

Usage:
    mcp-cli call apple_image list_styles
    mcp-cli call apple_image generate_image --prompt "a sunset over mountains" --style illustration
    mcp-cli call apple_image generate_social_pack --prompt "product launch" --platforms instagram_post,twitter_post

Requirements:
    pip install "mcp[cli]" pillow
    macOS 15.4+ with Apple Intelligence enabled
"""
from apple_intelligence import mcp

if __name__ == "__main__":
    mcp.run()
