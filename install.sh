#!/usr/bin/env bash
# Install CronJovi for the current user. Safe to re-run; workflows are kept.
#
#   ./install.sh                  ask before touching your compositor config
#   ./install.sh --link-hotkeys   add the one line that loads generated hotkeys
#   ./install.sh --no-hotkeys     leave your compositor config alone
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/cronjovi"
venv="$data_dir/venv"
bin_dir="$HOME/.local/bin"
workflows="${XDG_CONFIG_HOME:-$HOME/.config}/cronjovi/workflows"

link=ask
case "${1:-}" in
    "") ;;
    --link-hotkeys) link=yes ;;
    --no-hotkeys) link=no ;;
    *) echo "usage: $0 [--link-hotkeys|--no-hotkeys]" >&2; exit 2 ;;
esac

for tool in python3 systemctl systemd-analyze systemd-run; do
    if ! command -v "$tool" >/dev/null; then
        echo "error: $tool is required" >&2
        exit 1
    fi
done
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    echo "error: Python 3.11 or newer is required" >&2
    exit 1
fi

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/cronjovi"
if [[ -e "$state_dir/gui.lock" ]] && ! flock -n "$state_dir/gui.lock" true; then
    echo "error: Cron Jovi is open. Close it, then run this again." >&2
    exit 1
fi

echo "==> Installing into $venv"
mkdir -p "$data_dir" "$bin_dir" "$workflows"
# System packages supply GTK and WebKit for the app window.
python3 -m venv --clear --system-site-packages "$venv"
# Build from a copy so the repo stays free of build/ and egg-info.
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cp -r "$repo/pyproject.toml" "$repo/README.md" "$repo/cron_jovi" "$build/"
"$venv/bin/pip" install --quiet --disable-pip-version-check --force-reinstall "$build"
ln -sf "$venv/bin/cronjovi" "$bin_dir/cronjovi"

echo "==> Adding Cron Jovi to your app launcher"
share="${XDG_DATA_HOME:-$HOME/.local/share}"
mkdir -p "$share/applications" "$share/icons/hicolor/scalable/apps"
cp "$repo/cron_jovi/gui/static/cronjovi.svg" "$share/icons/hicolor/scalable/apps/cronjovi.svg"
cat > "$share/applications/cronjovi.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Cron Jovi
Comment=Automate your desktop with simple workflows
Exec=$bin_dir/cronjovi gui
Icon=cronjovi
Terminal=false
Categories=Utility;
Keywords=automation;shortcuts;schedule;hotkey;
DESKTOP
if ! python3 -c 'import gi; gi.require_version("WebKit2", "4.1")' 2>/dev/null; then
    echo "Note: WebKitGTK wasn't found, so Cron Jovi will open in your browser."
    echo "      For its own window, install webkit2gtk-4.1 and python-gobject."
fi

echo "==> Adding example workflows (disabled) to $workflows"
cp -n "$repo"/workflows/*.yaml "$workflows/"

export PATH="$bin_dir:$PATH"
if [[ "$link" == ask ]]; then
    link=no
    if [[ -t 0 ]]; then
        read -rp "Add one line to your compositor config so hotkeys load? A backup is made. [y/N] " reply
        [[ "$reply" == [yY]* ]] && link=yes
    fi
fi

echo "==> Syncing triggers"
if [[ "$link" == yes ]]; then
    cronjovi sync --link-hotkeys
else
    cronjovi sync
fi

# Anything already running would carry on with the old code.
systemctl --user try-restart cronjovi-engine.service 2>/dev/null || true

echo
cronjovi doctor
if [[ ":$PATH:" != *":$bin_dir:"* ]] || ! bash -lc 'command -v cronjovi' >/dev/null 2>&1; then
    echo
    echo "Note: add $bin_dir to your PATH to use cronjovi from a shell."
fi
echo
echo "Installed. Open Cron Jovi from your app launcher, or run: cronjovi gui"
echo "Workflows live in $workflows"
