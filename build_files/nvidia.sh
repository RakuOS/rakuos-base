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

# Legacy images (NVIDIA_LEGACY=1, a build arg from the *-nvidia-legacy CI
# jobs) ship the 580xx driver, the last branch for Maxwell, Pascal and Volta:
# the same packages with a -580xx suffix, and the current driver's libraries
# kept out instead of the 580xx ones.
NV=""
NV_EXCLUDES=(libnvidia-cfg-580xx libnvidia-gpucomp-580xx nvidia-driver-580xx-cuda-libs libnvidia-ml-580xx)
if [ "${NVIDIA_LEGACY:-0}" = "1" ]; then
    NV="-580xx"
    NV_EXCLUDES=(libnvidia-cfg libnvidia-gpucomp nvidia-driver-cuda-libs libnvidia-ml)
fi

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' ${KERNEL_PKG})

# Install NVIDIA stack — skip systemd scriptlets that fail in containers
rum install -y --setopt=tsflags=noscripts --skip-broken \
    $(printf -- '--exclude=%s ' "${NV_EXCLUDES[@]}") \
    rakuos-kmod-nvidia${NV}${KMOD_SUFFIX} \
    nvidia-driver${NV} \
    nvidia-modprobe${NV} \
    nvidia-settings${NV} \
    nvidia-driver${NV}-cuda \
    nvidia-persistenced${NV} \
    xorg-x11-nvidia${NV} \
    libva-nvidia-driver \
    ${KERNEL_PKG}-devel-matched

# 32-bit libraries for Steam and other 32-bit games, each on its own: the
# repos don't always carry a matching i686 build of everything they need
# (e.g. no libnvidia-gpucomp-580xx.i686 for the legacy driver), and one that
# can't be installed would otherwise fail the whole NVIDIA install. Skip it
# with a warning instead.
for pkg in "nvidia-driver${NV}-libs.i686" "nvidia-driver${NV}-cuda-libs.i686"; do
    rum install -y --setopt=tsflags=noscripts \
        $(printf -- '--exclude=%s ' "${NV_EXCLUDES[@]}") \
        "$pkg" \
        || echo "WARNING: skipping $pkg: its 32-bit dependencies aren't available"
done

# --skip-broken above would quietly drop the kernel modules if they couldn't
# be installed (e.g. not yet built for this kernel/driver version); an
# NVIDIA image without them is broken, so fail the build instead.
rpm -q "rakuos-kmod-nvidia${NV}${KMOD_SUFFIX}" || {
    echo "ERROR: rakuos-kmod-nvidia${NV}${KMOD_SUFFIX} is not installed; is it built for ${QUALIFIED_KERNEL} and this nvidia-driver version?"
    exit 1
}
# ...and it must carry modules for this kernel, not just an older one.
grep -q "^/usr/lib/modules/${QUALIFIED_KERNEL}/" < <(rpm -ql "rakuos-kmod-nvidia${NV}${KMOD_SUFFIX}") || {
    echo "ERROR: $(rpm -q "rakuos-kmod-nvidia${NV}${KMOD_SUFFIX}") has no modules for ${QUALIFIED_KERNEL}; rebuild signed-kmods"
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

# Enable NVIDIA power management services (the 580xx driver may not ship
# nvidia-powerd, so only enable the units that are there).
for unit in nvidia-powerd.service nvidia-persistenced.service; do
    if systemctl cat "$unit" >/dev/null 2>&1; then
        systemctl enable "$unit"
    else
        echo "WARNING: $unit not installed; not enabling it"
    fi
done

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
    --add ostree --add fido2 --add rakuos-overlay --add rakuos-groups --omit selinux -f "/usr/lib/modules/${QUALIFIED_KERNEL}/initramfs.img"

chmod 0600 /usr/lib/modules/"${QUALIFIED_KERNEL}"/initramfs.img

PROTECTED_FILE="/usr/share/rakuos/protected-packages.txt"

cat >> "$PROTECTED_FILE" << 'EOF'

# Base image packages (from rakuos-base/build_files/nvidia.sh)
EOF
for pkg in nvidia-driver nvidia-modprobe nvidia-settings libnvidia-gpucomp \
           libnvidia-cfg libnvidia-ml nvidia-persistenced; do
    echo "${pkg}${NV}" >> "$PROTECTED_FILE"
done
echo "libva-nvidia-driver" >> "$PROTECTED_FILE"
echo "rakuos-kmod-nvidia${NV}${KMOD_SUFFIX}" >> "$PROTECTED_FILE"

echo "protected-packages.txt ready ($(grep -c '^[^#]' "$PROTECTED_FILE") packages)."

echo "Generating base file manifest..."
/usr/libexec/rakuos/generate-base-manifest
