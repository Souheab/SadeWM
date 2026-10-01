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
        gitRevision = self.rev or (self.dirtyRev or "unknown");

        # ── sadeshell (PySide6/QML status bar) ───────────────────────────────
        pythonEnv = python.withPackages (ps: with ps; [
          pyside6
          dbus-next
          pulsectl
          emoji
          xlib
          pillow
          xcffib
        ]);

        settingsPythonEnv = python.withPackages (ps: with ps; [ pyside6 tomlkit ]);

        shellSrc = pkgs.lib.cleanSourceWith {
          src    = ./shell;
          filter = path: _type:
            let rel = pkgs.lib.removePrefix (toString ./shell + "/") (toString path); in
            baseNameOf path != "result" &&
            ! pkgs.lib.hasPrefix "build" rel &&
            ! pkgs.lib.hasPrefix "dist" rel &&
            ! pkgs.lib.hasPrefix "src/.venv"    rel &&
            ! pkgs.lib.hasPrefix "src/.qt_path" rel &&
            ! pkgs.lib.hasInfix  "__pycache__"  rel &&
            ! pkgs.lib.hasSuffix ".pyc"         rel &&
            ! pkgs.lib.hasPrefix ".git"         rel;
        };

        settingsSrc = pkgs.lib.cleanSourceWith {
          src    = ./settings-app;
          filter = path: _type:
            let rel = pkgs.lib.removePrefix (toString ./settings-app + "/") (toString path); in
            ! pkgs.lib.hasInfix "__pycache__" rel &&
            ! pkgs.lib.hasSuffix ".pyc"       rel &&
            ! pkgs.lib.hasPrefix ".git"       rel;
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
            cp -r src/sadeshell $out/lib/sadeshell
            runHook postInstall
          '';

          postFixup = ''
            mkdir -p $out/bin $out/libexec
            # Capture the session before Qt/Python and private helpers alter it.
            # AppService restores it for desktop entries, terminals and scopes.
            makeWrapper ${pythonEnv}/bin/python3 $out/libexec/sadeshell-python \
              --run ${pkgs.lib.escapeShellArg (builtins.readFile ./nix/save-session-environment.sh)} \
              --unset        PYTHONPATH                                    \
              --unset        PYTHONHOME                                    \
              --set          PYTHONPATH "$out/lib"                        \
              --suffix PATH : "${pkgs.lib.makeBinPath [ pkgs.xrandr pkgs.networkmanager pkgs.bluez ]}" \
              --prefix LD_LIBRARY_PATH : "${pkgs.libx11}/lib"             \
              --prefix LD_LIBRARY_PATH : "${pkgs.libxext}/lib"            \
              --prefix LD_LIBRARY_PATH : "${pkgs.libpulseaudio}/lib"      \
              --prefix LD_LIBRARY_PATH : "${pkgs.xcb-util-cursor}/lib"    \
              "''${qtWrapperArgs[@]}"
            makeWrapper $out/libexec/sadeshell-python $out/bin/sadeshell \
              --add-flags "-m sadeshell.main"
          '';

          meta = with pkgs.lib; {
            description = "PySide6/QML status bar for X11 window managers";
            license     = licenses.mit;
            platforms   = [ "x86_64-linux" "aarch64-linux" ];
            mainProgram = "sadeshell";
          };
        };

        # ── sadesettings (PySide6 settings app) ──────────────────────────────
        sadesettings = pkgs.stdenv.mkDerivation {
          pname   = "sadesettings";
          version = "0.1.0";
          src     = settingsSrc;

          nativeBuildInputs = with pkgs; [
            qt6.wrapQtAppsHook
            makeWrapper
          ];

          buildInputs = with pkgs; [
            qt6.qtbase
            qt6.qtdeclarative
            kdePackages.breeze
            kdePackages.plasma-integration
            libx11
            libxext
            xcb-util-cursor
          ];

          dontBuild = true;
          dontWrapQtApps = true;

          installPhase = ''
            runHook preInstall
            mkdir -p $out/lib
            cp -r sadesettings $out/lib/sadesettings
            runHook postInstall
          '';

          postFixup = ''
            mkdir -p $out/bin
            makeWrapper ${settingsPythonEnv}/bin/python3 $out/bin/sadesettings       \
              --add-flags    "-m sadesettings.main"                         \
              --unset        PYTHONPATH                                      \
              --unset        PYTHONHOME                                      \
              --set          PYTHONPATH "$out/lib"                          \
              --set SADE_THEME_DATA_DIRS "${pkgs.kdePackages.breeze}/share" \
              --prefix XDG_DATA_DIRS : "${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}" \
              --prefix GIO_EXTRA_MODULES : "${pkgs.dconf.lib}/lib/gio/modules" \
              --prefix PATH : "${pkgs.glib.bin}/bin"                        \
              --suffix PATH : "${pkgs.xrandr}/bin"                          \
              --prefix LD_LIBRARY_PATH : "${pkgs.libx11}/lib"               \
              --prefix LD_LIBRARY_PATH : "${pkgs.libxext}/lib"              \
              --prefix LD_LIBRARY_PATH : "${pkgs.xcb-util-cursor}/lib"      \
              "''${qtWrapperArgs[@]}"
          '';

          meta = with pkgs.lib; {
            description = "PySide6 settings app for SADE";
            license     = licenses.mit;
            platforms   = [ "x86_64-linux" "aarch64-linux" ];
            mainProgram = "sadesettings";
          };
        };

        # ── sadewm (Go / X11 window manager) ─────────────────────────────────
        sadewm = pkgs.buildGoModule {
          pname   = "sadewm";
          version = "0.1";
          src     = ./wm;

          vendorHash = null;  # uses go mod vendor or set to actual hash
          ldflags = [ "-X main.gitCommit=${gitRevision}" ];

          nativeBuildInputs = with pkgs; [
            pkg-config
            makeWrapper
          ];

          buildInputs = with pkgs; [
            libx11
            libxinerama
            libxcursor
            cairo
            libxext
            libxscrnsaver
          ];

          subPackages = [ "cmd/sadewm" ];

          postFixup = ''
            wrapProgram $out/bin/sadewm \
              --suffix PATH : "${pkgs.lib.makeBinPath [ pkgs.xrandr ]}"
          '';

          meta = with pkgs.lib; {
            description = "sadewm window manager";
            license     = licenses.mit;
            platforms   = [ "x86_64-linux" "aarch64-linux" ];
            mainProgram = "sadewm";
          };
        };

        sadewm-rs = pkgs.rustPlatform.buildRustPackage {
          pname = "sadewm-rs";
          version = "0.1.0";
          src = pkgs.lib.cleanSourceWith {
            src = ./wm-rs;
            filter = path: type:
              pkgs.lib.cleanSourceFilter path type &&
              !(pkgs.lib.hasPrefix "target" (pkgs.lib.removePrefix (toString ./wm-rs + "/") (toString path)));
          };
          cargoLock.lockFile = ./wm-rs/Cargo.lock;
          SADEWM_REVISION = gitRevision;
          nativeBuildInputs = [ pkgs.makeWrapper ];
          postInstall = ''
            install -Dm644 assets/LICENSE-DejaVu $out/share/licenses/sadewm-rs/DejaVu
            install -Dm644 assets/LICENSE-xgbutil $out/share/licenses/sadewm-rs/xgbutil
          '';
          postFixup = ''
            wrapProgram $out/bin/sadewm-rs \
              --suffix PATH : "${pkgs.lib.makeBinPath [ pkgs.xrandr ]}"
          '';
          meta = with pkgs.lib; {
            description = "Rust SADE X11 window manager";
            license = licenses.mit;
            platforms = [ "x86_64-linux" "aarch64-linux" ];
            mainProgram = "sadewm-rs";
          };
        };

        # ── sadewm-greeter (Qt5/QML LightDM greeter) ─────────────────────────
        sadewm-greeter = pkgs.stdenv.mkDerivation {
          pname   = "sadewm-greeter";
          version = "0.1.0";
          src     = ./lightdm-qml-greeter;

          nativeBuildInputs = with pkgs; [
            cmake
            pkg-config
            libsForQt5.wrapQtAppsHook
          ];

          buildInputs = with pkgs; [
            libsForQt5.qtbase
            libsForQt5.qtdeclarative
            libsForQt5.qtquickcontrols2
            libsForQt5.qtgraphicaleffects
            libsForQt5.qtsvg
            lightdm_qt
          ];

          # Pass through the standard cmake install prefix.
          cmakeFlags = [ "-DCMAKE_BUILD_TYPE=Release" ];

          meta = with pkgs.lib; {
            description = "LightDM QML greeter matching the sadewm/sadeshell aesthetic";
            license     = licenses.mit;
            platforms   = [ "x86_64-linux" "aarch64-linux" ];
            mainProgram = "sadewm-greeter";
          };
        };

        combined = pkgs.symlinkJoin {
          name  = "sadewm-with-sadeshell";
            paths = [ sadewm sadeshell sadesettings sadewm-greeter ];
        };

      in {
        packages.default        = combined;
        packages.sadewm         = combined;
        packages.sadewm-rs      = sadewm-rs;
        packages.sadeshell      = sadeshell;
        packages.sadesettings   = sadesettings;
        packages.sadewm-greeter = sadewm-greeter;

        checks.packages = combined;
        checks.sadewm-rs = sadewm-rs;
        checks.nixos-modules = import ./nix/check-modules.nix {
          inherit pkgs nixpkgs system;
          module = self.nixosModules.default;
        };
        checks.desktop-startup = pkgs.runCommand "sade-desktop-startup" {
          nativeBuildInputs = [
            (python.withPackages (ps: [ ps.xlib ]))
            pkgs.xorgserver
            pkgs.dbus
          ];
          TEST_SHELL = pkgs.runtimeShell;
        } ''
          dbus-run-session --config-file=${pkgs.dbus}/share/dbus-1/session.conf -- python ${./nix/check-packages.py} \
            ${sadeshell} ${sadesettings} ${sadewm-greeter} ${sadewm} ${sadewm-rs}
          touch $out
        '';

        apps.default = {
          type    = "app";
          program = "${sadewm}/bin/sadewm";
          meta = sadewm.meta;
        };

        apps.sadeshell = {
          type    = "app";
          program = "${sadeshell}/bin/sadeshell";
          meta = sadeshell.meta;
        };

        apps.sadewm-rs = {
          type = "app";
          program = "${sadewm-rs}/bin/sadewm-rs";
          meta = sadewm-rs.meta;
        };

        apps.sadesettings = {
          type    = "app";
          program = "${sadesettings}/bin/sadesettings";
          meta = sadesettings.meta;
        };

        apps.sadewm-greeter = {
          type    = "app";
          program = "${sadewm-greeter}/bin/sadewm-greeter";
          meta = sadewm-greeter.meta;
        };

        # Keep nix develop and nix-shell on the same development environment.
        devShells.default = import ./shell.nix { inherit pkgs; };

        devShells.sadewm-greeter = pkgs.mkShell {
          nativeBuildInputs = with pkgs; [
            cmake
            pkg-config
            libsForQt5.wrapQtAppsHook
          ];

          buildInputs = with pkgs; [
            libsForQt5.qtbase
            libsForQt5.qtdeclarative
            libsForQt5.qtquickcontrols2
            libsForQt5.qtgraphicaleffects
            libsForQt5.qtsvg
            lightdm_qt
          ];

          shellHook = ''
            echo "sadewm-greeter dev shell ready (Qt5 + LightDM)"
            echo "  Build: mkdir -p lightdm-qml-greeter/build && cd lightdm-qml-greeter/build && cmake .. && make"
          '';
        };
      }
    ) // {

      # ── NixOS module: sadewm window manager ─────────────────────────────────
      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg   = config.services.xserver.windowManager.sadewm;
          packages = self.packages.${pkgs.stdenv.hostPlatform.system};
          wmPkg = if cfg.backend == "rust" then packages.sadewm-rs else packages.sadewm;
          wmExecutable = if cfg.backend == "rust" then "sadewm-rs" else "sadewm";
        in {
          imports = [ self.nixosModules.sadeshell self.nixosModules.sadewm-greeter ];

          options.services.xserver.windowManager.sadewm = {
            enable = lib.mkEnableOption "sadewm window manager";
            backend = lib.mkOption {
              type = lib.types.enum [ "go" "rust" ];
              default = "go";
              description = "Window manager implementation used by the SADE session.";
            };
          };

          config = lib.mkIf cfg.enable {
            services.xserver.windowManager.session = [
              {
                name = "SADE";
                managed = "desktop";
                start = ''
                  export QT_QPA_PLATFORMTHEME=kde
                  ${packages.sadesettings}/bin/sadesettings --apply-appearance || true
                  ${wmPkg}/bin/${wmExecutable} &
                  waitPID=$!

                  systemctl --user start sade.target
                  trap 'systemctl --user stop sade.target' EXIT
                '';
              }
            ];

            environment.systemPackages = [
              wmPkg
              pkgs.kdePackages.breeze
              pkgs.kdePackages.breeze.qt5
              pkgs.kdePackages.plasma-integration
              pkgs.kdePackages.plasma-integration.qt5
            ] ++ lib.optionals (cfg.backend == "rust") [ packages.sadeshell packages.sadesettings packages.sadewm-greeter ];

            # Expose both Qt plugin versions without forcing a widget style;
            # SadeSettings chooses the style and palette through kdeglobals.
            qt.enable = lib.mkDefault true;
            programs.dconf.enable = lib.mkDefault true;

            systemd.user.targets.sade = {
              description = "SADE desktop session";
            };

            services.sadeshell.enable = lib.mkDefault true;
          };
        };

      # ── NixOS module: sadeshell status bar ──────────────────────────────────
      nixosModules.sadeshell = { config, lib, pkgs, ... }:
        let
          cfg = config.services.sadeshell;
          pkg = self.packages.${pkgs.stdenv.hostPlatform.system}.sadeshell;
        in {
          options.services.sadeshell.enable =
            lib.mkEnableOption "sadeshell X11 status bar";

          config = lib.mkIf cfg.enable {
            environment.systemPackages = [ pkg ];

            systemd.user.services.sadeshell = {
              description = "sadeshell X11 status bar";
              wantedBy    = [ "sade.target" ];
              partOf      = [ "sade.target" ];
              after       = [ "sade.target" ];
              # Resolve session tools from host/user profiles before NixOS's
              # default service utilities. Keep this composable via service.path.
              path = lib.mkBefore [
                "/run/wrappers"
                "%h/.nix-profile"
                "%h/.local/state/nix/profile"
                "/etc/profiles/per-user/%u"
                "/run/current-system/sw"
              ];
              serviceConfig = {
                ExecStart       = lib.getExe pkg;
                Restart         = "on-failure";
                RestartSec      = "3s";
                StandardOutput  = "journal";
                StandardError   = "journal";
              };
              environment = {
                PYTHONUNBUFFERED = "1";
                XDG_CURRENT_DESKTOP = "SADE";
                QT_QPA_PLATFORMTHEME = "kde";
              };
            };
          };
        };

      # ── NixOS module: sadewm-greeter (LightDM QML greeter) ──────────────────
      nixosModules.sadewm-greeter = { config, lib, pkgs, ... }:
        let
          cfg = config.services.xserver.displayManager.lightdm.greeters.sadewm;
        in {
          options.services.xserver.displayManager.lightdm.greeters.sadewm = {

            enable = lib.mkOption {
              type        = lib.types.bool;
              default     = false;
              description = ''
                Whether to enable sadewm-greeter as the LightDM greeter.

                Enabling this option automatically enables LightDM, disables
                the default GTK greeter, and points LightDM at the sadewm QML
                greeter provided by the sadewm flake.
              '';
            };

            package = lib.mkOption {
              type        = lib.types.package;
              default     = self.packages.${pkgs.stdenv.hostPlatform.system}.sadewm-greeter;
              defaultText = lib.literalExpression
                "sadewm.packages.\${pkgs.stdenv.hostPlatform.system}.sadewm-greeter";
              description = ''
                The sadewm-greeter package to use.  Override this if you are
                building the greeter yourself or need a patched version.
              '';
            };

          };

          config = lib.mkIf cfg.enable {
            services.xserver.displayManager.lightdm = {
              enable              = lib.mkDefault true;
              greeters.gtk.enable = false;
              # LightDM sets greeters-directory to greeter.package and then
              # looks for <name>.desktop at the root of that directory.
              # We create a flat xgreeters derivation (same pattern as
              # lightdm-slick-greeter.xgreeters) so the .desktop file is at
              # the package root rather than buried in share/xgreeters/.
              greeter = lib.mkDefault {
                package = pkgs.runCommand "sadewm-greeter-xgreeters" {} ''
                  mkdir -p "$out"
                  cp ${cfg.package}/share/xgreeters/sadewm-greeter.desktop "$out/"
                '';
                name = "sadewm-greeter";
              };
            };

            environment.systemPackages = [ cfg.package ];
          };
        };

    };
}
