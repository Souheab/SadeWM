"""PyShell main entry point — launches the PySide6/QML bar."""

import sys
import os
import signal

from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
from PySide6.QtCore import QUrl, QLibraryInfo

# TODO(nix-packaging): This entire QML path resolution block is a workaround for
# running pyshell outside of a proper Nix derivation.  When the app is packaged
# with wrapQtAppsHook (or equivalent), Qt sets up QML2_IMPORT_PATH automatically
# and none of this is needed.  Remove _qt_qml_import_paths(), _QML_PATH_CACHE,
# and the cache load/save calls in main() at that point.

_QML_PATH_CACHE = os.path.join(os.path.dirname(__file__), ".qt_path_cache.env")


def _load_cached_qml_paths() -> list[str] | None:
    """Return cached QML import paths if the cache exists and all paths are still valid."""
    try:
        with open(_QML_PATH_CACHE) as f:
            paths = [line.rstrip("\n") for line in f if line.strip()]
        if paths and all(os.path.isdir(p) for p in paths):
            return paths
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return None


def _save_qml_path_cache(paths: list[str]) -> None:
    try:
        with open(_QML_PATH_CACHE, "w") as f:
            f.write("\n".join(paths) + "\n")
    except Exception:
        pass


def _discover_qml_import_paths() -> list[str]:
    """Discover QML import paths for this Qt installation.

    On NixOS, QLibraryInfo points to qtbase's store path, but QtQuick lives in
    qtdeclarative — a separate store package.  We find it by tracing ldd on the
    PySide6.QtQml shared library to locate libQt6Qml.so, then derive the sibling
    qml/ directory from that store path.

    Results are cached in .qt_path_cache.env next to this file so that subsequent
    launches skip the ldd search entirely.
    """
    paths = []

    # Strategy 1: ldd PySide6.QtQml → libQt6Qml.so → derive qtdeclarative qml dir.
    try:
        import subprocess
        import PySide6.QtQml as _qml_mod
        ldd = subprocess.run(
            ["ldd", _qml_mod.__file__],
            capture_output=True, text=True, timeout=5,
        )
        for line in ldd.stdout.splitlines():
            if "libQt6Qml.so" in line and "=>" in line:
                lib = line.split("=>")[1].strip().split()[0]
                # lib → e.g. /nix/store/HASH-qtdeclarative-6.x/lib/libQt6Qml.so.6
                real = os.path.realpath(lib)
                pkg_root = os.path.dirname(os.path.dirname(real))  # .../lib → pkg root
                candidate = os.path.join(pkg_root, "lib", "qt-6", "qml")
                if os.path.isdir(candidate):
                    paths.append(candidate)
                break
    except Exception:
        pass

    # Strategy 2: QLibraryInfo (may point to qtbase, not qtdeclarative, but worth trying).
    try:
        p = QLibraryInfo.path(QLibraryInfo.LibraryPath.Qml2ImportsPath)
        if p and p not in paths:
            paths.append(p)
    except Exception:
        pass

    # Strategy 3: pip-installed PySide6 bundles QML inside the package directory.
    try:
        import PySide6
        pkg_qml = os.path.join(os.path.dirname(PySide6.__file__), "Qt", "qml")
        if os.path.isdir(pkg_qml) and pkg_qml not in paths:
            paths.append(pkg_qml)
    except Exception:
        pass

    return paths


def _qt_qml_import_paths() -> list[str]:
    cached = _load_cached_qml_paths()
    if cached is not None:
        return cached
    paths = _discover_qml_import_paths()
    if paths:
        _save_qml_path_cache(paths)
    return paths

from pyshell.services.tag_service import TagService
from pyshell.services.audio_service import AudioService
from pyshell.services.brightness_service import BrightnessService
from pyshell.services.media_service import MediaService
from pyshell.services.wifi_service import WiFiService
from pyshell.services.notification_service import NotificationService
from pyshell.services.app_service import AppService
from pyshell.services.power_service import PowerService
from pyshell.services.window_helper import WindowHelper


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("pyshell")

    # Create service singletons
    tag_service = TagService()
    audio_service = AudioService()
    brightness_service = BrightnessService()
    media_service = MediaService()
    wifi_service = WiFiService()
    notification_service = NotificationService()
    app_service = AppService()
    power_service = PowerService()
    window_helper = WindowHelper()

    # Register singletons for QML access
    qmlRegisterSingletonInstance(TagService, "PyShell.Services", 1, 0, "TagService", tag_service)
    qmlRegisterSingletonInstance(AudioService, "PyShell.Services", 1, 0, "AudioService", audio_service)
    qmlRegisterSingletonInstance(BrightnessService, "PyShell.Services", 1, 0, "BrightnessService", brightness_service)
    qmlRegisterSingletonInstance(MediaService, "PyShell.Services", 1, 0, "MediaService", media_service)
    qmlRegisterSingletonInstance(WiFiService, "PyShell.Services", 1, 0, "WiFiService", wifi_service)
    qmlRegisterSingletonInstance(NotificationService, "PyShell.Services", 1, 0, "NotificationService", notification_service)
    qmlRegisterSingletonInstance(AppService, "PyShell.Services", 1, 0, "AppService", app_service)
    qmlRegisterSingletonInstance(PowerService, "PyShell.Services", 1, 0, "PowerService", power_service)
    qmlRegisterSingletonInstance(WindowHelper, "PyShell.Services", 1, 0, "WindowHelper", window_helper)

    engine = QQmlApplicationEngine()

    for p in _qt_qml_import_paths():
        engine.addImportPath(p)

    qml_dir = os.path.join(os.path.dirname(__file__), "components")
    engine.addImportPath(os.path.dirname(__file__))

    shell_qml = os.path.join(qml_dir, "Shell.qml")
    engine.load(QUrl.fromLocalFile(shell_qml))

    if not engine.rootObjects():
        print("Failed to load QML", file=sys.stderr)
        sys.exit(1)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
