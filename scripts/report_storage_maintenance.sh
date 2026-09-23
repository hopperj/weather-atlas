#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)

usage() {
  cat <<'EOF'
Usage: report_storage_maintenance.sh [OPTIONS]

Read-only storage integrity and retention-candidate report. This command has no
delete mode.

Options:
  --data-root PATH          Data tree (default: WEATHER_DATA_DIR or
                            WEATHERAPP_DATA_DIR/weather)
  --raw-days N              Raw retention age (default: 30)
  --staging-days N          Staging retention age (default: 2)
  --temporary-days N        Temporary retention age (default: 1)
  --quarantine-days N       Quarantine retention age (default: 14)
  --processed-days N        Processed retention age (default: 180)
  --derived-days N          Derived retention age (default: 180)
  --check-catalogue         Compare registered database paths and sizes to disk
  --verify-checksums        Hash catalogue files too (implies --check-catalogue)
  --fail-on-integrity       Exit 1 when an integrity issue is found
  --verbose                 List individual candidates and anomalies
  --help                    Show this help

Catalogue checks require WEATHER_READONLY_PASSWORD. No files or database rows
are changed, regardless of options.
EOF
}

file_size() {
  if stat -c '%s' "$1" >/dev/null 2>&1; then
    stat -c '%s' "$1"
  else
    stat -f '%z' "$1"
  fi
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "Neither sha256sum nor shasum is available." >&2
    return 1
  fi
}

format_mib() {
  awk -v bytes="$1" 'BEGIN { printf "%.2f", bytes / 1024 / 1024 }'
}

is_days() {
  [[ "$1" =~ ^[0-9]+$ ]]
}

if [[ -f "$repo_root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$repo_root/.env"
  set +a
fi

data_root=${WEATHER_DATA_DIR:-${WEATHERAPP_DATA_DIR:-./weatherapp_data}/weather}
raw_days=${WEATHER_RETENTION_RAW_DAYS:-30}
staging_days=${WEATHER_RETENTION_STAGING_DAYS:-2}
temporary_days=${WEATHER_RETENTION_TEMPORARY_DAYS:-1}
quarantine_days=${WEATHER_RETENTION_QUARANTINE_DAYS:-14}
processed_days=${WEATHER_RETENTION_PROCESSED_DAYS:-180}
derived_days=${WEATHER_RETENTION_DERIVED_DAYS:-180}
check_catalogue=false
verify_checksums=false
fail_on_integrity=false
verbose=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-root)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      data_root=$2
      shift 2
      ;;
    --raw-days|--staging-days|--temporary-days|--quarantine-days|--processed-days|--derived-days)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      case "$1" in
        --raw-days) raw_days=$2 ;;
        --staging-days) staging_days=$2 ;;
        --temporary-days) temporary_days=$2 ;;
        --quarantine-days) quarantine_days=$2 ;;
        --processed-days) processed_days=$2 ;;
        --derived-days) derived_days=$2 ;;
      esac
      shift 2
      ;;
    --check-catalogue)
      check_catalogue=true
      shift
      ;;
    --verify-checksums)
      check_catalogue=true
      verify_checksums=true
      shift
      ;;
    --fail-on-integrity)
      fail_on_integrity=true
      shift
      ;;
    --verbose)
      verbose=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

for days in "$raw_days" "$staging_days" "$temporary_days" "$quarantine_days" \
  "$processed_days" "$derived_days"; do
  if ! is_days "$days"; then
    echo "Retention ages must be non-negative whole days: $days" >&2
    exit 2
  fi
done

if [[ "$data_root" != /* ]]; then
  data_root="$repo_root/$data_root"
fi
if [[ ! -d "$data_root" ]]; then
  echo "Data root is not an existing directory: $data_root" >&2
  exit 2
fi

echo "DRY RUN: no files or database rows will be changed."
echo "Data root: $data_root"
printf '%-14s %10s %12s %12s %14s\n' "Class" "Files" "Size MiB" "Candidates" "Candidate MiB"

total_candidates=0
total_candidate_bytes=0
integrity_issues=0

scan_class() {
  class_name=$1
  retention_days=$2
  class_dir="$data_root/$class_name"
  file_count=0
  byte_count=0
  candidate_count=0
  candidate_bytes=0

  if [[ -d "$class_dir" ]]; then
    while IFS= read -r -d '' path; do
      size=$(file_size "$path")
      file_count=$((file_count + 1))
      byte_count=$((byte_count + size))
      if (( size == 0 )); then
        integrity_issues=$((integrity_issues + 1))
        [[ "$verbose" == true ]] && echo "INTEGRITY zero-byte file: $path"
      fi
    done < <(find "$class_dir" -type f ! -name '.gitkeep' -print0)

    while IFS= read -r -d '' path; do
      size=$(file_size "$path")
      candidate_count=$((candidate_count + 1))
      candidate_bytes=$((candidate_bytes + size))
      [[ "$verbose" == true ]] && echo "RETENTION candidate ($retention_days days): $path"
    done < <(find "$class_dir" -type f ! -name '.gitkeep' -mtime "+$retention_days" -print0)
  fi

  total_candidates=$((total_candidates + candidate_count))
  total_candidate_bytes=$((total_candidate_bytes + candidate_bytes))
  printf '%-14s %10d %12s %12d %14s\n' \
    "$class_name" "$file_count" "$(format_mib "$byte_count")" \
    "$candidate_count" "$(format_mib "$candidate_bytes")"
}

scan_size_only_class() {
  class_name=$1
  class_dir="$data_root/$class_name"
  file_count=0
  byte_count=0

  if [[ -d "$class_dir" ]]; then
    while IFS= read -r -d '' path; do
      size=$(file_size "$path")
      file_count=$((file_count + 1))
      byte_count=$((byte_count + size))
    done < <(find "$class_dir" -type f ! -name '.gitkeep' -print0)
  fi

  printf '%-14s %10d %12s %12s %14s\n' \
    "$class_name" "$file_count" "$(format_mib "$byte_count")" "size-based" "-"
}

scan_class raw "$raw_days"
scan_class staging "$staging_days"
scan_class temporary "$temporary_days"
scan_class quarantine "$quarantine_days"
scan_class processed "$processed_days"
scan_class derived "$derived_days"
scan_size_only_class cache

for class_name in raw processed derived; do
  class_dir="$data_root/$class_name"
  if [[ -d "$class_dir" ]]; then
    while IFS= read -r -d '' path; do
      integrity_issues=$((integrity_issues + 1))
      [[ "$verbose" == true ]] && echo "INTEGRITY incomplete published file: $path"
    done < <(find "$class_dir" -type f \( -name '*.part' -o -name '*.tmp' \) -print0)
  fi
done

while IFS= read -r -d '' path; do
  if [[ ! -e "$path" ]]; then
    integrity_issues=$((integrity_issues + 1))
    [[ "$verbose" == true ]] && echo "INTEGRITY broken symlink: $path"
  fi
done < <(find "$data_root" -type l -print0)

if [[ "$check_catalogue" == true ]]; then
  readonly_user=${WEATHER_READONLY_USER:-weather_readonly}
  readonly_password=${WEATHER_READONLY_PASSWORD:-}
  if [[ -z "$readonly_password" ]]; then
    echo "WEATHER_READONLY_PASSWORD is required for --check-catalogue." >&2
    exit 2
  fi

  catalogue_rows=$(docker compose --project-directory "$repo_root" --file "$repo_root/compose.yaml" \
    exec -T -e "PGPASSWORD=$readonly_password" postgres psql \
    --host 127.0.0.1 \
    --username "$readonly_user" \
    --dbname "${WEATHER_APP_DATABASE:-weather_app}" \
    --set ON_ERROR_STOP=1 \
    --tuples-only --no-align --field-separator=$'\x1f' \
    --file - < "$repo_root/database/queries/administration/list_catalogue_storage_records.sql")

  catalogue_count=0
  if [[ -n "$catalogue_rows" ]]; then
    while IFS=$'\x1f' read -r record_kind relative_path expected_size expected_sha; do
      catalogue_count=$((catalogue_count + 1))
      if [[ "$relative_path" == /* || "/$relative_path/" == *"/../"* ]]; then
        integrity_issues=$((integrity_issues + 1))
        echo "INTEGRITY unsafe catalogue path ($record_kind): $relative_path"
        continue
      fi
      absolute_path="$data_root/$relative_path"
      if [[ ! -f "$absolute_path" ]]; then
        integrity_issues=$((integrity_issues + 1))
        echo "INTEGRITY missing catalogue file ($record_kind): $relative_path"
        continue
      fi
      if [[ -L "$absolute_path" ]]; then
        integrity_issues=$((integrity_issues + 1))
        echo "INTEGRITY catalogue file is a symlink ($record_kind): $relative_path"
        continue
      fi
      actual_size=$(file_size "$absolute_path")
      if [[ -n "$expected_size" && "$actual_size" != "$expected_size" ]]; then
        integrity_issues=$((integrity_issues + 1))
        echo "INTEGRITY size mismatch ($record_kind): $relative_path"
      fi
      if [[ "$verify_checksums" == true && -n "$expected_sha" ]]; then
        actual_sha=$(sha256_file "$absolute_path")
        if [[ "$actual_sha" != "$expected_sha" ]]; then
          integrity_issues=$((integrity_issues + 1))
          echo "INTEGRITY checksum mismatch ($record_kind): $relative_path"
        fi
      fi
    done <<<"$catalogue_rows"
  fi
  echo "Catalogue records checked: $catalogue_count"
else
  echo "Catalogue comparison: not requested"
fi

echo "Retention candidates: $total_candidates ($(format_mib "$total_candidate_bytes") MiB)"
echo "Integrity issues:     $integrity_issues"
echo "Report complete; no deletion was performed."

if [[ "$fail_on_integrity" == true && $integrity_issues -gt 0 ]]; then
  exit 1
fi
