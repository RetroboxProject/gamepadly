#!/usr/bin/env bash
# Gamepadly installer: installs the Python package system-wide into /usr/local with pip
# (remove it with `pip uninstall gamepadly` or `./install.sh --uninstall`), plus the udev rule
# and modules-load file that give /dev/uinput the right permissions.
#
# Local checkout:  ./install.sh
# Remote:          curl -fsSL https://raw.githubusercontent.com/RetroboxProject/gamepadly/main/install.sh | sudo bash
#                  ... | sudo bash -s -- --ref v0.1.0
set -euo pipefail

REPO="RetroboxProject/gamepadly"
REF="main"
PY_PREFIX="/usr/local"
SYSCONF="/etc"
DO_DEPS=1
PIP_DEPS=0
USER_MODE=0
ACTION=install
ASSUME_YES=0

usage() {
    cat <<USAGE
Usage: install.sh [options]
  --ref REF           git tag/branch to download when not run from a checkout (default: $REF)
  --python-prefix DIR pip prefix (default: $PY_PREFIX; commands go to DIR/bin)
  --user              per-user install (~/.local) without udev/modules-load
  --no-deps           do not install distro packages (python3-pip, pygame, evdev)
  --pip-deps          let pip install pygame/evdev instead of distro packages
  --uninstall         remove gamepadly (pip uninstall + udev/modules-load files)
  -y, --yes           non-interactive package manager calls
  -h, --help          this help
USAGE
}

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

while (($#)); do
    case "$1" in
        --ref) REF="${2:?}"; shift 2 ;;
        --python-prefix) PY_PREFIX="${2:?}"; shift 2 ;;
        --user) USER_MODE=1; shift ;;
        --no-deps) DO_DEPS=0; shift ;;
        --pip-deps) PIP_DEPS=1; DO_DEPS=0; shift ;;
        --uninstall) ACTION=uninstall; shift ;;
        -y|--yes) ASSUME_YES=1; shift ;;
        # Retrobox component contract: accepted, unused (gamepadly lives in the Python tree).
        --prefix|--bin-dir) shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown option: $1" ;;
    esac
done

if ((USER_MODE)); then
    PIP_SCOPE=(--user)
else
    [[ $EUID -eq 0 ]] || die "run as root (sudo), or use --user"
    # Debian/Ubuntu/Fedora pip already installs to /usr/local when run as root (and Debian's
    # scheme turns an explicit --prefix /usr/local into /usr/local/local), so only pass
    # --prefix for a non-default location.
    PIP_SCOPE=(--break-system-packages)
    [[ "$PY_PREFIX" == /usr/local ]] || PIP_SCOPE+=(--prefix "$PY_PREFIX")
fi

pip_cmd() { python3 -m pip "$@"; }

install_distro_deps() {
    local yes=()
    if command -v apt-get >/dev/null 2>&1; then
        ((ASSUME_YES)) && yes=(-y)
        apt-get install "${yes[@]}" python3-pip python3-pygame python3-evdev
    elif command -v dnf >/dev/null 2>&1; then
        ((ASSUME_YES)) && yes=(-y)
        dnf install "${yes[@]}" python3-pip python3-pygame python3-evdev
    else
        warn "no apt/dnf found: install python3-pip, pygame and evdev yourself or use --pip-deps"
    fi
}

SRC=""; TMP=""
cleanup() { [[ -n "$TMP" ]] && rm -rf "$TMP"; return 0; }
trap cleanup EXIT

fetch_source() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
    if [[ -n "$here" && -f "$here/pyproject.toml" && -d "$here/src/gamepadly" ]]; then
        SRC="$here"; return
    fi
    command -v curl >/dev/null || die "curl is required to download gamepadly"
    TMP="$(mktemp -d)"
    log "downloading $REPO@$REF"
    curl -fsSL "https://github.com/$REPO/archive/$REF.tar.gz" | tar -xz -C "$TMP" --strip-components=1
    SRC="$TMP"
}

system_files() { # source -> destination
    echo "$SRC/system/70-gamepadly-uinput.rules $SYSCONF/udev/rules.d/70-gamepadly-uinput.rules"
    echo "$SRC/system/gamepadly-uinput.conf $SYSCONF/modules-load.d/gamepadly-uinput.conf"
}

reload_udev() {
    command -v udevadm >/dev/null 2>&1 || return 0
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger --subsystem-match=misc --sysname-match=uinput 2>/dev/null || true
}

do_install() {
    command -v python3 >/dev/null || die "python3 not found"
    ((DO_DEPS)) && install_distro_deps
    pip_cmd --version >/dev/null 2>&1 || die "pip not available (install python3-pip)"
    fetch_source

    local args=("${PIP_SCOPE[@]}" --upgrade)
    ((PIP_DEPS)) || args+=(--no-deps)
    # The system Python is "externally managed" (PEP 668); older pip lacks the flag.
    pip_cmd install --help 2>/dev/null | grep -q -- --break-system-packages \
        || { local a=(); for x in "${args[@]}"; do [[ $x == --break-system-packages ]] || a+=("$x"); done; args=("${a[@]}"); }
    log "pip install gamepadly (${PIP_SCOPE[*]})"
    pip_cmd install "${args[@]}" "$SRC"

    if ((!USER_MODE)); then
        local pair s d
        while read -r s d; do
            install -Dm0644 "$s" "$d"
        done < <(system_files)
        reload_udev
        modprobe uinput 2>/dev/null || true
    else
        warn "--user: udev rule and modules-load not installed; /dev/uinput needs permissions"
    fi
    if ((!USER_MODE)) && [[ "$PY_PREFIX" == /usr/local ]]; then
        local loc
        loc="$(python3 -c 'import gamepadly,sys;print(gamepadly.__file__)' 2>/dev/null || true)"
        [[ "$loc" == /usr/local/* ]] || warn "installed outside /usr/local ($loc)"
    fi
    log "done. Add your user to the 'input' group if needed, then run: gamepadly-mapper --help"
}

do_uninstall() {
    pip_cmd uninstall -y --break-system-packages gamepadly 2>/dev/null \
        || pip_cmd uninstall -y gamepadly || true
    if ((!USER_MODE)); then
        rm -f "$SYSCONF/udev/rules.d/70-gamepadly-uinput.rules" \
              "$SYSCONF/modules-load.d/gamepadly-uinput.conf"
        reload_udev
    fi
    log "gamepadly removed"
}

"do_$ACTION"
