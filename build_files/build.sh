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
  bridge-utils \
  virt-install \
  fuse \
  squashfuse \
  glibc-langpack-en

cp -r /ctx/system_files /

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
