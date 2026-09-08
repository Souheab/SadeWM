import subprocess
import sys
from unittest import mock

from sadeshell.main import COMMANDS, main


def test_ipc_flags():
    for command in COMMANDS:
        with mock.patch("sadeshell.services.shared.ipc_client.send_ipc_command", return_value="ok") as send:
            assert main(["--" + command]) == 0
            send.assert_called_once_with(command)


def test_import_does_not_load_qt_or_execute_commands():
    subprocess.run([sys.executable, "-c", "import sys; sys.argv.append('--open-keybinds'); import sadeshell.main; assert 'PySide6' not in sys.modules"], check=True)
