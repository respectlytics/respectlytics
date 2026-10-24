#!/usr/bin/env bash
# Build static/css/tailwind.css with Tailwind's standalone CLI, the one release pinned below and
# checked against its SHA-256 before it runs. No Node toolchain: until 2026-10-23 the npm tree
# built it, and with it came braces (GHSA-vfj7-8cjw-p6xm), which has no fixed release.
#
#   scripts/tailwind.sh            rebuild tailwind.css (after a template, script or token change)
#   scripts/tailwind.sh --watch    rebuild on every change while developing
#   scripts/tailwind.sh --check    fail when the committed file is not what the sources build
#                                  (CI: a class a template uses that the file lacks has no style)
#
# The binary bundles @tailwindcss/typography, which tailwind.config.js requires. Upgrading is a
# new VERSION and its four digests from the release's sha256sums.txt, then a rebuild compared
# page by page with the old file.
set -euo pipefail
export BROWSERSLIST_IGNORE_OLD_DATA=1  # the binary carries its own browser data

VERSION=3.4.19
cd "$(dirname "$0")/.."
# Plain case statements: macOS's own bash (3.2) has no associative arrays.
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) PLATFORM=macos-arm64 DIGEST=7fdeb00818b6214a337383063282b2361ecb08bbc08f8c8a7ba97ee1e2eaa4fe ;;
  Darwin-x86_64) PLATFORM=macos-x64 DIGEST=a597f407e0f1f03535731f5b42f1576a8152cb5fffc2f38e754722bc0c280045 ;;
  Linux-x86_64) PLATFORM=linux-x64 DIGEST=4af3198c015616ea7d6617974ec3d70d987ecc00c1ca8463b0a30fd65cc7c06e ;;
  Linux-aarch64) PLATFORM=linux-arm64 DIGEST=e5b2d27694daa80cc52ec29553ba2c6bd43d86bd51a9d633ed24058b9c05a676 ;;
  *) echo "No pinned Tailwind binary for $(uname -s) $(uname -m)." >&2; exit 1 ;;
esac

# Kept outside the repository, so no worktree or edition needs an ignore rule, and one download
# serves them all.
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/tailwindcss"
BIN="$CACHE/tailwindcss-$VERSION-$PLATFORM"
sha() { shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1 || sha256sum "$1" | cut -d' ' -f1; }
if [ ! -x "$BIN" ] || [ "$(sha "$BIN")" != "$DIGEST" ]; then
  mkdir -p "$CACHE"
  curl -fsSL -o "$BIN.part" \
    "https://github.com/tailwindlabs/tailwindcss/releases/download/v$VERSION/tailwindcss-$PLATFORM"
  if [ "$(sha "$BIN.part")" != "$DIGEST" ]; then
    rm -f "$BIN.part"
    echo "The downloaded Tailwind $VERSION ($PLATFORM) is not the pinned file. Nothing was built." >&2
    exit 1
  fi
  chmod +x "$BIN.part" && mv "$BIN.part" "$BIN"
fi

IN=static/css/tailwind-input.css
OUT=static/css/tailwind.css
case "${1:-}" in
  --watch) exec "$BIN" -i "$IN" -o "$OUT" --watch ;;
  --check)
    BUILT="$(mktemp)"
    trap 'rm -f "$BUILT"' EXIT
    "$BIN" -i "$IN" -o "$BUILT" --minify 2>/dev/null
    if ! cmp -s "$BUILT" "$OUT"; then
      echo "$OUT is not what the templates build: run scripts/tailwind.sh and commit it." >&2
      exit 1
    fi
    echo "$OUT matches its sources."
    ;;
  "") "$BIN" -i "$IN" -o "$OUT" --minify ;;
  *) echo "Usage: scripts/tailwind.sh [--watch|--check]" >&2; exit 2 ;;
esac
