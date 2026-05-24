import json
import os
import socket
import sys
import tempfile
import threading
import unittest


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.shared import wm_ipc_client  # noqa: E402


class TestWMIPCClient(unittest.TestCase):
    def setUp(self):
        self._old_env = {
            "DISPLAY": os.environ.get("DISPLAY"),
            "SADEWM_SOCKET": os.environ.get("SADEWM_SOCKET"),
        }

    def tearDown(self):
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_socket_path_honors_override(self):
        os.environ["SADEWM_SOCKET"] = "/tmp/custom-sadewm.sock"
        os.environ["DISPLAY"] = ":7.0"

        self.assertEqual(wm_ipc_client.get_socket_path(), "/tmp/custom-sadewm.sock")

    def test_socket_path_matches_wm_display_rule(self):
        os.environ.pop("SADEWM_SOCKET", None)
        os.environ["DISPLAY"] = ":7.0"

        self.assertEqual(wm_ipc_client.get_socket_path(), "/tmp/sadewm-7-0.sock")

    def test_send_wm_command_returns_decoded_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sadewm.sock")
            os.environ["SADEWM_SOCKET"] = path

            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(path)
            server.listen(1)
            received = {}

            def serve():
                conn, _ = server.accept()
                with conn:
                    received["payload"] = json.loads(conn.recv(4096).decode("utf-8"))
                    conn.sendall(b'{"ok":true}\n')
                server.close()

            thread = threading.Thread(target=serve)
            thread.start()
            try:
                response = wm_ipc_client.send_wm_command("quit")
            finally:
                thread.join(timeout=2)

            self.assertEqual(received["payload"], {"cmd": "quit"})
            self.assertEqual(response, {"ok": True})

    def test_quit_wm_true_only_on_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sadewm.sock")
            os.environ["SADEWM_SOCKET"] = path

            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(path)
            server.listen(1)

            def serve():
                conn, _ = server.accept()
                with conn:
                    conn.recv(4096)
                    conn.sendall(b'{"ok":true}\n')
                server.close()

            thread = threading.Thread(target=serve)
            thread.start()
            try:
                self.assertTrue(wm_ipc_client.quit_wm())
            finally:
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
