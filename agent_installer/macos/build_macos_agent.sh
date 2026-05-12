#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MAC_ROOT="$ROOT/agent_installer/macos"

python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller
python3 -m pip install -r "$ROOT/requirements.txt"

python3 -m PyInstaller --noconfirm --clean "$ROOT/agent_installer/pyinstaller/AriaAgent.spec"

mkdir -p "$MAC_ROOT/dist"
rm -rf "$MAC_ROOT/dist/AriaAgent.app"
cp -R "$ROOT/dist/AriaAgent" "$MAC_ROOT/dist/AriaAgent.app"

bash "$MAC_ROOT/scripts/install_prereqs.sh"
bash "$MAC_ROOT/pkg/build_pkg.sh"

echo "[Build] Done. Installer at $MAC_ROOT/output/AriaAgentSetup.pkg"
