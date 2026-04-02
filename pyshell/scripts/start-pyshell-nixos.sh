#!/usr/bin/env bash
set -euo pipefail

# start-pyshell-nixos.sh — convenient launcher for PyShell on NixOS
# Places to run:
#  - Manual: ./scripts/start-pyshell-nixos.sh
#  - Systemd user unit (see pyshell.service.sample)

# Change to the repository root (parent of this `pyshell` directory)
# so Python can import the `pyshell` package via `-m pyshell.main`.
cd "$(dirname "$0")/../.."

# Recommended: use nix-shell to provide runtime dependencies
if command -v nix-shell >/dev/null 2>&1; then
  exec nix-shell -p python3 python3Packages.pyside6 python3Packages.dbus-next python3Packages.pulsectl --run 'python3 -m pyshell.main'
fi

# Fallback: system python (assumes required Python packages are installed)
exec python3 -m pyshell.main
