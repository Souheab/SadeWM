{ pkgs ? import <nixpkgs> { } }:

let
  devPythonEnv = pkgs.python3.withPackages (ps: with ps; [
    pytest
    xlib
    pillow
    emoji
    pyside6
    tomlkit
    dbus-next
    pulsectl
    xcffib
    build
    setuptools
    pip
    ruff
  ]);
in
pkgs.mkShell {
  nativeBuildInputs = with pkgs; [
    # WM build tools
    gcc
    gnumake
    pkg-config
    gdb
    cargo
    rustc
    rustfmt
    clippy
    # Shell Qt wrapping
    qt6.wrapQtAppsHook
  ];

  buildInputs = with pkgs; [
    # WM libraries and X11 development tools
    libx11
    libxinerama
    xorgserver
    xrandr
    xprop
    xdpyinfo
    xwd
    imagemagick
    picom
    dbus
    xterm
    wmctrl
    cairo
    libxscrnsaver

    # Shell libraries and development/testing tools
    devPythonEnv
    qt6.qtbase
    qt6.qtdeclarative
    qt6.qtsvg
    libx11
    libxext
    libpulseaudio
    xcb-util-cursor
  ];

  shellHook = ''
    # Make the Python applications importable during development.
    export PYTHONPATH="$PWD/shell/src:$PWD/settings-app:$PWD/xdrive''${PYTHONPATH:+:$PYTHONPATH}"

    echo "sadewm + sadeshell dev shell ready"
    echo "  WM:       cargo build --manifest-path wm/Cargo.toml"
    echo "  Shell:    python -m sadeshell.main"
    echo "  Settings: python -m sadesettings.main"
  '';
}
