"""Qt application startup (imported only for a graphical launch)."""
import os
import signal
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
from PySide6.QtCore import QUrl

from sadeshell.qt_paths import qml_import_paths

from sadeshell.services.bar.tag_service import TagService
from sadeshell.services.bar.audio_service import AudioService
from sadeshell.services.bar.brightness_service import BrightnessService
from sadeshell.services.bar.fullscreen_service import FullscreenService
from sadeshell.services.bar.media_service import MediaService
from sadeshell.services.bar.wifi_service import WiFiService
from sadeshell.services.bar.notification_service import NotificationService
from sadeshell.services.bar.power_service import PowerService
from sadeshell.services.bar.bluetooth_service import BluetoothService
from sadeshell.services.bar.systray_service import SystrayService
from sadeshell.services.shared.app_service import AppService
from sadeshell.services.shared.emoji_service import EmojiService
from sadeshell.services.shared.window_helper import WindowHelper
from sadeshell.services.shared.ipc_service import IPCService
from sadeshell.services.shared.wm_ipc_service import WMIPCService
from sadeshell.services.shared.window_picker_service import WindowPickerService
from sadeshell.services.shared.keybind_service import KeybindService


from sadeshell.overlays import OverlayDispatcher
from sadeshell.services.shared.async_bus import BusWorker


def main(argv=None):
    app = QApplication([sys.argv[0], *(argv or [])])
    app.setApplicationName("sadeshell")
    ipc = IPCService()
    dispatcher = OverlayDispatcher(ipc)
    services = []
    engine = None
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    try:
        # No other service or QML root exists until the singleton is acquired.
        if not ipc.start():
            print("Refusing to start a second sadeshell instance", file=sys.stderr)
            return 1
        qmlRegisterSingletonInstance(IPCService, "PyShell.Services", 1, 0, "IPCService", ipc)
        for service_type in (TagService, AudioService, BrightnessService, FullscreenService, MediaService, WiFiService, NotificationService, AppService, EmojiService, PowerService, WindowHelper, BluetoothService, SystrayService, WMIPCService, WindowPickerService, KeybindService,):
            service = service_type()
            services.append(service)
            qmlRegisterSingletonInstance(service_type, "PyShell.Services", 1, 0, service_type.__name__, service)
        fullscreen = next(s for s in services if isinstance(s, FullscreenService))
        picker = next(s for s in services if isinstance(s, WindowPickerService))
        fullscreen.windowsRemoved.connect(picker.removeWindows)
        engine = QQmlApplicationEngine()
        for path in reversed(qml_import_paths(engine.importPathList())):
            engine.addImportPath(path)
        qml_dir = os.path.join(os.path.dirname(__file__), "components")
        engine.addImportPath(os.path.dirname(__file__))
        engine.addImportPath(os.path.join(qml_dir, "shared"))
        engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "bar", "Shell.qml")))
        if not engine.rootObjects():
            print("Failed to load Shell QML", file=sys.stderr)
            return 1
        dispatcher.set_engine(engine)
        return app.exec()
    except Exception as exc:
        print(f"Shell startup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        dispatcher.stop()
        if engine:
            for root in engine.rootObjects():
                root.close()
        for service in reversed(services):
            stop = getattr(service, "stop", None)
            if stop:
                try:
                    stop()
                except Exception as exc:
                    print(f"Stopping {type(service).__name__}: {exc}", file=sys.stderr)
        if BusWorker._instance:
            BusWorker._instance.stop()
        ipc.stop()
