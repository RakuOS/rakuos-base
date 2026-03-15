%define debug_package %{nil}
%define __os_install_post %{nil}

Name: cemu
Summary: Nintendo Wii-U emulator

Version: 2.6
License: GPLv3
Release: 1%{?dist}
URL:     https://github.com/cemu-project/Cemu
Source0: %{url}/releases/download/v%{version}/cemu-%{version}-ubuntu-22.04-x64.zip
Source1: https://raw.githubusercontent.com/RakuOS/rakuos-base/refs/heads/main/spec_files/cemu/cemu.desktop
Source2: https://raw.githubusercontent.com/RakuOS/rakuos-base/refs/heads/main/spec_files/cemu/README.md
Source3: https://raw.githubusercontent.com/RakuOS/rakuos-base/refs/heads/main/spec_files/cemu/LICENSE.txt
Source4: https://raw.githubusercontent.com/RakuOS/rakuos-base/refs/heads/main/spec_files/cemu/cemu.png

ExclusiveArch:  x86_64
BuildRequires:  coreutils
BuildRequires:  unzip
BuildRequires:  chrpath
BuildRequires:  fdupes
BuildRequires:  update-desktop-files
BuildRequires:  curl
BuildRequires:  nasm
BuildRequires:  zip
BuildRequires:  unzip
BuildRequires:  hicolor-icon-theme
BuildRequires:  libboost-filesystem-devel
BuildRequires:  libboost-program-options-devel
BuildRequires:  pkgconfig
BuildRequires:  pkgconfig(alsa)
BuildRequires:  pkgconfig(jack)
BuildRequires:  pkgconfig(fmt)
BuildRequires:  pkgconfig(libglm-devel)
BuildRequires:  pkgconfig(openssl)
BuildRequires:  pkgconfig(hidapi-hidraw)
BuildRequires:  pkgconfig(libavdevice)
BuildRequires:  pkgconfig(libavfilter)
BuildRequires:  pkgconfig(libavformat)
BuildRequires:  pkgconfig(libavutil)
BuildRequires:  pkgconfig(libcurl)
BuildRequires:  pkgconfig(liblz4)
BuildRequires:  pkgconfig(liblzma)
BuildRequires:  pkgconfig(libpng)
BuildRequires:  pkgconfig(libpostproc)
BuildRequires:  pkgconfig(libpulse)
BuildRequires:  pkgconfig(libswresample)
BuildRequires:  pkgconfig(libswscale)
BuildRequires:  pkgconfig(libzip)
BuildRequires:  pkgconfig(libzstd)
BuildRequires:  pkgconfig(zlib)
BuildRequires:  pkgconfig(pugixml)
BuildRequires:  pkgconfig(RapidJSON)
BuildRequires:  pkgconfig(sdl2)
BuildRequires:  pkgconfig(speexdsp)
BuildRequires:  pkgconfig(vulkan)
BuildRequires:  pkgconfig(wayland-client)
BuildRequires:  pkgconfig(wayland-protocols)
BuildRequires:  pkgconfig(wayland-scanner)

%description
This is Cemu, a Wii U emulator that is able to run most Wii U games and homebrew in a playable state.
It's written in C/C++ and is being actively developed with new features and fixes to increase compatibility, convenience and usability.

%prep
%setup -q -c -n Cemu_%{version}
%install
mkdir -p %{buildroot}/%{_bindir}
mkdir -p %{buildroot}/%{_datadir}/applications
mkdir -p %{buildroot}/%{_datadir}/%{name}
mkdir -p %{buildroot}/%{_datadir}/doc/packages/%{name}
mkdir -p %{buildroot}/%{_datadir}/licenses/%{name}
mkdir -p %{buildroot}/%{_datadir}/pixmaps
cp Cemu_%{version}/Cemu %{buildroot}/%{_bindir}/%{name}
chmod +x %{buildroot}/%{_bindir}/%{name}
cp %{SOURCE1} %{buildroot}/%{_datadir}/applications
cp -R Cemu_%{version}/gameProfiles %{buildroot}/%{_datadir}/%{name}/gameProfiles
cp -R Cemu_%{version}/resources %{buildroot}/%{_datadir}/%{name}/resources
cp %{SOURCE2} %{buildroot}/%{_datadir}/doc/packages/%{name}
cp %{SOURCE3} %{buildroot}/%{_datadir}/licenses/%{name}
cp %{SOURCE4} %{buildroot}/%{_datadir}/pixmaps


%files
%doc README.md
%license LICENSE.txt
%{_bindir}/*
%{_datadir}/cemu
%{_datadir}/applications/%{name}.desktop
%{_datadir}/pixmaps/%{name}.*

%changelog
