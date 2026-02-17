#!/bin/bash

set -ouex pipefail

## Enable repos
dnf5 -y install dnf5-plugins
dnf5 -y copr enable atim/xpadneo


# install packages
dnf5 -y install scx-scheds \
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

# Disable fedora flatpak repos
systemctl disable flatpak-add-fedora-repos.service

#enable libvirt
systemctl enable libvirtd