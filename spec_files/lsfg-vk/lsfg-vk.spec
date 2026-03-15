%global tag 1.0.0
%global date %(date +%Y%m%d)
%global commit 5e04b4f
%global longcommit 5e04b4f5f60eae5345acfb156610609cb77c671a

Name:           lsfg-vk
Version:        %{tag}
Release:        1.%{date}git%{commit}%{?dist}
Summary:        Lossless Scaling Frame Generation on Linux via DXVK/Vulkan.

# SPDX
License:        MIT
URL:            https://github.com/PancakeTAS/lsfg-vk

BuildRequires:       clang
BuildRequires:       llvm
BuildRequires:       cmake
BuildRequires:       cmake-rpm-macros
BuildRequires:       cargo-rpm-macros >= 24
BuildRequires:       ninja-build
BuildRequires:       git
BuildRequires:       pkgconfig(gl)
BuildRequires:       pkgconfig(vulkan)
BuildRequires:       pkgconfig(SPIRV-Headers)
BuildRequires:       vulkan-headers
BuildRequires:       pkgconfig(wayland-client) >= 0.2.7
BuildRequires:       pkgconfig(wayland-cursor) >= 0.2.7
BuildRequires:       pkgconfig(wayland-egl) >= 0.2.7
BuildRequires:       pkgconfig(xkbcommon) >= 0.5.0
BuildRequires:       pkgconfig(x11)
BuildRequires:       pkgconfig(xext)
BuildRequires:       pkgconfig(xrandr)
BuildRequires:       pkgconfig(xinerama)
BuildRequires:       pkgconfig(xcursor)
BuildRequires:       pkgconfig(xi)
BuildRequires:       pkgconfig(wayland-protocols)

# UI dependencies
BuildRequires:       pkgconfig(glib-2.0)
BuildRequires:       pkgconfig(pango)
BuildRequires:       pkgconfig(gdk-pixbuf-2.0)
BuildRequires:       pkgconfig(graphene-gobject-1.0)
BuildRequires:       pkgconfig(gtk4)
BuildRequires:       pkgconfig(libadwaita-1)

Recommends:          mesa-dri-drivers
Recommends:          mesa-vulkan-drivers
Recommends:          lsfg-vk-ui

Requires:            %{name}-libs = %{version}-%{release}

%description
The %{name} package provides Lossless Scaling Frame Generation on Linux via DXVK/Vulkan.

%prep
git clone --single-branch --branch develop https://github.com/PancakeTAS/lsfg-vk
cd lsfg-vk
git checkout %{longcommit}
git submodule update --init --recursive

%build
cd lsfg-vk

CMAKE_OPTIONS=(
   -DCMAKE_BUILD_TYPE=Release \
   -DCMAKE_C_COMPILER=clang \
   -DCMAKE_CXX_COMPILER=clang++ \
   -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON
)
%__cmake "${CMAKE_OPTIONS[@]}" .
%__cmake --build . %{?_smp_mflags} --verbose

cd ui
# Call on cargo directly, need to wait for various rust packages to be updated
%__cargo build --release --locked

%install
cd lsfg-vk

# Install the Vulkan layer JSON file and shared library
install -Dm644 VkLayer_LS_frame_generation.json "%{buildroot}/%{_datadir}/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json"
install -Dm644 liblsfg-vk.so "%{buildroot}/%{_libdir}/liblsfg-vk.so"

# Install the UI binary and desktop bits (for ui subpackage)
install -Dm755 ui/target/release/lsfg-vk-ui "%{buildroot}%{_bindir}/lsfg-vk-ui"
install -Dm644 ui/rsc/gay.pancake.lsfg-vk-ui.desktop "%{buildroot}%{_datadir}/applications/lsfg-vk-ui.desktop"
install -Dm644 ui/rsc/icon.png "%{buildroot}%{_datadir}/icons/hicolor/256x256/apps/gay.pancake.lsfg-vk-ui.png"

%files
%license lsfg-vk/LICENSE.md
%{_datadir}/vulkan/implicit_layer.d/VkLayer_LS_frame_generation*.json

%package libs
Summary:       lsfg-vk libraries
%description libs
%summary

%files libs
%{_libdir}/liblsfg-vk.so

%package ui
Summary:       Rust-based GUI for modifying lsfg-vk configuration
Requires:      %{name} = %{version}-%{release}
%description ui
This package provides the GUI for modifying configuration of lsfg-vk.

%files ui
%{_bindir}/lsfg-vk-ui
%{_datadir}/applications/lsfg-vk-ui.desktop
%{_datadir}/icons/hicolor/256x256/apps/gay.pancake.lsfg-vk-ui.png

%changelog
%autochangelog