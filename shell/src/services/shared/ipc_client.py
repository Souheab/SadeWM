"""Lightweight IPC client for sadeshell — no PySide6 dependency."""

import glob
import os
import re
import socket


def _socket_candidates() -> list[str]:
    """Return all candidate socket paths in priority order.

    Checks:
    1. XDG_RUNTIME_DIR/sadeshell-{display}.sock  (exact, preferred)
    2. /tmp/sadeshell-{display}.sock             (exact, fallback dir)
    3. All sadeshell-*.sock in XDG_RUNTIME_DIR   (scan, DISPLAY mismatch)
    4. All sadeshell-*.sock in /tmp              (scan, DISPLAY mismatch)

    All candidates are returned regardless of whether the file exists;
    the caller is responsible for trying each and reporting results.
    """
    display = os.environ.get("DISPLAY", ":0")
    # Normalise: strip screen number (:0.0 → :0)
    display = re.sub(r"\.\d+$", "", display)
    display_clean = display.lstrip(":").replace("/", "_") or "0"
    filename = f"sadeshell-{display_clean}.sock"

    search_dirs: list[str] = []
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isdir(runtime):
        search_dirs.append(runtime)
    search_dirs.append("/tmp")

    seen: set[str] = set()
    candidates: list[str] = []

    # Exact-name candidates first
    for d in search_dirs:
        p = os.path.join(d, filename)
        if p not in seen:
            seen.add(p)
            candidates.append(p)

    # Scan for any other sadeshell-*.sock (handles DISPLAY env mismatch
    # between the systemd service and the calling shell)
    for d in search_dirs:
        try:
            found = glob.glob(os.path.join(d, "sadeshell-*.sock"))
            # Most-recently modified first — the live instance
            found.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
                       reverse=True)
            for p in found:
                if p not in seen:
                    seen.add(p)
                    candidates.append(p)
        except Exception:
            pass

    return candidates


def send_ipc_command(command: str) -> str:
    """Send a command to a running sadeshell instance.

    Tries every candidate socket in order.  If all fail, returns an error
    string that lists each path and why it was rejected so the user can
    diagnose what went wrong.
    """
    display = os.environ.get("DISPLAY", ":0")
    candidates = _socket_candidates()

    tried: list[str] = []
    for path in candidates:
        if not os.path.exists(path):
            tried.append(f"{path} — not found")
            continue
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(2.0)
            sock.connect(path)
            sock.sendall(command.encode("utf-8") + b"\n")
            response = sock.recv(4096).decode("utf-8").strip()
            return response
        except (ConnectionRefusedError, FileNotFoundError):
            tried.append(f"{path} — stale socket (connection refused)")
        except socket.timeout:
            tried.append(f"{path} — timeout")
        except Exception as e:
            tried.append(f"{path} — {e}")
        finally:
            try:
                sock.close()
            except Exception:
                pass

    if not tried:
        return (
            f"error: no sadeshell socket candidates found\n"
            f"  DISPLAY={display}\n"
            f"  XDG_RUNTIME_DIR={os.environ.get('XDG_RUNTIME_DIR', '(not set)')}"
        )

    paths = "\n  ".join(tried)
    return (
        f"error: no sadeshell instance responding\n"
        f"  DISPLAY={display}\n"
        f"  XDG_RUNTIME_DIR={os.environ.get('XDG_RUNTIME_DIR', '(not set)')}\n"
        f"searched:\n  {paths}"
    )
