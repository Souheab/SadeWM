{ pkgs, nixpkgs, system, module }:
let
  inherit (pkgs) lib;
  checkBackend = backend:
    let
      config = (nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [ module {
          system.stateVersion = "26.05";
          services.xserver.windowManager.sadewm = {
            enable = true;
            inherit backend;
          };
          services.xserver.displayManager.lightdm.greeters.sadewm.enable = true;
          # Downstream modules can extend the service's path normally.
          systemd.user.services.sadeshell.path = [ "/extra-session-tools" ];
        } ];
      }).config;
      executable = if backend == "rust" then "sadewm-rs" else "sadewm";
      session = lib.findFirst (s: s.name == "SADE") null config.services.xserver.windowManager.session;
      service = config.systemd.user.services.sadeshell;
    in
    assert lib.hasPrefix "/run/wrappers/bin:%h/.nix-profile/bin:" service.environment.PATH;
    assert lib.hasInfix "/run/current-system/sw/bin:" service.environment.PATH;
    assert lib.hasInfix "/extra-session-tools/bin:" service.environment.PATH;
    assert lib.hasInfix "/bin/${executable} &" session.start;
    assert config.services.xserver.displayManager.lightdm.greeter.name == "sadewm-greeter";
    {
      inherit backend;
      path = service.environment.PATH;
      execStart = service.serviceConfig.ExecStart;
      session = session.start;
      packages = map (p: p.name) config.environment.systemPackages;
    };
in
pkgs.writeText "sade-nixos-modules.json" (builtins.toJSON (map checkBackend [ "go" "rust" ]))
