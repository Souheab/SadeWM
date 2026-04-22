# sadewm LightDM QML greeter

A minimal LightDM greeter written in C++ + QML that mirrors the Tokyo-
Night aesthetic of [`sadeshell`](../shell).  It uses
[`liblightdm-qt5-3`](https://github.com/canonical/lightdm) for
authentication and starting the selected session; all UI lives in
QML under [`qml/`](qml).

## Look & feel

* Same palette / spacing / radii as the sadeshell bar (see
  [`qml/Theme.qml`](qml/Theme.qml) vs
  [`../shell/src/components/shared/Theme.qml`](../shell/src/components/shared/Theme.qml)).
* Fullscreen frameless window, vertical gradient backdrop with a soft
  accent glow behind a centered login card.
* Top-left: large live clock + date.
* Top-right: power pills (Suspend / Hibernate / Restart / Shutdown) —
  each hidden if the running LightDM daemon says the action isn't
  available.
* Card: username + password fields, PAM status line, session picker
  dropdown and a highlighted "Log in" pill.

## Files

```
lightdm-qml-greeter/
├── CMakeLists.txt
├── data/sadewm-greeter.desktop   # xgreeters entry installed by cmake
├── src/
│   ├── main.cpp                  # QGuiApplication + QQmlEngine glue
│   ├── greeterbridge.{h,cpp}     # QLightDM::Greeter → QML bridge
└── qml/
    ├── Greeter.qml               # root Window
    ├── LoginCard.qml             # username/password card
    ├── PowerButtons.qml          # pill row using PowerInterface
    ├── SessionPicker.qml         # session dropdown
    ├── PillButton.qml            # shared button primitive
    └── Theme.qml                 # singleton palette
```

The C++ side is deliberately thin:

* `main.cpp` boots a `QGuiApplication`, `connectSync()`s to the
  LightDM daemon, instantiates `QLightDM::UsersModel`,
  `SessionsModel`, `PowerInterface` and the bridge, and exposes them
  as QML context properties (`greeter`, `usersModel`, `sessionsModel`,
  `power`, `bridge`).
* `GreeterBridge` forwards LightDM's `showPrompt` / `showMessage` /
  `authenticationComplete` signals in a QML-friendly form (plain
  strings + `bool secret/error`) and keeps enough state for the UI
  (`lastPrompt`, `awaitingResponse`, …).

## Build

### Nix (recommended)

```bash
nix build .#sadewm-greeter              # build the greeter
nix build                                # build wm + shell + greeter
```

The output contains `bin/sadewm-greeter` and
`share/xgreeters/sadewm-greeter.desktop`.

### CMake (inside `nix develop`)

```bash
nix develop                              # drops you into a shell with
                                         # Qt5 + liblightdm-qt5-3
cmake -S lightdm-qml-greeter -B lightdm-qml-greeter/build
cmake --build lightdm-qml-greeter/build -j
```

Dependencies (already provided by the flake's dev shell):

* Qt 5 ≥ 5.15: `Qt5Core`, `Qt5Gui`, `Qt5Qml`, `Qt5Quick`,
  `qtquickcontrols2`
* `liblightdm-qt5-3` (nixpkgs `lightdm_qt`)
* `pkg-config`, `cmake` ≥ 3.16, a C++17 compiler

On Debian/Ubuntu the equivalent packages are
`qtbase5-dev qtdeclarative5-dev qml-module-qtquick-controls2
liblightdm-qt5-3-dev cmake pkg-config g++`.

## Running under LightDM

1. Install the package:

   ```bash
   nix build .#sadewm-greeter
   sudo cp -r ./result/{bin,share} /usr/local/
   ```

   (or enable the NixOS module — see below.)

2. Point LightDM at it in `/etc/lightdm/lightdm.conf`:

   ```ini
   [Seat:*]
   greeter-session=sadewm-greeter
   ```

3. Restart `lightdm.service`.

### NixOS

The flake exposes `nixosModules.sadewm-greeter` which both installs the
package and registers it as an LightDM greeter.  Minimal example:

```nix
{
  imports = [ inputs.sadewm.nixosModules.sadewm-greeter ];
  services.xserver.displayManager.lightdm = {
    enable = true;
    greeter = {
      enable  = true;
      package = inputs.sadewm.packages.${pkgs.system}.sadewm-greeter;
      name    = "sadewm-greeter";
    };
  };
}
```

Alternatively the `services.xserver.displayManager.lightdm.greeters.sadewm.enable`
option is provided for consistency with the other greeter modules —
see `flake.nix` for details.

## Development / smoke-test

You cannot fully exercise the greeter without a LightDM daemon
(`connectSync()` will fail and the process will exit with code 1), but
you can at least verify that the binary builds, links against
`liblightdm-qt5-3` and loads its QML without errors:

```bash
ldd ./result/bin/sadewm-greeter | grep lightdm   # should show liblightdm-qt5-3
QT_DEBUG_PLUGINS=1 ./result/bin/sadewm-greeter   # will error "failed to
                                                 # connect to the LightDM
                                                 # daemon" if run standalone
```

To iterate on the UI without LightDM, set `SADEWM_GREETER_DEV=1`:

```bash
xvfb-run -a env SADEWM_GREETER_DEV=1 ./result/bin/sadewm-greeter
```

This skips `connectSync()` and still exposes the `greeter` /
`usersModel` / `sessionsModel` / `power` context properties so the QML
tree loads end-to-end (authentication just won't work).

## Layout conventions

QML components follow the same rules as sadeshell:

* CamelCase filenames, one top-level component per file.
* Shared tokens live in the `Theme` singleton — don't hard-code
  colours or sizes elsewhere.
* Keep the C++ layer free of presentation logic; anything that needs
  to change for theming or layout belongs in QML.
