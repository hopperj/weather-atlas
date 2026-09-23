"""Restricted HTTPS directory listing retrieval for operator inventory commands."""

from __future__ import annotations

import html
import os
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from weather_ingest.models import RemoteObject

_ENTRY_RE = re.compile(
    r'<a\s+href="(?P<href>[^"]+)">.*?</a>\s+'
    r'(?P<modified>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+'
    r'(?P<size>-|\d+(?:\.\d+)?[KMGTP]?)',
    re.IGNORECASE,
)
_SIZE_MULTIPLIERS = {
    "": 1,
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
    "P": 1024**5,
}


class ListingSource(Protocol):
    def get_text(self, url: str) -> str: ...


def parse_apache_size(value: str) -> int | None:
    if value == "-":
        return None
    suffix = value[-1].upper() if value[-1].isalpha() else ""
    number = value[:-1] if suffix else value
    try:
        return int(float(number) * _SIZE_MULTIPLIERS[suffix])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid Apache directory size: {value!r}") from exc


def parse_directory_listing(directory_url: str, document: str) -> list[RemoteObject]:
    base = urlsplit(directory_url)
    if base.scheme != "https" or not base.hostname:
        raise ValueError("directory URL must be absolute HTTPS")

    objects: list[RemoteObject] = []
    for match in _ENTRY_RE.finditer(document):
        href = unquote(html.unescape(match.group("href")))
        href_parts = urlsplit(href)
        if href_parts.scheme or href_parts.netloc or href_parts.query or href_parts.fragment:
            continue
        path = PurePosixPath(href_parts.path)
        if len(path.parts) != 1 or path.name in {"", ".", ".."}:
            continue
        if path.suffix.lower() not in {".grib2", ".json", ".nc"}:
            continue
        object_url = urljoin(directory_url.rstrip("/") + "/", path.name)
        resolved = urlsplit(object_url)
        if resolved.scheme != "https" or resolved.hostname != base.hostname:
            continue
        modified = datetime.strptime(match.group("modified"), "%Y-%m-%d %H:%M").replace(
            tzinfo=UTC
        )
        objects.append(
            RemoteObject(
                url=object_url,
                filename=path.name,
                size_bytes=parse_apache_size(match.group("size")),
                size_is_exact=match.group("size").isdigit(),
                last_modified=modified,
            )
        )
    return sorted(objects, key=lambda obj: obj.filename)


class HttpsListingSource:
    """Fetch listings from a small explicit allowlist; not a scheduling mechanism."""

    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str] = frozenset({"dd.weather.gc.ca"}),
        timeout_seconds: float = 30.0,
        user_agent: str = "weather-platform-inventory/0.1 (+operator initiated)",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._allowed_hosts = allowed_hosts
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 10.0)),
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "text/html"},
            transport=transport,
        )

    def get_text(self, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in self._allowed_hosts:
            raise ValueError(f"listing host is not allowed: {parts.hostname!r}")
        response = self._client.get(url)
        response.raise_for_status()
        final = urlsplit(str(response.url))
        if final.scheme != "https" or final.hostname not in self._allowed_hosts:
            raise ValueError("listing request redirected outside the allowed HTTPS hosts")
        return response.text

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpsListingSource:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class FixtureListingSource:
    """Read saved directory listings named ``000.html`` etc. for offline inspection."""

    def __init__(self, fixture_directory: PathLike) -> None:
        from pathlib import Path

        self._directory = Path(fixture_directory).expanduser().resolve()

    def get_text(self, url: str) -> str:
        from pathlib import Path

        forecast_hour = PurePosixPath(urlsplit(url).path).parts[-1]
        if not re.fullmatch(r"\d{2,3}", forecast_hour):
            raise ValueError(f"cannot resolve time directory from URL: {url}")
        fixture = (self._directory / f"{forecast_hour}.html").resolve()
        if not fixture.is_relative_to(self._directory):
            raise ValueError("fixture path escapes fixture directory")
        return Path(fixture).read_text(encoding="utf-8")


PathLike = str | os.PathLike[str]
