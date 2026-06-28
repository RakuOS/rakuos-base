#!/bin/bash

set -ouex pipefail

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)
XPADNEO_VERSION="0.10.2"
V4L2LOOPBACK_VERSION="0.15.3"

dnf5 install -y \
    dkms \
    akmods \
    kernel-cachyos-devel-matched \
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
    brcmfmac-firmware

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT


BROADCOM_WL_VERSION="6.30.223.271"
BROADCOM_WL_TARBALL="hybrid-v35_64-nodebug-pcoem-${BROADCOM_WL_VERSION//./_}.tar.gz"
ARCH_BROADCOM_RAW="https://gitlab.archlinux.org/archlinux/packaging/packages/broadcom-wl-dkms/-/raw/main"

echo "Building broadcom-wl ${BROADCOM_WL_VERSION} from upstream source..."
mkdir -p "$tmpdir/broadcom-wl"
curl -fsSL "https://docs.broadcom.com/docs-and-downloads/docs/linux_sta/${BROADCOM_WL_TARBALL}" \
    | tar -xz -C "$tmpdir/broadcom-wl"

pushd "$tmpdir/broadcom-wl"
# Apply all compatibility patches from the Arch Linux packaging repo
for patch in \
    001-null-pointer-fix.patch \
    002-rdtscl.patch \
    003-linux407.patch \
    004-linux408.patch \
    005-debian-fix-kernel-warnings.patch \
    006-linux411.patch \
    007-linux412.patch \
    008-linux415.patch \
    009-fix_mac_profile_discrepancy.patch \
    010-linux506.patch \
    011-linux509.patch \
    012-linux517.patch \
    013-linux518.patch \
    014-linux414.patch \
    015-linux600.patch \
    016-linux601.patch \
    017-linux612.patch \
    018-linux613.patch \
    019-linux614.patch \
    020-linux615.patch \
    021-linux617.patch \
    022-linux701.patch; do
    curl -fsSL "${ARCH_BROADCOM_RAW}/${patch}" -o "$tmpdir/${patch}"
    patch -Np1 --no-backup-if-mismatch < "$tmpdir/${patch}"
done
# Use wlan prefix for interface naming
sed -i -e '/BRCM_WLAN_IFNAME/s/eth/wlan/' src/wl/sys/wl_linux.c
# Point ldflags at installed lib location and enable GE_49 for modern kernels
sed -i \
    -e "/ldflags-y/s|\$(src)/lib|/usr/lib/broadcom-wl-dkms|" \
    -e "/GE_49 :=/s|:= .*|:= 1|" \
    Makefile
# Generate dkms.conf
curl -fsSL "${ARCH_BROADCOM_RAW}/dkms.conf.in" \
    | sed "s/@PACKAGE_VERSION@/${BROADCOM_WL_VERSION}/" \
    > dkms.conf
# Install source tree
_bwl_src="/usr/src/broadcom-wl-${BROADCOM_WL_VERSION}"
rm -rf "$_bwl_src"
install -Dm644 Makefile "$_bwl_src/Makefile"
install -Dm644 dkms.conf "$_bwl_src/dkms.conf"
cp -a src "$_bwl_src/"
# Install shared object and modprobe blacklist
install -Dm644 lib/wlc_hybrid.o_shipped \
    "/usr/lib/broadcom-wl-dkms/wlc_hybrid.o_shipped"
curl -fsSL "${ARCH_BROADCOM_RAW}/broadcom-wl-dkms.conf" \
    -o /usr/lib/modprobe.d/broadcom-wl-dkms.conf
dkms install -m broadcom-wl -v "${BROADCOM_WL_VERSION}" -k "${QUALIFIED_KERNEL}" --force || {
    echo "DKMS build failed for broadcom-wl ${BROADCOM_WL_VERSION} — make.log:"
    cat "/var/lib/dkms/broadcom-wl/${BROADCOM_WL_VERSION}/build/make.log" 2>/dev/null || true
    exit 1
}
popd

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

echo "Building v4l2loopback ${V4L2LOOPBACK_VERSION} from upstream source..."
git clone --depth 1 --branch "v${V4L2LOOPBACK_VERSION}" \
    https://github.com/v4l2loopback/v4l2loopback.git "$tmpdir/v4l2loopback"

pushd "$tmpdir/v4l2loopback"
echo "Installing v4l2loopback ${V4L2LOOPBACK_VERSION} DKMS source tree..."
rm -rf /usr/src/v4l2loopback-"${V4L2LOOPBACK_VERSION}"
cp -a . /usr/src/v4l2loopback-"${V4L2LOOPBACK_VERSION}"
sed -i "s/#MODULE_VERSION#/${V4L2LOOPBACK_VERSION}/g" \
    /usr/src/v4l2loopback-"${V4L2LOOPBACK_VERSION}"/dkms.conf
# Remove BUILD_EXCLUSIVE_KERNEL — it only allows 5.x/6.x and blocks kernel 7.x+
sed -i '/^BUILD_EXCLUSIVE_KERNEL/d' \
    /usr/src/v4l2loopback-"${V4L2LOOPBACK_VERSION}"/dkms.conf
dkms install -m v4l2loopback -v "${V4L2LOOPBACK_VERSION}" -k "${QUALIFIED_KERNEL}" --force || {
    echo "DKMS build failed for v4l2loopback ${V4L2LOOPBACK_VERSION} — make.log:"
    cat "/var/lib/dkms/v4l2loopback/${V4L2LOOPBACK_VERSION}/build/make.log" 2>/dev/null || true
    exit 1
}
popd

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
--add ostree --add fido2 -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img

dnf5 remove -y --no-autoremove \
    dkms \
    akmods \
    kernel-cachyos-devel-matched \
    gcc \
    make \
    cabextract \
    bluez || true
rm -rf /var/lib/dkms /var/cache/akmods /usr/src/broadcom-wl-* /usr/src/hid-xpadneo-* /usr/src/xpad-noone-* /usr/src/zenergy-* /usr/src/xone-* /usr/src/v4l2loopback-* /usr/src/VERSION
