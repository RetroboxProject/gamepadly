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

%files -n python3-%{pypi_name} -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/gamepadly-mapper
%{_udevrulesdir}/70-gamepadly-uinput.rules
%{_modulesloaddir}/gamepadly-uinput.conf

%changelog
* @DATE@ Manu Romero <manu4.2012@gmail.com> - @VERSION@-1
- Release @VERSION@
