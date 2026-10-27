%global pypi_name gamepadly

Name:           python-%{pypi_name}
Version:        @VERSION@
Release:        1%{?dist}
Summary:        Linux gamepad-to-keyboard/mouse mapper
License:        GPL-2.0-only
URL:            https://github.com/RetroboxProject/gamepadly
Source0:        %{pypi_name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  systemd-rpm-macros

%global _description %{expand:
Gamepadly translates gamepad input into virtual keyboard and mouse events
through uinput, using evmapy-compatible profiles.}

%description %_description

%package -n python3-%{pypi_name}
Summary:        %{summary}
Requires:       python3-pygame
Requires:       python3-evdev

%description -n python3-%{pypi_name} %_description

%prep
%autosetup -n %{pypi_name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files %{pypi_name}
install -Dpm 0644 system/70-gamepadly-uinput.rules %{buildroot}%{_udevrulesdir}/70-gamepadly-uinput.rules
install -Dpm 0644 system/gamepadly-uinput.conf %{buildroot}%{_modulesloaddir}/gamepadly-uinput.conf

%check
%pyproject_check_import

%post
add_input_group() {
    # /dev/uinput and /dev/input/* are group "input": add the invoking (sudo) user, or else
    # every regular user (UID 1000-59999 with a login shell). Opt out: GAMEPADLY_NO_INPUT_GROUP=1
    [ "${GAMEPADLY_NO_INPUT_GROUP:-}" = 1 ] && return 0
    getent group input >/dev/null 2>&1 || return 0
    if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
        _users="$SUDO_USER"
    else
        _users="$(getent passwd | awk -F: '$3 >= 1000 && $3 < 60000 && $7 !~ /(nologin|false)$/ {print $1}')"
    fi
    for _u in $_users; do
        id -nG "$_u" 2>/dev/null | tr ' ' '\n' | grep -qx input && continue
        if usermod -aG input "$_u" 2>/dev/null; then
            echo "gamepadly: added $_u to the 'input' group (log out and back in to apply)" >&2
        fi
    done
}
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules >/dev/null 2>&1 || :
    udevadm trigger --subsystem-match=misc --sysname-match=uinput >/dev/null 2>&1 || :
fi
# Fresh installs only (not upgrades).
if [ "$1" -eq 1 ]; then
    add_input_group || :
fi
:

%files -n python3-%{pypi_name} -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/gamepadly-mapper
%{_udevrulesdir}/70-gamepadly-uinput.rules
%{_modulesloaddir}/gamepadly-uinput.conf

%changelog
* @DATE@ Manu Romero <manu4.2012@gmail.com> - @VERSION@-1
- Release @VERSION@
