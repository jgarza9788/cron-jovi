#!/usr/bin/env bash
# Remove CronJovi: timers, units, hotkey bindings, the program itself.
# Workflows and run history stay unless you pass --purge.
set -euo pipefail

data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/cronjovi"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/cronjovi"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/cronjovi"
bin_link="$HOME/.local/bin/cronjovi"
venv="$data_dir/venv"

purge=no
case "${1:-}" in
    "") ;;
    --purge) purge=yes ;;
    *) echo "usage: $0 [--purge]" >&2; exit 2 ;;
esac

if [[ -x "$venv/bin/python" ]]; then
    echo "==> Removing timers and hotkey bindings"
    "$venv/bin/python" -m cron_jovi teardown
else
    echo "CronJovi is not installed at $venv; nothing to tear down."
fi

echo "==> Removing the program"
if [[ -L "$bin_link" ]]; then
    rm "$bin_link"
fi
rm -rf "$data_dir"
share="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$share/applications/cronjovi.desktop" "$share/icons/hicolor/scalable/apps/cronjovi.svg"

if [[ "$purge" == yes ]]; then
    echo "==> Removing workflows and history"
    rm -rf "$config_dir" "$state_dir"
else
    echo "Kept workflows in $config_dir and history in $state_dir"
    echo "Run with --purge to delete them too."
fi
echo "Uninstalled."
