#!/bin/bash

set -ouex pipefail

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-p03-v3)

dnf5 install -y \
    akmods \
    kernel-p03-v3-devel \
    kernel-p03-v3-devel-matched \
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
    broadcom-wl


tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# Build akmod packages (e.g. broadcom-wl) for the installed kernel.
# akmods installs the resulting kmod RPM so the .ko lands in
# /usr/lib/modules/$QUALIFIED_KERNEL/extra/ where the signing loop picks it up.
echo "Building akmods for kernel ${QUALIFIED_KERNEL}..."
akmods --kernels "$QUALIFIED_KERNEL" --rebuild
# Install any built kmod RPMs from the cache
find /var/cache/akmods -name "*.rpm" ! -name "*src.rpm" | xargs -r dnf5 install -y


# ASUS G733ZM HDA audio firmware — sits in /usr/lib/firmware unused on other hardware.
# The modprobe config that activates it is written at runtime via `rakuos setup-g733zm-audio`.
# https://github.com/Hyperchaotic/G733ZM-audio-fix
echo "Installing ASUS G733ZM audio firmware..."
curl -fsSL \
    "https://raw.githubusercontent.com/Hyperchaotic/G733ZM-audio-fix/main/hda-jack-retask.fw" \
    -o /usr/lib/firmware/hda-jack-retask.fw

# Sign all DKMS extra modules with MOK key (skipped silently if key not present)
MOK_KEY="/run/secrets/mok_key"
MOK_CERT="/usr/share/rakuos/sb_pubkey.der"
SIGN_FILE="/usr/src/kernels/${QUALIFIED_KERNEL}/scripts/sign-file"
if [[ -f "$MOK_KEY" ]] && [[ -f "$SIGN_FILE" ]]; then
    echo "Signing all extra kernel modules..."
    while IFS= read -r ko; do
        case "$ko" in
            *.ko.xz)
                bare="${ko%.xz}"
                xz -dk "$ko"
                "$SIGN_FILE" sha256 "$MOK_KEY" "$MOK_CERT" "$bare"
                xz -f "$bare"
                ;;
            *.ko.zst)
                bare="${ko%.zst}"
                zstd -dq "$ko" -o "$bare"
                "$SIGN_FILE" sha256 "$MOK_KEY" "$MOK_CERT" "$bare"
                zstd -qf "$bare" -o "$ko"
                rm -f "$bare"
                ;;
            *.ko)
                "$SIGN_FILE" sha256 "$MOK_KEY" "$MOK_CERT" "$ko"
                ;;
        esac
        echo "  Signed: $(basename "$ko")"
    done < <(find "/usr/lib/modules/${QUALIFIED_KERNEL}/extra" \
        \( -name "*.ko" -o -name "*.ko.xz" -o -name "*.ko.zst" \) 2>/dev/null)
    echo "Module signing complete."
else
    echo "MOK key or sign-file not available — skipping module signing."
fi

# Sign the kernel vmlinuz with MOK key
VMLINUZ="/usr/lib/modules/${QUALIFIED_KERNEL}/vmlinuz"
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
--add ostree --add fido2 --add rakuos-overlay -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img

rm -rf /var/lib/dkms /var/cache/akmods /usr/src/broadcom-wl-* /usr/src/hid-xpadneo-* /usr/src/xpad-noone-* /usr/src/zenergy-* /usr/src/xone-* /usr/src/v4l2loopback-* /usr/src/VERSION
