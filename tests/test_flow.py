import json

from conftest import make_pack

from gtnh_installer import cli
from gtnh_installer.install import JavaChoice, detect_variant
from gtnh_installer.cfg import read_cfg
from gtnh_installer.packlist import remote_mod_files
from gtnh_installer.prism import list_instances, load_paths
from gtnh_installer.update import MigrationOptions, detect_user_mods, find_user_mods
from gtnh_installer.util import Reporter
from gtnh_installer.versions import parse_manifest


def _manifest(base, ids):
    data = {}
    for vid in ids:
        data[vid] = {
            "title": "Stable release",
            "releaseDate": "2026/01/01",
            "maxJavaVersion": 25,
            "mmc": {"java8Url": f"{base}/Multi_mc_downloads/{vid}_8.zip", "java17_2XUrl": f"{base}/Multi_mc_downloads/{vid}.zip"},
        }
    return data


def _setup(server, tmp_path, monkeypatch):
    root, base = server
    (root / "Multi_mc_downloads").mkdir()
    stock_old = ["gregtech-5.09.1.jar", "NotEnoughItems-2.0.jar", "oldmod-1.0.jar"]
    stock_new = ["gregtech-5.09.2.jar", "NotEnoughItems-2.1.jar"]
    make_pack(root / "Multi_mc_downloads" / "2.8.0.zip", "2.8.0", stock_old)
    make_pack(root / "Multi_mc_downloads" / "2.9.0.zip", "2.9.0", stock_new)
    (root / "versions.json").write_text(json.dumps(_manifest(base, ["2.9.0", "2.8.0"])))
    monkeypatch.setenv("GTNH_MANIFEST_URL", f"{base}/versions.json")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr("gtnh_installer.install.cache_dir", lambda: (tmp_path / "cache").mkdir(exist_ok=True) or tmp_path / "cache")
    prism = tmp_path / "prism"
    (prism / "instances").mkdir(parents=True)
    return base, prism


def test_install_then_update_migrates_user_data(server, tmp_path, monkeypatch):
    base, prism_dir = _setup(server, tmp_path, monkeypatch)
    paths = load_paths(prism_dir)
    fake_java = tmp_path / "jre" / "bin" / "java"
    fake_java.parent.mkdir(parents=True)
    fake_java.write_text("")

    # 1) install the old version with a Java override
    assert cli.run(["install", "2.8.0", "--prism-dir", str(prism_dir), "--java-path", str(fake_java), "--ignore-java-compat"]) == 0
    old = prism_dir / "instances" / "GT New Horizons 2.8.0"
    cfg = read_cfg(old / "instance.cfg")
    assert cfg["name"] == "GT New Horizons 2.8.0"
    assert cfg["OverrideJavaLocation"] == "true" and cfg["JavaPath"] == fake_java.as_posix()
    assert cfg["IgnoreJavaCompatibility"] == "true"
    assert (old / ".minecraft" / "run.sh").stat().st_mode & 0o111
    assert detect_variant(old) == "modern"
    assert not (prism_dir / "instances" / ".LAUNCHER_TEMP").exists()

    # the user plays: worlds, settings, a customised config and an extra mod
    mc = old / ".minecraft"
    (mc / "saves" / "World1").mkdir(parents=True)
    (mc / "saves" / "World1" / "level.dat").write_text("world")
    (mc / "journeymap").mkdir()
    (mc / "journeymap" / "map.png").write_text("map")
    (mc / "options.txt").write_text("fov:90")
    (mc / "config" / "GregTech" / "Pollution.cfg").write_text("pollution=false")
    (mc / "config" / "tectech.cfg").write_text("tesla=false")
    (mc / "mods" / "worldedit-1.2.jar").write_text("we")
    (mc / "mods" / "NotEnoughItems-9.9.jar").write_text("renamed version of stock mod")

    # stock-vs-user mod detection through Range requests
    versions = parse_manifest(json.loads((tmp_path / "www" / "versions.json").read_text()))
    target = next(v for v in versions if v.id == "2.9.0")
    mods, known = detect_user_mods(old, versions, "2.8.0", target, "modern")
    assert known and mods == ["worldedit-1.2.jar"]
    assert remote_mod_files(target.url_for("modern")) == {"gregtech-5.09.2.jar", "NotEnoughItems-2.1.jar"}

    # 2) update with one optional item + extra mod, but not the other config
    rc = cli.run([
        "update", "2.9.0", "--prism-dir", str(prism_dir), "--from", "GT New Horizons 2.8.0",
        "--optional", "pollution", "--extra-mods", "--java-path", str(fake_java),
    ])
    assert rc == 0
    new = prism_dir / "instances" / "GT New Horizons 2.9.0"
    nmc = new / ".minecraft"
    assert (nmc / "saves" / "World1" / "level.dat").read_text() == "world"
    assert (nmc / "journeymap" / "map.png").read_text() == "map"
    assert (nmc / "options.txt").read_text() == "fov:90"
    assert (nmc / "config" / "GregTech" / "Pollution.cfg").read_text() == "pollution=false"  # opted in
    assert (nmc / "config" / "tectech.cfg").read_text() == "default-2.9.0"  # not opted in
    assert (nmc / "mods" / "worldedit-1.2.jar").exists()
    assert not (nmc / "mods" / "NotEnoughItems-9.9.jar").exists()
    assert (nmc / "mods" / "gregtech-5.09.2.jar").exists()
    assert read_cfg(new / "instance.cfg")["MaxMemAlloc"] == "6144"
    # the old instance is untouched
    assert (mc / "saves" / "World1" / "level.dat").exists()
    assert [i.name for i in list_instances(paths.instances_dir)] == ["GT New Horizons 2.8.0", "GT New Horizons 2.9.0"]


def test_skipping_a_major_version_is_refused(server, tmp_path, monkeypatch, capsys):
    base, prism_dir = _setup(server, tmp_path, monkeypatch)
    inst = prism_dir / "instances" / "GT New Horizons 2.6.1"
    inst.mkdir()
    (inst / "instance.cfg").write_text("[General]\nname=GT New Horizons 2.6.1\n")
    assert cli.run(["update", "2.9.0", "--prism-dir", str(prism_dir), "--from", inst.name]) == 1
    assert "--force" in capsys.readouterr().err


def test_find_user_mods_without_stock_list_returns_everything(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    (mods / "a-1.jar").write_text("")
    assert find_user_mods(tmp_path, None) == ["a-1.jar"]


def test_install_with_default_java_reuses_prism_java(server, tmp_path, monkeypatch):
    import sys

    import pytest
    from test_core import _fake_java

    if sys.platform.startswith("win"):
        pytest.skip("fake java is a shell script")
    base, prism_dir = _setup(server, tmp_path, monkeypatch)
    paths = load_paths(prism_dir)
    exe = _fake_java(paths.java_dir, "temurin-25", "25.0.1")
    from gtnh_installer.install import install_instance

    version = parse_manifest(_manifest(base, ["2.9.0"]))[0]
    out = install_instance(paths, version, "modern", "Auto", JavaChoice(auto_major=25), Reporter())
    cfg = read_cfg(out / "instance.cfg")
    assert cfg["OverrideJavaLocation"] == "true" and cfg["JavaPath"] == exe.as_posix()
