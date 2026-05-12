#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
MAC_ROOT="$ROOT/agent_installer/macos"
PKG_ROOT="$MAC_ROOT/pkg"
OUT_DIR="$MAC_ROOT/output"

APP_SRC="$MAC_ROOT/dist/AriaAgent.app"
APP_DST="$PKG_ROOT/payload/Applications/AriaAgent.app"

rm -rf "$PKG_ROOT/payload"
mkdir -p "$PKG_ROOT/payload/Applications"
mkdir -p "$OUT_DIR"

cp -R "$APP_SRC" "$APP_DST"
chmod +x "$PKG_ROOT/postinstall"

pkgbuild \
  --root "$PKG_ROOT/payload" \
  --identifier "com.projectaria.agent" \
  --version "1.0.0" \
  --scripts "$PKG_ROOT" \
  "$OUT_DIR/AriaAgent-component.pkg"

productbuild \
  --package "$OUT_DIR/AriaAgent-component.pkg" \
  "$OUT_DIR/AriaAgentSetup.pkg"

echo "[PKG] Created $OUT_DIR/AriaAgentSetup.pkg"
