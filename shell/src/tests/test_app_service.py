import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.shared import app_service  # noqa: E402


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
