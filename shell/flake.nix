{
  description = "PyShell — PySide6/QML X11 status bar for dwm/sadewm";

  inputs = {
    nixpkgs.url     = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachSystem [ "x86_64-linux" "aarch64-linux" ] (system:
      let
        pkgs   = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        # Python environment with all runtime dependencies.
        pythonEnv = python.withPackages (ps: with ps; [
          pyside6    # Qt6 bindings (links against nixpkgs Qt)
          dbus-next  # async D-Bus (notifications, MPRIS)
          pulsectl   # PulseAudio ctypes wrapper
        ]);

        # Source filtered to skip large/irrelevant paths.
        src = pkgs.lib.cleanSourceWith {
          src    = ./.;
          filter = path: _type:
            let rel = pkgs.lib.removePrefix (toString ./. + "/") (toString path); in
            ! pkgs.lib.hasPrefix "pyshell/.venv"    rel &&
            ! pkgs.lib.hasPrefix "pyshell/.qt_path" rel &&
            ! pkgs.lib.hasInfix  "__pycache__"      rel &&
            ! pkgs.lib.hasSuffix ".pyc"             rel &&
            ! pkgs.lib.hasPrefix ".git"             rel;
        };

        pyshell = pkgs.stdenv.mkDerivation {
          pname   = "pyshell";
          version = "0.1.0";
          inherit src;

          nativeBuildInputs = with pkgs; [
            # wrapQtAppsHook populates $qtWrapperArgs with QT_PLUGIN_PATH,
            # QML_IMPORT_PATH, etc., pointing at the correct Nix store paths.
            # It runs during fixupPhase to collect args; we apply them below.
            qt6.wrapQtAppsHook
            makeWrapper
          ];

          # These are scanned by wrapQtAppsHook to build $qtWrapperArgs.
          buildInputs = with pkgs; [
            qt6.qtbase        # core Qt + xcb platform plugin
            qt6.qtdeclarative # QtQuick / QML runtime
            qt6.qtsvg         # SVG image support
            libx11            # window_helper: EWMH / XShape
            libxext           # XShapeCombineRectangles (input region)
            libpulseaudio     # pulsectl ctypes: libpulse.so.0
            xcb-util-cursor   # required by Qt xcb platform plugin since Qt 6.5
          ];

          dontBuild = true;

          # Prevent the hook from auto-wrapping — we do ONE explicit wrap in
          # postFixup after the hook has populated $qtWrapperArgs.
          dontWrapQtApps = true;

          installPhase = ''
            runHook preInstall
            # Install the Python package tree; PYTHONPATH=$out/lib makes
            # `python -m pyshell.main` importable as `pyshell`.
            mkdir -p $out/lib
            cp -r pyshell $out/lib/
            runHook postInstall
          '';

          # postFixup runs AFTER wrapQtAppsHook has populated $qtWrapperArgs.
          # Creating the wrapper here ensures Qt env vars are actually present.
          postFixup = ''
            mkdir -p $out/bin
            makeWrapper ${pythonEnv}/bin/python3 $out/bin/pyshell        \
              --add-flags    "-m pyshell.main"                           \
              --unset        PYTHONPATH                                   \
              --unset        PYTHONHOME                                   \
              --set          PYTHONPATH "$out/lib"                       \
              --prefix LD_LIBRARY_PATH : "${pkgs.libx11}/lib"            \
              --prefix LD_LIBRARY_PATH : "${pkgs.libxext}/lib"           \
              --prefix LD_LIBRARY_PATH : "${pkgs.libpulseaudio}/lib"     \
              --prefix LD_LIBRARY_PATH : "${pkgs.xcb-util-cursor}/lib"   \
              "''${qtWrapperArgs[@]}"
          '';

          meta = with pkgs.lib; {
            description = "PySide6/QML status bar for X11 window managers";
            license     = licenses.mit;
            platforms   = [ "x86_64-linux" "aarch64-linux" ];
            mainProgram = "pyshell";
          };
        };

      in {
        packages.default = pyshell;
        packages.pyshell  = pyshell;

        apps.default = {
          type    = "app";
          program = "${pyshell}/bin/pyshell";
        };

        devShells.default = pkgs.mkShell {
          nativeBuildInputs = with pkgs; [ qt6.wrapQtAppsHook ];
          buildInputs = with pkgs; [
            pythonEnv
            qt6.qtbase
            qt6.qtdeclarative
            qt6.qtsvg
            libx11
            libxext
            libpulseaudio
            xcb-util-cursor
          ];
          shellHook = ''
            export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"
            echo "PyShell dev shell — run: python -m pyshell.main"
          '';
        };
      }
    ) // {

      # ── NixOS module ────────────────────────────────────────────────────────
      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.pyshell;
          pkg = self.packages.${pkgs.system}.default;
        in {
          options.services.pyshell.enable =
            lib.mkEnableOption "PyShell X11 status bar";

          config = lib.mkIf cfg.enable {
            environment.systemPackages = [ pkg ];

            systemd.user.services.pyshell = {
              description = "PyShell X11 status bar";
              wantedBy    = [ "graphical-session.target" ];
              partOf      = [ "graphical-session.target" ];
              after       = [ "graphical-session.target" ];
              serviceConfig = {
                ExecStart  = lib.getExe pkg;
                Restart    = "on-failure";
                RestartSec = "3s";
              };
            };
          };
        };

    };
}

