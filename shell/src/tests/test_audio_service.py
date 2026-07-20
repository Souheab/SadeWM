import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from PySide6.QtCore import QCoreApplication


_src = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_src))

from services.bar import audio_service as audio_module  # noqa: E402


class _FakePulse:
    def __init__(self):
        self.sinks = [SimpleNamespace(index=4)]
        self.volume_updates = []

    def sink_list(self):
        return self.sinks

    def volume_set_all_chans(self, item, volume):
        self.volume_updates.append((item.index, volume))


class _WorkerPulse:
    connections = 0
    volume_updates = []

    def __init__(self, _client_name):
        type(self).connections += 1
        self._sink = SimpleNamespace(
            index=4,
            name="main",
            description="Main output",
            volume=SimpleNamespace(value_flat=0.5),
            mute=False,
        )

    def sink_list(self):
        return [self._sink]

    def source_list(self):
        return []

    def sink_input_list(self):
        return []

    def server_info(self):
        return SimpleNamespace(
            default_sink_name="main",
            default_source_name="",
        )

    def volume_set_all_chans(self, item, volume):
        type(self).volume_updates.append((item.index, volume))

    def close(self):
        pass


class TestAudioService(unittest.TestCase):
    def _service_without_worker(self):
        with mock.patch.object(audio_module, "HAS_PULSECTL", False):
            service = audio_module.AudioService()
        self.addCleanup(service.stop)
        return service

    def test_slider_commands_are_coalesced_per_device(self):
        service = self._service_without_worker()

        with mock.patch.object(audio_module, "HAS_PULSECTL", True):
            service.applySinkVolume(4, 0.1)
            service.applySinkVolume(4, 0.4)
            service.applySinkVolume(4, 0.9)
        commands, poll_requested = service._drain_pending_work()

        self.assertFalse(poll_requested)
        self.assertEqual(commands, [("set_sink_volume", 4, 0.9)])

    def test_command_execution_uses_one_device_list_lookup(self):
        service = self._service_without_worker()
        pulse = _FakePulse()
        pulse.sink_list = mock.Mock(wraps=pulse.sink_list)

        service._execute_command(pulse, ("set_sink_volume", 4, 0.75))

        pulse.sink_list.assert_called_once_with()
        self.assertEqual(pulse.volume_updates, [(4, 0.75)])

    def test_worker_reuses_one_pulse_connection(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        self.assertIsNotNone(app)
        _WorkerPulse.connections = 0
        _WorkerPulse.volume_updates = []
        fake_module = SimpleNamespace(Pulse=_WorkerPulse)

        with (
            mock.patch.object(audio_module, "pulsectl", fake_module, create=True),
            mock.patch.object(audio_module, "HAS_PULSECTL", True),
        ):
            service = audio_module.AudioService()
            try:
                service.applySinkVolume(4, 0.1)
                service.applySinkVolume(4, 0.4)
                service.applySinkVolume(4, 0.9)
                deadline = time.monotonic() + 1.0
                while (
                    not _WorkerPulse.volume_updates
                    or _WorkerPulse.volume_updates[-1] != (4, 0.9)
                ):
                    if time.monotonic() >= deadline:
                        self.fail("audio worker did not process the latest volume")
                    time.sleep(0.01)
            finally:
                service.stop()

        self.assertEqual(_WorkerPulse.connections, 1)

    def test_poll_state_is_buffered_during_drag(self):
        with mock.patch.object(audio_module, "HAS_PULSECTL", False):
            service = audio_module.AudioService()

        state = {
            "sinks": [{"index": 4, "name": "main", "volume": 0.5, "muted": False}],
            "sources": [],
            "sink_inputs": [],
            "default_sink": "main",
            "default_source": "",
        }
        service.beginDrag()
        service._receive_state(state)

        self.assertEqual(service.sinks, [])
        service.endDrag()
        self.assertEqual(service.sinks, state["sinks"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
