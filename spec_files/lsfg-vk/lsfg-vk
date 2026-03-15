# building with gcc leads to a crash in the config parser https://github.com/PancakeTAS/lsfg-vk/issues/214
%define __builder ninja
%bcond_without clang
# we mostly build the library on 32bit for the 32bit package
%ifarch x86_64
%bcond_without ui
%else
%bcond_with ui
%endif
Name:           lsfg-vk
Version:        1.0.0
Release:        1%{?dist}
Summary:        Lossless Scaling Frame Generation on Linux
License:        MIT
URL:            https://github.com/PancakeTAS/lsfg-vk

# see _service
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz
Source2:        https://raw.githubusercontent.com/RakuOS/rakuos-base/refs/heads/main/spec_files/lsfg-vk/baselibs.conf
BuildRequires:  cmake
BuildRequires:  ninja
BuildRequires:  pkgconfig
BuildRequires:  zstd
BuildRequires:  pkgconfig(vulkan)
%if %{with ui}
BuildRequires:  cmake(Qt6Quick)
Requires:       qt6qmlimport(QtQuick)
BuildRequires:  hicolor-icon-theme
Requires:       hicolor-icon-theme
%endif
%if %{with clang}
BuildRequires:  clang-devel
%else
BuildRequires:  gcc-c++
%endif

%description
Lossless Scaling is a Windows-exclusive app bringing frame generation (among
other features) to every single game or app.

lsfg-vk brings this frame generation to Linux users by acting as a Vulkan layer
inbetween your game and your graphics card.

%prep
%autosetup -p1

%build
%cmake \
  %if %{with clang}
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++ \
  %endif
%if %{with ui}
  -DLSFGVK_BUILD_UI=On \
  -DLSFGVK_INSTALL_XDG_FILES=ON \
%endif
  -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=On
%cmake_build


%install
%cmake_install

%files
%license LICENSE.md
%doc README.md
%{_bindir}/lsfg-vk-cli
#
%dir %{_datadir}/vulkan/implicit_layer.d/
%{_datadir}/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json
%{_libdir}/liblsfg-vk-layer.so
#
%if %{with ui}
%{_bindir}/lsfg-vk-ui
%{_datadir}/applications/gay.pancake.lsfg-vk-ui.desktop
%{_datadir}/icons/hicolor/256x256/apps/gay.pancake.lsfg-vk-ui.png
%endif

%changelog
