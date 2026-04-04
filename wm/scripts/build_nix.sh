#!/usr/bin/env nix-shell
#!nix-shell -i bash -p xorg.libX11 xorg.libXft xorg.libXinerama fontconfig freetype pkg-config gcc gnumake

# Build script for sadewm using nix-shell
# This allows compilation regardless of host operating system environment

echo "Building sadewm with Nix environment..."
make "$@"
