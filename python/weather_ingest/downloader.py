"""Bounded, streaming, atomic HTTPS downloads for canonical ECCC objects."""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from weather_ingest.models import DownloadResult, RemoteObject
from weather_ingest.storage import resolve_under


class DownloadError(RuntimeError):
    """Base class for deterministic download failures."""


class DownloadIntegrityError(DownloadError):
    """The response or existing file disagrees with declared source metadata."""


class InsufficientStorageError(DownloadError):
    """The configured free-space floor would be crossed."""


class SourceUnavailableError(DownloadError):
    """An old, unretained source was confirmed absent by its provider."""


def classify_source_failure(
    error: Exception, *, reference_time: datetime, now: datetime, retry_window_hours: int
) -> Exception:
    """Only retire confirmed 404/410 responses outside the publication retry window.

    A missing current file can be late. Authentication, network, validation, and
    server errors must still fail/retry, regardless of the age of the source.
    Local retained files are attempted before this classifier is ever called.
    """
    if (
        isinstance(error, httpx.HTTPStatusError)
        and error.response.status_code in {404, 410}
        and reference_time < now - timedelta(hours=retry_window_hours)
    ):
        return SourceUnavailableError(
            f"Provider no longer serves source outside the {retry_window_hours}-hour "
            f"publication retry window; historical gap retained: {error}"
        )
    return error


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


class StreamingDownloader:
    def __init__(
        self,
        data_root: Path | str,
        *,
        allowed_hosts: frozenset[str] = frozenset({"dd.weather.gc.ca"}),
        minimum_free_bytes: int = 0,
        maximum_download_bytes: int = 2 * 1024**3,
        timeout_seconds: float = 120.0,
        user_agent: str = "weather-platform-ingest/0.1",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if minimum_free_bytes < 0 or maximum_download_bytes <= 0:
            raise ValueError("storage limits must be positive")
        self.data_root = Path(data_root).expanduser().resolve()
        self.allowed_hosts = allowed_hosts
        self.minimum_free_bytes = minimum_free_bytes
        self.maximum_download_bytes = maximum_download_bytes
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 15.0)),
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "application/octet-stream"},
            transport=transport,
        )

    def download(
        self,
        remote: RemoteObject,
        relative_path: Path | str,
        *,
        replace_existing: bool = False,
    ) -> DownloadResult:
        self._validate_remote(remote)
        destination = resolve_under(self.data_root, relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = resolve_under(self.data_root, destination.relative_to(self.data_root))

        if destination.exists():
            if not destination.is_file() or destination.is_symlink():
                raise DownloadIntegrityError(f"destination is not a regular file: {destination}")
            if not replace_existing:
                size = destination.stat().st_size
                if (
                    remote.size_is_exact
                    and remote.size_bytes is not None
                    and size != remote.size_bytes
                ):
                    raise DownloadIntegrityError(
                        f"existing file size {size} does not match remote size {remote.size_bytes}"
                    )
                return DownloadResult(destination, size, sha256_file(destination), True)

        expected_bytes = remote.size_bytes or 0
        self._check_free_space(expected_bytes)
        temporary = destination.with_name(destination.name + ".part")
        if temporary.exists():
            if temporary.is_symlink() or not temporary.is_file():
                raise DownloadIntegrityError(f"unsafe temporary download target: {temporary}")
            temporary.unlink()

        digest = hashlib.sha256()
        byte_count = 0
        try:
            with self._client.stream("GET", remote.url) as response:
                response.raise_for_status()
                final_url = urlsplit(str(response.url))
                if final_url.scheme != "https" or final_url.hostname not in self.allowed_hosts:
                    raise DownloadError("download redirected outside allowed HTTPS hosts")
                content_length = self._content_length(response)
                has_exact_listing_size = remote.size_is_exact and remote.size_bytes is not None
                if has_exact_listing_size and content_length not in {
                    None,
                    remote.size_bytes,
                }:
                    raise DownloadIntegrityError(
                        "HTTP Content-Length does not match listing size "
                        f"({content_length} != {remote.size_bytes})"
                    )
                with temporary.open("xb") as output:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        byte_count += len(chunk)
                        if byte_count > self.maximum_download_bytes:
                            raise DownloadIntegrityError("download exceeds configured maximum size")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())

            if content_length is not None and byte_count != content_length:
                raise DownloadIntegrityError(
                    f"downloaded {byte_count} bytes but Content-Length was {content_length}"
                )
            if has_exact_listing_size and byte_count != remote.size_bytes:
                raise DownloadIntegrityError(
                    f"downloaded {byte_count} bytes but listing reported {remote.size_bytes}"
                )
            if destination.exists() and not replace_existing:
                existing_size = destination.stat().st_size
                if existing_size != byte_count or sha256_file(destination) != digest.hexdigest():
                    raise DownloadIntegrityError("concurrent download produced different content")
                temporary.unlink()
                return DownloadResult(destination, byte_count, digest.hexdigest(), True)
            os.replace(temporary, destination)
            return DownloadResult(destination, byte_count, digest.hexdigest(), False)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _validate_remote(self, remote: RemoteObject) -> None:
        parts = urlsplit(remote.url)
        if (
            parts.scheme != "https"
            or parts.hostname not in self.allowed_hosts
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
        ):
            raise DownloadError(f"remote URL is not an allowed HTTPS object: {remote.url}")
        if Path(parts.path).name != remote.filename:
            raise DownloadError("remote filename does not match URL path")
        if remote.size_bytes is not None and remote.size_bytes > self.maximum_download_bytes:
            raise DownloadIntegrityError("listed object exceeds configured maximum size")

    def _check_free_space(self, incoming_bytes: int) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        free_bytes = shutil.disk_usage(self.data_root).free
        if free_bytes - incoming_bytes < self.minimum_free_bytes:
            raise InsufficientStorageError(
                f"download requires {incoming_bytes} bytes with only {free_bytes} free; "
                f"configured floor is {self.minimum_free_bytes}"
            )

    @staticmethod
    def _content_length(response: httpx.Response) -> int | None:
        value = response.headers.get("Content-Length")
        if value is None:
            return None
        try:
            length = int(value)
        except ValueError as exc:
            raise DownloadIntegrityError("invalid HTTP Content-Length") from exc
        if length < 0:
            raise DownloadIntegrityError("negative HTTP Content-Length")
        return length

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> StreamingDownloader:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
