"""Shared helpers: progress reporting, HTTP downloads, platform detection."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from . import __version__

USER_AGENT = f"gtnh-prism-installer/{__version__}"


_certifi_ctx: Optional[ssl.SSLContext] = None


def urlopen(req, timeout: float = 30):
    """urlopen that retries with the bundled certifi CA list when the OS store lacks a root
    (common on Windows: CERTIFICATE_VERIFY_FAILED / unable to get local issuer certificate)."""
    global _certifi_ctx
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        if not isinstance(e.reason, ssl.SSLCertVerificationError):
            raise
        try:
            import certifi
        except ImportError:
            raise e
        if _certifi_ctx is None:
            _certifi_ctx = ssl.create_default_context(cafile=certifi.where())
        return urllib.request.urlopen(req, timeout=timeout, context=_certifi_ctx)


class Cancelled(Exception):
    """Raised when the user cancels a running operation."""


class InstallerError(Exception):
    """A user-presentable failure."""


class Reporter:
    """Thread-safe progress/log sink. GUI and CLI each provide callbacks."""

    def __init__(
        self,
        log: Optional[Callable[[str], None]] = None,
        progress: Optional[Callable[[str, Optional[float]], None]] = None,
    ):
        self._log = log or (lambda m: None)
        self._progress = progress or (lambda label, frac: None)
        self.cancel_event = threading.Event()

    def log(self, msg: str) -> None:
        self._log(msg)

    def progress(self, label: str, fraction: Optional[float] = None) -> None:
        self._progress(label, fraction)

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()


def platform_info() -> tuple[str, str]:
    """Return (os, arch) using Adoptium-style names: windows/linux/mac, x64/aarch64."""
    if sys.platform.startswith("win"):
        os_name = "windows"
    elif sys.platform == "darwin":
        os_name = "mac"
    else:
        os_name = "linux"
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        arch = "aarch64"
    elif machine in ("amd64", "x86_64", "x64"):
        arch = "x64"
    elif machine in ("i386", "i686", "x86"):
        arch = "x86"
    else:
        arch = machine
    return os_name, arch


def _request(url: str, headers: Optional[dict] = None) -> urllib.request.Request:
    h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        h.update(headers)
    return urllib.request.Request(url, headers=h)


def fetch_bytes(url: str, timeout: float = 30, retries: int = 3) -> bytes:
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            with urlopen(_request(url), timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 401, 403, 404):
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise InstallerError(f"İstek başarısız / Request failed: {url} ({last})")


def fetch_json(url: str, timeout: float = 30):
    return json.loads(fetch_bytes(url, timeout).decode("utf-8"))


def hash_file(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(
    url: str,
    dest: Path,
    reporter: Reporter,
    label: str = "",
    checksum: Optional[str] = None,
    algo: str = "sha256",
    retries: int = 4,
) -> Path:
    """Download with resume support (.part file), progress and optional checksum."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and checksum and hash_file(dest, algo) == checksum.lower():
        return dest
    part = dest.with_name(dest.name + ".part")
    last: Optional[Exception] = None
    for attempt in range(retries):
        reporter.check_cancel()
        try:
            have = part.stat().st_size if part.exists() else 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            with urlopen(_request(url, headers), timeout=30) as resp:
                status = getattr(resp, "status", 200)
                length = int(resp.headers.get("Content-Length") or 0)
                if status == 206:
                    total = have + length
                    mode = "ab"
                else:
                    have, total, mode = 0, length, "wb"
                done = have
                with open(part, mode) as out:
                    while True:
                        reporter.check_cancel()
                        chunk = resp.read(1 << 18)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        reporter.progress(label, done / total if total else None)
            break
        except urllib.error.HTTPError as e:
            if e.code == 416 and part.exists():  # range past EOF: file already complete
                break
            last = e
            if e.code in (403, 404):
                raise InstallerError(f"Dosya bulunamadı / Not found: {url} (HTTP {e.code})")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(2 * (attempt + 1))
    else:
        raise InstallerError(f"İndirme başarısız / Download failed: {url} ({last})")

    if checksum and hash_file(part, algo) != checksum.lower():
        part.unlink(missing_ok=True)
        raise InstallerError(f"Sağlama toplamı uyuşmuyor / Checksum mismatch: {url}")
    part.replace(dest)
    return dest


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def cache_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    d = base / "gtnh-prism-installer"
    d.mkdir(parents=True, exist_ok=True)
    return d
