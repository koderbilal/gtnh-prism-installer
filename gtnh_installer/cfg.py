"""Minimal reader/writer for the Qt-style INI files Prism Launcher uses."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping, Optional


def _unescape(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value.replace("\\\\", "\\")


def _escape(value: str) -> str:
    value = value.replace("\\", "\\\\")
    if any(c in value for c in ',;"'):
        value = '"' + value.replace('"', '\\"') + '"'
    return value


def read_cfg(path: Path) -> dict[str, str]:
    """Return all key/value pairs (section names are ignored, Prism only uses [General])."""
    result: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("[", ";", "#")) or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = _unescape(value)
    return result


def update_cfg(
    path: Path,
    values: Mapping[str, str],
    remove: Iterable[str] = (),
) -> None:
    """Set/replace keys in the [General] section, drop `remove` keys, keep everything else."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    removals = set(remove)
    pending = dict(values)

    start = next((i for i, l in enumerate(lines) if l.strip().lower() == "[general]"), None)
    if start is None:
        # Section-less files are treated as [General]; otherwise create the section up front.
        if any(l.strip().startswith("[") for l in lines):
            lines = ["[General]", ""] + lines
        else:
            lines = ["[General]"] + lines
        start = 0
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))

    section: list[str] = []
    for line in lines[start + 1 : end]:
        key = line.partition("=")[0].strip() if "=" in line else None
        if key in pending:
            section.append(f"{key}={_escape(pending.pop(key))}")
        elif key in removals:
            continue
        else:
            section.append(line)
    while section and not section[-1].strip():
        section.pop()
    section += [f"{k}={_escape(v)}" for k, v in pending.items()]
    if end < len(lines):
        section.append("")
    path.write_text("\n".join(lines[: start + 1] + section + lines[end:]) + "\n", encoding="utf-8")


_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+(?:-[A-Za-z]+-?\d+)?)")


def find_version_in_text(text: str) -> Optional[str]:
    m = _VERSION_RE.search(text or "")
    return m.group(1) if m else None
