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
    assert ipc(cmd="view", mask=2)["ok"]
    assert ipc(cmd="focus_window", win_id=win.id)["ok"]
    wait_for(lambda: win.get_attributes().map_state == X.IsViewable)
    state = win.get_full_property(connection.intern_atom("WM_STATE"), X.AnyPropertyType)
    assert state.value[0] == 1
    if style == "fullscreen":
        state = win.get_full_property(connection.intern_atom("_NET_WM_STATE"), Xatom.ATOM)
        assert connection.intern_atom("_NET_WM_STATE_FULLSCREEN") in state.value
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


def test_property_republication_class_updates_and_stacking(desktop):
    connection, _, _ = desktop
    root = connection.screen().root
    # Keep focus-follows-mouse out of the overlapping dialog raise sequence.
    root.warp_pointer(connection.screen().width_in_pixels - 1,
                      connection.screen().height_in_pixels - 1)
    connection.sync()
    clients = [window(connection, str(index), style="floating") for index in range(3)]
    ids = [client.id for client in clients]

    def values(win, name):
        prop = win.get_full_property(connection.intern_atom(name), X.AnyPropertyType)
        return list(prop.value) if prop is not None else []

    assert values(root, "_NET_CLIENT_LIST") == ids
    for name in ("_NET_CLIENT_LIST", "_NET_CLIENT_LIST_STACKING"):
        root.delete_property(connection.intern_atom(name))
        connection.sync()
        wait_for(lambda: set(values(root, name)) == set(ids))
    clients[0].set_wm_class("changed-instance", "ChangedClass")
    connection.sync()
    wait_for(lambda: any(c["win_id"] == ids[0] and c["class"] == "ChangedClass"
                         for c in ipc(cmd="get_clients")["clients"]))
    assert ipc(cmd="focus_window", win_id=ids[0])["ok"]
    focused_atom = connection.intern_atom("_NET_WM_STATE_FOCUSED")
    clients[0].delete_property(connection.intern_atom("_NET_WM_STATE"))
    connection.sync()
    wait_for(lambda: focused_atom in values(clients[0], "_NET_WM_STATE"))

    # Reinstall the same server modifier mapping to exercise MappingNotify
    # without modifying the user's keyboard (this is a private X server).
    connection.set_modifier_mapping(connection.get_modifier_mapping())
    connection.sync()
    for client in clients:
        assert ipc(cmd="focus_window", win_id=client.id)["ok"]
        assert values(root, "_NET_CLIENT_LIST") == ids
        frames = {c.query_tree().parent.id: c.id for c in clients}
        expected = [frames.get(child.id, child.id) for child in root.query_tree().children
                    if child.id in frames or child.id in ids]
        assert values(root, "_NET_CLIENT_LIST_STACKING") == expected
        # Separate GetProperty replies are not an atomic server snapshot; a
        # queued EnterNotify may otherwise change focus between those replies.
        wait_for(lambda: sum(focused_atom in values(c, "_NET_WM_STATE") for c in clients) == 1)


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


@pytest.mark.parametrize("count", [1, 10, 50])
def test_shell_resource_measurements(desktop, count):
    """Measure readiness and idle work without hardware-specific time gates.

    The audit hook records Python subprocess launches, including short-lived
    children that /proc polling would miss. Qt/native child launches are outside
    this counter. All commands address this fixture's socket directly.
    """
    connection, _, tmp_path = desktop
    for index in range(count):
        window(connection, str(index))
    runner = (
        "import json,os,runpy,sys,time\n"
        "def audit(event,args):\n"
        " if event == 'subprocess.Popen':\n"
        "  os.write(1,('SUBPROCESS '+json.dumps([time.monotonic(),str(args[0])])+'\\n').encode())\n"
        "sys.addaudithook(audit)\n"
        "runpy.run_module('sadeshell.main',run_name='__main__')\n"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="xcb", QT_QUICK_BACKEND="software")
    # A pre-change package can be supplied without modifying the checkout.
    baseline = os.environ.get("SADESHELL_BENCH_SOURCE")
    if baseline:
        env["PYTHONPATH"] = baseline
    log_path = tmp_path / "measurements.log"
    root = connection.screen().root
    pid_atom = connection.intern_atom("_NET_WM_PID")

    def visible_shell_windows(pid):
        found = set()
        for child in root.query_tree().children:
            try:
                prop = child.get_full_property(pid_atom, Xatom.CARDINAL)
                if prop is not None and prop.value[0] == pid and child.get_attributes().map_state == X.IsViewable:
                    found.add(child.id)
            except Exception:  # Native windows may disappear between queries.
                continue
        return found

    def cpu_ticks(pid):
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return int(fields[11]) + int(fields[12])

    from sadeshell.services.shared.ipc_service import _ipc_socket_path
    def toggle_picker():
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(5)
            client.connect(_ipc_socket_path())
            client.sendall(b"open-window-picker")
            assert client.recv(1024).strip() == b"ok"

    with log_path.open("w") as log:
        started = time.monotonic()
        process = subprocess.Popen([sys.executable, "-c", runner], env=env, stdout=log, stderr=log)
        try:
            wait_for(lambda: visible_shell_windows(process.pid) and Path(_ipc_socket_path()).exists(), 20)
            startup_ms = (time.monotonic() - started) * 1000
            bar_windows = visible_shell_windows(process.pid)
            started = time.monotonic()
            toggle_picker()
            wait_for(lambda: visible_shell_windows(process.pid) - bar_windows)
            picker_ms = (time.monotonic() - started) * 1000
            time.sleep(1)
            toggle_picker()
            wait_for(lambda: visible_shell_windows(process.pid) == bar_windows)
            time.sleep(1)
            before_fds = len(list(Path(f"/proc/{process.pid}/fd").iterdir()))
            before_ticks = cpu_ticks(process.pid)
            idle_start = time.monotonic()
            time.sleep(12)  # Covers the former eight-/ten-second CLI poll timers.
            idle_end = time.monotonic()
            cpu_percent = ((cpu_ticks(process.pid) - before_ticks) / os.sysconf("SC_CLK_TCK") /
                           (idle_end - idle_start) * 100)
            launches = [json.loads(line.removeprefix("SUBPROCESS "))
                        for line in log_path.read_text().splitlines() if line.startswith("SUBPROCESS ")]
            idle_launches = [name for stamp, name in launches if idle_start <= stamp <= idle_end]
            images = list(tmp_path.glob("sadeshell-winpicker-*/*.png"))
            cache_bytes = sum(path.stat().st_size for path in images)
            after_fds = len(list(Path(f"/proc/{process.pid}/fd").iterdir()))
            print(json.dumps(dict(shell_windows=count, startup_ms=startup_ms, picker_map_ms=picker_ms,
                                  idle_cpu_percent=cpu_percent, idle_seconds=idle_end-idle_start,
                                  idle_subprocesses=idle_launches, total_subprocesses=len(launches),
                                  cache_files=len(images), cache_bytes=cache_bytes,
                                  fd_before=before_fds, fd_after=after_fds)))
            assert process.poll() is None, log_path.read_text()
            if not baseline:
                assert idle_launches == []
                assert len(images) <= 128 and cache_bytes <= 32 * 1024 * 1024
                assert after_fds <= before_fds
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise
