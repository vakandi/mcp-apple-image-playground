#!/usr/bin/env node
/**
 * postinstall.js — Compile Swift helper + install Python deps
 * Runs automatically after `npm install mcp-apple-image-playground`
 * or when invoked via `npx mcp-apple-image-playground`.
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

// ── Step 1: Compile Swift helper ─────────────────────────────────────────────
function compileSwift() {
  if (process.platform !== "darwin") return false;
  if (!fs.existsSync(SWIFT_SRC)) return false;

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

  try {
    execSync("which swiftc", { stdio: "ignore" });
  } catch {
    warn(
      "swiftc not found. Install Xcode CLI tools: xcode-select --install\n" +
        "Apple Intelligence on-device styles unavailable."
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
  } catch {
    warn(
      "Swift compilation failed — Apple Intelligence engine unavailable.\n" +
        "  This is expected on non-macOS or if Xcode CLI tools aren't installed.\n" +
        "  Apple Intelligence on-device styles unavailable."
    );
    return false;
  }
}

// ── Step 2: Install Python dependencies ──────────────────────────────────────
function installPythonDeps() {
  let python = "python3";
  try {
    execSync("which python3", { stdio: "ignore" });
  } catch {
    warn("python3 not found — Python deps not installed. Install Python 3.10+");
    return false;
  }

  try {
    execSync(`${python} -c "import mcp; import PIL"`, { stdio: "ignore", timeout: 5000 });
    log("Python dependencies already installed ✓");
    return true;
  } catch {
  }

  log("Installing Python dependencies...");

  const deps = ['"mcp[cli]"', "pillow"];

  try {
    execSync(`${python} -m pip install --quiet --no-warn-script-location ${deps.join(" ")}`, {
      stdio: "inherit",
      timeout: 120_000,
    });
    log("Python dependencies installed ✓");
    return true;
  } catch {
    warn(
      "pip install failed. Try manually:\n" +
        `  ${python} -m pip install "mcp[cli]" pillow`
    );
    return false;
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────
function main() {
  // Non-macOS: Apple Image Playground unavailable
  if (process.platform !== "darwin") {
    warn("Not macOS — Apple Image Playground requires macOS with Apple Intelligence.");
    installPythonDeps();
    return;
  }

  log("Setting up apple-image-mcp...");

  const swiftOk = compileSwift();
  installPythonDeps();

  console.log("");
  log("Setup complete!");
  console.log("");
  log("Quick start:");
  log("  npx mcp-apple-image-playground");
  console.log("");
  log("Or add to your MCP client config:");
  log('  "apple_image": { "command": "npx", "args": ["mcp-apple-image-playground"] }');
  console.log("");
}

main();
