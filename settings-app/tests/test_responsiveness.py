import threading
import time

from PySide6.QtCore import QCoreApplication
import pytest

from sadesettings import config_store, main


def wait_for(predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert predicate()


def test_atomic_save_preserves_existing_file_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / "wm.toml"
    original = config_store.load_toml(path)
    config_store.save_toml(path, original)
    before = path.read_bytes()
    original["new"] = 1
    def fail(*args):
        raise OSError("disk error")
    monkeypatch.setattr(config_store.os, "replace", fail)
    with pytest.raises(OSError):
        config_store.save_toml(path, original)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_discovery_and_apply_are_off_thread_and_apply_is_serialized(tmp_path, monkeypatch):
    gate = threading.Event()
    discovery_threads = []
    def discover():
        discovery_threads.append(threading.get_ident())
        gate.wait(2)
        return []
    monkeypatch.setattr(main.display, "query_outputs", discover)
    window = main.SettingsWindow(tmp_path)
    window.show()
    try:
        wait_for(lambda: discovery_threads)
        assert window.isVisible()
        assert discovery_threads[0] != threading.get_ident()
        gate.set()
        monkeypatch.setattr(window, "_confirm_apply", lambda: True)
        calls = []
        def save(path, doc):
            calls.append((path, threading.get_ident()))
            time.sleep(0.02)
        monkeypatch.setattr(main.config_store, "save_toml", save)
        monkeypatch.setattr(main.ipc, "send_reload", lambda: dict(ok=False, error="not running"))
        window.apply()
        window.apply()
        wait_for(lambda: not window._applying)
        assert len(calls) == 2
        assert all(ident != threading.get_ident() for _, ident in calls)
        assert window.status.text() == "Saved, not applied: not running"
    finally:
        gate.set()
        window.close()
