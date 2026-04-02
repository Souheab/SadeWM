#!/usr/bin/env bash
# Build script for NixOS: fetch deps ad-hoc with nix-shell or `nix shell`, then compile pulse_monitor.c
# Modeled on build_audio.sh but ensures dependencies are available on NixOS without changing system state.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/pulse_monitor.c"
OUT="$SCRIPT_DIR/pulse_monitor"

if [ ! -f "$SRC" ]; then
  echo "Source not found: $SRC" >&2
  exit 1
fi

# Packages to provide via Nix
PKGS="gcc pkg-config pulseaudio"

if command -v nix-shell >/dev/null 2>&1; then
  # Use nix-shell (older CLI)
  nix-shell -p $PKGS --run "bash -lc 'gcc -O2 -Wall -Wextra -o \"$OUT\" \"$SRC\" \$(pkg-config --cflags --libs libpulse)'"
elif command -v nix >/dev/null 2>&1; then
  # Use modern `nix` CLI
  nix shell nixpkgs#gcc nixpkgs#pkg-config nixpkgs#pulseaudio --run "bash -lc 'gcc -O2 -Wall -Wextra -o \"$OUT\" \"$SRC\" \$(pkg-config --cflags --libs libpulse)'"
else
  echo "Nix not found. Install Nix or use build_audio.sh instead." >&2
  exit 1
fi

echo "Built: $OUT"
