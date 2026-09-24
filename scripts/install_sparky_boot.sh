#!/usr/bin/env bash
# Install the mount dependency without restarting Docker or rebooting the host.
set -euo pipefail
[[ $# == 0 ]] || { echo "Usage: sudo bash scripts/install_sparky_boot.sh" >&2; exit 2; }
[[ $(hostname -s) == sparky ]] || { echo "This installer is only for sparky." >&2; exit 1; }
[[ $EUID == 0 ]] || { echo "Run with sudo on sparky; no password is stored." >&2; exit 1; }
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
template="$script_dir/../docs/systemd/sparky-docker-nfs.conf"
target_dir=/etc/systemd/system/docker.service.d
target="$target_dir/20-weather-nfs.conf"
test -f "$template"
findmnt --noheadings --mountpoint /home/hopperj/weather-atlas/data \
  --source databanks.iolan:/volume1/data/weather-atlas-data --types nfs,nfs4
test -d /home/hopperj/weather-atlas/data/weather
test -d /home/hopperj/weather-atlas/data/services
install -d -m 0755 "$target_dir"
if [[ -e "$target" ]] && ! cmp -s "$template" "$target"; then
  backup_dir=$(mktemp -d "$target_dir/weather-nfs-backup.XXXXXX")
  cp -p "$target" "$backup_dir/20-weather-nfs.conf"
  echo "Previous setting saved in $backup_dir"
fi
install -o root -g root -m 0644 "$template" "$target"
systemctl daemon-reload
systemctl enable docker.service
systemd-analyze verify docker.service
systemctl show docker.service -p RequiresMountsFor -p DropInPaths
echo "Installed: Docker now requires the NAS at startup. Docker was not restarted."
