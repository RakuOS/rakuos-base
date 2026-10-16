#!/bin/bash

set -ouex pipefail

# Same staging switch as build.sh (RAKUOS_STAGING persists as an image ENV
# from that layer, so it's already set here).
KERNEL_PKG="kernel-rakuos-v2"
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    KERNEL_PKG="kernel-rakuos-v2-staging"
fi

# Prebuilt, RakuOS-signed kernel modules (signed-kmods repo) for this kernel:
# rakuos-kmod-<name>, or rakuos-kmod-<name>-staging for the staging kernel.
# Nothing is compiled or signed here any more.
KMOD_SUFFIX=""
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    KMOD_SUFFIX="-staging"
fi

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' ${KERNEL_PKG})

# Every module the signed-kmods repo builds, except NVIDIA (the nvidia
# scripts install rakuos-kmod-nvidia; nvidia-580xx is for a later legacy
# image), VirtualBox (users add rakuos-kmod-VirtualBox to their overlay
# along with VirtualBox itself) and openrazer (it misbehaves with Razer's RGB
# hub; users with Razer peripherals can add rakuos-kmod-openrazer). Each
# package pulls in its companion userspace/firmware package (xone, xpadneo,
# broadcom-wl, v4l2loopback, ...) through its dependencies.
# Keep in sync with DECK_KMODS in rakuos-gamescope's drivers.sh.
KMODS=(
    wl v4l2loopback
    xone xpadneo xpad-noone
    hid-fanatecff hid-tmff2 t150-driver new-lg4ff logitech-trueforce
    ayaneo-leds
    mediatek-mt7927 xtables-addons
    intel-ipu6 intel-vision sc0710
    nct6687d ryzen_smu zenergy
)

rum install -y \
    ${KERNEL_PKG}-devel \
    ${KERNEL_PKG}-devel-matched \
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
# current when they were built. One that predates this kernel installs
# without complaint and ships nothing loadable, so fail the build instead.
for pkg in $(printf "rakuos-kmod-%s${KMOD_SUFFIX} " "${KMODS[@]}"); do
    grep -q "^/usr/lib/modules/${QUALIFIED_KERNEL}/" < <(rpm -ql "$pkg") || {
        echo "ERROR: $(rpm -q "$pkg") has no modules for ${QUALIFIED_KERNEL}; rebuild signed-kmods"
        exit 1
    }
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

#Build initramfs
# Generate module dependencies
depmod "$QUALIFIED_KERNEL"

# Generate initramfs for that kernel
/usr/bin/dracut --no-hostonly --kver "$QUALIFIED_KERNEL" --reproducible --zstd -v \
--add ostree --add fido2 --add rakuos-overlay --omit selinux -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img

rm -rf /var/lib/dkms /var/cache/akmods /usr/src/broadcom-wl-* /usr/src/hid-xpadneo-* /usr/src/xpad-noone-* /usr/src/zenergy-* /usr/src/xone-* /usr/src/v4l2loopback-* /usr/src/VERSION
