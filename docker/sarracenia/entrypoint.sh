#!/bin/sh
set -eu

# Airflow and the syncing user must be able to publish/clean up deliveries.
# The shared data directories supply the group through setgid inheritance.
umask 0002
exec "$@"
