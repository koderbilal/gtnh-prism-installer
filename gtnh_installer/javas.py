"""Java runtime catalogue + installer, mirroring Prism Launcher's "Download Java" dialog.

Vendors: Mojang (official launcher runtimes), Adoptium (Temurin), Azul Zulu, IBM Semeru.
Runtimes are installed into Prism's `java/` folder so Prism also lists them.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .archive import extract_tar, extract_zip
from .util import (
    InstallerError,
    Reporter,
    download_file,
    fetch_bytes,
    fetch_json,
    hash_file,
    platform_info,
)

VENDORS = {
    "mojang": "Mojang",
    "adoptium": "Adoptium",
    "azul": "Azul Zulu",
    "semeru": "IBM Semeru",
}
STATIC_MAJORS = [25, 21, 17, 11, 8]


@dataclass
class JavaBuild:
    vendor: str
    major: int
    version: str
    name: str  # folder name under Prism's java/ directory
    released: str = ""
    kind: str = "jre"
    url: str = ""
    checksum: Optional[str] = None
    algo: str = "sha256"
    archive: str = "zip"  # zip | tar.gz | mojang
    size: int = 0


def _date(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else (iso or "")


def _version_key(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v))


# --------------------------------------------------------------------------- Adoptium

def adoptium_majors() -> list[int]:
    try:
        data = fetch_json("https://api.adoptium.net/v3/info/available_releases")
        return sorted((m for m in data["available_releases"] if m >= 8), reverse=True)
    except Exception:
        return list(STATIC_MAJORS)


def adoptium_builds(major: int) -> list[JavaBuild]:
    os_name, arch = platform_info()
    q = urllib.parse.urlencode(
        {
            "image_type": "jre",
            "os": os_name,
            "architecture": arch,
            "jvm_impl": "hotspot",
            "vendor": "eclipse",
            "page_size": 20,
            "sort_order": "DESC",
        }
    )
    try:
        items = fetch_json(f"https://api.adoptium.net/v3/assets/feature_releases/{major}/ga?{q}")
    except InstallerError:
        return []  # 404 = no build of this major for this platform
    return parse_adoptium(items, major)


def parse_adoptium(items: list, major: int) -> list[JavaBuild]:
    builds: list[JavaBuild] = []
    for rel in items:
        vd = rel["version_data"]
        for b in rel.get("binaries", []):
            if b.get("image_type") != "jre":
                continue
            pkg = b["package"]
            version = f"{vd['major']}.{vd['minor']}.{vd['security']}+{vd['build']}"
            archive = "zip" if pkg["name"].endswith(".zip") else "tar.gz"
            builds.append(
                JavaBuild(
                    vendor="adoptium",
                    major=major,
                    version=version,
                    name=f"eclipse_temurin_jre{version}",
                    released=_date(rel.get("timestamp", "")),
                    url=pkg["link"],
                    checksum=pkg.get("checksum"),
                    archive=archive,
                    size=pkg.get("size", 0),
                )
            )
            break
    builds.sort(key=lambda b: _version_key(b.version), reverse=True)
    return builds


# --------------------------------------------------------------------------- Azul Zulu

def azul_builds(major: int) -> list[JavaBuild]:
    os_name, arch = platform_info()
    azul_os = {"mac": "macos"}.get(os_name, os_name)
    azul_arch = {"x64": "amd64", "x86": "i686"}.get(arch, arch)
    q = urllib.parse.urlencode(
        {
            "java_version": major,
            "java_package_type": "jre",
            "javafx_bundled": "false",
            "release_status": "ga",
            "availability_types": "CA",
            "archive_type": "zip",
            "os": azul_os,
            "arch": azul_arch,
            "include_fields": "build_date,size,sha256_hash",
            "page_size": 100,
        }
    )
    try:
        items = fetch_json(f"https://api.azul.com/metadata/v1/zulu/packages/?{q}")
    except InstallerError:
        return []
    return parse_azul(items, major)


def parse_azul(items: list, major: int) -> list[JavaBuild]:
    builds = []
    for p in items:
        jv = ".".join(str(x) for x in p.get("java_version", []))
        dv = ".".join(str(x) for x in p.get("distro_version", []))
        if not p.get("download_url") or not jv:
            continue
        builds.append(
            JavaBuild(
                vendor="azul",
                major=major,
                version=jv,
                name=f"azul_zulu_jre{jv}_{dv}" if dv else f"azul_zulu_jre{jv}",
                released=_date(p.get("build_date", "")),
                url=p["download_url"],
                checksum=p.get("sha256_hash"),
                archive="zip",
                size=p.get("size", 0),
            )
        )
    builds.sort(key=lambda b: (_version_key(b.version), b.name), reverse=True)
    return builds[:20]


# --------------------------------------------------------------------------- IBM Semeru

def semeru_builds(major: int) -> list[JavaBuild]:
    os_name, arch = platform_info()
    try:
        releases = fetch_json(f"https://api.github.com/repos/ibmruntimes/semeru{major}-binaries/releases?per_page=12")
    except InstallerError:
        return []
    return parse_semeru(releases, major, os_name, arch)


def parse_semeru(releases: list, major: int, os_name: str, arch: str) -> list[JavaBuild]:
    ext = "zip" if os_name == "windows" else "tar.gz"
    pattern = re.compile(rf"^ibm-semeru-open-jre_{arch}_{os_name}_(.+)\.{re.escape(ext)}$")
    builds = []
    for rel in releases:
        if rel.get("prerelease") or rel.get("draft"):
            continue
        assets = {a["name"]: a for a in rel.get("assets", [])}
        for name, asset in assets.items():
            m = pattern.match(name)
            if not m:
                continue
            version = m.group(1).replace("_", "+")
            builds.append(
                JavaBuild(
                    vendor="semeru",
                    major=major,
                    version=version,
                    name=f"ibm_semeru_jre{version}",
                    released=_date(rel.get("published_at", "")),
                    url=asset["browser_download_url"],
                    checksum=f"@{assets[name + '.sha256.txt']['browser_download_url']}"
                    if name + ".sha256.txt" in assets
                    else None,
                    archive=ext,
                    size=asset.get("size", 0),
                )
            )
    return builds


# --------------------------------------------------------------------------- Mojang

MOJANG_ALL = "https://launchermeta.mojang.com/v1/products/java-runtime/2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"


def mojang_platform() -> str:
    os_name, arch = platform_info()
    if os_name == "windows":
        return {"x64": "windows-x64", "aarch64": "windows-arm64", "x86": "windows-x86"}.get(arch, "windows-x64")
    if os_name == "mac":
        return "mac-os-arm64" if arch == "aarch64" else "mac-os"
    return "linux-i386" if arch == "x86" else "linux"


def mojang_builds(major: Optional[int] = None) -> list[JavaBuild]:
    try:
        data = fetch_json(MOJANG_ALL)
    except InstallerError:
        return []
    return parse_mojang(data, mojang_platform(), major)


def parse_mojang(data: dict, platform_key: str, major: Optional[int] = None) -> list[JavaBuild]:
    builds = []
    for component, entries in (data.get(platform_key) or {}).items():
        for e in entries:
            name = e.get("version", {}).get("name", "")
            m = re.match(r"(\d+)", name)
            if not m or not e.get("manifest"):
                continue
            mj = int(m.group(1))
            if major is not None and mj != major:
                continue
            builds.append(
                JavaBuild(
                    vendor="mojang",
                    major=mj,
                    version=name,
                    name=component,
                    released=_date(e["version"].get("released", "")),
                    url=e["manifest"]["url"],
                    checksum=e["manifest"].get("sha1"),
                    algo="sha1",
                    archive="mojang",
                    size=e["manifest"].get("size", 0),
                )
            )
    builds.sort(key=lambda b: _version_key(b.version), reverse=True)
    return builds


# --------------------------------------------------------------------------- facade

def list_majors(vendor: str) -> list[int]:
    if vendor == "mojang":
        return sorted({b.major for b in mojang_builds()}, reverse=True)
    if vendor == "adoptium":
        return adoptium_majors()
    if vendor == "azul":
        return adoptium_majors()
    return [25, 21, 17, 11, 8]


def list_builds(vendor: str, major: int) -> list[JavaBuild]:
    fn: dict[str, Callable[[int], list[JavaBuild]]] = {
        "mojang": mojang_builds,
        "adoptium": adoptium_builds,
        "azul": azul_builds,
        "semeru": semeru_builds,
    }
    return fn[vendor](major)


def java_exe_name(windowed: bool = True) -> str:
    if sys.platform.startswith("win"):
        return "javaw.exe" if windowed else "java.exe"
    return "java"


def find_java_exe(root: Path) -> Optional[Path]:
    """Locate bin/java inside an installed runtime (handles macOS Contents/Home layouts)."""
    name = java_exe_name()
    for rel in ("bin", "Contents/Home/bin", "jre/bin", "Contents/Home/jre/bin"):
        p = root / rel / name
        if p.is_file():
            return p
        alt = root / rel / java_exe_name(False)
        if alt.is_file():
            return alt
    return None


def installed_javas(java_dir: Path) -> list[tuple[str, Path]]:
    """Runtimes already present in Prism's java/ directory."""
    result = []
    if java_dir.is_dir():
        for d in sorted(java_dir.iterdir()):
            exe = find_java_exe(d) if d.is_dir() else None
            if exe:
                result.append((d.name, exe))
    return result


def _install_mojang(build: JavaBuild, dest: Path, reporter: Reporter) -> None:
    manifest = fetch_json(build.url)
    files = manifest["files"]
    dest.mkdir(parents=True, exist_ok=True)
    total = sum(f["downloads"]["raw"]["size"] for f in files.values() if f["type"] == "file") or 1
    done = [0]

    for rel, f in files.items():
        if f["type"] == "directory":
            (dest / rel).mkdir(parents=True, exist_ok=True)

    def fetch(item):
        rel, f = item
        reporter.check_cancel()
        raw = f["downloads"]["raw"]
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = fetch_bytes(raw["url"], timeout=60)
        if hashlib.sha1(data).hexdigest() != raw["sha1"]:
            raise InstallerError(f"Sağlama toplamı uyuşmuyor / Checksum mismatch: {rel}")
        target.write_bytes(data)
        if f.get("executable") and os.name != "nt":
            target.chmod(0o755)
        done[0] += len(data)
        reporter.progress(f"Java ({build.name})", min(done[0] / total, 1.0))

    file_items = [(r, f) for r, f in files.items() if f["type"] == "file"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(fetch, file_items))
    for rel, f in files.items():
        if f["type"] == "link" and os.name != "nt":
            link = dest / rel
            link.parent.mkdir(parents=True, exist_ok=True)
            if link.is_symlink() or link.exists():
                link.unlink()
            os.symlink(f["target"], link)


def install_java(build: JavaBuild, java_dir: Path, reporter: Reporter) -> Path:
    """Download + unpack a runtime into <java_dir>/<build.name>. Returns the java executable."""
    java_dir.mkdir(parents=True, exist_ok=True)
    final = java_dir / build.name
    existing = find_java_exe(final) if final.is_dir() else None
    if existing:
        reporter.log(f"Java zaten kurulu / already installed: {final}")
        return existing

    staging = Path(tempfile.mkdtemp(prefix=".gtnh-java-", dir=java_dir))
    try:
        if build.archive == "mojang":
            reporter.log(f"Java indiriliyor / downloading Java: Mojang {build.name} {build.version}")
            _install_mojang(build, staging, reporter)
        else:
            checksum = build.checksum
            if checksum and checksum.startswith("@"):
                text = fetch_bytes(checksum[1:]).decode("utf-8", "replace").split()
                checksum = text[0] if text else None
            ext = "zip" if build.archive == "zip" else "tar.gz"
            archive = staging.parent / f".{build.name}.download.{ext}"
            reporter.log(f"Java indiriliyor / downloading Java: {VENDORS[build.vendor]} {build.version}")
            download_file(build.url, archive, reporter, label=f"Java ({build.version})", checksum=checksum)
            reporter.progress("Java çıkarılıyor / extracting Java", 0)
            if build.archive == "zip":
                extract_zip(archive, staging, reporter, label="Java çıkarılıyor / extracting Java")
            else:
                extract_tar(archive, staging, reporter, label="Java çıkarılıyor / extracting Java")
            archive.unlink(missing_ok=True)
        if not find_java_exe(staging):
            raise InstallerError("Kurulan Java içinde çalıştırılabilir dosya bulunamadı / java executable missing")
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        staging.rename(final)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    exe = find_java_exe(final)
    assert exe is not None
    return exe


def probe_java(exe: Path, timeout: float = 20) -> tuple[Optional[int], str]:
    """Run `java -version`; return (major, first output line)."""
    exe = Path(exe)
    if exe.name.lower() == "javaw.exe":
        exe = exe.with_name("java.exe")
    try:
        proc = subprocess.run([str(exe), "-version"], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)
    out = (proc.stderr or proc.stdout or "").strip()
    m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
    if not m:
        return None, out.splitlines()[0] if out else "?"
    major = int(m.group(1))
    if major == 1 and m.group(2):  # legacy "1.8.0_x"
        major = int(m.group(2))
    return major, out.splitlines()[0]
