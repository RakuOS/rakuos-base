Name:           helium-browser
Version:        0.10.5.1
Release:        1%{?dist}
Summary:        Privacy-focused minimal Chromium-based web browser

License:        GPL-3.0
URL:            https://helium.computer/
Source0:        https://github.com/imputnet/helium-linux/releases/download/%{version}/helium-%{version}-x86_64_linux.tar.xz

# Chromium/Chrome style runtime dependencies
Requires:       alsa-lib
Requires:       atk
Requires:       at-spi2-atk
Requires:       at-spi2-core
Requires:       cairo
Requires:       cups-libs
Requires:       dbus-libs
Requires:       expat
Requires:       glib2
Requires:       gtk3
Requires:       libX11
Requires:       libX11-xcb
Requires:       libXcomposite
Requires:       libXcursor
Requires:       libXdamage
Requires:       libXext
Requires:       libXfixes
Requires:       libXi
Requires:       libXrandr
Requires:       libXrender
Requires:       libXScrnSaver
Requires:       libXtst
Requires:       libdrm
Requires:       libxcb
Requires:       libxkbcommon
Requires:       mesa-libEGL
Requires:       mesa-libgbm
Requires:       mesa-libGL
Requires:       mesa-libGLES
Requires:       nspr
Requires:       nss
Requires:       pango
Requires:       zlib
Requires:       liberation-fonts
Requires:       xdg-utils

%description
Helium is a privacy-focused, lightweight Chromium-based web browser
designed to provide a clean and distraction-free browsing experience.
It supports modern web technologies while avoiding unnecessary
bloat and tracking commonly found in mainstream browsers.

Helium can be used as a full web browser or for web applications such
as streaming services, dashboards, and productivity tools.

This package installs Helium under /opt/helium and integrates it with
the system desktop environment.

%prep
%setup -c -T -n helium-%{version}
# Now we're in helium-0.10.5.1

%build
# Nothing to build (binary release)

%install
# Install browser to /opt
mkdir -p %{buildroot}/opt/helium
cp -a * %{buildroot}/opt/helium/

# Desktop entry
mkdir -p %{buildroot}%{_datadir}/applications
install -m 0644 helium.desktop %{buildroot}%{_datadir}/applications/

# Icon
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/256x256/apps
install -m 0644 product_logo_256.png %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/helium.png

# Wrapper binary
mkdir -p %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/helium << 'EOF'
#!/bin/bash
exec /opt/helium/helium "$@"
EOF
chmod +x %{buildroot}%{_bindir}/helium

%files
/opt/helium
%{_bindir}/helium
%{_datadir}/applications/helium.desktop
%{_datadir}/icons/hicolor/256x256/apps/helium.png

%post
update-desktop-database &> /dev/null || :

%postun
update-desktop-database &> /dev/null || :

%changelog
* Sat Mar 14 2026 RakuOS Maintainer <maintainer@rakuos.org> - 0.10.5.1-1
- Initial package