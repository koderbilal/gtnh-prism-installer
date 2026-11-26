"""Archive extraction that keeps exec bits/symlinks and strips a common root folder."""

from __future__ import annotations

import os
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

from .util import InstallerError, Reporter


def _common_root(entries: list[tuple[str, bool]]) -> str:
    """Return the single top-level folder shared by every (name, is_dir) entry, else ''."""
    roots = set()
    for n, is_dir in entries:
        parts = PurePosixPath(n.replace("\\", "/")).parts
        if not parts:
            continue
        if len(parts) == 1 and not is_dir:
            return ""  # a file at the archive root: nothing to strip
        roots.add(parts[0])
    return roots.pop() if len(roots) == 1 else ""


def _strip(name: str, prefix: str) -> Optional[str]:
    name = name.replace("\\", "/")
    if prefix:
        if name.rstrip("/") == prefix:
            return None
        if not name.startswith(prefix + "/"):
            return None  # outside the root folder: not part of the payload
        name = name[len(prefix) + 1 :]
    return name or None


def _safe_target(dest: Path, rel: str) -> Path:
    target = (dest / rel).resolve()
    if dest.resolve() not in target.parents and target != dest.resolve():
        raise InstallerError(f"Güvensiz arşiv yolu / Unsafe archive path: {rel}")
    return target


def zip_instance_prefix(zf: zipfile.ZipFile) -> str:
    """Folder inside a MultiMC/Prism zip that holds instance.cfg ('' if at the root)."""
    for info in zf.infolist():
        p = PurePosixPath(info.filename.replace("\\", "/"))
        if p.name.lower() == "instance.cfg" and len(p.parts) <= 2:
            return str(p.parent) if len(p.parts) == 2 else ""
    raise InstallerError("Bu zip bir MultiMC/Prism örneği değil (instance.cfg yok) / not an instance zip")


def extract_zip(zip_path: Path, dest: Path, reporter: Reporter, prefix: Optional[str] = None, label: str = "") -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if prefix is None:
            prefix = _common_root([(i.filename, i.is_dir()) for i in infos])
        prefix = prefix.strip("/")
        total = sum(i.file_size for i in infos) or 1
        done = 0
        for info in infos:
            reporter.check_cancel()
            rel = _strip(info.filename, prefix)
            if rel is None:
                continue
            target = _safe_target(dest, rel)
            mode = (info.external_attr >> 16) & 0xFFFF
            if info.is_dir() or rel.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if stat.S_ISLNK(mode) and os.name != "nt":
                link_to = zf.read(info).decode()
                if target.is_symlink() or target.exists():
                    target.unlink()
                os.symlink(link_to, target)
            else:
                with zf.open(info) as src, open(target, "wb") as out:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        reporter.progress(label, min(done / total, 1.0))
                if mode & 0o111 and os.name != "nt":
                    target.chmod(target.stat().st_mode | 0o111)


def extract_tar(tar_path: Path, dest: Path, reporter: Reporter, label: str = "") -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:*") as tf:
        members = tf.getmembers()
        prefix = _common_root([(m.name, m.isdir()) for m in members])
        total = len(members) or 1
        for i, m in enumerate(members):
            reporter.check_cancel()
            rel = _strip(m.name, prefix)
            if rel is None:
                continue
            _safe_target(dest, rel)
            m.name = rel
            if hasattr(tarfile, "data_filter"):
                tf.extract(m, dest, filter="data")
            else:
                tf.extract(m, dest)
            reporter.progress(label, (i + 1) / total)
