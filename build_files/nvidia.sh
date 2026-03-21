#!/bin/bash

set -ouex pipefail

# Enable NVIDIA repo
#sed -i 's@enabled=0@enabled=1@g' /etc/yum.repos.d/rpmfusion-nonfree-nvidia-driver.repo

# Install NVIDIA stack
dnf5 install -y \
    akmod-nvidia \
    xorg-x11-drv-nvidia \
    xorg-x11-drv-nvidia-libs \
    xorg-x11-drv-nvidia-libs.i686 \
    xorg-x11-drv-nvidia-cuda \
    xorg-x11-drv-nvidia-power

#build akmods and update initramfs with nvidia drivers included
KVER="$(dnf5 repoquery --installed --qf '%{VERSION}-%{RELEASE}.%{ARCH}' kernel-cachyos)"
akmods --force --kernels "$KVER"

#Build initramfs
# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)

# Generate module dependencies
depmod "$QUALIFIED_KERNEL"

# Generate initramfs for that kernel
/usr/bin/dracut --no-hostonly --kver "$QUALIFIED_KERNEL" --reproducible --zstd -v \
    --add ostree --add fido2 -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img

# Disable repo again
sed -i 's@enabled=1@enabled=0@g' /etc/yum.repos.d/rpmfusion-nonfree-nvidia-driver.repo