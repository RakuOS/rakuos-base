#!/bin/bash

set -ouex pipefail
FEDORA_VERSION=$(rpm -E %fedora)

KERNEL_RAKUOS_PKG="kernel-rakuos-v4"
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    KERNEL_RAKUOS_PKG="kernel-rakuos-v4-staging"
fi

KERNEL_P03_PKG="kernel-p03-v4"
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    KERNEL_P03_PKG="kernel-p03-v4-staging"
fi

# Remove unneeded packages
rum remove -y \
    ${KERNEL_RAKUOS_PKG} \
    ${KERNEL_RAKUOS_PKG}-core \
    ${KERNEL_RAKUOS_PKG}-modules \
    ${KERNEL_RAKUOS_PKG}-devel \
    ${KERNEL_RAKUOS_PKG}-devel-matched \
    broadcom-wl \
    v4l2loopback \
    ananicy-cpp \
    cachyos-ananicy-rules \
    scx-scheds \
    scx-tools

rm -rf /boot/* /usr/lib/modules/* /lib/modules/*

systemctl mask systemd-oomd.service

# Install P03
rum install -y \
    ${KERNEL_P03_PKG} \
    ${KERNEL_P03_PKG}-core \
    ${KERNEL_P03_PKG}-modules \
    ${KERNEL_P03_PKG}-devel \
    ${KERNEL_P03_PKG}-devel-matched

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' ${KERNEL_P03_PKG})

#Build initramfs
# Generate module dependencies
depmod "$QUALIFIED_KERNEL"

# Generate initramfs for that kernel
/usr/bin/dracut --no-hostonly --kver "$QUALIFIED_KERNEL" --reproducible --zstd -v \
--add ostree --add fido2 --add rakuos-overlay -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img