#!/usr/bin/env bash
# Build python3-gamepadly noarch RPM into dist/. Needs: rpm-build python3-devel pyproject-rpm-macros
# systemd-rpm-macros, plus the build backend (hatchling) via `dnf builddep`.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="$("$ROOT/tools/version.sh")"
TOP="$(mktemp -d)"; trap 'rm -rf "$TOP"' EXIT
mkdir -p "$TOP"/{SOURCES,SPECS} "$ROOT/dist"
SRC="$TOP/gamepadly-$VER"; mkdir -p "$SRC"
git -C "$ROOT" ls-files -z --cached --others --exclude-standard | grep -zv '^packaging/\|^\.github/' \
    | (cd "$ROOT" && xargs -0 cp --parents -t "$SRC")
tar -C "$TOP" -czf "$TOP/SOURCES/gamepadly-$VER.tar.gz" "gamepadly-$VER"
sed -e "s/@VERSION@/$VER/g" -e "s/@DATE@/$(LC_ALL=C date '+%a %b %d %Y')/" \
    "$ROOT/packaging/rpm/python-gamepadly.spec" > "$TOP/SPECS/python-gamepadly.spec"
rpmbuild --define "_topdir $TOP" -bb "$TOP/SPECS/python-gamepadly.spec"
cp "$TOP"/RPMS/noarch/*.rpm "$ROOT/dist/"
ls "$ROOT"/dist/*.rpm
