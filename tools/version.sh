#!/usr/bin/env bash
# Print the project version from pyproject.toml.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
sed -n 's/^version *= *"\(.*\)"/\1/p' pyproject.toml | head -n1
