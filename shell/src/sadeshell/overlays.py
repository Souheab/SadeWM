"""Central IPC dispatcher. Each overlay is constructed only on first use."""
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QUrl, QMetaObject, Qt
from PySide6.QtQml import QQmlComponent, QQmlEngine


class OverlayDispatcher(QObject):
    OVERLAYS = {
        "openLauncherRequested": "AppLauncher.qml",
        "openKeybindsRequested": "KeybindOverlay.qml",
        "openEmojiPickerRequested": "EmojiPicker.qml",
        "openWindowPickerRequested": "WindowPicker.qml",
        "openMinimizedPickerRequested": "MinimizedWindowPicker.qml",
        "confirmExitRequested": "ExitConfirmation.qml",
    }

    def __init__(self, ipc, parent=None):
        super().__init__(parent)
        self.engine = None
        self.roots = {}
        self.loading = {}
        self.components = {}
        self.desired = {}
        for signal, filename in self.OVERLAYS.items():
            getattr(ipc, signal).connect(lambda filename=filename: self.toggle(filename))

    def set_engine(self, engine):
        self.engine = engine
        for filename, desired in list(self.desired.items()):
            if desired:
                self._load(filename)

    def toggle(self, filename):
        root = self.roots.get(filename)
        current = self.desired.get(filename, False)
        if root:
            current = root.property("opened") if root.metaObject().indexOfProperty("opened") >= 0 else root.property("visible")
        self.desired[filename] = not current
        if root:
            self._show(filename)
        elif self.engine and filename not in self.loading:
            self._load(filename)

    def _load(self, filename):
        component = QQmlComponent(self.engine, self)
        self.loading[filename] = component
        component.statusChanged.connect(lambda status: self._loaded(filename, component))
        component.loadUrl(QUrl.fromLocalFile(str(Path(__file__).parent / "components" / "launcher" / filename)),
                          QQmlComponent.CompilationMode.Asynchronous)
        self._loaded(filename, component)

    def _loaded(self, filename, component):
        if self.loading.get(filename) is not component or component.isLoading() or component.isNull():
            return
        if component.isError():
            print(f"Cannot load {filename}: {component.errorString()}", file=sys.stderr)
            self.desired[filename] = False
        else:
            root = component.create()
            if root is None:
                print(f"Cannot create {filename}: {component.errorString()}", file=sys.stderr)
                self.desired[filename] = False
            else:
                QQmlEngine.setObjectOwnership(root, QQmlEngine.ObjectOwnership.CppOwnership)
                QObject.setParent(root, self)
                self.roots[filename] = root
                self.components[filename] = component
                self._show(filename)
        self.loading.pop(filename, None)
        if filename not in self.roots:
            component.deleteLater()

    def _show(self, filename):
        method = "open" if self.desired[filename] else "close"
        QMetaObject.invokeMethod(self.roots[filename], method, Qt.ConnectionType.DirectConnection)

    def stop(self):
        for root in self.roots.values():
            root.close()
            root.deleteLater()
        for component in self.loading.values():
            component.deleteLater()
        for component in self.components.values():
            component.deleteLater()
        self.components.clear()
        self.roots.clear()
        self.loading.clear()
