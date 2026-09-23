from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def _write_fake_docker(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

command_text=""
migration_name=""
migration_checksum=""
previous=""

for argument in "$@"; do
  if [[ "$previous" == "--command" ]]; then
    command_text=$argument
    previous=""
    continue
  fi

  case "$argument" in
    --command)
      previous="--command"
      ;;
    migration_name=*)
      migration_name=${argument#migration_name=}
      ;;
    migration_checksum=*)
      migration_checksum=${argument#migration_checksum=}
      ;;
  esac
done

state_file=${FAKE_MIGRATION_STATE:?}
touch "$state_file"

if [[ -n "$command_text" ]]; then
  case "$command_text" in
    *"current_database()"*)
      echo "weather_app|weather_migrator|127.0.0.1|5432"
      ;;
    *"to_regclass('app.schema_migration')"*)
      if [[ -s "$state_file" ]]; then
        echo "t"
      else
        echo "f"
      fi
      ;;
    *"SELECT checksum FROM app.schema_migration"*)
      awk -F '|' -v name="$migration_name" '$1 == name { print $2 }' "$state_file"
      ;;
    *)
      echo "Unexpected fake psql command: $command_text" >&2
      exit 90
      ;;
  esac
  exit 0
fi

if [[ -z "$migration_name" || -z "$migration_checksum" ]]; then
  echo "Migration variables were not passed to psql." >&2
  exit 91
fi

cat >/dev/null
printf '%s|%s\n' "$migration_name" "$migration_checksum" >> "$state_file"
"""
    )
    path.chmod(0o755)


def _build_test_repository(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    migrations = repository / "database" / "migrations"
    fake_bin = tmp_path / "bin"
    scripts.mkdir(parents=True)
    migrations.mkdir(parents=True)
    fake_bin.mkdir()

    for script_name in ("apply_migration.sh", "apply_migrations.sh"):
        source = PROJECT_ROOT / "scripts" / script_name
        destination = scripts / script_name
        shutil.copy2(source, destination)
        destination.chmod(0o755)

    (repository / ".env").write_text(
        "WEATHER_APP_DATABASE=weather_app\n"
        "WEATHER_MIGRATOR_USER=weather_migrator\n"
        "WEATHER_MIGRATOR_PASSWORD=test-only\n"
    )
    (migrations / "0001_first.sql").write_text("SELECT 1;\n")
    (migrations / "0002_second.sql").write_text("SELECT 2;\n")

    _write_fake_docker(fake_bin / "docker")
    state_file = tmp_path / "migration-state.txt"
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["FAKE_MIGRATION_STATE"] = str(state_file)
    return repository, environment


def _run(
    script: Path, *arguments: str, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *arguments],
        cwd=script.parents[2],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_migration_directory_can_be_applied_twice(tmp_path: Path) -> None:
    repository, environment = _build_test_repository(tmp_path)
    runner = repository / "scripts" / "apply_migrations.sh"

    first = _run(runner, "--yes", environment=environment)
    second = _run(runner, "--yes", environment=environment)

    assert first.returncode == 0, first.stderr
    assert "2 applied, 0 unchanged" in first.stdout
    assert second.returncode == 0, second.stderr
    assert "0 applied, 2 unchanged" in second.stdout


def test_directory_continues_after_unchanged_migration(tmp_path: Path) -> None:
    repository, environment = _build_test_repository(tmp_path)
    runner = repository / "scripts" / "apply_migrations.sh"
    second_migration = repository / "database" / "migrations" / "0002_second.sql"
    second_migration.unlink()

    initial = _run(runner, "--yes", environment=environment)
    assert initial.returncode == 0, initial.stderr
    assert "1 applied, 0 unchanged" in initial.stdout

    second_migration.write_text("SELECT 2;\n")
    extended = _run(runner, "--yes", environment=environment)

    assert extended.returncode == 0, extended.stderr
    assert "1 applied, 1 unchanged" in extended.stdout


def test_changed_applied_migration_is_rejected(tmp_path: Path) -> None:
    repository, environment = _build_test_repository(tmp_path)
    directory_runner = repository / "scripts" / "apply_migrations.sh"
    migration_runner = repository / "scripts" / "apply_migration.sh"
    migration = repository / "database" / "migrations" / "0001_first.sql"

    first = _run(directory_runner, "--yes", environment=environment)
    assert first.returncode == 0, first.stderr

    migration.write_text("SELECT 'changed';\n")
    changed = _run(migration_runner, "--yes", str(migration), environment=environment)

    assert changed.returncode == 1
    assert "Refusing changed migration" in changed.stderr
