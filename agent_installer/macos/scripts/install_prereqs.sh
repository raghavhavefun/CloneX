#!/usr/bin/env bash
set -euo pipefail

echo "[Prereqs] Checking OBS..."
if ! command -v obs >/dev/null 2>&1; then
  echo "[Prereqs] OBS not found. TODO: trigger OBS installer here."
fi

echo "[Prereqs] Checking BlackHole..."
if ! system_profiler SPAudioDataType | grep -qi blackhole; then
  echo "[Prereqs] BlackHole not found. TODO: install BlackHole package here."
fi

echo "[Prereqs] Done."
