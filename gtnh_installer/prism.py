"""Locate Prism Launcher data and enumerate its instances."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .cfg import find_version_in_text, read_cfg


@dataclass
class PrismPaths:
    data_dir: Path
    instances_dir: Path
    java_dir: Path
    label: str = ""

    def __str__(self) -> str:
        return f"{self.label or self.data_dir}"


@dataclass
class InstanceInfo:
    path: Path
    name: str
    version: Optional[str]
    is_gtnh: bool


def candidate_data_dirs() -> list[tuple[str, Path]]:
    home = Path.home()
    found: list[tuple[str, Path]] = []
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            found.append(("Prism Launcher", Path(appdata) / "PrismLauncher"))
        found.append(("Prism Launcher (Scoop)", home / "scoop" / "apps" / "prismlauncher" / "current"))
    elif sys.platform == "darwin":
        found.append(("Prism Launcher", home / "Library" / "Application Support" / "PrismLauncher"))
    else:
        xdg = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
        found.append(("Prism Launcher", xdg / "PrismLauncher"))
        found.append(
            (
                "Prism Launcher (Flatpak)",
                home / ".var" / "app" / "org.prismlauncher.PrismLauncher" / "data" / "PrismLauncher",
            )
        )
    return found


def _resolve(base: Path, value: Optional[str], default: str) -> Path:
    p = Path(value or default)
    return p if p.is_absolute() else base / p


def load_paths(data_dir: Path, label: str = "") -> PrismPaths:
    """Read prismlauncher.cfg (if any) to find the instance/java folders."""
    data_dir = Path(data_dir)
    cfg = read_cfg(data_dir / "prismlauncher.cfg")
    return PrismPaths(
        data_dir=data_dir,
        instances_dir=_resolve(data_dir, cfg.get("InstanceDir"), "instances"),
        java_dir=_resolve(data_dir, cfg.get("JavaDir"), "java"),
        label=label or str(data_dir),
    )


def detect_prism() -> list[PrismPaths]:
    """Return every Prism data directory that exists on this machine."""
    return [load_paths(p, label) for label, p in candidate_data_dirs() if p.is_dir()]


def minecraft_dir(instance: Path) -> Path:
    """Prism uses `.minecraft` unless only a legacy `minecraft` folder exists."""
    dot = instance / ".minecraft"
    plain = instance / "minecraft"
    if not dot.exists() and plain.exists():
        return plain
    return dot


def read_instance(path: Path) -> Optional[InstanceInfo]:
    cfg_path = path / "instance.cfg"
    if not cfg_path.is_file():
        return None
    cfg = read_cfg(cfg_path)
    name = cfg.get("name") or path.name
    version = find_version_in_text(name) or find_version_in_text(path.name)
    mc = minecraft_dir(path)
    low = f"{name} {path.name}".lower()
    is_gtnh = (
        "gt new horizons" in low
        or "gt_new_horizons" in low
        or "gtnh" in low
        or (mc / "config" / "GregTech").is_dir()
    )
    return InstanceInfo(path=path, name=name, version=version, is_gtnh=is_gtnh)


def list_instances(instances_dir: Path) -> list[InstanceInfo]:
    result: list[InstanceInfo] = []
    if not instances_dir.is_dir():
        return result
    for child in sorted(instances_dir.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith((".", "_")) or not child.is_dir():
            continue
        info = read_instance(child)
        if info:
            result.append(info)
    result.sort(key=lambda i: (not i.is_gtnh, i.name.lower()))
    return result


def unique_dir(parent: Path, name: str) -> Path:
    safe = "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip().rstrip(".") or "GTNH"
    candidate = parent / safe
    n = 2
    while candidate.exists():
        candidate = parent / f"{safe} ({n})"
        n += 1
    return candidate
