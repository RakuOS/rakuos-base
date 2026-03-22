#!/bin/bash

set -ouex pipefail

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)

# Install NVIDIA stack + kernel devel headers needed for DKMS build
dnf5 install -y \
    dkms-nvidia \
    nvidia-modprobe \
    nvidia-driver \
    nvidia-settings \
    nvidia-persistenced \
    libva-nvidia-driver \
    kernel-cachyos-devel-${QUALIFIED_KERNEL}

# Build DKMS module for the installed kernel
NVIDIA_VER=$(rpm -q --queryformat '%{VERSION}\n' dkms-nvidia)
dkms install -m nvidia -v "${NVIDIA_VER}" -k "${QUALIFIED_KERNEL}" --force

# Generate module dependencies
depmod "${QUALIFIED_KERNEL}"

# Generate initramfs with nvidia module included
/usr/bin/dracut --no-hostonly --kver "${QUALIFIED_KERNEL}" --reproducible --zstd -v \
    --add ostree --add fido2 -f "/usr/lib/modules/${QUALIFIED_KERNEL}/initramfs.img"

chmod 0600 /usr/lib/modules/"${QUALIFIED_KERNEL}"/initramfs.img