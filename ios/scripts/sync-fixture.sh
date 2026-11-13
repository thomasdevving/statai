#!/usr/bin/env bash
# Copies the fixture recipe (and its placeholder images) from ai/fixtures into the iOS bundle.
# Run from anywhere after pulling a new AI-01 / AI-03 / AI-06 fixture, then rebuild.
# Reads ai/ only; writes only under ios/.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
src="$here/../ai/fixtures"
dst="$here/GhostChef/Resources/Fixtures"
if [[ ! -f "$src/sushi_recipe.json" ]]; then
  echo "error: $src/sushi_recipe.json not found (has AI-01 been pushed and pulled?)" >&2
  exit 1
fi
mkdir -p "$dst/images"
cp "$src/sushi_recipe.json" "$dst/sushi_recipe.json"
if compgen -G "$src/images/step-*.jpg" > /dev/null; then
  rm -f "$dst"/images/step-*.jpg
  cp "$src"/images/step-*.jpg "$dst/images/"
fi
echo "Synced fixture from ai/fixtures into $dst"
ls -l "$dst" "$dst/images"
