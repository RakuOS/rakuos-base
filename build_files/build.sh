#!/bin/bash

set -ouex pipefail

## Enable repos
dnf5 -y install dnf5-plugins
dnf5 -y copr enable bieszczaders/kernel-cachyos-addons
dnf5 -y copr enable atim/xpadneo


# install packages
dnf5 -y install ananicy-cpp \
  cachyos-ananicy-rules \
  scx-scheds \
  scx-tools \
  mangohud \
  mangohud.i686 \
  gamemode \
  gamemode.i686 \
  dkms \
  flatpak \
  rsync \
  podman \
  distrobox \
  xpadneo \
  nodejs \
  nodejs-npm \
  qemu-kvm \
  libvirt-daemon \
  libvirt-daemon-driver-qemu \
  libvirt-client \
  bridge-utils \
  virt-install 

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

echo "RakuOS: Installing default Flatpaks..."

# Exit cleanly if no list exists
if [[ ! -f "$FLATPAK_LIST" ]]; then
    echo "No flatpaks.list found, skipping."
    exit 0
fi

# Ensure Flathub exists
if ! flatpak remote-list | grep -q '^flathub'; then
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
fi

# Read flatpak IDs from file
while read -r app; do
    [[ -z "$app" || "$app" =~ ^# ]] && continue
    flatpak install -y --noninteractive --system flathub "$app"
done < "$FLATPAK_LIST"

echo "Flatpak installation complete."
# Disable service so it never runs again
systemctl disable rakuos-firstboot-flatpaks.service
EOF

chmod +x /usr/libexec/rakuos/firstboot-flatpaks.sh

# Create systemd service
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

# Disable fedora flatpak repos
systemctl disable flatpak-add-fedora-repos.service

#enable enable services
systemctl enable rakuos-firstboot-flatpaks.service
systemctl enable libvirtd