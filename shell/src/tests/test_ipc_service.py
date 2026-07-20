import os
import socket
import sys
import tempfile
import time
import unittest


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.shared.ipc_service import IPCService  # noqa: E402


class TestIPCService(unittest.TestCase):
    def test_idle_connection_does_not_block_other_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "shell.sock")
            service = IPCService()
            service._socket_path = path
            self.assertTrue(service.start())
            idle = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                idle.connect(path)
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(0.5)
                started = time.monotonic()
                try:
                    client.connect(path)
                    client.sendall(b"bogus")
                    self.assertEqual(client.recv(4096), b"unknown command\n")
                finally:
                    client.close()
                self.assertLess(time.monotonic() - started, 0.5)
            finally:
                idle.close()
                service.stop()

    def test_second_server_does_not_unlink_live_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "shell.sock")
            first = IPCService()
            second = IPCService()
            first._socket_path = path
            second._socket_path = path
            try:
                self.assertTrue(first.start())
                self.assertFalse(second.start())
                self.assertTrue(os.path.exists(path))
            finally:
                second.stop()
                first.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
