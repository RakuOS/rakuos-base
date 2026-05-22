#!/bin/bash

set -ouex pipefail

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)
XPADNEO_VERSION="0.10.2"

dnf5 install -y \
    dkms \
    kernel-cachyos-devel-matched \
    gcc \
    make \
    cabextract \
    git \
    bluez \
    cabextract \
    curl \
    sbsigntools

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

echo "Building xpadneo ${XPADNEO_VERSION} from upstream source..."
git clone --depth 1 --branch "v${XPADNEO_VERSION}" \
    https://github.com/atar-axis/xpadneo.git "$tmpdir/xpadneo"

pushd "$tmpdir/xpadneo"
# Install support files and DKMS source tree manually so we avoid runtime-only
# steps like `udevadm control --reload` during container builds.
echo "Installing xpadneo support files and DKMS source tree..."
mkdir -p /usr/lib/modprobe.d /usr/lib/udev/rules.d /usr/share/doc/xpadneo
rm -rf /usr/src/hid-xpadneo-"${XPADNEO_VERSION}"
cp -a hid-xpadneo /usr/src/hid-xpadneo-"${XPADNEO_VERSION}"
printf '%s\n' "${XPADNEO_VERSION}" > /usr/src/VERSION
make -C /usr/src/hid-xpadneo-"${XPADNEO_VERSION}" dkms.conf VERSION="${XPADNEO_VERSION}"
install -D -m 0644 hid-xpadneo/etc-modprobe.d/xpadneo.conf /usr/lib/modprobe.d/xpadneo.conf
install -D -m 0644 hid-xpadneo/etc-udev-rules.d/60-xpadneo.rules /usr/lib/udev/rules.d/60-xpadneo.rules
install -D -m 0644 hid-xpadneo/etc-udev-rules.d/70-xpadneo-disable-hidraw.rules /usr/lib/udev/rules.d/70-xpadneo-disable-hidraw.rules
cp -a docs/. /usr/share/doc/xpadneo/
cp -a NEWS.md /usr/share/doc/xpadneo/NEWS.md
dkms install -m hid-xpadneo -v "${XPADNEO_VERSION}" -k "${QUALIFIED_KERNEL}" --force || {
    echo "DKMS build failed for hid-xpadneo ${XPADNEO_VERSION} — make.log:"
    cat "/var/lib/dkms/hid-xpadneo/${XPADNEO_VERSION}/build/make.log" 2>/dev/null || true
    exit 1
}
popd

echo "Building xpad-noone from upstream source..."
git clone --depth 1 https://github.com/medusalix/xpad-noone.git "$tmpdir/xpad-noone"

pushd "$tmpdir/xpad-noone"
XPAD_NOONE_VERSION="1.0"
echo "Installing xpad-noone ${XPAD_NOONE_VERSION} DKMS source tree..."
rm -rf /usr/src/xpad-noone-"${XPAD_NOONE_VERSION}"
cp -a . /usr/src/xpad-noone-"${XPAD_NOONE_VERSION}"
sed -i \
    -e 's/ida_simple_get(&xpad_pad_seq, 0, 0, GFP_KERNEL)/ida_alloc(\&xpad_pad_seq, GFP_KERNEL)/g' \
    -e 's/ida_simple_remove(&xpad_pad_seq, xpad->pad_nr)/ida_free(\&xpad_pad_seq, xpad->pad_nr)/g' \
    /usr/src/xpad-noone-"${XPAD_NOONE_VERSION}"/xpad.c
dkms install -m xpad-noone -v "${XPAD_NOONE_VERSION}" -k "${QUALIFIED_KERNEL}" --force || {
    echo "DKMS build failed for xpad-noone ${XPAD_NOONE_VERSION} — make.log:"
    cat "/var/lib/dkms/xpad-noone/${XPAD_NOONE_VERSION}/build/make.log" 2>/dev/null || true
    exit 1
}
popd

echo "Building zenergy from upstream source..."
git clone --depth 1 https://github.com/boukehaarsma23/zenergy.git "$tmpdir/zenergy"

pushd "$tmpdir/zenergy"
ZENERGY_VERSION="1.0"
echo "Installing zenergy ${ZENERGY_VERSION} DKMS source tree..."
rm -rf /usr/src/zenergy-"${ZENERGY_VERSION}"
cp -a . /usr/src/zenergy-"${ZENERGY_VERSION}"
dkms install -m zenergy -v "${ZENERGY_VERSION}" -k "${QUALIFIED_KERNEL}" --force || {
    echo "DKMS build failed for zenergy ${ZENERGY_VERSION} — make.log:"
    cat "/var/lib/dkms/zenergy/${ZENERGY_VERSION}/build/make.log" 2>/dev/null || true
    exit 1
}
popd

echo "Building xone from upstream main branch..."
git clone --depth 1 https://github.com/medusalix/xone.git "$tmpdir/xone"

pushd "$tmpdir/xone"
XONE_VERSION="0.0.3.git$(git rev-parse --short HEAD)"
echo "Installing xone ${XONE_VERSION} support files, firmware, and DKMS source tree..."
rm -rf /usr/src/xone-"${XONE_VERSION}"
cp -a . /usr/src/xone-"${XONE_VERSION}"
find /usr/src/xone-"${XONE_VERSION}" -type f \( -name dkms.conf -o -name '*.c' \) \
    -exec sed -i "s/#VERSION#/${XONE_VERSION}/g" {} +
install -D -m 0644 install/modprobe.conf /usr/lib/modprobe.d/xone-blacklist.conf
install -D -m 0755 install/firmware.sh /usr/bin/xone-get-firmware.sh
dkms install -m xone -v "${XONE_VERSION}" -k "${QUALIFIED_KERNEL}" --force || {
    echo "DKMS build failed for xone ${XONE_VERSION} — make.log:"
    cat "/var/lib/dkms/xone/${XONE_VERSION}/build/make.log" 2>/dev/null || true
    exit 1
}
(
    cd /tmp
    xone-get-firmware.sh --skip-disclaimer
)
popd

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
--add ostree --add fido2 -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img

dnf5 remove -y --no-autoremove \
    dkms \
    kernel-cachyos-devel-matched \
    gcc \
    make \
    cabextract \
    bluez || true
rm -rf /var/lib/dkms /usr/src/hid-xpadneo-* /usr/src/xpad-noone-* /usr/src/zenergy-* /usr/src/xone-* /usr/src/VERSION
