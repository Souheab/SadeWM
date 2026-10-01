"""Restore the session environment when launching an external application."""

import os


def launch_environment() -> dict[str, str]:
    env = os.environ.copy()
    # The Nix wrapper saves variables before adding its private dependencies.
    # Unwrapped installations inherit the environment normally. A missing saved
    # value means the variable was unset; an empty value stays explicitly empty.
    for name in env.pop("SADESHELL_SESSION_VARS", "").split():
        value = env.pop("SADESHELL_SESSION_" + name, None)
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env
