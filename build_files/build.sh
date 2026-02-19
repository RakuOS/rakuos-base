#!/bin/bash

set -ouex pipefail
FEDORA_VERSION="${FEDORA_VERSION:-43}"
## Enable repos
dnf5 -y install dnf5-plugins
dnf5 -y copr enable bieszczaders/kernel-cachyos-addons fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable sentry/xpadneo fedora-${FEDORA_VERSION}-x86_64

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
  libxcrypt-compat \
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
  libvirt-daemon-config-network \
  libvirt-daemon-driver-network \
  libvirt-daemon-driver-storage-core \
  libvirt-daemon-driver-storage-dir \
  dnsmasq \
  iptables-nft \
  bridge-utils \
  virt-install \
  fuse \
  squashfuse \
  glibc-langpack-en

# enable flathub
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# Disable services
systemctl disable flatpak-add-fedora-repos.service
systemctl mask akmods-keygen@akmods-keygen.service
systemctl mask systemd-remount-fs.service

#enable enable services
systemctl enable rakuos-firstboot-flatpaks.service
systemctl enable libvirtd

mkdir -p /var/log//var/log/akmods
touch /var/log//var/log/akmods/akmods.log
KVER="$(dnf5 repoquery --installed --qf '%{VERSION}-%{RELEASE}.%{ARCH}' kernel)"
akmods --force --kernels "$KVER"
