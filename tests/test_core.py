import json
from pathlib import Path

from gtnh_installer import javas
from gtnh_installer.cfg import read_cfg, update_cfg
from gtnh_installer.i18n import STRINGS
from gtnh_installer.versions import parse_manifest, upgrade_skips_major

FIXTURES = Path(__file__).parent / "fixtures"


def test_cfg_roundtrip_keeps_other_sections(tmp_path):
    p = tmp_path / "instance.cfg"
    p.write_text("[General]\nname=Old\nJavaVersion=17\nkeep=1\n\n[Other]\nx=2\n")
    update_cfg(p, {"name": "New, Name", "JavaPath": "C:/Java/bin/javaw.exe"}, remove=["JavaVersion"])
    cfg = read_cfg(p)
    assert cfg["name"] == "New, Name" and cfg["JavaPath"] == "C:/Java/bin/javaw.exe"
    assert "JavaVersion" not in cfg and cfg["keep"] == "1" and cfg["x"] == "2"
    assert "[Other]" in p.read_text()


def test_manifest_parsing_and_java_recommendations():
    versions = {v.id: v for v in parse_manifest(json.loads((FIXTURES / "versions.json").read_text()))}
    v = versions["2.9.2"]
    assert v.is_stable and v.modern_url.endswith("GT_New_Horizons_2.9.2_Java_17-26.zip")
    assert v.recommended_majors("modern") == [26, 25, 21, 17]  # matches the pack's declared majors
    assert v.recommended_majors("java8") == [8]
    assert versions["2.8.4"].recommended_majors("modern") == [25, 21, 17]
    assert not versions["2.9.0-RC-2"].is_stable
    assert versions["2.9.2"].changelog_url.startswith("https://github.com/GTNewHorizons/")


def test_upgrade_skip_detection():
    assert upgrade_skips_major("2.6.1", "2.8.0")
    assert not upgrade_skips_major("2.7.4", "2.8.0")
    assert not upgrade_skips_major("2.8.3", "2.8.4")
    assert not upgrade_skips_major(None, "2.8.0")


def test_java_catalogue_parsers():
    adoptium = [{
        "timestamp": "2026-07-28T10:00:00Z",
        "version_data": {"major": 26, "minor": 0, "security": 2, "build": 10},
        "binaries": [{"image_type": "jre", "package": {"name": "x.tar.gz", "link": "http://x", "checksum": "ab", "size": 1}}],
    }]
    b = javas.parse_adoptium(adoptium, 26)[0]
    assert b.name == "eclipse_temurin_jre26.0.2+10" and b.released == "28.07.2026"

    azul = [{"java_version": [21, 0, 5], "distro_version": [21, 38, 21], "download_url": "http://z", "build_date": "2025-01-02T00:00:00Z", "sha256_hash": "cd"}]
    assert javas.parse_azul(azul, 21)[0].name == "azul_zulu_jre21.0.5_21.38.21"

    rel = [{"published_at": "2026-10-28T00:00:00Z", "assets": [
        {"name": "ibm-semeru-open-jre_x64_linux_21.0.13.0.tar.gz", "browser_download_url": "http://s", "size": 5},
        {"name": "ibm-semeru-open-jre_x64_linux_21.0.13.0.tar.gz.sha256.txt", "browser_download_url": "http://s.sha", "size": 1},
        {"name": "ibm-semeru-open-jre_x64_windows_21.0.13.0.zip", "browser_download_url": "http://w", "size": 5},
    ]}]
    s = javas.parse_semeru(rel, 21, "linux", "x64")
    assert [x.version for x in s] == ["21.0.13.0"] and s[0].checksum == "@http://s.sha"
    assert javas.parse_semeru(rel, 21, "windows", "x64")[0].archive == "zip"

    mojang = {"linux": {"java-runtime-epsilon": [{"manifest": {"url": "http://m", "sha1": "x", "size": 1}, "version": {"name": "25.0.1.8.1", "released": "2025-12-10T00:00:00Z"}}],
                        "jre-legacy": [{"manifest": {"url": "http://l", "sha1": "y", "size": 1}, "version": {"name": "8u202", "released": "2024-01-01T00:00:00Z"}}]}}
    mb = javas.parse_mojang(mojang, "linux")
    assert [(b.name, b.major) for b in mb] == [("java-runtime-epsilon", 25), ("jre-legacy", 8)]


def test_mojang_runtime_install(server, tmp_path):
    import hashlib

    from gtnh_installer.util import Reporter

    root, base = server
    blob = b"#!/bin/sh\necho hi\n"
    (root / "java.bin").write_bytes(blob)
    manifest = {"files": {
        "bin": {"type": "directory"},
        "bin/java": {"type": "file", "executable": True, "downloads": {"raw": {"url": f"{base}/java.bin", "sha1": hashlib.sha1(blob).hexdigest(), "size": len(blob)}}},
    }}
    (root / "manifest.json").write_text(json.dumps(manifest))
    build = javas.JavaBuild(vendor="mojang", major=25, version="25.0.1", name="java-runtime-epsilon", url=f"{base}/manifest.json", archive="mojang")
    exe = javas.install_java(build, tmp_path / "java", Reporter())
    assert exe.read_bytes() == blob and exe.stat().st_mode & 0o111
    assert javas.installed_javas(tmp_path / "java")[0][0] == "java-runtime-epsilon"


def test_every_gui_string_exists():
    import re

    src = (Path(__file__).parents[1] / "gtnh_installer" / "gui.py").read_text(encoding="utf-8")
    keys = set(re.findall(r'\bt\("([a-z0-9_]+)"', src)) | set(re.findall(r'f"opt_\{|t\(f"(opt_)', src))
    missing = [k for k in keys if k and k != "opt_" and k not in STRINGS]
    assert not missing
    from gtnh_installer.update import OPTIONAL_ITEMS

    assert all(f"opt_{i.id}" in STRINGS for i in OPTIONAL_ITEMS)
    channel = {"channel_stable", "channel_beta"}
    assert channel <= set(STRINGS)
