"""Command-line interface (also handy for scripting and CI smoke tests)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import __version__, javas
from .i18n import set_language
from .install import JavaChoice, default_instance_name, detect_variant, install_instance
from .prism import PrismPaths, detect_prism, list_instances, load_paths, minecraft_dir
from .update import OPTIONAL_ITEMS, MigrationOptions, detect_user_mods, update_instance
from .util import Cancelled, InstallerError, Reporter, platform_info
from .versions import GtnhVersion, fetch_versions, upgrade_skips_major


def _reporter() -> Reporter:
    last = {"label": None, "pct": -1}

    def progress(label: str, frac: Optional[float]) -> None:
        if frac is None:
            return
        pct = int(frac * 100)
        if label != last["label"] or pct // 5 != last["pct"] // 5:
            last.update(label=label, pct=pct)
            print(f"\r{label}: {pct}%   ", end="" if pct < 100 else "\n", flush=True)

    return Reporter(log=lambda m: print(m, flush=True), progress=progress)


def _prism(args) -> PrismPaths:
    if args.prism_dir:
        return load_paths(Path(args.prism_dir).expanduser())
    found = detect_prism()
    if not found:
        raise InstallerError("Prism Launcher bulunamadı; --prism-dir verin / Prism not found, pass --prism-dir")
    return found[0]


def _version(versions: list[GtnhVersion], vid: str) -> GtnhVersion:
    for v in versions:
        if v.id.lower() == vid.lower():
            return v
    if vid.lower() == "latest":
        return next(v for v in versions if v.is_stable)
    raise InstallerError(f"Sürüm bulunamadı / unknown version: {vid} (see `list --all`)")


def _java_choice(args, prism: PrismPaths, reporter: Reporter) -> Optional[JavaChoice]:
    if args.java_path:
        return JavaChoice(Path(args.java_path), args.ignore_java_compat)
    if args.java:
        vendor, _, rest = args.java.partition(":")
        major_s, _, wanted = rest.partition(":")
        if vendor not in javas.VENDORS or not major_s.isdigit():
            raise InstallerError("--java biçimi / format: vendor:major[:version], e.g. adoptium:25")
        builds = javas.list_builds(vendor, int(major_s))
        if wanted:
            builds = [b for b in builds if b.version == wanted]
        if not builds:
            raise InstallerError(f"Bu platformda {args.java} için Java bulunamadı / no such Java build")
        exe = javas.install_java(builds[0], prism.java_dir, reporter)
        return JavaChoice(exe, args.ignore_java_compat)
    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gtnh-prism-installer", description="Install/update GTNH in Prism Launcher")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--lang", choices=["tr", "en"])
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="open the graphical interface (default)")

    def common(sp):
        sp.add_argument("--prism-dir", help="Prism data folder (auto-detected by default)")

    sp = sub.add_parser("list", help="list GTNH versions")
    sp.add_argument("--all", action="store_true", help="include beta/special versions")

    sp = sub.add_parser("instances", help="list Prism instances")
    common(sp)

    sp = sub.add_parser("java-list", help="list downloadable Java builds")
    sp.add_argument("vendor", choices=list(javas.VENDORS))
    sp.add_argument("major", type=int, nargs="?")

    def java_args(sp):
        sp.add_argument("--java", metavar="VENDOR:MAJOR[:VERSION]", help="download+use a Java, e.g. adoptium:25")
        sp.add_argument("--java-path", help="use an existing Java executable")
        sp.add_argument("--ignore-java-compat", action="store_true", help="skip Prism's Java compatibility checks")

    sp = sub.add_parser("install", help="install a version as a new instance")
    common(sp)
    java_args(sp)
    sp.add_argument("version", help="e.g. 2.9.2 or 'latest'")
    sp.add_argument("--java8-pack", action="store_true", help="use the Java 8 pack instead of the Java 17+ one")
    sp.add_argument("--name")
    sp.add_argument("--keep-zip", action="store_true")

    sp = sub.add_parser("update", help="install a newer version and migrate data from an old instance")
    common(sp)
    java_args(sp)
    sp.add_argument("version", help="target version, e.g. 2.9.2 or 'latest'")
    sp.add_argument("--from", dest="old", required=True, help="old instance folder name")
    sp.add_argument("--java8-pack", action="store_true")
    sp.add_argument("--name")
    sp.add_argument("--keep-zip", action="store_true")
    sp.add_argument(
        "--optional",
        default="",
        help="comma separated: " + ",".join(i.id for i in OPTIONAL_ITEMS) + " (or 'all')",
    )
    sp.add_argument("--extra-mods", action="store_true", help="also copy mods you added yourself")
    sp.add_argument("--no-memory", action="store_true", help="don't carry over RAM settings")
    sp.add_argument("--jvm-args", action="store_true", help="carry over custom JVM arguments")
    sp.add_argument("--force", action="store_true", help="allow skipping a major version")
    return p


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lang:
        set_language(args.lang)
    if args.cmd in (None, "gui"):
        from .gui import main as gui_main

        gui_main()
        return 0
    try:
        return _dispatch(args)
    except Cancelled:
        print("İptal edildi / cancelled")
        return 130
    except InstallerError as e:
        print(f"Hata / Error: {e}", file=sys.stderr)
        return 1


def _dispatch(args) -> int:
    if args.cmd == "list":
        for v in fetch_versions():
            if v.is_stable or args.all:
                print(f"{v.id:<14} {v.release_date}  {v.channel:<6} Java<= {v.max_java}")
        return 0
    if args.cmd == "instances":
        prism = _prism(args)
        for i in list_instances(prism.instances_dir):
            print(f"{'*' if i.is_gtnh else ' '} {i.path.name:<40} {i.version or '?'}")
        return 0
    if args.cmd == "java-list":
        majors = [args.major] if args.major else javas.list_majors(args.vendor)
        for m in majors:
            for b in javas.list_builds(args.vendor, m):
                print(f"{javas.VENDORS[b.vendor]:<12} Java {m:<3} {b.version:<16} {b.released:<11} {b.name}")
        return 0

    prism = _prism(args)
    reporter = _reporter()
    versions = fetch_versions()
    target = _version(versions, args.version)
    variant = "java8" if args.java8_pack else "modern"
    name = args.name or default_instance_name(target, variant)

    if args.cmd == "install":
        java = _java_choice(args, prism, reporter)
        path = install_instance(prism, target, variant, name, java, reporter, args.keep_zip)
        print(path)
        return 0

    old_path = prism.instances_dir / args.old
    if not (old_path / "instance.cfg").is_file():
        raise InstallerError(f"Örnek bulunamadı / instance not found: {old_path}")
    old = next(i for i in list_instances(prism.instances_dir) if i.path == old_path)
    if upgrade_skips_major(old.version, target.id) and not args.force:
        raise InstallerError(
            f"{old.version} → {target.id}: GTNH tek seferde bir ana sürüm güncellemeyi öneriyor; "
            "yine de istiyorsanız --force / GTNH advises one major version at a time; use --force to override"
        )
    ids = {i.id for i in OPTIONAL_ITEMS}
    chosen = ids if args.optional == "all" else {x for x in args.optional.split(",") if x}
    unknown = chosen - ids
    if unknown:
        raise InstallerError(f"Bilinmeyen seçenek / unknown option: {', '.join(sorted(unknown))}")
    opts = MigrationOptions(optional=chosen, copy_memory=not args.no_memory, copy_jvm_args=args.jvm_args)
    if args.extra_mods:
        mods, known = detect_user_mods(old_path, versions, old.version, target, variant)
        if not known:
            print("Uyarı / Warning: stock mod list unavailable; copying every mod is unsafe, skipping extra mods")
        else:
            opts.extra_mods = mods
    java = _java_choice(args, prism, reporter)
    path = update_instance(prism, old_path, target, variant, name, java, opts, reporter, args.keep_zip)
    print(path)
    return 0
