"""Exercise installed wrappers and GUI startup on a private X server and bus."""

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

from Xlib import X, Xatom, display


shell, settings, greeter, go_wm, rust_wm = map(Path, sys.argv[1:])


def wait_for(predicate, process, log, timeout=20):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert process.poll() is None, log.read_text()
        assert time.monotonic() < deadline, log.read_text()
        time.sleep(0.05)


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    env = dict(os.environ, HOME=str(root), XDG_RUNTIME_DIR=str(root),
               XDG_CONFIG_HOME=str(root / "config"), XDG_DATA_HOME=str(root / "data"),
               XDG_CACHE_HOME=str(root / "cache"), XAUTHORITY="",
               QT_QPA_PLATFORM="xcb", QT_QUICK_BACKEND="software",
               SADEWM_SOCKET=str(root / "wm.sock"))
    # Deliberately request the KDE controls that failed without Kirigami.
    env["QT_QUICK_CONTROLS_STYLE"] = "org.kde.desktop"
    env["QT_QPA_PLATFORMTHEME"] = "kde"
    probe_env = dict(env, PYTHONPATH="/session/python path", PYTHONHOME="/session/python",
                     QT_PLUGIN_PATH="", LD_LIBRARY_PATH="/session/libs",
                     XDG_DATA_DIRS="/session/share", XDG_CONFIG_DIRS="/session/config")
    probe = subprocess.run(
        [str(shell / "libexec/sadeshell-python"), "-c",
         "import json, os; from sadeshell.launch_environment import launch_environment; "
         "print(json.dumps([os.environ['SADESHELL_SESSION_VARS'].split(), launch_environment()]))"],
        env=probe_env, capture_output=True, text=True, timeout=20,
    )
    assert probe.returncode == 0, probe.stderr
    names, restored = json.loads(probe.stdout)
    for name in names:
        assert restored.get(name) == probe_env.get(name), name
        assert (name in restored) == (name in probe_env), name
    assert not any(name.startswith("SADESHELL_SESSION_") for name in restored)

    # Check which systemctl a WM startup script (and its children) actually sees.
    host_bin = root / "host-bin"
    host_bin.mkdir()
    systemctl = host_bin / "systemctl"
    # Nix build sandboxes have no /bin/sh.
    systemctl.write_text(f"#!{os.environ['TEST_SHELL']}\nprintf 'host-systemd\\n'\n")
    systemctl.chmod(0o755)
    env["PATH"] = str(host_bin) + ":" + env["PATH"]

    read_fd, write_fd = os.pipe()
    server = subprocess.Popen(["Xvfb", "-displayfd", str(write_fd), "-screen", "0",
                               "1280x800x24", "-ac", "-nolisten", "tcp"], pass_fds=(write_fd,))
    os.close(write_fd)
    try:
        with os.fdopen(read_fd) as pipe:
            assert select.select([pipe], [], [], 10)[0], "Xvfb did not start"
            number = pipe.readline().strip()
        assert number.isdigit(), "Xvfb did not provide a display number"
        env["DISPLAY"] = ":" + number
        connection = display.Display(env["DISPLAY"])
        try:
            for package, executable in ((go_wm, "sadewm"), (rust_wm, "sadewm-rs")):
                config = root / executable
                config.mkdir()
                result = config / "systemctl.txt"
                (config / "startup.sh").write_text(f'systemctl --version > "{result}"\n')
                log_path = config / "wm.log"
                with log_path.open("w") as log:
                    process = subprocess.Popen([str(package / "bin" / executable),
                                                "--custom-config", str(config)], env=env,
                                               stdout=log, stderr=log)
                    try:
                        wait_for(lambda: result.exists() and result.stat().st_size, process, log_path)
                        assert result.read_text() == "host-systemd\n", result.read_text()
                    finally:
                        process.terminate()
                        process.wait(timeout=10)

            def visible_windows(pid):
                windows = []
                for window in connection.screen().root.query_tree().children:
                    try:
                        owner = window.get_full_property(connection.intern_atom("_NET_WM_PID"), Xatom.CARDINAL)
                        if owner is not None and owner.value[0] == pid and window.get_attributes().map_state == X.IsViewable:
                            windows.append(window)
                    except Exception:
                        pass  # A popup can disappear between queries.
                return windows

            for package, executable in ((shell, "sadeshell"), (settings, "sadesettings"),
                                        (greeter, "sadewm-greeter")):
                log_path = root / (executable + ".log")
                app_env = dict(env)
                if executable == "sadesettings":
                    # Validate the schema/helper closure without persisting dconf
                    # changes through a session service outside this test home.
                    appearance = subprocess.run(
                        [str(package / "bin" / executable), "--apply-appearance"],
                        env=dict(app_env, GSETTINGS_BACKEND="memory"),
                        capture_output=True, text=True, timeout=20,
                    )
                    assert appearance.returncode == 0 and not appearance.stderr, appearance.stderr
                if executable == "sadewm-greeter":
                    app_env["SADEWM_GREETER_DEV"] = "1"
                    app_env.pop("QT_QUICK_CONTROLS_STYLE")  # Qt5 greeter has its own style.
                    app_env.pop("QT_QPA_PLATFORMTHEME")
                with log_path.open("w") as log:
                    process = subprocess.Popen([str(package / "bin" / executable)], env=app_env,
                                               stdout=log, stderr=log)
                    try:
                        wait_for(lambda: visible_windows(process.pid), process, log_path)
                        time.sleep(0.3)
                        assert process.poll() is None, log_path.read_text()
                    finally:
                        process.terminate()
                        process.wait(timeout=20)
                output = log_path.read_text()
                assert "failed to load" not in output.lower(), output
                assert "Traceback" not in output, output
                print(f"{executable}: mapped a window and shut down without QML/Python errors")
        finally:
            connection.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
