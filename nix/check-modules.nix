{ pkgs, nixpkgs, system, module }:
let
  inherit (pkgs) lib;
  evaluate = settings: (nixpkgs.lib.nixosSystem {
    inherit system;
    modules = [ module {
      system.stateVersion = "26.05";
      services.xserver.windowManager.sadewm = settings;
      services.xserver.displayManager.lightdm.greeters.sadewm.enable = true;
      # Downstream modules can extend the service's path normally.
      systemd.user.services.sadeshell.path = [ "/extra-session-tools" ];
    } ];
  }).config;
  check = settings:
    let
      config = evaluate settings;
      session = lib.findFirst (s: s.name == "SADE") null config.services.xserver.windowManager.session;
      service = config.systemd.user.services.sadeshell;
      backendWarnings = builtins.filter (lib.hasInfix "sadewm.backend") config.warnings;
      expectedWarnings = if settings ? backend then 1 else 0;
      packageNames = map (p: p.pname or p.name) config.environment.systemPackages;
    in
    assert lib.hasPrefix "/run/wrappers/bin:%h/.nix-profile/bin:" service.environment.PATH;
    assert lib.hasInfix "/run/current-system/sw/bin:" service.environment.PATH;
    assert lib.hasInfix "/extra-session-tools/bin:" service.environment.PATH;
    assert lib.hasInfix "/bin/sadewm &" session.start;
    assert !(lib.hasInfix "/bin/sadewm-rs &" session.start);
    assert builtins.length backendWarnings == expectedWarnings;
    assert builtins.all (name: builtins.elem name packageNames) [ "sadewm" "sadeshell" "sadesettings" "sadewm-greeter" ];
    assert config.services.xserver.displayManager.lightdm.greeter.name == "sadewm-greeter";
    {
      selection = settings.backend or "default";
      warnings = backendWarnings;
      path = service.environment.PATH;
      execStart = service.serviceConfig.ExecStart;
      session = session.start;
      packages = packageNames;
    };
  rejectedGo = builtins.tryEval (evaluate { enable = true; backend = "go"; }).services.xserver.windowManager.sadewm.backend;
  disabled = evaluate { enable = false; };
in
assert !rejectedGo.success;
assert builtins.filter (lib.hasInfix "sadewm.backend") disabled.warnings == [];
assert !(builtins.any (s: s.name == "SADE") disabled.services.xserver.windowManager.session);
pkgs.writeText "sade-nixos-modules.json" (builtins.toJSON (map check [
  { enable = true; }
  { enable = true; backend = "rust"; }
]))
