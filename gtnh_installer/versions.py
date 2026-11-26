"""Fetch the official GTNH release manifest (the one gtnewhorizons.com/version-history uses)."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from .util import InstallerError, fetch_json

MANIFEST_URLS = (
    "https://www.gtnewhorizons.com/versions.json",
    "https://raw.githubusercontent.com/GTNewHorizons/GTNewHorizons.github.io/master/public/versions.json",
    "https://cdn.jsdelivr.net/gh/GTNewHorizons/GTNewHorizons.github.io@master/public/versions.json",
    "https://api.github.com/repos/GTNewHorizons/GTNewHorizons.github.io/contents/public/versions.json",
)

LTS_MAJORS = (8, 11, 17, 21, 25)


@dataclass
class GtnhVersion:
    id: str
    title: str
    release_date: str  # YYYY/MM/DD
    max_java: int
    java8_url: Optional[str]
    modern_url: Optional[str]
    changelog_url: Optional[str]

    @property
    def is_stable(self) -> bool:
        return bool(re.fullmatch(r"\d+\.\d+\.\d+", self.id))

    @property
    def channel(self) -> str:
        return "stable" if self.is_stable else "beta"

    def url_for(self, variant: str) -> Optional[str]:
        return self.java8_url if variant == "java8" else self.modern_url

    def recommended_majors(self, variant: str) -> list[int]:
        """Java majors this pack is known to run on (LTS releases plus the newest supported)."""
        if variant == "java8":
            return [8]
        majors = [m for m in LTS_MAJORS if 17 <= m <= self.max_java]
        if self.max_java not in majors:
            majors.append(self.max_java)
        return sorted(majors, reverse=True)

    def all_majors(self, variant: str) -> list[int]:
        if variant == "java8":
            return [8]
        return list(range(self.max_java, 16, -1))


def _changelog(description: str) -> Optional[str]:
    m = re.search(r'href="([^"]+)"', description or "")
    return m.group(1) if m else None


def parse_manifest(data: dict) -> list[GtnhVersion]:
    versions: list[GtnhVersion] = []
    for vid, v in data.items():
        mmc = v.get("mmc") or {}
        if not mmc:
            continue
        versions.append(
            GtnhVersion(
                id=vid,
                title=v.get("title", ""),
                release_date=v.get("releaseDate", ""),
                max_java=int(v.get("maxJavaVersion") or 21),
                java8_url=mmc.get("java8Url"),
                modern_url=mmc.get("java17_2XUrl"),
                changelog_url=_changelog(v.get("description", "")),
            )
        )
    versions.sort(key=lambda x: x.release_date, reverse=True)
    return versions


def _load_manifest(url: str):
    data = fetch_json(url)
    if isinstance(data, dict) and data.get("encoding") == "base64" and "content" in data:
        data = json.loads(base64.b64decode(data["content"]).decode("utf-8"))  # GitHub contents API
    return data


def fetch_versions() -> list[GtnhVersion]:
    errors: list[str] = []
    override = os.environ.get("GTNH_MANIFEST_URL")  # for testing/mirrors
    for url in ((override,) if override else MANIFEST_URLS):
        try:
            return parse_manifest(_load_manifest(url))
        except Exception as e:  # try the next mirror
            errors.append(f"- {url}\n  {type(e).__name__}: {e}")
    raise InstallerError("Sürüm listesi alınamadı / Could not fetch version list:\n" + "\n".join(errors))


def major_minor(version_id: str) -> Optional[tuple[int, int]]:
    m = re.match(r"(\d+)\.(\d+)", version_id or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def upgrade_skips_major(old_id: Optional[str], new_id: str) -> bool:
    """GTNH advises updating one minor series (2.6 -> 2.7 -> 2.8) at a time."""
    a, b = major_minor(old_id or ""), major_minor(new_id)
    if not a or not b or a[0] != b[0]:
        return bool(a and b and a[0] != b[0])
    return b[1] - a[1] > 1
