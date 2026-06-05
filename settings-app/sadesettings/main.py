from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import config_store, display, ipc


class ColorButton(QPushButton):
    def __init__(self, value: str):
        super().__init__(value)
        self._value = value
        self.clicked.connect(self._choose)
        self._sync()

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = value
        self.setText(value)
        self._sync()

    def _choose(self) -> None:
        color = QColorDialog.getColor()
        if color.isValid():
            self.set_value(color.name())

    def _sync(self) -> None:
        self.setStyleSheet(
            f"QPushButton {{ text-align: left; padding: 6px; border-left: 24px solid {self._value}; }}"
        )


class SettingsWindow(QMainWindow):
    def __init__(self, config_dir: Path):
        super().__init__()
        self.config_dir = config_dir
        self.wm_path, self.settings_path = config_store.config_paths(config_dir)
        self.wm_doc = config_store.load_toml(self.wm_path)
        self.settings_doc = config_store.load_toml(self.settings_path)
        config_store.ensure_wm_defaults(self.wm_doc)
        config_store.ensure_display_defaults(self.settings_doc)

        self.wm_widgets: dict[str, QWidget] = {}
        self.outputs = display.query_outputs()

        self.setWindowTitle("SADE Settings")
        self.resize(860, 560)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        body = QHBoxLayout()
        outer.addLayout(body, 1)

        self.nav = QListWidget()
        self.nav.setFixedWidth(160)
        for name in ("WM", "Display"):
            item = QListWidgetItem(name)
            item.setTextAlignment(Qt.AlignVCenter)
            self.nav.addItem(item)
        body.addWidget(self.nav)

        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        body.addWidget(line)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_wm_page())
        self.pages.addWidget(self._build_display_page())
        body.addWidget(self.pages, 1)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

        actions = QHBoxLayout()
        self.status = QLabel("")
        actions.addWidget(self.status, 1)
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self.apply)
        actions.addWidget(apply_button)
        outer.addLayout(actions)

        self.setCentralWidget(root)

    def _build_wm_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        specs = [
            ("appearance.borderpx", "Border width", "int", 0, 64),
            ("appearance.gappx", "Gaps", "int", 0, 128),
            ("appearance.snap", "Snap distance", "int", 0, 256),
            ("layout.mfact", "Master factor", "float", 0.05, 0.95),
            ("layout.nmaster", "Master windows", "int", 0, 16),
            ("layout.topoffset", "Top offset", "int", 0, 512),
            ("layout.bottomoffset", "Bottom offset", "int", 0, 512),
            ("layout.resizehints", "Resize hints", "bool", None, None),
            ("layout.lockfullscreen", "Lock fullscreen", "bool", None, None),
            ("colors.norm.border", "Normal border", "color", None, None),
            ("colors.sel.border", "Selected border", "color", None, None),
            ("titlebar.bg", "Titlebar background", "color", None, None),
            ("titlebar.bg_focused", "Focused titlebar background", "color", None, None),
            ("titlebar.sep", "Titlebar separator", "color", None, None),
            ("titlebar.text", "Title text", "color", None, None),
            ("titlebar.close", "Close button", "color", None, None),
            ("titlebar.above", "Above button", "color", None, None),
            ("titlebar.minimize", "Minimize button", "color", None, None),
        ]
        for key, label, kind, minimum, maximum in specs:
            widget: QWidget
            if kind == "int":
                spin = QSpinBox()
                spin.setRange(int(minimum), int(maximum))
                widget = spin
            elif kind == "float":
                spin = QDoubleSpinBox()
                spin.setRange(float(minimum), float(maximum))
                spin.setSingleStep(0.01)
                spin.setDecimals(2)
                widget = spin
            elif kind == "bool":
                widget = QCheckBox()
            else:
                widget = ColorButton("#000000")
            self.wm_widgets[key] = widget
            form.addRow(label, widget)
        return page

    def _build_display_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.display_enabled = QCheckBox()
        self.display_output = QComboBox()
        self.display_resolution = QComboBox()
        self.display_refresh = QComboBox()
        self.display_output.currentIndexChanged.connect(self._sync_display_modes)
        self.display_resolution.currentIndexChanged.connect(self._sync_refresh_rates)

        form.addRow("Manage display", self.display_enabled)
        form.addRow("Output", self.display_output)
        form.addRow("Resolution", self.display_resolution)
        form.addRow("Refresh rate", self.display_refresh)
        return page

    def _load_values(self) -> None:
        values = config_store.get_wm_values(self.wm_doc)
        for key, widget in self.wm_widgets.items():
            value = values[key]
            if isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, ColorButton):
                widget.set_value(str(value))

        self.display_output.clear()
        if self.outputs:
            for output in self.outputs:
                self.display_output.addItem(output.name)
        else:
            self.display_output.addItem("default")
        self._sync_display_modes()

        display_values = config_store.get_display_values(self.settings_doc)
        self.display_enabled.setChecked(bool(display_values["enabled"]))
        self._set_combo_text(self.display_output, str(display_values["output"] or "default"))
        self._sync_display_modes()
        self._set_combo_text(self.display_resolution, str(display_values["resolution"]))
        self._set_combo_text(self.display_refresh, str(display_values["refresh_rate"]))

    def _sync_display_modes(self) -> None:
        output_name = self.display_output.currentText()
        selected = next((out for out in self.outputs if out.name == output_name), None)
        current_resolution = self.display_resolution.currentText()
        self.display_resolution.clear()
        if selected:
            self.display_resolution.addItems(selected.resolutions.keys())
        self._set_combo_text(self.display_resolution, current_resolution)
        self._sync_refresh_rates()

    def _sync_refresh_rates(self) -> None:
        output_name = self.display_output.currentText()
        resolution = self.display_resolution.currentText()
        selected = next((out for out in self.outputs if out.name == output_name), None)
        current = self.display_refresh.currentText()
        self.display_refresh.clear()
        rates = selected.resolutions.get(resolution, []) if selected else []
        for rate in rates:
            self.display_refresh.addItem(f"{rate:g}")
        self._set_combo_text(self.display_refresh, current)

    def _set_combo_text(self, combo: QComboBox, text: str) -> None:
        if not text:
            return
        idx = combo.findText(text)
        if idx < 0:
            combo.addItem(text)
            idx = combo.findText(text)
        combo.setCurrentIndex(idx)

    def apply(self) -> None:
        wm_values = {}
        for key, widget in self.wm_widgets.items():
            if isinstance(widget, QSpinBox):
                wm_values[key] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                wm_values[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                wm_values[key] = widget.isChecked()
            elif isinstance(widget, ColorButton):
                wm_values[key] = widget.value()
        config_store.set_wm_values(self.wm_doc, wm_values)

        refresh = self.display_refresh.currentText()
        display_values = {
            "enabled": self.display_enabled.isChecked(),
            "output": self.display_output.currentText() or "default",
            "resolution": self.display_resolution.currentText(),
            "refresh_rate": float(refresh) if refresh else 0.0,
        }
        config_store.set_display_values(self.settings_doc, display_values)

        config_store.save_toml(self.wm_path, self.wm_doc)
        config_store.save_toml(self.settings_path, self.settings_doc)

        response = ipc.send_reload()
        if response.get("ok") is True:
            self.status.setText("Saved and applied")
        else:
            self.status.setText(f"Saved, not applied: {response.get('error', 'unknown IPC error')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", default=str(config_store.DEFAULT_CONFIG_DIR))
    args = parser.parse_args(argv)

    app = QApplication(sys.argv if argv is None else ["sadesettings", *argv])
    window = SettingsWindow(Path(args.config_dir).expanduser())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
