#!/bin/bash

set -ouex pipefail

## Enable repos
dnf5 -y install dnf5-plugins
dnf5 -y copr enable bieszczaders/kernel-cachyos
dnf5 -y copr enable bieszczaders/kernel-cachyos-addons
dnf5 -y copr enable atim/xpadneo

#remove fedora kernel
dnf5 -y remove --no-autoremove kernel kernel-core kernel-modules kernel-modules-core kernel-modules-extra kernel-tools kernel-tools-libs

# Install cachyos kernel
dnf5 -y --setopt=tsflags=noscripts install kernel-cachyos kernel-cachyos-devel-matched

#Build initramfs
# Determine the installed CachyOS kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)

# Generate module dependencies
depmod "$QUALIFIED_KERNEL"

# Generate initramfs for that kernel
/usr/bin/dracut --no-hostonly --kver "$QUALIFIED_KERNEL" --reproducible --zstd -v \
    --add ostree --add fido2 -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img

# install packages
dnf5 -y install ananicy-cpp \
  cachyos-ananicy-rules \
  scx-scheds \
  scx-tools \
  mangohud \
  mangohud.i686 \
  dkms \
  flatpak \
  rsync \
  podman \
  distrobox \
  xpadneo

# enable flathub
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo