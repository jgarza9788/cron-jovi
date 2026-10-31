#!/usr/bin/env bash
# Tag the commit and publish dist-release/vX.Y.Z/ as a GitHub pre-release. Public.
#   publish.sh             stops if the release already exists
#   publish.sh --replace   deletes that release and its tag first
# Run scripts/release/build.sh first, and put the notes in dist-release/notes.md.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo"
version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' cron_jovi/__init__.py)"
codename="$(sed -n 's/^__codename__ = "\(.*\)"/\1/p' cron_jovi/__init__.py)"
stage="$(sed -n 's/^__stage__ = "\(.*\)"/\1/p' cron_jovi/__init__.py)"
tag="v$version"
out="dist-release/$tag"
notes="dist-release/notes.md"
title="Cron Jovi $tag $codename ($stage)"

git fetch -q origin
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || { echo "error: check out the latest main first" >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "error: commit your changes first" >&2; exit 1; }
[[ -f "$out/SHA256SUMS" ]] || { echo "error: run scripts/release/build.sh first" >&2; exit 1; }
[[ -f "$notes" ]] || { echo "error: write $notes first" >&2; exit 1; }
(cd "$out" && sha256sum -c --quiet SHA256SUMS)

exists=no
gh release view "$tag" >/dev/null 2>&1 && exists=yes
if [[ "$exists" == yes && "${1:-}" != --replace ]]; then
    echo "error: $tag is already released. Use --replace to delete it first." >&2
    exit 1
fi

echo "$title from $(git rev-parse --short HEAD)"
ls -lh "$out"
[[ "$exists" == yes ]] && echo "This DELETES the published $tag release and tag first."
read -rp "Publish this for everyone? Type yes: " reply
[[ "$reply" == yes ]] || exit 1

if [[ "$exists" == yes ]]; then
    gh release delete "$tag" --yes --cleanup-tag
fi
git tag -d "$tag" 2>/dev/null || true
git tag -a "$tag" -m "$tag $codename ($stage)"
git push origin "$tag"
flags=(); [[ "$stage" == Beta ]] && flags=(--prerelease)
gh release create "$tag" --title "$title" "${flags[@]}" --verify-tag --notes-file "$notes" "$out"/*
gh release view "$tag" --json url --jq .url
