#!/usr/bin/env bash
set -euo pipefail

# start-pyshell-nixos.sh — convenient launcher for sadeshell on NixOS
# Places to run:
#  - Manual: ./scripts/start-pyshell-nixos.sh
#  - Systemd user unit (see sadeshell.service.sample)

# Change to the repository root (parent of this `src` directory)
# so Python can import the `sadeshell` package via `-m sadeshell.main`.
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# Use the Nix flake — produces a properly-wrapped binary with all deps baked in.
# nix run evaluates flake.nix at the repo root and runs the default app.
if command -v nix >/dev/null 2>&1; then
  # Fast path: use a pre-built result if it already exists and is not a dead link.
  if [[ -x "$REPO_ROOT/result/bin/sadeshell" ]]; then
    exec "$REPO_ROOT/result/bin/sadeshell" "$@"
  fi
  exec nix run "path:$REPO_ROOT" -- "$@"
fi

# Absolute fallback: system python (assumes required Python packages are installed).
exec python3 -m sadeshell.main "$@"
