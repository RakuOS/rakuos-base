%define debug_package %{nil}
%define __os_install_post %{nil}

Name:           ryujinx
Version:        1.3.3
Release:        1%{?dist}
Summary:        Experimental Nintendo Switch Emulator written in C# (master build channel release)
License:        MIT
URL:            https://git.ryujinx.app/ryubing/ryujinx

Source0:        https://git.ryujinx.app/api/v4/projects/1/packages/generic/Ryubing/%{version}/ryujinx-%{version}-linux_x64.tar.gz
Source1:        https://raw.githubusercontent.com/RakuOS/rakuos-base/refs/heads/main/spec_files/ryujinx/Ryujinx.desktop
Source2:        https://raw.githubusercontent.com/RakuOS/rakuos-base/refs/heads/main/spec_files/ryujinx/Logo.svg
Source3:        https://raw.githubusercontent.com/RakuOS/rakuos-base/refs/heads/main/spec_files/ryujinx/Ryujinx.xml

%description
Ryujinx is an experimental Nintendo Switch emulator written in C#. This package installs the master build channel release.

%prep
%setup -q -n publish

%build
# No build step needed

%install
# Create installation directories
mkdir -p %{buildroot}/opt/ryujinx
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/scalable/apps
mkdir -p %{buildroot}/usr/share/mime/packages

# Copy application files to /opt/ryujinx
cp -R * %{buildroot}/opt/ryujinx
chmod +x %{buildroot}/opt/ryujinx/Ryujinx

# Create writable logs directory
install -d -m 777 %{buildroot}/opt/ryujinx/Logs

# Create symlinks
ln -s /opt/ryujinx/Ryujinx %{buildroot}/usr/bin/Ryujinx
ln -s /opt/ryujinx/Ryujinx.sh %{buildroot}/usr/bin/Ryujinx.sh

# Install desktop file, icon, and MIME type
install -m 644 %{SOURCE1} %{buildroot}/usr/share/applications/Ryujinx.desktop
install -m 644 %{SOURCE2} %{buildroot}/usr/share/icons/hicolor/scalable/apps/Ryujinx.svg
install -m 644 %{SOURCE3} %{buildroot}/usr/share/mime/packages/Ryujinx.xml

%files
%defattr(-,root,root,-)
%dir /opt/ryujinx
/opt/ryujinx/*
/usr/bin/Ryujinx
/usr/bin/Ryujinx.sh
%dir /usr/share/icons/hicolor
%dir /usr/share/icons/hicolor/scalable
%dir /usr/share/icons/hicolor/scalable/apps
/usr/share/applications/Ryujinx.desktop
/usr/share/icons/hicolor/scalable/apps/Ryujinx.svg
/usr/share/mime/packages/Ryujinx.xml

%changelog
