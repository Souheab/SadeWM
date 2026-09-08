"""Run explicitly with: dbus-run-session -- python -m pytest tests/integration -v."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import statistics

import pytest
from Xlib import X, Xatom, display
from Xlib.protocol import event
from xdrive import VirtualDisplay


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out")


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    with VirtualDisplay(width=1280, height=800) as server:
        monkeypatch.setenv("DISPLAY", server.name)
        nested = None
        compositor = None
        if os.environ.get("SADEWM_TEST_XEPHYR"):
            read_fd, write_fd = os.pipe()
            nested = subprocess.Popen(["Xephyr", "-displayfd", str(write_fd), "-screen", "1280x800",
                                       "-ac", "-nolisten", "tcp"], pass_fds=(write_fd,),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.close(write_fd)
            with os.fdopen(read_fd) as reader:
                number = reader.readline().strip()
            assert number.isdigit()
            monkeypatch.setenv("DISPLAY", ":" + number)
            compositor = subprocess.Popen(["picom", "--config", "/dev/null", "--backend", "xrender"],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.3)
            assert compositor.poll() is None
        monkeypatch.setenv("SADEWM_SOCKET", str(tmp_path / "wm.sock"))
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        log = (tmp_path / "wm.log").open("w")
        process = subprocess.Popen([os.environ.get("SADEWM_TEST_BINARY", "/tmp/sadewm-validation"), "--no-config"], stdout=log, stderr=log)
        try:
            wait_for(lambda: (tmp_path / "wm.sock").exists())
            connection = display.Display()
            yield connection, process, tmp_path
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                if not os.environ.get("SADEWM_BENCH_BASELINE"):
                    raise
            if "connection" in locals():
                connection.close()
            log.close()
            if compositor:
                compositor.terminate()
                compositor.wait(timeout=5)
            if nested:
                nested.terminate()
                nested.wait(timeout=5)


def ipc(**request):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5)
        connection.connect(os.environ["SADEWM_SOCKET"])
        connection.sendall(json.dumps(request).encode())
        connection.shutdown(socket.SHUT_WR)
        data = b""
        while chunk := connection.recv(65536):
            data += chunk
        return json.loads(data)


def window(connection, title="integration", style="tiled"):
    root = connection.screen().root
    result = root.create_window(20, 20, 640, 480, 0, connection.screen().root_depth,
                                X.InputOutput, X.CopyFromParent, background_pixel=0xff0000)
    result.set_wm_name(title)
    result.set_wm_class("integration", "Integration")
    if style == "floating":
        result.change_property(connection.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM, 32,
                               [connection.intern_atom("_NET_WM_WINDOW_TYPE_DIALOG")])
    elif style == "fullscreen":
        result.change_property(connection.intern_atom("_NET_WM_STATE"), Xatom.ATOM, 32,
                               [connection.intern_atom("_NET_WM_STATE_FULLSCREEN")])
    result.map()
    connection.sync()
    wait_for(lambda: any(c["win_id"] == result.id for c in ipc(cmd="get_clients").get("clients", [])))
    return result


@pytest.mark.parametrize("style", ["tiled", "floating", "fullscreen"])
def test_minimize_restore_and_capture(desktop, style):
    from sadeshell.services.shared.thumbnail_capture import CaptureConnection
    connection, process, _ = desktop
    win = window(connection, style=style)
    root = connection.screen().root
    root.send_event(event.ClientMessage(window=win, client_type=connection.intern_atom("WM_CHANGE_STATE"),
                                       data=(32, [3, 0, 0, 0, 0])),
                    event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    connection.sync()
    wait_for(lambda: win.get_attributes().map_state != X.IsViewable)
    assert ipc(cmd="focus_window", win_id=win.id)["ok"]
    wait_for(lambda: win.get_attributes().map_state == X.IsViewable)
    state = win.get_full_property(connection.intern_atom("WM_STATE"), X.AnyPropertyType)
    assert state.value[0] == 1
    capture = CaptureConnection()
    try:
        assert capture.render is not None
        image = capture.capture(win.id)
        assert image is not None
        assert image.width <= 212 and image.height <= 136
        assert image.getpixel((image.width // 2, image.height // 2))[0] > 200
        # Force the bounded fallback path on the same negotiated visual.
        capture.render = None
        assert capture.capture(win.id) is not None
    finally:
        capture.close()
    win.destroy()
    connection.sync()
    wait_for(lambda: not ipc(cmd="get_clients").get("clients", []))
    assert process.poll() is None


def test_shell_lazy_overlays_and_singleton(desktop):
    connection, _, tmp_path = desktop
    window(connection)
    env = dict(os.environ, QT_QPA_PLATFORM="xcb", QT_QUICK_BACKEND="software")
    shell_command = [os.environ["SADESHELL_TEST_BINARY"]] if os.environ.get("SADESHELL_TEST_BINARY") else [sys.executable, "-m", "sadeshell.main"]
    log_path = tmp_path / "shell.log"
    with log_path.open("w") as log:
        shell = subprocess.Popen(shell_command, env=env, stdout=log, stderr=log)
        try:
            from sadeshell.services.shared.ipc_service import _ipc_socket_path
            wait_for(lambda: Path(_ipc_socket_path()).exists() or shell.poll() is not None, 15)
            assert shell.poll() is None, log_path.read_text()
            duplicate = subprocess.run(shell_command, env=env, capture_output=True, timeout=10)
            assert duplicate.returncode == 1
            for command in ("open-launcher", "open-keybinds", "open-emoji-picker", "open-window-picker", "open-minimized-picker", "confirm-exit"):
                for _ in range(2):
                    result = subprocess.run([*shell_command, "--" + command], env=env, capture_output=True, timeout=10)
                    assert result.returncode == 0, result.stderr.decode()
                    time.sleep(0.4)
            assert shell.poll() is None, log_path.read_text()
        finally:
            if shell.poll() is None:
                shell.terminate()
                shell.wait(timeout=20)
        content = log_path.read_text()
        assert shell.returncode == 0, content
        assert "failed to load" not in content.lower(), content
        assert "Cannot load " not in content, content
        assert "Cannot create " not in content, content
        assert "ReferenceError" not in content, content
        assert "Traceback" not in content, content


@pytest.mark.parametrize("count", [1, 10, 50])
def test_focus_request_budget(desktop, count):
    connection, _, _ = desktop
    root = connection.screen().root
    clients = [window(connection, str(index)) for index in range(count)]
    root.change_attributes(event_mask=X.PropertyChangeMask)
    for client in clients:
        client.change_attributes(event_mask=X.PropertyChangeMask)
    ipc(cmd="focus_window", win_id=clients[0].id)
    connection.sync()
    while connection.pending_events():
        connection.next_event()
    elapsed = []
    for index in range(10):
        started = time.perf_counter()
        assert ipc(cmd="focus_window", win_id=clients[index % count].id)["ok"]
        elapsed.append((time.perf_counter() - started) * 1000)
    connection.sync()
    membership = focused = 0
    membership_atom = connection.intern_atom("_NET_CLIENT_LIST")
    state_atom = connection.intern_atom("_NET_WM_STATE")
    while connection.pending_events():
        change = connection.next_event()
        if change.type == X.PropertyNotify:
            membership += change.atom == membership_atom
            focused += change.atom == state_atom
    print(json.dumps(dict(windows=count, median_ms=statistics.median(elapsed),
                          max_ms=max(elapsed), membership_writes=membership,
                          client_state_writes=focused)))
    if not os.environ.get("SADEWM_BENCH_BASELINE"):
        assert membership == 0
        assert focused <= 20


def test_large_capture_bounds_and_x_resources(desktop):
    import xcffib.res as res
    from sadeshell.services.shared.thumbnail_capture import CaptureConnection
    connection, _, _ = desktop
    root = connection.screen().root
    win = root.create_window(0, 0, 4096, 2160, 0, connection.screen().root_depth,
                             X.InputOutput, X.CopyFromParent, override_redirect=True,
                             background_pixel=0xff0000)
    win.map()
    connection.sync()
    capture = CaptureConnection()
    try:
        extension = capture.connection(res.key)
        def resources():
            capture.connection.core.GetInputFocus().reply()
            reply = extension.QueryClientResources(capture.connection.get_setup().resource_id_base).reply()
            return {item.resource_type: item.count for item in reply.types}
        baseline = resources()
        for _ in range(30):
            image = capture.capture(win.id)
            assert image is not None and image.width <= 212 and image.height <= 136
        assert resources() == baseline
        capture.render = None
        assert capture.capture(win.id) is None  # raw image exceeds 32 MiB
    finally:
        capture.close()
        win.destroy()
        connection.sync()
