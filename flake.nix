{
  description = "sadewm window manager + sadeshell status bar";

  inputs = {
    nixpkgs.url     = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachSystem [ "x86_64-linux" "aarch64-linux" ] (system:
      let
        pkgs   = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        # ── sadewm (C / X11 window manager) ──────────────────────────────────
        sadewm = pkgs.stdenv.mkDerivation {
          pname   = "sadewm";
          version = "0.9";
          src     = ./wm;

          nativeBuildInputs = with pkgs; [ gnumake pkg-config ];
          buildInputs = with pkgs; [
            libX11
            libXft
            libXinerama
            fontconfig
            freetype
          ];

          makeFlags = [
            "X11INC=${pkgs.libX11.dev}/include"
            "X11LIB=${pkgs.libX11}/lib"
            "FREETYPEINC=${pkgs.freetype.dev}/include/freetype2"
          ];

          installFlags = [ "PREFIX=${placeholder "out"}" ];

          passthru.providedSessions = [ "sadewm" ];

          meta = with pkgs.lib; {
            description = "sadewm window manager";
            license     = licenses.mit;
            platforms   = [ "x86_64-linux" "aarch64-linux" ];
            mainProgram = "sadewm";
          };
        };

        # ── sadeshell (PySide6/QML status bar) ───────────────────────────────
        pythonEnv = python.withPackages (ps: with ps; [
          pyside6
          dbus-next
          pulsectl
        ]);

        shellSrc = pkgs.lib.cleanSourceWith {
          src    = ./shell;
          filter = path: _type:
            let rel = pkgs.lib.removePrefix (toString ./shell + "/") (toString path); in
            ! pkgs.lib.hasPrefix "src/.venv"    rel &&
            ! pkgs.lib.hasPrefix "src/.qt_path" rel &&
            ! pkgs.lib.hasInfix  "__pycache__"  rel &&
            ! pkgs.lib.hasSuffix ".pyc"         rel &&
            ! pkgs.lib.hasPrefix ".git"         rel;
        };

        sadeshell = pkgs.stdenv.mkDerivation {
          pname   = "sadeshell";
          version = "0.1.0";
          src     = shellSrc;

          nativeBuildInputs = with pkgs; [
            qt6.wrapQtAppsHook
            makeWrapper
          ];

          buildInputs = with pkgs; [
            qt6.qtbase
            qt6.qtdeclarative
            qt6.qtsvg
            libx11
            libxext
            libpulseaudio
            xcb-util-cursor
          ];

          dontBuild = true;
          dontWrapQtApps = true;

          installPhase = ''
            runHook preInstall
            mkdir -p $out/lib
            cp -r src $out/lib/sadeshell
            runHook postInstall
          '';

          postFixup = ''
            mkdir -p $out/bin
            makeWrapper ${pythonEnv}/bin/python3 $out/bin/sadeshell       \
              --add-flags    "-m sadeshell.main"                          \
              --unset        PYTHONPATH                                    \
              --unset        PYTHONHOME                                    \
              --set          PYTHONPATH "$out/lib"                        \
              --prefix LD_LIBRARY_PATH : "${pkgs.libx11}/lib"             \
              --prefix LD_LIBRARY_PATH : "${pkgs.libxext}/lib"            \
              --prefix LD_LIBRARY_PATH : "${pkgs.libpulseaudio}/lib"      \
              --prefix LD_LIBRARY_PATH : "${pkgs.xcb-util-cursor}/lib"    \
              "''${qtWrapperArgs[@]}"
          '';

          meta = with pkgs.lib; {
            description = "PySide6/QML status bar for X11 window managers";
            license     = licenses.mit;
            platforms   = [ "x86_64-linux" "aarch64-linux" ];
            mainProgram = "sadeshell";
          };
        };

        combined = pkgs.symlinkJoin {
          name  = "sadewm-with-sadeshell";
          paths = [ sadewm sadeshell ];
        };

      in {
        packages.default   = combined;
        packages.sadewm    = sadewm;
        packages.sadeshell = sadeshell;

        apps.default = {
          type    = "app";
          program = "${sadewm}/bin/sadewm";
        };

        apps.sadeshell = {
          type    = "app";
          program = "${sadeshell}/bin/sadeshell";
        };

        devShells.default = pkgs.mkShell {
          nativeBuildInputs = with pkgs; [
            # WM build tools
            gcc
            gnumake
            pkg-config
            gdb
            # Shell Qt wrapping
            qt6.wrapQtAppsHook
          ];

          buildInputs = with pkgs; [
            # WM libraries
            libX11
            libXft
            libXinerama
            fontconfig
            freetype
            xorgserver
            xprop
            python3
            # Shell libraries
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
            export MAKEFLAGS="\
              X11INC=${pkgs.libX11.dev}/include \
              X11LIB=${pkgs.libX11}/lib \
              FREETYPEINC=${pkgs.freetype.dev}/include/freetype2"

            # Make sadeshell importable during development
            ln -sfn src shell/sadeshell 2>/dev/null || true
            export PYTHONPATH="$PWD/shell''${PYTHONPATH:+:$PYTHONPATH}"

            echo "sadewm + sadeshell dev shell ready"
            echo "  WM:    cd wm && make"
            echo "  Shell: python -m sadeshell.main"
          '';
        };
      }
    ) // {

      # ── NixOS module: sadewm window manager ─────────────────────────────────
      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg    = config.services.xserver.windowManager.sadewm;
          sadewm = self.packages.${pkgs.system}.sadewm;
        in {
          imports = [ self.nixosModules.sadeshell ];

          options.services.xserver.windowManager.sadewm.enable =
            lib.mkEnableOption "sadewm window manager";

          config = lib.mkIf cfg.enable {
            services.xserver.windowManager.session = lib.singleton {
              name = "sadewm";
              start = ''
                dbus-update-activation-environment --systemd DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS PATH XDG_RUNTIME_DIR XDG_DATA_DIRS
                ${sadewm}/bin/sadewm &
                waitPID=$!
              '';
            };

            environment.systemPackages = [ sadewm ];

            services.sadeshell.enable = lib.mkDefault true;
          };
        };

      # ── NixOS module: sadeshell status bar ──────────────────────────────────
      nixosModules.sadeshell = { config, lib, pkgs, ... }:
        let
          cfg = config.services.sadeshell;
          pkg = self.packages.${pkgs.system}.sadeshell;
        in {
          options.services.sadeshell.enable =
            lib.mkEnableOption "sadeshell X11 status bar";

          config = lib.mkIf cfg.enable {
            environment.systemPackages = [ pkg ];

            systemd.user.services.sadeshell = {
              description = "sadeshell X11 status bar";
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
