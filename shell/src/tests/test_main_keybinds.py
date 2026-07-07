import importlib.util
import os
import sys
import types
import unittest


class TestMainKeybinds(unittest.TestCase):
    def test_open_keybinds_flag_sends_ipc_command(self):
        main_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
        old_argv = sys.argv[:]
        old_modules = {
            name: sys.modules.get(name)
            for name in (
                "sadeshell",
                "sadeshell.services",
                "sadeshell.services.shared",
                "sadeshell.services.shared.ipc_client",
            )
        }
        sent = []

        ipc_client = types.ModuleType("sadeshell.services.shared.ipc_client")

        def send_ipc_command(command):
            sent.append(command)
            return "ok"

        ipc_client.send_ipc_command = send_ipc_command

        sys.modules["sadeshell"] = types.ModuleType("sadeshell")
        sys.modules["sadeshell.services"] = types.ModuleType("sadeshell.services")
        sys.modules["sadeshell.services.shared"] = types.ModuleType("sadeshell.services.shared")
        sys.modules["sadeshell.services.shared.ipc_client"] = ipc_client
        sys.argv = ["sadeshell", "--open-keybinds"]

        try:
            spec = importlib.util.spec_from_file_location("_sadeshell_main_keybinds_test", main_path)
            module = importlib.util.module_from_spec(spec)
            with self.assertRaises(SystemExit) as exc:
                spec.loader.exec_module(module)
        finally:
            sys.argv = old_argv
            for name, old_module in old_modules.items():
                if old_module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = old_module

        self.assertEqual(exc.exception.code, 0)
        self.assertEqual(sent, ["open-keybinds"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
