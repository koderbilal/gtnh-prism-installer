"""Install a GTNH release as a new Prism Launcher instance."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from .archive import extract_zip, zip_instance_prefix
from .cfg import read_cfg, update_cfg
from .javas import probe_java
from .prism import PrismPaths, unique_dir
from .util import InstallerError, Reporter, cache_dir, download_file, human_size
from .versions import GtnhVersion

# Cached by Prism after it inspects a Java; stale values would hide a changed runtime.
STALE_JAVA_KEYS = ("JavaVersion", "JavaArchitecture", "JavaRealArchitecture", "JavaVendor")


@dataclass
class JavaChoice:
    path: Optional[Path] = None  # None keeps the pack's/Prism's automatic Java selection
    ignore_compat: bool = False


def default_instance_name(version: GtnhVersion, variant: str) -> str:
    suffix = " (Java 8)" if variant == "java8" else ""
    return f"GT New Horizons {version.id}{suffix}"


def compatible_majors(instance_dir: Path) -> Optional[list[int]]:
    """Java majors the pack declares in its Minecraft component patch, if present."""
    for rel in ("patches/net.minecraft.json",):
        p = instance_dir / rel
        if p.is_file():
            try:
                return [int(x) for x in json.loads(p.read_text(encoding="utf-8")).get("compatibleJavaMajors", [])] or None
            except (ValueError, OSError):
                return None
    return None


def apply_instance_settings(instance_dir: Path, name: str, java: Optional[JavaChoice]) -> None:
    values = {"name": name}
    remove: list[str] = []
    if java and java.path:
        values["OverrideJavaLocation"] = "true"
        values["JavaPath"] = Path(java.path).as_posix()
        values["IgnoreJavaCompatibility"] = "true" if java.ignore_compat else "false"
        remove = list(STALE_JAVA_KEYS)
    update_cfg(instance_dir / "instance.cfg", values, remove)


def _check_space(path: Path, needed: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < needed:
        raise InstallerError(
            f"Yetersiz disk alanı / Not enough disk space: {human_size(needed)} gerekli/needed, "
            f"{human_size(free)} boş/free ({path})"
        )


def install_instance(
    prism: PrismPaths,
    version: GtnhVersion,
    variant: str,
    name: str,
    java: Optional[JavaChoice],
    reporter: Reporter,
    keep_zip: bool = False,
) -> Path:
    url = version.url_for(variant)
    if not url:
        raise InstallerError(f"{version.id} için {variant} paketi yok / no {variant} pack for {version.id}")

    zip_path = cache_dir() / unquote(Path(urlparse(url).path).name)
    reporter.log(f"Paket indiriliyor / downloading pack: {url}")
    download_file(url, zip_path, reporter, label=f"GTNH {version.id}")

    try:
        with zipfile.ZipFile(zip_path) as zf:
            prefix = zip_instance_prefix(zf)
            unpacked = sum(i.file_size for i in zf.infolist())
    except zipfile.BadZipFile:
        zip_path.unlink(missing_ok=True)
        raise InstallerError("İndirilen zip bozuk, tekrar deneyin / downloaded zip is corrupt, retry")

    temp_root = prism.instances_dir / ".LAUNCHER_TEMP"  # Prism ignores this folder
    _check_space(prism.instances_dir, unpacked + (200 << 20))
    temp_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="gtnh-", dir=temp_root))
    try:
        reporter.log("Örnek çıkarılıyor / extracting instance...")
        extract_zip(zip_path, staging, reporter, prefix=prefix, label="Çıkarılıyor / extracting")
        apply_instance_settings(staging, name, java)

        majors = compatible_majors(staging)
        if java and java.path and majors and not java.ignore_compat:
            major, _ = probe_java(java.path)
            if major is not None and major not in majors:
                reporter.log(
                    f"UYARI / WARNING: Java {major} bu paketle uyumlu değil / not in compatible list {majors}"
                )

        final = unique_dir(prism.instances_dir, name)
        staging.rename(final)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        try:
            temp_root.rmdir()
        except OSError:
            pass
    if not keep_zip:
        zip_path.unlink(missing_ok=True)
    reporter.log(f"Kuruldu / installed: {final}")
    return final


def read_instance_java(instance_dir: Path) -> Optional[str]:
    return read_cfg(instance_dir / "instance.cfg").get("JavaPath")


def detect_variant(instance_dir: Path) -> str:
    """'modern' (LWJGL3/Java 17+) or 'java8' for an existing instance."""
    pack = instance_dir / "mmc-pack.json"
    try:
        uids = {c.get("uid") for c in json.loads(pack.read_text(encoding="utf-8")).get("components", [])}
    except (OSError, ValueError):
        uids = set()
    if "org.lwjgl3" in uids or (instance_dir / "patches" / "org.lwjgl3.json").exists():
        return "modern"
    return "java8" if uids else "modern"
