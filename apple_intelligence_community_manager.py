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
from apple_intelligence import mcp

if __name__ == "__main__":
    mcp.run()
