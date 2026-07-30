#!/bin/bash

set -ouex pipefail

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-p03-v3)

# Install NVIDIA stack — skip systemd scriptlets that fail in containers
dnf5.real install -y --setopt=tsflags=noscripts \
    --exclude=libnvidia-cfg-580xx \
    --exclude=libnvidia-gpucomp-580xx \
    --exclude=nvidia-driver-580xx-cuda-libs \
    --exclude=libnvidia-ml-580xx \
    dkms-nvidia \
    nvidia-driver \
    nvidia-modprobe \
    nvidia-settings \
    libnvidia-gpucomp \
    nvidia-driver-cuda \
    libnvidia-cfg \
    libnvidia-ml \
    nvidia-persistenced \
    libva-nvidia-driver \
    kernel-p03-v3-devel-matched


# Build DKMS module for the installed kernel
# Force ld.bfd — gold linker fails with NVIDIA's -r + --gc-sections combination
NVIDIA_VER=$(rpm -q --queryformat '%{VERSION}\n' dkms-nvidia)
LD=ld.bfd dkms install -m nvidia -v "${NVIDIA_VER}" -k "${QUALIFIED_KERNEL}" --force || {
    echo "DKMS build failed — make.log:"
    cat /var/lib/dkms/nvidia/${NVIDIA_VER}/build/make.log || true
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

# Sign all DKMS extra modules with MOK key (skipped silently if key not present)
# Must happen BEFORE kernel-p03-devel-matched is removed (sign-file lives there).
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

#dnf5.real remove -y --noautoremove dkms
#systemctl disable --now dkms.service

# Generate module dependencies
depmod "${QUALIFIED_KERNEL}"

# Generate initramfs with nvidia module included
/usr/bin/dracut --no-hostonly --kver "${QUALIFIED_KERNEL}" --reproducible --zstd -v \
    --add ostree --add fido2 -f "/usr/lib/modules/${QUALIFIED_KERNEL}/initramfs.img"

chmod 0600 /usr/lib/modules/"${QUALIFIED_KERNEL}"/initramfs.img

PROTECTED_FILE="/usr/share/rakuos/protected-packages.txt"

cat >> "$PROTECTED_FILE" << 'EOF'

# Base image packages (from rakuos-base/build_files/nvidia.sh)
dkms-nvidia
nvidia-driver
nvidia-modprobe
nvidia-settings
libnvidia-gpucomp
libnvidia-cfg
libnvidia-ml
nvidia-persistenced
libva-nvidia-driver
EOF

echo "protected-packages.txt ready ($(grep -c '^[^#]' "$PROTECTED_FILE") packages)."

echo "Generating base file manifest..."
/usr/libexec/rakuos/generate-base-manifest
