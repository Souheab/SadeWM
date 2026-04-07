{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  name = "sadeshell-shell";

  buildInputs = with pkgs; [ python3 python3Packages.virtualenv ];

  # Create and activate a .venv and install runtime packages on first entry.
  shellHook = ''
    echo "Entering sadeshell dev shell"
    if [ ! -d .venv ]; then
      echo "Creating virtualenv .venv and installing Python dependencies (PySide6, dbus-next, pulsectl)."
      python3 -m venv .venv
      . .venv/bin/activate
      python -m pip install --upgrade pip
      python -m pip install PySide6 dbus-next pulsectl emoji
    else
      . .venv/bin/activate
    fi

    export PYTHONPATH="$PWD:$PYTHONPATH"
    echo "Activated .venv; run: python -m sadeshell.main"
  '';
}
