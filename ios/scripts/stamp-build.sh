#!/usr/bin/env bash
# Writes the build label the app shows in Settings → About and the operator overlay (IOS-07.6):
# "<git short hash>[+dirty] · <date time>". Run before `xcodegen generate` and the install build.
# Writes only ios/GhostChef/Resources/build-label.txt (git-ignored).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
hash="$(git -C "$here" rev-parse --short HEAD)"
if ! git -C "$here" diff --quiet HEAD -- . 2>/dev/null; then hash="$hash+dirty"; fi
label="$hash · $(date '+%Y-%m-%d %H:%M')"
printf '%s\n' "$label" > "$here/GhostChef/Resources/build-label.txt"
echo "Build label: $label"
