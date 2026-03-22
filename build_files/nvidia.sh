#!/bin/bash

set -ouex pipefail

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)

# Install NVIDIA stack — skip systemd scriptlets that fail in containers
dnf5 install -y --setopt=tsflags=noscripts \
    dkms-nvidia \
    nvidia-modprobe \
    nvidia-driver \
    nvidia-settings \
    nvidia-persistenced \
    libva-nvidia-driver

# Build DKMS module for the installed kernel
# Force ld.bfd — gold linker fails with NVIDIA's -r + --gc-sections combination
NVIDIA_VER=$(rpm -q --queryformat '%{VERSION}\n' dkms-nvidia)
LD=ld.bfd dkms install -m nvidia -v "${NVIDIA_VER}" -k "${QUALIFIED_KERNEL}" --force || {
    echo "DKMS build failed — make.log:"
    cat /var/lib/dkms/nvidia/${NVIDIA_VER}/build/make.log || true
    exit 1
}

# Enable NVIDIA power management services
systemctl enable nvidia-hibernate.service \
    nvidia-powerd.service \
    nvidia-resume.service \
    nvidia-suspend.service \
    nvidia-suspend-then-hibernate.service

# Generate module dependencies
depmod "${QUALIFIED_KERNEL}"

# Generate initramfs with nvidia module included
/usr/bin/dracut --no-hostonly --kver "${QUALIFIED_KERNEL}" --reproducible --zstd -v \
    --add ostree --add fido2 -f "/usr/lib/modules/${QUALIFIED_KERNEL}/initramfs.img"

chmod 0600 /usr/lib/modules/"${QUALIFIED_KERNEL}"/initramfs.img