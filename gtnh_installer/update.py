"""Upgrade: install a newer pack as a new instance, then migrate the user's data (GTNH 'Method 1')."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .cfg import read_cfg, update_cfg
from .install import JavaChoice, install_instance
from .packlist import remote_mod_files
from .prism import PrismPaths, minecraft_dir
from .util import InstallerError, Reporter, human_size
from .versions import GtnhVersion


@dataclass(frozen=True)
class Item:
    id: str
    rel: str  # path relative to the instance's .minecraft folder (posix style)


# Always migrated when present (step 2 of the official guide).
REQUIRED_ITEMS: tuple[Item, ...] = (
    Item("backups", "backups"),
    Item("vendingmachine", "config/vendingmachine/favourites"),
    Item("shaders_properties", "config/shaders.properties"),
    Item("esm", "ESM"),
    Item("journeymap", "journeymap"),
    Item("resourcepacks", "resourcepacks"),
    Item("saves", "saves"),
    Item("schematics", "schematics"),
    Item("screenshots", "screenshots"),
    Item("shaderpacks", "shaderpacks"),
    Item("tcnodetracker", "TCNodeTracker"),
    Item("visualprospecting", "visualprospecting"),
    Item("botaniavars", "BotaniaVars.dat"),
    Item("localconfig", "localconfig.cfg"),
    Item("options", "options.txt"),
    Item("optionsnf", "optionsnf.txt"),
    Item("servers", "servers.dat"),
)

# Opt-in customisations (step 3 of the official guide). Extra mods are handled separately.
OPTIONAL_ITEMS: tuple[Item, ...] = (
    Item("ingameinfo", "config/InGameInfoXML"),
    Item("pollution", "config/GregTech/Pollution.cfg"),
    Item("menu_music", "config/txloader/load/minecraft/sounds.json"),
    Item("space_elevator", "config/gtnhintergalactic.cfg"),
    Item("lwjgl3ify", "config/lwjgl3ify.cfg"),
    Item("tesla_tower", "config/tectech.cfg"),
    Item("tinkers_layout", "config/TinkersConstruct.cfg"),
    Item("serverutilities", "serverutilities"),
)

# Memory (RAM) and custom JVM arguments live in Prism's instance.cfg.
MEMORY_KEYS = ("OverrideMemory", "MaxMemAlloc", "MinMemAlloc", "PermGen")
JVM_ARG_KEYS = ("OverrideJavaArgs", "JvmArgs")


@dataclass
class MigrationOptions:
    optional: set[str] = field(default_factory=set)  # ids from OPTIONAL_ITEMS
    extra_mods: list[str] = field(default_factory=list)  # paths relative to .minecraft/mods
    copy_memory: bool = True
    copy_jvm_args: bool = False


def present_items(old_mc: Path, items: Iterable[Item]) -> list[Item]:
    return [i for i in items if (old_mc / i.rel).exists()]


_VERSION_SPLIT = re.compile(r"[-_+ ]v?\d")


def _mod_base(filename: str) -> str:
    stem = re.sub(r"\.(jar|zip|litemod)(\.disabled)?$", "", filename, flags=re.I)
    m = _VERSION_SPLIT.search(stem)
    return (stem[: m.start()] if m else stem).lower()


def _scan_mods(mc: Path) -> list[str]:
    mods = mc / "mods"
    found: list[str] = []
    if mods.is_dir():
        for dirpath, _, files in os.walk(mods):
            for f in files:
                if f.lower().endswith((".jar", ".zip", ".litemod")):
                    found.append((Path(dirpath) / f).relative_to(mods).as_posix())
    return sorted(found)


def find_user_mods(old_mc: Path, stock_files: Optional[Iterable[str]]) -> list[str]:
    """Mods in the old instance that aren't part of the stock pack (matched by name without version).

    With `stock_files=None` (stock list unavailable) every mod is returned so the user can pick.
    """
    old = _scan_mods(old_mc)
    if stock_files is None:
        return old
    known_names = {Path(f).name.lower() for f in stock_files}
    known_bases = {_mod_base(Path(f).name) for f in stock_files}
    return [r for r in old if Path(r).name.lower() not in known_names and _mod_base(Path(r).name) not in known_bases]


def detect_user_mods(
    old_instance: Path,
    versions: list[GtnhVersion],
    old_version_id: Optional[str],
    target: GtnhVersion,
    variant: str,
) -> tuple[list[str], bool]:
    """Return (user-added mods, whether a stock list was available).

    The stock list is the old pack's mod set (read remotely via Range requests) plus the new pack's.
    """
    stock: set[str] = set()
    known = False
    old = next((v for v in versions if v.id.lower() == (old_version_id or "").lower()), None)
    for ver in (old, target):
        url = ver.url_for(variant) if ver else None
        names = remote_mod_files(url) if url else None
        if names:
            stock |= names
            known = True
    if old is None or not known:
        return find_user_mods(minecraft_dir(old_instance), None), False
    return find_user_mods(minecraft_dir(old_instance), stock), True


def _walk_files(src: Path) -> list[Path]:
    if src.is_file() or src.is_symlink():
        return [src]
    return [Path(d) / n for d, _, names in os.walk(src) for n in names]


def _copy_plan(plan: list[tuple[Path, Path]], reporter: Reporter) -> None:
    """Copy (src, dst) pairs; directories are merged, same-named files are replaced."""
    work: list[tuple[Path, Path, int]] = []
    for src, dst in plan:
        for f in _walk_files(src):
            target = dst / f.relative_to(src) if src.is_dir() else dst
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            work.append((f, target, size))
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)  # keep empty folders
    total = sum(s for _, _, s in work) or 1
    reporter.log(f"{len(work)} dosya / files, {human_size(total)}")
    done = 0
    for f, target, size in work:
        reporter.check_cancel()
        target.parent.mkdir(parents=True, exist_ok=True)
        if f.is_symlink():
            if target.is_symlink() or target.exists():
                target.unlink()
            os.symlink(os.readlink(f), target)
        else:
            shutil.copyfile(f, target)
            try:
                shutil.copystat(f, target)
            except OSError:
                pass
        done += size
        reporter.progress("Veriler aktarılıyor / migrating data", min(done / total, 1.0))


def migrate(old_instance: Path, new_instance: Path, opts: MigrationOptions, reporter: Reporter) -> None:
    old_mc, new_mc = minecraft_dir(old_instance), minecraft_dir(new_instance)
    if not old_mc.is_dir():
        raise InstallerError(f"Eski örnekte .minecraft yok / no .minecraft in {old_instance}")
    new_mc.mkdir(parents=True, exist_ok=True)

    chosen = [i for i in OPTIONAL_ITEMS if i.id in opts.optional]
    items = present_items(old_mc, REQUIRED_ITEMS) + present_items(old_mc, chosen)
    plan = [(old_mc / i.rel, new_mc / i.rel) for i in items]
    for i in items:
        reporter.log(f"  + {i.rel}")
    new_bases = {_mod_base(Path(r).name) for r in _scan_mods(new_mc)}
    for rel in opts.extra_mods:
        src = old_mc / "mods" / rel
        if not src.is_file():
            continue
        if _mod_base(src.name) in new_bases:
            reporter.log(f"  - mods/{rel} (yeni pakette zaten var / already in new pack)")
            continue
        plan.append((src, new_mc / "mods" / rel))
        reporter.log(f"  + mods/{rel}")
    _copy_plan(plan, reporter)

    keys = (MEMORY_KEYS if opts.copy_memory else ()) + (JVM_ARG_KEYS if opts.copy_jvm_args else ())
    if keys:
        old_cfg = read_cfg(old_instance / "instance.cfg")
        values = {k: old_cfg[k] for k in keys if k in old_cfg}
        if values:
            update_cfg(new_instance / "instance.cfg", values)
            reporter.log("  + instance.cfg: " + ", ".join(values))


def update_instance(
    prism: PrismPaths,
    old_instance: Path,
    version: GtnhVersion,
    variant: str,
    name: str,
    java: Optional[JavaChoice],
    opts: MigrationOptions,
    reporter: Reporter,
    keep_zip: bool = False,
) -> Path:
    new_instance = install_instance(prism, version, variant, name, java, reporter, keep_zip)
    reporter.progress("Veriler aktarılıyor / migrating data", 0)
    try:
        migrate(old_instance, new_instance, opts, reporter)
    except Exception:
        reporter.log(
            "Aktarım yarıda kaldı; eski örnek dokunulmadan duruyor / migration interrupted, "
            f"old instance untouched. New instance: {new_instance}"
        )
        raise
    reporter.log(
        "Bitti. Dünyayı ilk açışınızda 'eksik blok/eşya' sorusu çıkarsa Evet deyin; sunucuda /fml confirm yazın. "
        "/ Done. Confirm the missing blocks/items prompt on first world load."
    )
    return new_instance
