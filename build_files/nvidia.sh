#!/bin/bash

set -ouex pipefail

# The image's kernels (both variants), installed by bootstrap.sh in the
# image this one is built FROM. RAKUOS_ISA_LEVEL and RAKUOS_STAGING are build
# args, so they're in the environment of every build step.
source "$(dirname "$(readlink -f "$0")")/kernels.sh"

# Prebuilt, RakuOS-signed NVIDIA kernel modules (signed-kmods repo) for these
# kernels: rakuos-kmod-nvidia, or rakuos-kmod-nvidia-staging for the staging
# kernels. The package carries the modules for both kernel variants. Nothing
# is compiled or signed here any more.
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

# The installed kernels' releases, default first.
load_kernel_releases

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
    libva-nvidia-driver

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
    echo "ERROR: rakuos-kmod-nvidia${NV}${KMOD_SUFFIX} is not installed; is it built for ${KERNEL_RELEASES[*]} and this nvidia-driver version?"
    exit 1
}
# ...and it must carry modules for both kernels, not just older ones.
for kver in "${KERNEL_RELEASES[@]}"; do
    grep -q "^/usr/lib/modules/${kver}/" < <(rpm -ql "rakuos-kmod-nvidia${NV}${KMOD_SUFFIX}") || {
        echo "ERROR: $(rpm -q "rakuos-kmod-nvidia${NV}${KMOD_SUFFIX}") has no modules for ${kver}; rebuild signed-kmods"
        exit 1
    }
done

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

# Sign each kernel with the MOK key and rebuild its initramfs with the
# NVIDIA modules. The anti-cheat kernel's image is already vmlinuz.alternate
# (kernels.sh); the check confirms the default kernel is still the only one
# bootc sees.
#dnf5.real remove -y --noautoremove dkms
#systemctl disable --now dkms.service
for kver in "${KERNEL_RELEASES[@]}"; do
    sign_kernel "${kver}"
    build_initramfs "${kver}"
done
stash_alternate_kernels

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

# System accounts the NVIDIA packages created go to nss-altfiles like the
# rest (see finalize-accounts.sh, installed by the system image's post-build).
if [ -x /usr/libexec/rakuos/finalize-accounts ]; then
    /usr/libexec/rakuos/finalize-accounts
fi
