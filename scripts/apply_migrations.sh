#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)

assume_flag=""
if [[ "${1:-}" == "--yes" ]]; then
  assume_flag="--yes"
  shift
fi

if [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--yes]" >&2
  exit 2
fi

shopt -s nullglob
migrations=("$repo_root"/database/migrations/*.sql)
if [[ ${#migrations[@]} -eq 0 ]]; then
  echo "No migrations found." >&2
  exit 1
fi

applied_count=0
unchanged_count=0
for migration in "${migrations[@]}"; do
  if "$script_dir/apply_migration.sh" ${assume_flag:+"$assume_flag"} "$migration"; then
    applied_count=$((applied_count + 1))
  else
    status=$?
    case "$status" in
      10)
        unchanged_count=$((unchanged_count + 1))
        ;;
      *)
        exit "$status"
        ;;
    esac
  fi
done

echo "Migration directory complete: $applied_count applied, $unchanged_count unchanged."
