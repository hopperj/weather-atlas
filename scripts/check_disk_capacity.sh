#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)

usage() {
  cat <<'EOF'
Usage: check_disk_capacity.sh [OPTIONS]

Read-only admission check for the weather data filesystem.

Options:
  --data-root PATH            Filesystem path to inspect (default: WEATHER_DATA_DIR
                              or WEATHERAPP_DATA_DIR/weather)
  --minimum-free-gib NUMBER   Free GiB that must remain (default: 20)
  --minimum-free-percent N    Free percentage that must remain (default: 10)
  --required-gib NUMBER       Additional capacity required by a planned job (default: 0)
  --help                      Show this help

Exit status is 0 when the job can be admitted, 1 when capacity is below a
threshold, and 2 for invalid input. This command never creates or removes files.
EOF
}

is_number() {
  [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]
}

gib_to_bytes() {
  awk -v gib="$1" 'BEGIN { printf "%.0f\n", gib * 1024 * 1024 * 1024 }'
}

format_gib() {
  awk -v bytes="$1" 'BEGIN { printf "%.2f", bytes / 1024 / 1024 / 1024 }'
}

if [[ -f "$repo_root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$repo_root/.env"
  set +a
fi

data_root=${WEATHER_DATA_DIR:-${WEATHERAPP_DATA_DIR:-./weatherapp_data}/weather}
minimum_free_gib=${WEATHER_MIN_FREE_GIB:-20}
minimum_free_percent=${WEATHER_MIN_FREE_PERCENT:-10}
required_gib=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-root)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      data_root=$2
      shift 2
      ;;
    --minimum-free-gib)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      minimum_free_gib=$2
      shift 2
      ;;
    --minimum-free-percent)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      minimum_free_percent=$2
      shift 2
      ;;
    --required-gib)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      required_gib=$2
      shift 2
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

for value in "$minimum_free_gib" "$minimum_free_percent" "$required_gib"; do
  if ! is_number "$value"; then
    echo "Capacity values must be non-negative numbers: $value" >&2
    exit 2
  fi
done

if ! awk -v value="$minimum_free_percent" 'BEGIN { exit !(value <= 100) }'; then
  echo "--minimum-free-percent cannot exceed 100." >&2
  exit 2
fi

if [[ "$data_root" != /* ]]; then
  data_root="$repo_root/$data_root"
fi
if [[ ! -d "$data_root" ]]; then
  echo "Data root is not an existing directory: $data_root" >&2
  exit 2
fi

df_record=$(df -Pk "$data_root" | awk 'NR > 1 { line = $0 } END { print line }')
read -r filesystem total_kib used_kib available_kib capacity mountpoint <<<"$df_record"
if [[ ! "$total_kib" =~ ^[0-9]+$ || ! "$available_kib" =~ ^[0-9]+$ ]]; then
  echo "Unable to parse filesystem capacity for $data_root" >&2
  exit 2
fi

total_bytes=$((total_kib * 1024))
available_bytes=$((available_kib * 1024))
minimum_free_bytes=$(gib_to_bytes "$minimum_free_gib")
required_bytes=$(gib_to_bytes "$required_gib")
remaining_bytes=$((available_bytes - required_bytes))
if (( remaining_bytes < 0 )); then
  remaining_bytes=0
fi
remaining_percent=$(awk -v remaining="$remaining_bytes" -v total="$total_bytes" \
  'BEGIN { if (total == 0) print 0; else printf "%.2f", remaining * 100 / total }')

echo "Data root:              $data_root"
echo "Filesystem:             $filesystem"
echo "Mount point:            $mountpoint"
echo "Available now:          $(format_gib "$available_bytes") GiB"
echo "Planned requirement:    $(format_gib "$required_bytes") GiB"
echo "Free after planned job: $(format_gib "$remaining_bytes") GiB ($remaining_percent%)"
echo "Required floor:         $minimum_free_gib GiB and $minimum_free_percent%"

meets_percent=$(awk -v actual="$remaining_percent" -v minimum="$minimum_free_percent" \
  'BEGIN { print (actual >= minimum) ? "yes" : "no" }')
if (( remaining_bytes < minimum_free_bytes )) || [[ "$meets_percent" != "yes" ]]; then
  echo "Capacity decision:      BLOCKED"
  exit 1
fi

echo "Capacity decision:      ADMIT"
