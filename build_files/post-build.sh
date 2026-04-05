#!/bin/bash

set -ouex pipefail

# Rename real dnf5 and dnf binaries
mv /usr/bin/dnf5 /usr/bin/dnf5.real
mv /usr/bin/dnf /usr/bin/dnf.real

# Mark all base image packages as dependency so PackageKit only manages overlay packages
dnf5.real -y mark dependency $(rpm -qa --qf '%{NAME} ') --skip-unavailable

# Create dnf5 wrapper
cat > /usr/bin/dnf5 << 'WRAPPER'
#!/usr/bin/env bash
COMMAND="${1:-}"
case "$COMMAND" in
    install)
        shift
        exec rakuos install "$@"
        ;;
    update)
        shift
        exec rakuos update "$@"
        ;;
    remove|erase)
        shift
        exec rakuos remove "$@"
        ;;
    *)
        exec /usr/bin/dnf5.real "$@"
        ;;
esac
WRAPPER

# Create dnf wrapper
cat > /usr/bin/dnf << 'WRAPPER'
#!/usr/bin/env bash
exec /usr/bin/dnf5 "$@"
WRAPPER

# Make all wrappers executable
chmod +x /usr/bin/dnf5 /usr/bin/dnf

# Remove ostree boot condition from PackageKit so it starts on RakuOS
#sed -i '/ConditionPathExists=!\/run\/ostree-booted/d' /usr/lib/systemd/system/packagekit.service

echo "RakuOS post-build complete."

# ── Build protected-packages.txt ──────────────────────────────────────────────
# nvidia.sh writes this file first (if it ran) with nvidia packages + deps.
# We append the base build.sh packages either way.
# If nvidia.sh did NOT run this is a normal build — create the file fresh.
PROTECTED_FILE="/usr/share/rakuos/protected-packages.txt"
mkdir -p /usr/share/rakuos

if [[ -f "$PROTECTED_FILE" ]]; then
    echo "nvidia build detected — appending base packages to existing protected-packages.txt..."
else
    echo "Normal build — creating protected-packages.txt with base packages..."
    > "$PROTECTED_FILE"
fi

cat >> "$PROTECTED_FILE" << 'EOF'

# Base image packages (from rakuos-base/build_files/build.sh)
kernel-cachyos
kernel-cachyos-devel-matched
ananicy-cpp
cachyos-ananicy-rules
cachyos-settings
bore-sysctl
scx-scheds
scx-tools
gamemode
gamemode.i686
pulseaudio-utils
dkms
mokutil
elfutils-libelf-devel
openssl-devel
git
flatpak
podman
distrobox
podman-compose
lm_sensors
v4l-utils
virtualbox-guest-additions
mesa-dri-drivers.i686
mesa-va-drivers.i686
mesa-vulkan-drivers.i686
mesa-libEGL.i686
mesa-libGL.i686
libxcrypt-compat
rsync
fuse
squashfuse
sqlite3
openssl
libnotify
inotify-tools
unzip
python3-pip
python3-setuptools
appstream
appstream-data
fwupd
ffmpeg
fedora-logos
dkms-xpadneo
dkms-xpad-noone
dkms-xone
xone-firmware
dkms-zenergy
EOF

echo "protected-packages.txt ready ($(grep -c '^[^#]' "$PROTECTED_FILE") packages)."

echo "Generating base file manifest..."
/usr/libexec/rakuos/generate-base-manifest
