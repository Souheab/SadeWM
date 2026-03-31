{
  description = "sadewm";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems f;
    in {
      packages = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in {
          default = pkgs.stdenv.mkDerivation {
            pname = "sadewm";
            version = "0.9";
            src = self;

            nativeBuildInputs = with pkgs; [ gnumake pkg-config ];
            buildInputs = with pkgs; [
              libX11
              libXft
              libXinerama
              fontconfig
              freetype
            ];

            # Override the hardcoded paths in config.mk so the Nix store paths
            # are used instead of /usr/X11R6 and /usr/include/freetype2.
            makeFlags = [
              "X11INC=${pkgs.libX11.dev}/include"
              "X11LIB=${pkgs.libX11}/lib"
              "FREETYPEINC=${pkgs.freetype.dev}/include/freetype2"
            ];

            installFlags = [ "PREFIX=${placeholder "out"}" ];

            passthru.providedSessions = [ "sadewm" ];

            meta = with pkgs.lib; {
              description = "sadewm";
              license = licenses.mit;
              platforms = [ "x86_64-linux" "aarch64-linux" ];
              mainProgram = "sadewm";
            };
          };
        });

      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.xserver.windowManager.sadewm;
          sadewm = self.packages.${pkgs.system}.default;
        in {
          options.services.xserver.windowManager.sadewm.enable =
            lib.mkEnableOption "sadewm window manager";

          config = lib.mkIf cfg.enable {
            services.xserver.windowManager.session = lib.singleton {
              name = "sadewm";
              start = ''
                ${sadewm}/bin/sadewm &
                waitPID=$!
              '';
            };

            environment.systemPackages = [ sadewm ];
          };
        };

      devShells = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in {
          default = pkgs.mkShell {
            # Build tools
            nativeBuildInputs = with pkgs; [
              gcc
              gnumake
              pkg-config
              gdb
            ];

            # Libraries (their Nix setup hooks populate NIX_CFLAGS_COMPILE /
            # NIX_LDFLAGS so the gcc wrapper finds headers and libs even with
            # the hardcoded paths in config.mk overridden via MAKEFLAGS below)
            buildInputs = with pkgs; [
              libX11
              libXft
              libXinerama
              fontconfig
              freetype
              xorgserver
              xprop
              python3
            ];

            # config.mk hardcodes /usr/X11R6/include and friends.
            # MAKEFLAGS variable assignments act as command-line overrides so
            # every make invocation, including those inside the test script,
            # picks up the correct Nix store paths automatically.
            shellHook = ''
              export MAKEFLAGS="\
                X11INC=${pkgs.libX11.dev}/include \
                X11LIB=${pkgs.libX11}/lib \
                FREETYPEINC=${pkgs.freetype.dev}/include/freetype2"

              echo "sadewm dev shell ready"
              echo "  make                           build sadewm"
              echo "  make debug                     debug build"
              echo "  make clean                     clean build artefacts"
              echo "  ./scripts/test_sadewm.sh          run in Xephyr (requires host display)"
              echo "  ./scripts/test_sadewm.sh -r       recompile then run in Xephyr"
              echo "  ./scripts/test_sadewm.sh -d       debug build + gdb in Xephyr"
              echo "  ./sadewmctl get_state           query WM state (when sadewm is running)"            '';
          };
        });
    };
}
