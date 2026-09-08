"""PowerService — system power actions (lock, suspend, reboot, shutdown, logout)."""

import subprocess

from PySide6.QtCore import QObject, Slot


class PowerService(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

    def _run(self, cmd):
        try:
            subprocess.Popen(cmd, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    @Slot(str)
    def execute(self, action):
        """Dispatch a power action by name."""
        fn = getattr(self, action, None)
        if callable(fn):
            fn()

    @Slot()
    def lock(self):
        self._run(["loginctl", "lock-session"])

    @Slot()
    def suspend(self):
        self._run(["systemctl", "suspend"])

    @Slot()
    def reboot(self):
        self._run(["systemctl", "reboot"])

    @Slot()
    def shutdown(self):
        self._run(["systemctl", "poweroff"])

    @Slot()
    def logout(self):
        self._run(["loginctl", "terminate-session", "self"])
