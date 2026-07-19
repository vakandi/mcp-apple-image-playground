#!/usr/bin/env node
/**
 * postinstall.js — Compile Swift helper + install Python deps
 * Runs automatically after `npm install @vakandi/apple-image-mcp`
 */
const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const ROOT = __dirname;
const SWIFT_SRC = path.join(ROOT, "imagegen_helper.swift");
const SWIFT_BIN = path.join(ROOT, "imagegen_helper");

function log(msg) {
  console.log(`\x1b[36m[mcp-apple-image-playground]\x1b[0m ${msg}`);
}

function warn(msg) {
  console.warn(`\x1b[33m[mcp-apple-image-playground]\x1b[0m ${msg}`);
}

function fail(msg) {
  console.error(`\x1b[31m[mcp-apple-image-playground]\x1b[0m ${msg}`);
}

// ── Step 1: Compile Swift helper ─────────────────────────────────────────────
function compileSwift() {
  if (!fs.existsSync(SWIFT_SRC)) {
    warn("imagegen_helper.swift not found — skipping Swift compilation");
    return false;
  }

  // Already compiled and up-to-date?
  if (fs.existsSync(SWIFT_BIN)) {
    const srcMtime = fs.statSync(SWIFT_SRC).mtimeMs;
    const binMtime = fs.statSync(SWIFT_BIN).mtimeMs;
    if (binMtime >= srcMtime) {
      log("Swift helper already compiled ✓");
      return true;
    }
  }

  log("Compiling Swift helper (one-time, ~5s)...");

  // Check for swiftc
  try {
    execSync("which swiftc", { stdio: "ignore" });
  } catch {
    warn(
      "swiftc not found. Install Xcode CLI tools: xcode-select --install\n" +
        "Apple Intelligence engine will be unavailable — Pollinations still works."
    );
    return false;
  }

  try {
    execSync(
      `swiftc "${SWIFT_SRC}" -o "${SWIFT_BIN}" -O ` +
        `-framework ImagePlayground -framework AppKit -framework Vision -framework CoreImage`,
      { stdio: "inherit", timeout: 60_000 }
    );
    log("Swift helper compiled ✓");
    return true;
  } catch (e) {
    warn(
      "Swift compilation failed — Apple Intelligence engine unavailable.\n" +
        "  This is expected on non-macOS or if Xcode CLI tools aren't installed.\n" +
        "  Pollinations engine still works fine."
    );
    return false;
  }
}

// ── Step 2: Install Python dependencies ──────────────────────────────────────
function installPythonDeps() {
  log("Installing Python dependencies...");

  // Find python3
  let python = "python3";
  try {
    execSync("which python3", { stdio: "ignore" });
  } catch {
    warn("python3 not found — Python deps not installed. Install Python 3.10+");
    return false;
  }

  // Check version >= 3.10
  try {
    const ver = execSync("python3 -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")'", {
      encoding: "utf-8",
    }).trim();
    const [major, minor] = ver.split(".").map(Number);
    if (major < 3 || (major === 3 && minor < 10)) {
      warn(`Python ${ver} found but 3.10+ required. Pollinations may still work.`);
    }
  } catch {
    // version check failed, continue anyway
  }

  const deps = ['"mcp[cli]"', "pillow"];

  try {
    // Use --quiet to avoid noise, --no-warn-script-location for pipx users
    execSync(`python3 -m pip install --quiet --no-warn-script-location ${deps.join(" ")}`, {
      stdio: "inherit",
      timeout: 120_000,
    });
    log("Python dependencies installed ✓");
    return true;
  } catch (e) {
    warn(
      "pip install failed. Try manually:\n" +
        "  python3 -m pip install 'mcp[cli]' pillow"
    );
    return false;
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────
function main() {
  // Skip on non-macOS (Pollinations-only mode)
  if (process.platform !== "darwin") {
    warn("Not macOS — Apple Intelligence unavailable. Pollinations engine still works.");
    installPythonDeps();
    return;
  }

  log("Setting up apple-image-mcp...");

  const swiftOk = compileSwift();
  installPythonDeps();

  // Summary
  console.log("");
  log("Setup complete! 🎉");
  log("");
  log("Quick start:");
  log("  npx mcp-apple-image-playground");
  log("");
  log("Or add to your MCP client config:");
  log(`  "apple_image": { "command": "npx", "args": ["mcp-apple-image-playground"] }`);
  log("");

  if (!swiftOk) {
    warn("Apple Intelligence engine unavailable. Pollinations engine works on any machine.");
  }
}

main();
