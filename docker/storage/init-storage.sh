#!/bin/sh
set -eu

case "${WEATHER_MANAGE_DATA_PERMISSIONS:-true}" in
  true|false) ;;
  *) echo "WEATHER_MANAGE_DATA_PERMISSIONS must be true or false." >&2; exit 1 ;;
esac
case "${WEATHER_MANAGE_SERVICE_PERMISSIONS:-true}" in
  true|false) ;;
  *) echo "WEATHER_MANAGE_SERVICE_PERMISSIONS must be true or false." >&2; exit 1 ;;
esac

# PostgreSQL manages its independent mount through its own entrypoint.
if [ "${WEATHER_MANAGE_SERVICE_PERMISSIONS:-true}" = true ]; then
  mkdir -p /storage/redis /storage/airflow/logs \
    /storage/sarracenia/cache /storage/caddy/data /storage/caddy/config \
    /storage/tile-cache /storage/backups/postgres
  chown "${AIRFLOW_UID:-50000}:0" /storage/airflow /storage/airflow/logs
  chown "${AIRFLOW_UID:-50000}:0" /storage/backups /storage/backups/postgres
  # The subscriber image uses its own fixed UID, not Airflow's configurable UID.
  chown 50000:0 /storage/sarracenia /storage/sarracenia/cache
  chown 101:101 /storage/tile-cache
  chmod 0770 /storage/airflow /storage/airflow/logs /storage/sarracenia \
    /storage/sarracenia/cache /storage/caddy /storage/caddy/data /storage/caddy/config \
    /storage/tile-cache /storage/backups /storage/backups/postgres
else
  if [ -z "${WEATHER_MONITORING_DIR:-}" ]; then
    echo "Set WEATHER_MONITORING_DIR to local storage before using externally managed service directories." >&2
    exit 1
  fi
  for directory in redis airflow/logs sarracenia/cache caddy/data caddy/config tile-cache backups/postgres; do
    if [ ! -d "/storage/$directory" ]; then
      echo "Externally managed service directory must already exist: /storage/$directory" >&2
      exit 1
    fi
  done
  echo "Leaving externally managed service ownership and permissions unchanged."
fi

# Monitoring databases need local storage even when ordinary service files use NFS.
mkdir -p /monitoring/prometheus /monitoring/grafana
chown 65534:65534 /monitoring/prometheus
chown 472:0 /monitoring/grafana
chmod 0770 /monitoring/prometheus /monitoring/grafana

if [ "${WEATHER_MANAGE_DATA_PERMISSIONS:-true}" = true ]; then
  for directory in . raw staging processed derived quarantine cache temporary amqp amqp/inbox; do
    mkdir -p "/weather-data/$directory"
    chown "${AIRFLOW_UID:-50000}:${WEATHER_DATA_GID:-0}" "/weather-data/$directory"
    chmod 2770 "/weather-data/$directory"
  done
else
  # NFS ownership/ACLs are managed on the NAS. Never recursively chown copied data.
  echo "Leaving externally managed weather-data ownership and permissions unchanged."
fi
