#!/usr/bin/env bash
# Build the AppImage from this machine's Python, which ships inside it.
#   build.sh <source folder> <AppDir> <output file> <folder holding appimagetool>
set -euo pipefail

source="$1" appdir="$2" output="$3" tools="$4"
minor="$(python3 -c 'import sys; print("python%d.%d" % sys.version_info[:2])')"
stdlib="$(python3 -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')"
lib="$appdir/usr/lib"
site="$lib/$minor/site-packages"

mkdir -p "$appdir/usr/bin" "$lib"
cp -L "$(python3 -c 'import sys; print(sys.executable)')" "$appdir/usr/bin/python3"
tar -C "$(dirname "$stdlib")" --exclude=site-packages --exclude=__pycache__ --exclude="$minor/test" \
    --exclude=idlelib --exclude=tkinter --exclude=turtledemo -cf - "$minor" | tar -C "$lib" -xf -

python3 -m venv "$appdir/.venv"
"$appdir/.venv/bin/pip" install --quiet --disable-pip-version-check "$source"
mkdir -p "$site"
cp -r "$appdir/.venv/lib/$minor/site-packages/." "$site/"
rm -rf "$appdir/.venv" "$site"/pip "$site"/pip-*
find "$appdir" -name __pycache__ -type d -prune -exec rm -rf {} +

# Bundle what the Python and its modules link to, apart from glibc, which must be the host's own.
copied="$(mktemp)"
find "$appdir/usr" -type f \( -name '*.so*' -o -name python3 \) -print0 | xargs -0 ldd 2>/dev/null \
    | awk '/=> \//{print $3}' | sort -u > "$copied"
while read -r library; do
    case "$(basename "$library")" in
        libc.so*|libm.so*|libdl.so*|librt.so*|libpthread.so*|libutil.so*|ld-linux*) ;;
        *) cp -nL "$library" "$lib/" ;;
    esac
done < "$copied"
rm -f "$copied"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -m755 "$here/AppRun" "$appdir/AppRun"
install -m644 "$here/../arch/cronjovi.desktop" "$appdir/cronjovi.desktop"
install -m644 "$source/cron_jovi/gui/static/cronjovi.svg" "$appdir/cronjovi.svg"
sed -i 's/^Exec=.*/Exec=AppRun gui/' "$appdir/cronjovi.desktop"
ARCH=x86_64 "$tools/appimagetool-x86_64.AppImage" --no-appstream "$appdir" "$output" >/dev/null 2>&1
