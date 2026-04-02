"""PyShell main entry point — launches the PySide6/QML bar."""

import sys
import os
import signal

from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
from PySide6.QtCore import QUrl

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
