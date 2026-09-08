{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  packages = [ (pkgs.python3.withPackages (ps: with ps; [
    pyside6 dbus-next pulsectl emoji xlib pillow xcffib pytest build setuptools
  ])) pkgs.qt6.qtdeclarative pkgs.libxcb ];
  shellHook = ''
    export PYTHONPATH="${toString ./src}''${PYTHONPATH:+:$PYTHONPATH}"
    echo "Run python -m sadeshell.main (or use nix develop from the repository root)"
  '';
}
