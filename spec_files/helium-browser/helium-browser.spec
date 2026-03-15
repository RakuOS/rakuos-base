Name:           helium
Version:        0.10.5.1
Release:        1%{?dist}
Summary:        Privacy-focused minimal Chromium-based web browser

License:        GPL-3.0
URL:            https://github.com/imputnet/helium-linux
Source0:        %{url}/releases/download/%{version}/helium-%{version}-x86_64_linux.tar.xz
AutoReqProv:    no

# Disable automatic debug package (no ELF sources)
%define debug_package %{nil}

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
%setup -q -c

%build
# No build needed - binary distribution

%install
# Create directory structure
install -d %{buildroot}%{_libdir}/%{name}
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/pixmaps

# Navigate into the extracted directory
cd %{name}-%{version}-x86_64_linux

# Install all files to /usr/lib64/helium
mkdir -p %{buildroot}/opt/%{name}
cp -a * %{buildroot}/opt/%{name}/

# Create wrapper script in /usr/bin
cat > %{buildroot}%{_bindir}/%{name} << 'EOF'
#!/bin/bash
exec /opt/helium/helium-wrapper "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/%{name}

# Install desktop file
install -m 644 %{name}.desktop %{buildroot}%{_datadir}/applications/

# Install icon
install -m 644 product_logo_256.png %{buildroot}%{_datadir}/pixmaps/%{name}.png

# Fix desktop file to use correct paths
sed -i 's|Exec=.*|Exec=/usr/bin/helium %U|g' %{buildroot}%{_datadir}/applications/%{name}.desktop
sed -i 's|Icon=.*|Icon=helium|g' %{buildroot}%{_datadir}/applications/%{name}.desktop

%files
/opt/%{name}/
%{_bindir}/%{name}
%{_datadir}/applications/%{name}.desktop
%{_datadir}/pixmaps/%{name}.png

%changelog
* Sat Mar 14 2026 RakuOS Maintainer <maintainer@rakuos.org> - 0.10.5.1-1
- Initial package