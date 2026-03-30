{
  description = "sadewm";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems f;
    in {
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
              echo "  make                           build dwm"
              echo "  make debug                     debug build"
              echo "  make clean                     clean build artefacts"
              echo "  ./scripts/test_dwm.sh          run in Xephyr (requires host display)"
              echo "  ./scripts/test_dwm.sh -r       recompile then run in Xephyr"
              echo "  ./scripts/test_dwm.sh -d       debug build + gdb in Xephyr"
              echo "  ./sadewmctl get_state           query WM state (when dwm is running)"
            '';
          };
        });
    };
}
