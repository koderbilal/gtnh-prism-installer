"""Read a remote zip's file list with HTTP Range requests (no need to download the whole pack)."""

from __future__ import annotations

import io
import urllib.error
import zipfile
from typing import Optional

from .util import InstallerError, _request, urlopen


class HttpRangeFile(io.RawIOBase):
    """Seekable, read-only file object backed by Range requests."""

    def __init__(self, url: str):
        self.url = url
        self.pos = 0
        req = _request(url, {"Range": "bytes=0-0"})
        with urlopen(req, timeout=30) as resp:
            if resp.status != 206:
                raise InstallerError("Sunucu Range desteklemiyor / server does not support Range requests")
            cr = resp.headers.get("Content-Range", "")  # bytes 0-0/12345
            self.size = int(cr.rpartition("/")[2])

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        else:
            self.pos = self.size + offset
        self.pos = max(0, min(self.pos, self.size))
        return self.pos

    def readinto(self, buf) -> int:
        n = len(buf)
        if n == 0 or self.pos >= self.size:
            return 0
        end = min(self.pos + n, self.size) - 1
        req = _request(self.url, {"Range": f"bytes={self.pos}-{end}"})
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
        buf[: len(data)] = data
        self.pos += len(data)
        return len(data)


def remote_mod_files(url: str) -> Optional[set[str]]:
    """File names of every mod jar in a remote GTNH instance zip; None if it can't be listed."""
    try:
        raw = HttpRangeFile(url)
        with zipfile.ZipFile(io.BufferedReader(raw, buffer_size=1 << 20)) as zf:
            names = set()
            for n in zf.namelist():
                low = n.lower().replace("\\", "/")
                if "/mods/" in "/" + low and low.endswith((".jar", ".zip", ".litemod")):
                    names.add(n.replace("\\", "/").rsplit("/", 1)[-1])
            return names or None
    except (OSError, ValueError, zipfile.BadZipFile, InstallerError, urllib.error.URLError):
        return None
