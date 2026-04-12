#!/bin/bash

set -ouex pipefail

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)


# Install non-NVIDIA drivers for every image
dnf5 install -y --setopt=tsflags=noscripts \
    akmod-xpadneo \
    dkms-xpad-noone \
    dkms-xone \
    xone-firmware \
    dkms-zenergy

mkdir -p /var/log/akmods
touch /var/log/akmods/akmods.log
KVER="$(dnf5 repoquery --installed --qf '%{VERSION}-%{RELEASE}.%{ARCH}' kernel-cachyos)"
akmods --force --kernels "$KVER"

# Build all installed DKMS modules for the installed kernel (if any)
while IFS=' ' read -r pkg_name pkg_ver; do
    module="${pkg_name#dkms-}"
    echo "Building DKMS module: ${module} ${pkg_ver}"

    dkms install -m "${module}" -v "${pkg_ver}" -k "${QUALIFIED_KERNEL}" --force || {
        echo "DKMS build failed for ${module} ${pkg_ver} — make.log:"
        cat "/var/lib/dkms/${module}/${pkg_ver}/build/make.log" 2>/dev/null || true
        exit 1
    }
done < <(rpm -qa --queryformat '%{NAME} %{VERSION}\n' | grep '^dkms-')

#Build initramfs
# Generate module dependencies
depmod "$QUALIFIED_KERNEL"

# Generate initramfs for that kernel
/usr/bin/dracut --no-hostonly --kver "$QUALIFIED_KERNEL" --reproducible --zstd -v \
--add ostree --add fido2 -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img
