#!/usr/bin/env bash
# Build the release files into dist-release/vX.Y.Z/: the source tarball, the Arch package,
# the AppImage and SHA256SUMS. They come from the committed code, never the working folder.
# Publishes nothing.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tools="${TOOLS:-$HOME/Work/CaptainFM-tools}"      # holds appimagetool-x86_64.AppImage
commit="${1:-HEAD}"
cd "$repo"

for tool in git makepkg bsdtar sha256sum python3; do
    command -v "$tool" >/dev/null || { echo "error: $tool is required" >&2; exit 1; }
done
[[ -x "$tools/appimagetool-x86_64.AppImage" ]] || { echo "error: no appimagetool in $tools" >&2; exit 1; }

version="$(git show "$commit:cron_jovi/__init__.py" | sed -n 's/^__version__ = "\(.*\)"/\1/p')"
out="$repo/dist-release/v$version"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
rm -rf "$out"
mkdir -p "$out"
echo "==> Building $version from $(git rev-parse --short "$commit")"

echo "==> Source tarball"
git archive --format=tar.gz --prefix="cron-jovi-$version/" -o "$out/cron-jovi-$version.tar.gz" "$commit"

echo "==> Arch package"
cp "$out/cron-jovi-$version.tar.gz" "$work/"
git show "$commit:packaging/arch/PKGBUILD" | sed "s/^pkgver=.*/pkgver=$version/" > "$work/PKGBUILD"
(cd "$work" && PKGDEST="$out" makepkg -f --noconfirm --nodeps >/dev/null)

echo "==> AppImage"
source="$work/appimage-source"
mkdir "$source"
tar -xzf "$out/cron-jovi-$version.tar.gz" -C "$source" --strip-components=1
"$source/packaging/appimage/build.sh" "$source" "$work/AppDir" "$out/CronJovi-$version-x86_64.AppImage" "$tools"

(cd "$out" && sha256sum -- * > SHA256SUMS)
echo "==> Done"
ls -lh "$out"
