import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
import shiboken6



from sadeshell.services.shared import app_service  # noqa: E402
from sadeshell.launch_environment import launch_environment


def test_launch_environment_restores_unset_empty_and_custom_values(monkeypatch):
    monkeypatch.setenv("SADESHELL_SESSION_VARS", "PATH PYTHONPATH LD_LIBRARY_PATH QT_PLUGIN_PATH")
    monkeypatch.setenv("SADESHELL_SESSION_PATH", "/host/bin:/user/bin")
    monkeypatch.setenv("SADESHELL_SESSION_QT_PLUGIN_PATH", "")
    monkeypatch.setenv("SADESHELL_SESSION_LD_LIBRARY_PATH", "/host/lib with spaces")
    monkeypatch.delenv("SADESHELL_SESSION_PYTHONPATH", raising=False)
    for name in ("PATH", "PYTHONPATH", "LD_LIBRARY_PATH", "QT_PLUGIN_PATH"):
        monkeypatch.setenv(name, "/private/package")

    env = launch_environment()
    assert env["PATH"] == "/host/bin:/user/bin"
    assert env["QT_PLUGIN_PATH"] == ""
    assert env["LD_LIBRARY_PATH"] == "/host/lib with spaces"
    assert "PYTHONPATH" not in env
    assert not any(name.startswith("SADESHELL_SESSION_") for name in env)
    assert os.environ["PATH"] == "/private/package"


@pytest.mark.parametrize("scoped", [False, True])
@pytest.mark.parametrize("desktop_entry", [False, True])
def test_launch_uses_session_environment(monkeypatch, scoped, desktop_entry):
    monkeypatch.setenv("SADESHELL_SESSION_VARS", "PATH PYTHONPATH")
    monkeypatch.setenv("SADESHELL_SESSION_PATH", "/host/bin")
    monkeypatch.delenv("SADESHELL_SESSION_PYTHONPATH", raising=False)
    monkeypatch.setenv("PYTHONPATH", "/private/python")
    monkeypatch.setattr(app_service, "_SYSTEMD_RUN", "/host/bin/systemd-run" if scoped else None)
    service = app_service.AppService.__new__(app_service.AppService)
    with mock.patch.object(app_service.subprocess, "Popen") as popen:
        if desktop_entry:
            service.launch({"exec": "demo --flag"})
        else:
            service.launchCommand(["demo", "--flag"])
    args, kwargs = popen.call_args
    expected = ["demo", "--flag"]
    if scoped:
        expected = ["/host/bin/systemd-run", "--user", "--scope", "--", *expected]
    assert args[0] == expected
    assert kwargs["env"]["PATH"] == "/host/bin"
    assert "PYTHONPATH" not in kwargs["env"]


@pytest.mark.parametrize("stop_first", [False, True])
def test_scan_finishing_after_qobject_deletion_is_harmless(monkeypatch, tmp_path, stop_first):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    errors = []

    def scan():
        started.set()
        assert release.wait(5)
        return []

    original = app_service.AppService._do_scan

    def worker(service):
        try:
            original(service)
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()

    monkeypatch.setattr(app_service, "_apps_dirs", lambda: [str(tmp_path)])
    monkeypatch.setattr(app_service, "_parse_desktop_files", scan)
    monkeypatch.setattr(app_service.icons, "invalidate", lambda: None)
    monkeypatch.setattr(app_service.AppService, "_do_scan", worker)
    service = app_service.AppService()
    try:
        assert started.wait(5)
        if stop_first:
            service.stop()
        service.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not shiboken6.isValid(service)
    finally:
        release.set()
        assert finished.wait(5)
    assert errors == []


class TestDesktopEntries(unittest.TestCase):
    def test_exec_expansion_produces_argv_without_a_shell(self):
        entry = {
            "name": "Demo App",
            "icon": "demo-icon",
            "desktopFile": "/tmp/demo.desktop",
            "exec": 'demo --title "%c" %i %F %% %k',
        }

        self.assertEqual(
            app_service._expand_exec(entry),
            [
                "demo", "--title", "Demo App", "--icon", "demo-icon",
                "%", "/tmp/demo.desktop",
            ],
        )

    def test_unknown_exec_field_code_rejects_entry(self):
        self.assertEqual(app_service._expand_exec({"exec": "demo %Z"}), [])

    def test_desktop_visibility_fields(self):
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "sade:GNOME"}):
            self.assertTrue(
                app_service._visible_on_current_desktop({"onlyshowin": "sade;"})
            )
            self.assertFalse(
                app_service._visible_on_current_desktop({"onlyshowin": "KDE;"})
            )
            self.assertFalse(
                app_service._visible_on_current_desktop({"notshowin": "GNOME;"})
            )

    def test_parser_honors_hidden_tryexec_and_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apps = root / "share" / "applications"
            home = root / "home"
            apps.mkdir(parents=True)
            home.mkdir()
            (apps / "visible.desktop").write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Visible\n"
                "Exec=visible --flag\n"
                "Terminal=true\n",
                encoding="utf-8",
            )
            (apps / "hidden.desktop").write_text(
                "[Desktop Entry]\nType=Application\nName=Hidden\n"
                "Exec=hidden\nHidden=true\n",
                encoding="utf-8",
            )
            (apps / "missing.desktop").write_text(
                "[Desktop Entry]\nType=Application\nName=Missing\n"
                "Exec=missing\nTryExec=/definitely/not/installed\n",
                encoding="utf-8",
            )

            env = {
                "HOME": str(home),
                "XDG_DATA_DIRS": str(root / "share"),
                "XDG_CURRENT_DESKTOP": "sade",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                parsed = app_service._parse_desktop_files()

        self.assertEqual([entry["name"] for entry in parsed], ["Visible"])
        self.assertTrue(parsed[0]["terminal"])

    def test_launch_passes_argv_directly(self):
        service = app_service.AppService.__new__(app_service.AppService)
        entry = {
            "name": "Demo",
            "icon": "",
            "desktopFile": "/tmp/demo.desktop",
            "exec": 'demo "argument with spaces"',
            "terminal": False,
        }
        with (
            mock.patch.object(app_service, "_SYSTEMD_RUN", None),
            mock.patch.object(app_service.subprocess, "Popen") as popen,
        ):
            service.launch(entry)

        args, kwargs = popen.call_args
        self.assertEqual(args[0], ["demo", "argument with spaces"])
        self.assertNotIn("shell", kwargs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
