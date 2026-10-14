#!/bin/bash

set -ouex pipefail

# Same staging switch as build.sh — RAKUOS_STAGING is inherited here as an
# image ENV baked into the rakuos-base image this stage builds FROM.
KERNEL_PKG="kernel-rakuos-v2"
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    KERNEL_PKG="kernel-rakuos-v2-staging"
fi

# Prebuilt, RakuOS-signed NVIDIA kernel modules (signed-kmods repo) for this
# kernel: rakuos-kmod-nvidia, or rakuos-kmod-nvidia-staging for the staging
# kernel. Nothing is compiled or signed here any more.
KMOD_SUFFIX=""
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    KMOD_SUFFIX="-staging"
fi

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' ${KERNEL_PKG})

# Install NVIDIA stack — skip systemd scriptlets that fail in containers
rum install -y --setopt=tsflags=noscripts --skip-broken \
    --exclude=libnvidia-cfg-580xx \
    --exclude=libnvidia-gpucomp-580xx \
    --exclude=nvidia-driver-580xx-cuda-libs \
    --exclude=libnvidia-ml-580xx \
    rakuos-kmod-nvidia${KMOD_SUFFIX} \
    nvidia-driver \
    nvidia-modprobe \
    nvidia-settings \
    nvidia-driver-cuda \
    nvidia-persistenced \
    nvidia-driver-libs.i686 \
    nvidia-driver-cuda-libs.i686 \
    xorg-x11-nvidia \
    libva-nvidia-driver \
    ${KERNEL_PKG}-devel-matched

# --skip-broken above would quietly drop the kernel modules if they couldn't
# be installed (e.g. not yet built for this kernel/driver version); an
# NVIDIA image without them is broken, so fail the build instead.
rpm -q "rakuos-kmod-nvidia${KMOD_SUFFIX}" || {
    echo "ERROR: rakuos-kmod-nvidia${KMOD_SUFFIX} is not installed; is it built for ${QUALIFIED_KERNEL} and this nvidia-driver version?"
    exit 1
}

# # Build akmod packages (e.g. broadcom-wl) for the installed kernel.
# # akmods installs the resulting kmod RPM so the .ko lands in
# # /usr/lib/modules/$QUALIFIED_KERNEL/extra/ where the signing loop picks it up.
# echo "Building akmods for kernel ${QUALIFIED_KERNEL}..."
# mkdir -p /var/log/akmods
# touch /var/log/akmods/akmods.log
# akmods --kernels "$QUALIFIED_KERNEL" --rebuild
# # Install any built kmod RPMs from the cache
# find /var/cache/akmods -name "*.rpm" ! -name "*src.rpm" | xargs -r dnf5.real install -y

# Enable NVIDIA power management services
systemctl enable nvidia-powerd.service \
     nvidia-persistenced.service

# The NVIDIA modules (rakuos-kmod-nvidia*) arrive already signed with the
# RakuOS key by the signed-kmods CI, so there's no module signing step here.

# Sign the kernel vmlinuz with MOK key
VMLINUZ="/usr/lib/modules/${QUALIFIED_KERNEL}/vmlinuz"
MOK_KEY="/run/secrets/mok_key"
MOK_CERT_DER="/usr/share/rakuos/sb_pubkey.der"
if [[ -f "$MOK_KEY" ]] && [[ -f "$VMLINUZ" ]] && [[ -f "$MOK_CERT_DER" ]]; then
    echo "Signing kernel ${QUALIFIED_KERNEL}..."
    MOK_CERT_PEM=$(mktemp /tmp/MOK.XXXXXX.crt)
    openssl x509 -in "$MOK_CERT_DER" -inform DER -out "$MOK_CERT_PEM" -outform PEM
    sbsign --key "$MOK_KEY" --cert "$MOK_CERT_PEM" \
        --output "${VMLINUZ}.signed" "$VMLINUZ"
    mv "${VMLINUZ}.signed" "$VMLINUZ"
    rm -f "$MOK_CERT_PEM"
    echo "Kernel signed."
else
    echo "MOK key or vmlinuz not available — skipping kernel signing."
fi

#dnf5.real remove -y --noautoremove dkms
#systemctl disable --now dkms.service

# Generate module dependencies
depmod "${QUALIFIED_KERNEL}"

# Generate initramfs with nvidia module included
/usr/bin/dracut --no-hostonly --kver "${QUALIFIED_KERNEL}" --reproducible --zstd -v \
    --add ostree --add fido2 --add rakuos-overlay --omit selinux -f "/usr/lib/modules/${QUALIFIED_KERNEL}/initramfs.img"

chmod 0600 /usr/lib/modules/"${QUALIFIED_KERNEL}"/initramfs.img

PROTECTED_FILE="/usr/share/rakuos/protected-packages.txt"

cat >> "$PROTECTED_FILE" << 'EOF'

# Base image packages (from rakuos-base/build_files/nvidia.sh)
nvidia-driver
nvidia-modprobe
nvidia-settings
libnvidia-gpucomp
libnvidia-cfg
libnvidia-ml
nvidia-persistenced
libva-nvidia-driver
EOF
echo "rakuos-kmod-nvidia${KMOD_SUFFIX}" >> "$PROTECTED_FILE"

echo "protected-packages.txt ready ($(grep -c '^[^#]' "$PROTECTED_FILE") packages)."

echo "Generating base file manifest..."
/usr/libexec/rakuos/generate-base-manifest
