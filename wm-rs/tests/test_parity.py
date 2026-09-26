"""Private-server differential and lifecycle tests. Never connects to the user's DISPLAY.

SADEWM_GO_BINARY=/path/sadewm SADEWM_RUST_BINARY=/path/sadewm-rs \
  PYTHONPATH=xdrive python -m pytest wm-rs/tests -q
"""
import contextlib
import json
import os
from pathlib import Path
import signal
import select
import socket
import subprocess
import time

import pytest
from Xlib import X, Xatom
from Xlib.protocol import event
from xdrive import XDrive

GO = os.environ.get("SADEWM_GO_BINARY")
RUST = os.environ.get("SADEWM_RUST_BINARY")


def request(path, command=None, payload=None, **fields):
    with socket.socket(socket.AF_UNIX) as stream:
        stream.settimeout(3)
        stream.connect(str(path))
        stream.sendall(payload if payload is not None else json.dumps({"cmd": command, **fields}).encode())
        stream.shutdown(socket.SHUT_WR)
        data = bytearray()
        while chunk := stream.recv(65536):
            data.extend(chunk)
        assert data.endswith(b"\n")
        return json.loads(data)


@contextlib.contextmanager
def private_display(depth=24, disabled=(), nested=False):
    processes = []
    def start(program, args, env=None):
        read_fd, write_fd = os.pipe()
        try:
            process = subprocess.Popen([program, "-displayfd", str(write_fd), *args, "-ac", "-nolisten", "tcp"], env=env, pass_fds=(write_fd,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(process)
        finally:
            os.close(write_fd)
        with os.fdopen(read_fd) as reader:
            assert select.select([reader], [], [], 5)[0], "private X server startup timed out"
            number = reader.readline().strip()
        assert number.isdigit()
        return ":" + number
    try:
        args = ["-screen", "0", f"1280x800x{depth}"]
        for extension in disabled:
            args += ["-extension", extension]
        name = start("Xvfb", args)
        if nested:
            name = start("Xephyr", ["-screen", "1280x800"], dict(os.environ, DISPLAY=name))
            compositor = subprocess.Popen(["picom", "--config", "/dev/null", "--backend", "xrender"], env=dict(os.environ, DISPLAY=name), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(compositor)
            time.sleep(.2)
            assert compositor.poll() is None
        yield name
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


@contextlib.contextmanager
def desktop(binary, directory, config=None, debug=True, settings=None, extra_env=None, **display_options):
    directory.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(directory)
    for name in ("CONFIG", "DATA", "CACHE", "RUNTIME"):
        path = directory / name.lower()
        path.mkdir(mode=0o700, exist_ok=True)
        env[f"XDG_{name}_HOME" if name != "RUNTIME" else "XDG_RUNTIME_DIR"] = str(path)
    sock = directory / "wm.sock"
    env["SADEWM_SOCKET"] = str(sock)
    env.update(extra_env or {})
    args = [binary] + (["-d"] if debug else [])
    if config is None:
        args += ["--no-config"]
    else:
        cfg = directory / "configuration"
        cfg.mkdir()
        (cfg / "wm.toml").write_text(config)
        if settings is not None:
            (cfg / "settings.toml").write_text(settings)
        (cfg / "startup.sh").write_text('printf "started\\n" >> "$HOME/startup-runs"\n')
        args += ["--custom-config", str(cfg)]
    with private_display(**display_options) as display_name, (directory / "wm.log").open("w") as log:
        env["DISPLAY"] = display_name
        process = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            end = time.monotonic() + 10
            while not sock.exists():
                assert process.poll() is None, (directory / "wm.log").read_text()
                assert time.monotonic() < end, "IPC did not start"
                time.sleep(.02)
            with XDrive(display=display_name) as xd:
                yield xd, sock, process, env
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def send(xd, win, name, values):
    dpy = xd._xdisplay
    data = list(values) + [0] * (5 - len(values))
    dpy.screen().root.send_event(event.ClientMessage(window=win, client_type=dpy.intern_atom(name), data=(32, data)), event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    dpy.sync()
    time.sleep(.12)


def card(xd, win, name):
    prop = win.get_full_property(xd._xdisplay.intern_atom(name), X.AnyPropertyType)
    return list(prop.value) if prop is not None else []


def capture(xd, sock, windows):
    names = {win.id: name for name, win in windows.items()}
    def normalize(value):
        if isinstance(value, dict):
            return {k: names.get(v, v) if k == "win_id" else normalize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [normalize(v) for v in value]
        return value
    root = xd._xdisplay.screen().root
    state = {cmd: normalize(request(sock, cmd)) for cmd in ("get_state", "get_clients", "tags_state")}
    state["geometry"] = {name: list((w.geometry.x, w.geometry.y, w.geometry.width, w.geometry.height)) for name, w in windows.items()}
    state["states"] = {name: sorted(xd._xdisplay.get_atom_name(a) for a in card(xd, w._xwindow, "_NET_WM_STATE")) for name, w in windows.items()}
    state["mapped"] = {name: w.is_mapped for name, w in windows.items()}
    state["desktops"] = {name: card(xd, w._xwindow, "_NET_WM_DESKTOP") for name, w in windows.items()}
    for prop in ("_NET_CLIENT_LIST", "_NET_CLIENT_LIST_STACKING", "_NET_ACTIVE_WINDOW"):
        state[prop] = [names.get(v, v) for v in card(xd, root, prop)]
    for prop in ("_NET_CURRENT_DESKTOP", "_NET_WORKAREA", "_NET_SHOWING_DESKTOP"):
        state[prop] = card(xd, root, prop)
    return state


def scenario(binary, directory):
    result = {}
    with desktop(binary, directory) as (xd, sock, process, env):
        result["empty"] = capture(xd, sock, {})
        result["keybinds"] = request(sock, "keybinds")
        result["errors"] = [request(sock, "unknown"), request(sock, "focus_window", win_id=123), request(sock, "focus_window"), request(sock, payload=b'{"cmd":"unknown","CMD":"tags_state"}'), request(sock, payload=b"{"), request(sock, payload=b" " * 65537)]
        windows = {}
        for name in ("one", "two", "three"):
            windows[name] = xd.new_window(title=name, size=(400, 240))
        xd.wait_for_layout()
        result["tiled"] = capture(xd, sock, windows)
        request(sock, "focus_window", win_id=windows["two"].id)
        xd.keyboard.press("super+shift+Return")
        xd.wait_for_layout()
        result["zoom"] = capture(xd, sock, windows)
        request(sock, "tag", mask=6)
        request(sock, "focus_window", win_id=windows["two"].id)
        xd.wait_for_layout()
        result["tag-focus"] = capture(xd, sock, windows)
        request(sock, "toggleview", mask=1)
        xd.wait_for_layout()
        result["toggleview"] = capture(xd, sock, windows)
        windows["dialog"] = xd.new_window(title="dialog", size=(300, 200), position=(180, 180), type="dialog")
        xd.wait_for_layout()
        result["frame_focus"] = request(sock, "focus_window", win_id=windows["dialog"].frame.id)
        result["dialog"] = capture(xd, sock, windows)
        win = windows["dialog"]
        for label, atom in (("above", "_NET_WM_STATE_ABOVE"), ("fullscreen", "_NET_WM_STATE_FULLSCREEN")):
            send(xd, win.id, "_NET_WM_STATE", [1, xd._xdisplay.intern_atom(atom)])
            result[label] = capture(xd, sock, windows)
        send(xd, win.id, "_NET_WM_STATE", [0, xd._xdisplay.intern_atom("_NET_WM_STATE_FULLSCREEN")])
        result["fullscreen-restore"] = capture(xd, sock, windows)
        send(xd, win.id, "WM_CHANGE_STATE", [3])
        result["minimized"] = capture(xd, sock, windows)
        request(sock, "focus_window", win_id=win.id)
        xd.wait_for_layout()
        result["restored"] = capture(xd, sock, windows)
        send(xd, xd._xdisplay.screen().root, "_NET_SHOWING_DESKTOP", [1])
        result["show-desktop"] = capture(xd, sock, windows)
        send(xd, xd._xdisplay.screen().root, "_NET_SHOWING_DESKTOP", [0])
        result["hide-desktop"] = capture(xd, sock, windows)
        for w in windows.values():
            w.kill()
        xd.wait_for_layout()
        result["destroyed"] = capture(xd, sock, {})
        assert request(sock, "quit") == {"ok": True}
        assert process.wait(timeout=5) == 0
        assert not sock.exists()
    (directory / "snapshot.json").write_text(json.dumps(result, indent=2))
    return result


@pytest.mark.skipif(not GO or not RUST, reason="both backend binaries are required")
def test_differential_protocol_geometry_order_and_ipc(tmp_path):
    expected = scenario(GO, tmp_path / "go")
    actual = scenario(RUST, tmp_path / "rust")
    for step in expected:
        assert actual[step] == expected[step], f"backend difference at {step}; snapshots in {tmp_path}"


@pytest.mark.skipif(not RUST, reason="Rust binary required")
def test_takeover_refusal_signals_and_clean_exit(tmp_path):
    with desktop(RUST, tmp_path) as (xd, sock, process, env):
        win = xd.new_window(title="survivor", type="dialog")
        xd.wait_for_layout()
        second = subprocess.run([RUST, "--no-config"], env=env, capture_output=True, timeout=5)
        assert second.returncode != 0
        assert b"already running" in second.stderr
        assert request(sock, "get_state")["ok"]
        process.send_signal(signal.SIGUSR1)
        time.sleep(.1)
        assert "Rust WM state" in (tmp_path / "wm.log").read_text()
        process.send_signal(signal.SIGHUP)
        assert process.wait(timeout=5) == 0
        assert win._xwindow.query_tree().parent.id == xd._xdisplay.screen().root.id
        assert win.is_mapped
        assert not sock.exists()
        assert not card(xd, xd._xdisplay.screen().root, "_NET_SUPPORTING_WM_CHECK")
        # Restart on the same private server: scan/reparent surviving clients.
        with (tmp_path / "replacement.log").open("w") as log:
            replacement = subprocess.Popen([RUST, "--no-config"], env=env, stdout=log, stderr=log)
            try:
                end = time.monotonic() + 5
                while not sock.exists():
                    assert replacement.poll() is None
                    assert time.monotonic() < end
                    time.sleep(.02)
                xd.wait_for_layout()
                assert win.id in [c["win_id"] for c in request(sock, "get_clients")["clients"]]
                assert win.frame.id != win.id and win.is_mapped
                win.kill()
            finally:
                replacement.terminate()
                replacement.wait(timeout=5)


@pytest.mark.skipif(not GO or not RUST, reason="both backend binaries are required")
def test_configuration_reload_and_startup_contract(tmp_path):
    config = """[appearance]
gappx = 13
[layout]
mfact = 0.6
center_floating = false
[[keys]]
mod = ["super"]
key = "q"
action = "none"
[[keys]]
mod = ["super"]
key = "p"
action = "spawn"
cmd = "echo parity"
[[tagkeys]]
key = "1"
tag = 8
"""
    states = []
    for name, binary in (("go", GO), ("rust", RUST)):
        with desktop(binary, tmp_path / name, config) as (xd, sock, process, env):
            path = tmp_path / name / "configuration/wm.toml"
            initial = request(sock, "get_state")
            keys = request(sock, "keybinds")
            # Confirmed Go startup bug: bindings/rules are first loaded on reload.
            q_bound = any(k["key"] == "Q" and k["mod"] == ["Super"] for k in keys["keybinds"])
            assert q_bound == (name == "go")
            assert request(sock, "reload") == {"ok": True}
            loaded_keys = request(sock, "keybinds")
            if name == "rust":
                assert keys == loaded_keys
            path.write_text("[appearance]\ngappx=0\n[layout]\nnmaster=0\n")
            assert request(sock, "reload") == {"ok": True}
            immediate = request(sock, "get_state")
            # Go retains the current tag's old master count until a tag switch;
            # Rust applies the reloaded setting immediately.
            assert immediate.get("nmaster", 0) == (1 if name == "go" else 0)
            request(sock, "view", mask=2)
            request(sock, "view", mask=1)
            after = request(sock, "get_state")
            time.sleep(.15)
            assert (tmp_path / name / "startup-runs").read_text() == "started\n"
            states.append((initial, loaded_keys, after, request(sock, "keybinds")))
    assert states[0] == states[1]


@pytest.mark.skipif(not RUST, reason="Rust binary required")
@pytest.mark.parametrize("trigger", ["keyboard", "ewmh", "initial"])
def test_tiled_maximize_keeps_tile_slot_and_no_titlebar(tmp_path, trigger):
    from xdrive.window import Window

    with desktop(RUST, tmp_path) as (xd, sock, process, env):
        dpy = xd._xdisplay
        root = dpy.screen().root
        atom = dpy.intern_atom
        axes = [atom("_NET_WM_STATE_MAXIMIZED_HORZ"), atom("_NET_WM_STATE_MAXIMIZED_VERT")]
        peers = [xd.new_window(title=f"peer-{i}") for i in range(2)]
        if trigger == "initial":
            raw = root.create_window(100, 100, 400, 250, 0, X.CopyFromParent)
            raw.set_wm_class("Navigator", "firefox")
            raw.change_property(atom("_NET_WM_STATE"), Xatom.ATOM, 32, axes)
            raw.map()
            dpy.sync()
            win = Window(raw, dpy)
            xd.wait_for_layout()
        else:
            win = xd.new_window(title="tiled-maximize")
            xd.wait_for_layout()
        original = win.geometry
        peer_geometry = [w.geometry for w in peers]
        request(sock, "focus_window", win_id=win.id)
        if trigger == "keyboard":
            xd.keyboard.press("super+m")
            xd.wait_for_layout()
        elif trigger == "ewmh":
            send(xd, win.id, "_NET_WM_STATE", [1, *axes])

        client = next(c for c in request(sock, "get_clients")["clients"] if c["win_id"] == win.id)
        assert client["maximized"] and not client["floating"]
        assert win._xwindow.query_tree().parent.id == root.id
        assert card(xd, win._xwindow, "_NET_FRAME_EXTENTS") == [0, 0, 0, 0]
        assert set(axes).issubset(card(xd, win._xwindow, "_NET_WM_STATE"))
        assert win.geometry.x == 0 and win.geometry.y == 40
        assert win.geometry.width == 1276 and win.geometry.height == 756
        assert [w.geometry for w in peers] == peer_geometry

        if trigger == "keyboard":
            xd.keyboard.press("super+m")
            xd.wait_for_layout()
        else:
            send(xd, win.id, "_NET_WM_STATE", [0, *axes])
        client = next(c for c in request(sock, "get_clients")["clients"] if c["win_id"] == win.id)
        assert not client["maximized"] and not client["floating"]
        assert not set(axes).intersection(card(xd, win._xwindow, "_NET_WM_STATE"))
        assert win._xwindow.query_tree().parent.id == root.id
        assert [w.geometry for w in peers] == peer_geometry
        if trigger != "initial":
            assert win.geometry == original
        else:
            assert win.geometry.width < 1276 and win.geometry.x > 0
        win.kill()
        for peer in peers:
            peer.kill()


@pytest.mark.skipif(not RUST, reason="Rust binary required")
def test_tiled_maximize_axes_fullscreen_and_shade_restore(tmp_path):
    with desktop(RUST, tmp_path) as (xd, sock, process, env):
        xd.new_window(title="peer")
        win = xd.new_window(title="tiled-axes")
        xd.wait_for_layout()
        original = win.geometry
        atom = xd._xdisplay.intern_atom
        horizontal = atom("_NET_WM_STATE_MAXIMIZED_HORZ")
        vertical = atom("_NET_WM_STATE_MAXIMIZED_VERT")
        send(xd, win.id, "_NET_WM_STATE", [1, horizontal])
        assert win.geometry.width == 1276
        assert (win.geometry.y, win.geometry.height) == (original.y, original.height)
        send(xd, win.id, "_NET_WM_STATE", [1, vertical])
        maximized = win.geometry
        for state in ("_NET_WM_STATE_FULLSCREEN", "_NET_WM_STATE_SHADED"):
            send(xd, win.id, "_NET_WM_STATE", [1, atom(state)])
            send(xd, win.id, "_NET_WM_STATE", [0, atom(state)])
            client = next(c for c in request(sock, "get_clients")["clients"] if c["win_id"] == win.id)
            assert client["maximized"] and not client["floating"]
            assert win.geometry == maximized
            assert card(xd, win._xwindow, "_NET_FRAME_EXTENTS") == [0, 0, 0, 0]
        send(xd, win.id, "_NET_WM_STATE", [0, horizontal])
        assert (win.geometry.x, win.geometry.width) == (original.x, original.width)
        assert win.geometry.y == 40 and win.geometry.height == 756
        send(xd, win.id, "_NET_WM_STATE", [0, vertical])
        assert win.geometry == original
        send(xd, win.id, "_NET_WM_STATE", [1, horizontal, vertical])
        extra = xd.new_window(title="opened-while-maximized")
        xd.wait_for_layout()
        assert win.geometry == maximized
        send(xd, win.id, "_NET_WM_STATE", [0, horizontal, vertical])
        assert (win.geometry.x, win.geometry.y, win.geometry.width) == (
            original.x, original.y, original.width,
        )
        assert win.geometry.height == extra.geometry.height < original.height
        assert extra.geometry.y > win.geometry.y + win.geometry.height
        extra.kill()
        xd.wait_for_layout()
        assert win.geometry == original


@pytest.mark.skipif(not RUST, reason="Rust binary required")
def test_shade_maximize_axes_restore_and_frame_bounds(tmp_path):
    with desktop(RUST, tmp_path) as (xd, sock, process, env):
        win = xd.new_window(title="axes", size=(400, 250), position=(100, 200), type="dialog")
        xd.wait_for_layout()
        original = win.geometry
        atom = xd._xdisplay.intern_atom
        send(xd, win.id, "_NET_WM_STATE", [1, atom("_NET_WM_STATE_MAXIMIZED_HORZ")])
        assert win.geometry.width == 1280
        assert win.geometry.y == original.y and win.geometry.height == original.height
        send(xd, win.id, "_NET_WM_STATE", [1, atom("_NET_WM_STATE_MAXIMIZED_VERT")])
        assert win.frame.geometry.y == 40, "maximized titlebar must remain below reserved work area"
        send(xd, win.id, "_NET_WM_STATE", [0, atom("_NET_WM_STATE_MAXIMIZED_HORZ"), atom("_NET_WM_STATE_MAXIMIZED_VERT")])
        assert win.geometry == original
        send(xd, win.id, "_NET_WM_STATE", [1, atom("_NET_WM_STATE_SHADED")])
        assert not win.is_mapped and win.frame.geometry.height == 28
        send(xd, win.id, "_NET_WM_STATE", [0, atom("_NET_WM_STATE_SHADED")])
        assert win.is_mapped and win.geometry == original
        win.kill()


@pytest.mark.skipif(not RUST, reason="Rust binary required")
@pytest.mark.parametrize("nested", [False, True], ids=["xvfb", "xephyr-picom"])
def test_decoration_unicode_hover_resize_opacity_and_resource_cleanup(tmp_path, nested):
    from Xlib.ext import res  # noqa: F401 -- registers the XRes methods
    with desktop(RUST, tmp_path, nested=nested) as (xd, sock, process, env):
        dpy = xd._xdisplay
        root = dpy.screen().root
        check = card(xd, root, "_NET_SUPPORTING_WM_CHECK")[0]
        def resources():
            dpy.sync()
            reply = dpy.res_query_client_resources(check)
            return {dpy.get_atom_name(row.resource_type): row.count for row in reply.types if row.count}
        baseline = resources()
        for cycle in range(12):
            xd.mouse.move(0, 0)
            win = xd.new_window(title="Long Unicode title · Café Ω 日本語 😀 " * 5, size=(500, 180), position=(150, 150), type="dialog")
            xd.wait_for_layout()
            frame = win.frame
            titles = [child for child in frame._xwindow.query_tree().children if child.id != win.id]
            assert len(titles) == 1
            title = titles[0]
            before = title.get_image(0, 0, 100, 28, X.ZPixmap, 0xffffffff).data
            xd.mouse.move(frame.geometry.x + 16, frame.geometry.y + 14)
            xd.wait_for_layout()
            hover = title.get_image(0, 0, 100, 28, X.ZPixmap, 0xffffffff).data
            assert before != hover
            win._xwindow.change_property(dpy.intern_atom("_NET_WM_WINDOW_OPACITY"), Xatom.CARDINAL, 32, [0x90000000])
            dpy.sync()
            time.sleep(.08)
            assert card(xd, frame._xwindow, "_NET_WM_WINDOW_OPACITY") == [0x90000000]
            if cycle == 0:
                xd.screenshot(str(tmp_path / "decorations.png"))
            win._xwindow.configure(width=35, height=100)
            dpy.sync()
            time.sleep(.08)
            assert title.get_geometry().width == 35
            if cycle == 0:
                send(xd, win.id, "WM_CHANGE_STATE", [3])
                assert not win.is_mapped
                assert request(sock, "focus_window", win_id=win.id) == {"ok": True}
                xd.wait_for_layout()
                assert win.is_mapped
                original = win.geometry
                fullscreen = dpy.intern_atom("_NET_WM_STATE_FULLSCREEN")
                send(xd, win.id, "_NET_WM_STATE", [1, fullscreen])
                assert (win.geometry.x, win.geometry.y, win.geometry.width, win.geometry.height) == (0, 0, 1280, 800)
                send(xd, win.id, "_NET_WM_STATE", [0, fullscreen])
                assert win.geometry == original
            win.kill()
            xd.wait_for_layout()
            assert resources() == baseline


@pytest.mark.skipif(not RUST, reason="Rust binary required")
def test_missing_optional_extensions_and_16_bit_rendering(tmp_path):
    with desktop(RUST, tmp_path, depth=16, disabled=("RANDR", "XINERAMA", "MIT-SCREEN-SAVER", "DPMS")) as (xd, sock, process, env):
        dpy = xd._xdisplay
        root = dpy.screen().root
        supported = {dpy.get_atom_name(a) for a in card(xd, root, "_NET_SUPPORTED")}
        assert ("_NET_WM_SYNC_REQUEST" in supported) == bool(dpy.query_extension("SYNC").present)
        assert "_NET_WM_FULLSCREEN_MONITORS" not in supported
        win = xd.new_window(title="16-bit rendering Ω", size=(301, 100), type="dialog")
        xd.wait_for_layout()
        assert win.frame.id != win.id
        raw = win.frame._xwindow.get_image(0, 0, 301, 28, X.ZPixmap, 0xffffffff)
        assert raw.depth == 16 and len(set(raw.data)) > 8
        win.kill()


@pytest.mark.skipif(not RUST, reason="Rust binary required")
def test_minimize_restore_then_genuine_withdrawal(tmp_path):
    with desktop(RUST, tmp_path) as (xd, sock, process, env):
        win = xd.new_window(title="withdraw", type="dialog")
        xd.wait_for_layout()
        send(xd, win.id, "WM_CHANGE_STATE", [3])
        request(sock, "focus_window", win_id=win.id)
        xd.wait_for_layout()
        win._xwindow.unmap()
        xd._xdisplay.sync()
        time.sleep(.15)
        assert request(sock, "get_clients") == {"ok": True}
        assert not card(xd, win._xwindow, "_NET_WM_STATE")
        win.kill()


def test_supported_registry_matches_go_compliance_matrix():
    import re
    repository = Path(__file__).resolve().parents[2]
    source = (repository / "wm-rs/src/atoms.rs").read_text()
    rust = re.findall(r'"(_NET_[A-Z_0-9]+)"', source.split("pub const SUPPORTED", 1)[1])
    matrix = (repository / "wm/docs/ewmh-1.5.md").read_text().split("The unconditional `_NET_SUPPORTED` inventory is:", 1)[1].split("```text", 1)[1].split("```", 1)[0].split()
    assert rust == matrix


@pytest.mark.skipif(not RUST, reason="Rust binary required")
def test_moveresize_cancel_keyboard_and_sync_fallback(tmp_path):
    import xcffib
    import xcffib.sync as sync
    with desktop(RUST, tmp_path) as (xd, sock, process, env):
        win = xd.new_window(title="protocol-resize", size=(400, 250), type="dialog")
        xd.wait_for_layout()
        original = win.geometry
        # Keyboard move commits with Enter, while Escape rolls back to the
        # original geometry even after multiple queued motion steps.
        send(xd, win.id, "_NET_WM_MOVERESIZE", [500, 400, 10, 0, 2])
        xd.keyboard.press("Right")
        xd.keyboard.press("Down")
        xd.wait_for_layout()
        assert win.geometry.x == original.x + 10
        assert win.geometry.y == original.y + 10
        xd.keyboard.press("Escape")
        xd.wait_for_layout()
        assert win.geometry == original
        send(xd, win.id, "_NET_WM_MOVERESIZE", [500, 400, 8, 1, 2])
        xd.mouse.move(560, 430)
        xd.wait_for_layout()
        send(xd, win.id, "_NET_WM_MOVERESIZE", [0, 0, 11])
        assert win.geometry == original
        # A real Sync counter: the WM applies one resize, coalesces the next
        # while the client is unresponsive, then falls back after one second.
        connection = xcffib.connect(display=env["DISPLAY"])
        extension = connection(sync.key)
        extension.Initialize(3, 1).reply()
        counter = connection.generate_id()
        extension.CreateCounter(counter, sync.INT64.synthetic(1, 0), is_checked=True).check()
        win._xwindow.set_wm_protocols([xd._xdisplay.intern_atom("_NET_WM_SYNC_REQUEST")])
        win._xwindow.change_property(xd._xdisplay.intern_atom("_NET_WM_SYNC_REQUEST_COUNTER"), Xatom.CARDINAL, 32, [counter])
        xd._xdisplay.sync()
        time.sleep(.1)
        send(xd, win.id, "_NET_WM_MOVERESIZE", [500, 400, 9, 0, 2])
        xd.keyboard.press("Right")
        time.sleep(.1)
        first = win.geometry.width
        assert first == original.width + 10
        sync_messages = []
        while xd._xdisplay.pending_events():
            message = xd._xdisplay.next_event()
            if message.type == X.ClientMessage and message.client_type == xd._xdisplay.intern_atom("WM_PROTOCOLS"):
                if message.data[1][0] == xd._xdisplay.intern_atom("_NET_WM_SYNC_REQUEST"):
                    sync_messages.append(message.data[1])
        assert sync_messages and list(sync_messages[-1][2:4]) == [1, 1]
        xd.keyboard.press("Right")
        time.sleep(.1)
        assert win.geometry.width == first
        end = time.monotonic() + 2
        while win.geometry.width == first and time.monotonic() < end:
            time.sleep(.02)
        assert win.geometry.width == original.width + 20
        xd.keyboard.press("Right")
        time.sleep(.1)
        assert win.geometry.width == original.width + 20
        extension.SetCounter(counter, sync.INT64.synthetic(1, 2), is_checked=True).check()
        end = time.monotonic() + .5
        while win.geometry.width != original.width + 30 and time.monotonic() < end:
            time.sleep(.01)
        assert win.geometry.width == original.width + 30, "acknowledgement must release coalesced resize before timeout"
        xd.keyboard.press("Enter")
        xd.wait_for_layout()
        connection.disconnect()
        win.kill()


@pytest.mark.skipif(not GO or not RUST, reason="both backend binaries are required")
def test_maximized_frame_boundary_go_reproducer(tmp_path):
    for name, binary in (("go", GO), ("rust", RUST)):
        with desktop(binary, tmp_path / name) as (xd, sock, process, env):
            win = xd.new_window(title="maximized-frame", size=(400, 250), type="dialog")
            xd.wait_for_layout()
            original = win.geometry
            atom = xd._xdisplay.intern_atom
            axes = [atom("_NET_WM_STATE_MAXIMIZED_HORZ"), atom("_NET_WM_STATE_MAXIMIZED_VERT")]
            send(xd, win.id, "_NET_WM_STATE", [1, *axes])
            # Go's content starts at y=40 and its frame extends 28px above it.
            assert win.frame.geometry.y == (12 if name == "go" else 40)
            send(xd, win.id, "_NET_WM_STATE", [0, *axes])
            assert win.geometry == original
            win.kill()


@pytest.mark.skipif(not GO or not RUST, reason="both backend binaries are required")
def test_wallpaper_root_pixmaps_cover_and_cleanup(tmp_path):
    from PIL import Image
    for name, binary in (("go", GO), ("rust", RUST)):
        directory = tmp_path / name
        wallpaper = directory / ".config/sade/wp.jpg"
        wallpaper.parent.mkdir(parents=True)
        source = Image.new("RGB", (200, 100), "red")
        source.paste("blue", (100, 0, 200, 100))
        source.save(wallpaper, quality=100, subsampling=0)
        with desktop(binary, directory) as (xd, sock, process, env):
            root = xd._xdisplay.screen().root
            end = time.monotonic() + 5
            while not card(xd, root, "_XROOTPMAP_ID") and time.monotonic() < end:
                time.sleep(.02)
            pixmaps = card(xd, root, "_XROOTPMAP_ID")
            assert len(pixmaps) == 1 and pixmaps[0] != 0
            assert card(xd, root, "ESETROOT_PMAP_ID") == pixmaps
            pixmap = xd._xdisplay.create_resource_object("pixmap", pixmaps[0])
            geometry = pixmap.get_geometry()
            assert (geometry.width, geometry.height) == (1280, 800)
            raw = pixmap.get_image(0, 400, 1280, 1, X.ZPixmap, 0xffffffff)
            pixels = Image.frombytes("RGB", (1280, 1), raw.data, "raw", "BGRX")
            assert pixels.getpixel((100, 0))[0] >= 250
            assert pixels.getpixel((1180, 0))[2] >= 250
            process.terminate()
            assert process.wait(timeout=5) == 0
            assert not card(xd, root, "_XROOTPMAP_ID")
            assert not card(xd, root, "ESETROOT_PMAP_ID")


@pytest.mark.skipif(not GO or not RUST, reason="both backend binaries are required")
def test_stale_focus_events_preserve_toolkit_child_focus(tmp_path):
    for name, binary in (("go", GO), ("rust", RUST)):
        with desktop(binary, tmp_path / name) as (xd, sock, process, env):
            first = xd.new_window(title="toolkit", type="dialog")
            other = xd.new_window(title="other", type="dialog")
            xd.wait_for_layout()
            child = first._xwindow.create_window(10, 10, 80, 50, 0, X.CopyFromParent, X.InputOutput, X.CopyFromParent)
            child.map()
            request(sock, "focus_window", win_id=first.id)
            child.set_input_focus(X.RevertToParent, X.CurrentTime)
            xd._xdisplay.sync()
            # Model a queued obsolete event arriving after the current focus.
            other._xwindow.send_event(event.FocusIn(window=other.id, mode=X.NotifyNormal, detail=X.NotifyNonlinear), event_mask=X.FocusChangeMask)
            xd._xdisplay.sync()
            time.sleep(.15)
            assert xd._xdisplay.get_input_focus().focus.id == child.id
            other._xwindow.set_input_focus(X.RevertToParent, X.CurrentTime)
            xd._xdisplay.sync()
            time.sleep(.15)
            assert xd._xdisplay.get_input_focus().focus.id == first.id
            first.kill()
            other.kill()


@pytest.mark.skipif(not RUST, reason="Rust binary required")
def test_shutdown_cancels_display_job_but_preserves_launched_application(tmp_path):
    programs = tmp_path / "bin"
    programs.mkdir()
    xrandr = programs / "xrandr"
    xrandr.write_text('#!/bin/sh\necho $$ > "$HOME/display-job.pid"\nexec sleep 60\n')
    xrandr.chmod(0o755)
    config = '[[keys]]\nmod=["Super"]\nkey="p"\naction="spawn"\ncmd="echo $$ > $HOME/application.pid; exec sleep 60"\n'
    application = None
    try:
        with desktop(RUST, tmp_path, config=config, settings="[display]\nenabled=false\n", extra_env={"PATH": str(programs) + os.pathsep + os.environ["PATH"]}) as (xd, sock, process, env):
            end = time.monotonic() + 5
            while not (tmp_path / "display-job.pid").exists():
                assert time.monotonic() < end
                time.sleep(.02)
            xd.keyboard.press("super+p")
            while not (tmp_path / "application.pid").exists():
                assert time.monotonic() < end
                time.sleep(.02)
            application = int((tmp_path / "application.pid").read_text())
            display_job = int((tmp_path / "display-job.pid").read_text())
            assert request(sock, "get_state")["ok"]
            started = time.monotonic()
            process.terminate()
            assert process.wait(timeout=2) == 0
            assert time.monotonic() - started < 2
            with pytest.raises(ProcessLookupError):
                os.kill(display_job, 0)
            os.kill(application, 0)
    finally:
        if application:
            try:
                os.kill(application, signal.SIGTERM)
            except ProcessLookupError:
                pass
