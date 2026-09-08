"""Command-line entry point. IPC commands do not import or initialize Qt."""

import sys

COMMANDS = (
    "open-launcher", "open-keybinds", "open-emoji-picker", "open-window-picker",
    "open-minimized-picker", "confirm-exit",
)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    for command in COMMANDS:
        if "--" + command in args:
            from sadeshell.services.shared.ipc_client import send_ipc_command
            result = send_ipc_command(command)
            if result != "ok":
                print(result, file=sys.stderr)
                return 1
            return 0
    from sadeshell.runtime import main as run
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
