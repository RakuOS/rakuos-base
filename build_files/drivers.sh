#!/bin/bash

set -ouex pipefail

# The image's kernels (both variants), installed by bootstrap.sh.
# RAKUOS_ISA_LEVEL and RAKUOS_STAGING are build args, so they're in the
# environment of every build step.
source "$(dirname "$(readlink -f "$0")")/kernels.sh"

# Prebuilt, RakuOS-signed kernel modules (signed-kmods repo) for these
# kernels: rakuos-kmod-<name>, or rakuos-kmod-<name>-staging for the staging
# kernels. Each package carries the modules for both kernel variants.
# Nothing is compiled or signed here any more.
KMOD_SUFFIX=""
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    KMOD_SUFFIX="-staging"
fi

# The installed kernels' releases, default first.
load_kernel_releases

# Every module the signed-kmods repo builds, except NVIDIA (the nvidia
# scripts install rakuos-kmod-nvidia; nvidia-580xx is for a later legacy
# image), VirtualBox (users add rakuos-kmod-VirtualBox to their overlay
# along with VirtualBox itself), openrazer (it misbehaves with Razer's RGB
# hub; users with Razer peripherals can add rakuos-kmod-openrazer) and
# mediatek-mt7927 (it caused problems with a MediaTek USB Wi-Fi adapter; users
# who need it add rakuos-kmod-mediatek-mt7927). Each
# package pulls in its companion userspace/firmware package (xone, xpadneo,
# broadcom-wl, v4l2loopback, ...) through its dependencies.
# Keep in sync with DECK_KMODS in rakuos-gamescope's drivers.sh.
KMODS=(
    wl v4l2loopback
)

rum install -y \
    gcc \
    make \
    cabextract \
    git \
    bluez \
    cabextract \
    curl \
    sbsigntools \
    b43-fwcutter \
    b43-openfwwf \
    brcmfmac-firmware \
    broadcom-wl \
    v4l2loopback \
    $(printf "rakuos-kmod-%s${KMOD_SUFFIX} " "${KMODS[@]}")

# The signed-kmods packages carry modules only for the kernels that were
# current when they were built. One that predates these kernels installs
# without complaint and ships nothing loadable, so fail the build instead.
for pkg in $(printf "rakuos-kmod-%s${KMOD_SUFFIX} " "${KMODS[@]}"); do
    for kver in "${KERNEL_RELEASES[@]}"; do
        grep -q "^/usr/lib/modules/${kver}/" < <(rpm -ql "$pkg") || {
            echo "ERROR: $(rpm -q "$pkg") has no modules for ${kver}; rebuild signed-kmods"
            exit 1
        }
    done
done

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# ASUS G733ZM HDA audio firmware — sits in /usr/lib/firmware unused on other hardware.
# The modprobe config that activates it is written at runtime via `rakuos setup-g733zm-audio`.
# https://github.com/Hyperchaotic/G733ZM-audio-fix
echo "Installing ASUS G733ZM audio firmware..."
curl -fsSL \
    "https://raw.githubusercontent.com/Hyperchaotic/G733ZM-audio-fix/main/hda-jack-retask.fw" \
    -o /usr/lib/firmware/hda-jack-retask.fw

# Out-of-tree modules (rakuos-kmod-*) arrive already signed with the RakuOS
# key by the signed-kmods CI, so there's no module signing step here.

# Sign each kernel with the MOK key and build its initramfs, then leave
# only the default kernel's vmlinuz where bootc looks (kernels.sh).
for kver in "${KERNEL_RELEASES[@]}"; do
    sign_kernel "${kver}"
    build_initramfs "${kver}"
done
stash_alternate_kernels

rm -rf /var/lib/dkms /var/cache/akmods /usr/src/broadcom-wl-* /usr/src/hid-xpadneo-* /usr/src/xpad-noone-* /usr/src/zenergy-* /usr/src/xone-* /usr/src/v4l2loopback-* /usr/src/VERSION
