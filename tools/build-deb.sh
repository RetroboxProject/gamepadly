#!/usr/bin/env bash
# Build python3-gamepadly_<ver>_all.deb into dist/. Needs: dpkg-dev debhelper dh-python
# pybuild-plugin-pyproject python3-hatchling.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$("$ROOT/tools/version.sh")"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
SRC="$W/gamepadly-$VER"
mkdir -p "$SRC" "$ROOT/dist"
git -C "$ROOT" ls-files -z --cached --others --exclude-standard | grep -zv '^packaging/\|^\.github/' \
    | (cd "$ROOT" && xargs -0 cp --parents -t "$SRC")
cp -r "$ROOT/packaging/debian" "$SRC/debian"
cat > "$SRC/debian/changelog" <<CL
gamepadly ($VER) unstable; urgency=medium

  * Release $VER.

 -- Manu Romero <manu4.2012@gmail.com>  $(date -R)
CL
(cd "$SRC" && dpkg-buildpackage -us -uc -b)
cp "$W"/python3-gamepadly_"$VER"_all.deb "$ROOT/dist/"
echo "$ROOT/dist/python3-gamepadly_${VER}_all.deb"
