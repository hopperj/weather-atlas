"""Age- and count-bounded maintenance of only the new forecast/station archives."""

from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import dict_row
from weather_common.db import SqlFileLoader
from weather_common.settings import Settings


def maintain_insights(settings: Settings, *, now: datetime | None = None, dry_run: bool = True):
    now = now or datetime.now(UTC)
    files = []
    # Exact dedicated feature subdirectories. Existing model, imagery and latest paths are excluded.
    for relative, days, extension in (
        ("raw/eccc/stations", 7, ".xml"),
        ("raw/eccc/citypage_weather/history", 7, ".xml"),
        ("processed/eccc/citypage_weather/history", 30, ".json"),
    ):
        directory = settings.data_root / relative
        if directory.is_symlink() or not directory.exists():
            continue
        root = directory.resolve()
        if not root.is_relative_to(settings.data_root.resolve()):
            raise ValueError("Archive retention root escapes configured storage")
        for path in directory.rglob("*" + extension):
            if len(files) >= 5000:
                break
            if (
                path.is_file()
                and not path.is_symlink()
                and path.resolve().is_relative_to(root)
                and len(path.stem) == 64
                and all(c in "0123456789abcdef" for c in path.stem)
                and path.stat().st_mtime < (now - timedelta(days=days)).timestamp()
            ):
                files.append(path)
    result = {"dryRun": dry_run, "archiveFiles": len(files), "forecasts": 0, "observations": 0}
    if dry_run:
        return result
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            SqlFileLoader(settings.sql_root).load("insights/retention.sql"),
            {"cutoff": now - timedelta(days=30)},
        ).fetchone()
        result.update(row)
    for path in files:
        path.unlink(missing_ok=True)
    return result
