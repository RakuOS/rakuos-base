#!/bin/bash

set -ouex pipefail

## Enable repos
dnf5 -y install dnf5-plugins
dnf5 -y copr enable bieszczaders/kernel-cachyos-addons
dnf5 -y copr enable sentry/xpadneo

# install packages
dnf5 -y install ananicy-cpp \
  cachyos-ananicy-rules \
  scx-scheds \
  scx-tools \
  mangohud \
  mangohud.i686 \
  gamemode \
  gamemode.i686 \
  pulseaudio-utils \
  git \
  flatpak \
  rsync \
  podman \
  distrobox \
  xpadneo \
  kernel \
  kernel-devel-matched \
  kernel-headers \
  mokutil \
  openssl \
  steam-devices \
  openrgb-udev-rules \
  nodejs \
  nodejs-npm \
  qemu-kvm \
  libvirt-daemon \
  libvirt-daemon-driver-qemu \
  libvirt-client \
  bridge-utils \
  virt-install \
  squashfuse \
  glibc-langpack-en

# enable flathub
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

## add scripts and services for RakuOS and folder structures
mkdir -p /usr/share/rakuos
echo "Creating RakuOS first-boot Flatpak installer..."
mkdir -p /usr/libexec/rakuos
# Create the first-boot install script
cat << 'EOF' > /usr/libexec/rakuos/firstboot-flatpaks.sh
#!/usr/bin/env bash
set -euo pipefail

FLATPAK_LIST="/usr/share/rakuos/flatpaks.list"
MARKER_DIR="/var/lib/rakuos"
MARKER_FILE="$MARKER_DIR/default-flatpaks-installed"

echo "RakuOS: Checking default Flatpak installation state..."

# If marker exists, exit silently
if [[ -f "$MARKER_FILE" ]]; then
    echo "Default Flatpaks already installed. Skipping."
    exit 0
fi

echo "RakuOS: Installing default Flatpaks..."

# Exit cleanly if no list exists
if [[ ! -f "$FLATPAK_LIST" ]]; then
    echo "No flatpaks.list found, skipping."
    exit 0
fi

# Ensure marker directory exists
mkdir -p "$MARKER_DIR"

# Ensure Flathub exists
if ! flatpak remote-list | awk '{print $1}' | grep -qx "flathub"; then
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
fi

# Install apps
while read -r app; do
    [[ -z "$app" || "$app" =~ ^# ]] && continue
    flatpak install -y --noninteractive --system flathub "$app"
done < "$FLATPAK_LIST"

# Create marker only after successful install
mkdir -p /var/lib/rakuos
touch "$MARKER_FILE"

echo "RakuOS: Default Flatpak installation complete."
EOF

chmod +x /usr/libexec/rakuos/firstboot-flatpaks.sh

# Create systemd firstboot-flatpaks service
cat << 'EOF' > /etc/systemd/system/rakuos-firstboot-flatpaks.service
[Unit]
Description=RakuOS First Boot Flatpak Installer
After=network-online.target
Wants=network-online.target
ConditionPathExists=/usr/libexec/rakuos/firstboot-flatpaks.sh

[Service]
Type=oneshot
ExecStart=/usr/libexec/rakuos/firstboot-flatpaks.sh
RemainAfterExit=false

[Install]
WantedBy=multi-user.target
EOF

# Disable services
systemctl disable flatpak-add-fedora-repos.service
systemctl disable akmods-keygen@akmods-keygen.service
systemctl mask systemd-remount-fs.service

#enable enable services
systemctl enable rakuos-firstboot-flatpaks.service
systemctl enable libvirtd

mkdir -p /var/log//var/log/akmods
touch /var/log//var/log/akmods/akmods.log
KVER="$(dnf5 repoquery --installed --qf '%{VERSION}-%{RELEASE}.%{ARCH}' kernel)"
akmods --force --kernels "$KVER"
