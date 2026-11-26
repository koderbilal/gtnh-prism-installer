"""Test helpers: a Range-capable local HTTP server and a synthetic GTNH pack."""

from __future__ import annotations

import http.server
import io
import re
import threading
import zipfile
from functools import partial
from pathlib import Path

import pytest


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        path = Path(self.translate_path(self.path))
        rng = self.headers.get("Range")
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        if rng:
            m = re.match(r"bytes=(\d+)-(\d*)", rng)
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else len(data) - 1
            if start >= len(data):
                self.send_error(416)
                return
            end = min(end, len(data) - 1)
            chunk = data[start : end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        else:
            chunk = data
            self.send_response(200)
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


@pytest.fixture()
def server(tmp_path):
    root = tmp_path / "www"
    root.mkdir()
    handler = partial(RangeHandler, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield root, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def make_pack(path: Path, version: str, mods: list[str], modern: bool = True) -> None:
    """Zip shaped like the official MultiMC/Prism release (instance root folder + .minecraft)."""
    root = f"GT New Horizons {version}"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/instance.cfg", f"[General]\nInstanceType=OneSix\nname=GT New Horizons {version}\nOverrideMemory=true\nMaxMemAlloc=6144\n")
        components = [{"uid": "net.minecraft", "version": "1.7.10"}]
        if modern:
            components.insert(0, {"uid": "org.lwjgl3"})
            zf.writestr(f"{root}/patches/net.minecraft.json", '{"compatibleJavaMajors":[17,21,25]}')
        zf.writestr(f"{root}/mmc-pack.json", __import__("json").dumps({"components": components, "formatVersion": 1}))
        info = zipfile.ZipInfo(f"{root}/.minecraft/run.sh")
        info.external_attr = 0o755 << 16
        zf.writestr(info, "#!/bin/sh\n")
        zf.writestr(f"{root}/.minecraft/config/GregTech/Pollution.cfg", f"default-{version}")
        zf.writestr(f"{root}/.minecraft/config/tectech.cfg", f"default-{version}")
        for m in mods:
            zf.writestr(f"{root}/.minecraft/mods/{m}", "jar")
