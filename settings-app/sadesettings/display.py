"""Display mode discovery helpers."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field


_MODE_RE = re.compile(r"^\s+(\d+x\d+)\s+(.+)$")
_RATE_RE = re.compile(r"(\d+(?:\.\d+)?)(?:[*+]+)?")


@dataclass
class OutputInfo:
    name: str
    resolutions: dict[str, list[float]] = field(default_factory=dict)


def parse_xrandr_query(text: str) -> list[OutputInfo]:
    outputs: list[OutputInfo] = []
    current: OutputInfo | None = None
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "connected":
            current = OutputInfo(fields[0])
            outputs.append(current)
            continue
        if len(fields) >= 2 and fields[1] == "disconnected":
            current = None
            continue
        if current is None:
            continue
        match = _MODE_RE.match(line)
        if not match:
            continue
        resolution, rates_blob = match.groups()
        rates = [float(rate) for rate in _RATE_RE.findall(rates_blob)]
        if rates:
            current.resolutions[resolution] = rates
    return outputs


def query_outputs() -> list[OutputInfo]:
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return []
    return parse_xrandr_query(result.stdout)
