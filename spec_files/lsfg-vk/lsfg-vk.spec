# building with gcc leads to a crash in the config parser
%define __builder ninja
%bcond_without clang

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

# Define source but we handle cloning in prep
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  cmake
BuildRequires:  ninja-build
BuildRequires:  pkgconfig
BuildRequires:  zstd
BuildRequires:  git-core
BuildRequires:  pkgconfig(vulkan)

%if %{with ui}
BuildRequires:  cmake(Qt6Quick)
BuildRequires:  cmake(Qt6Widgets)
BuildRequires:  hicolor-icon-theme
Requires:       hicolor-icon-theme
%endif

%if %{with clang}
BuildRequires:  clang
BuildRequires:  llvm
%else
BuildRequires:  gcc-c++
%endif

%description
lsfg-vk brings frame generation to Linux users by acting as a Vulkan layer
in between your game and your graphics card.

%prep
%setup -q -c -T
git clone --depth 1 --branch v%{version} %{url}.git .
git submodule update --init --recursive

%build
%cmake \
    -G Ninja \
%if %{with clang}
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
%endif
%if %{with ui}
    -DLSFGVK_BUILD_UI=ON \
    -DLSFGVK_INSTALL_XDG_FILES=ON \
%else
    -DLSFGVK_BUILD_UI=OFF \
%endif
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON

%cmake_build

%install
%cmake_install

%files
%license LICENSE.md
%doc README.md
%{_bindir}/lsfg-vk-cli
%dir %{_datadir}/vulkan/
%dir %{_datadir}/vulkan/implicit_layer.d/
%{_datadir}/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json
%{_libdir}/liblsfg-vk-layer.so

%if %{with ui}
%{_bindir}/lsfg-vk-ui
%{_datadir}/applications/*.desktop
%{_datadir}/icons/hicolor/*/apps/*.png
%endif

%changelog
* Sat Mar 14 2026 RakuOS Maintainer <maintainer@rakuos.org> - 1.0.0-1
- Fixed macro expansion in comments causing rpkg parser failure
- Fixed %setup syntax and directory handling