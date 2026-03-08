#!/bin/bash

set -ouex pipefail
FEDORA_VERSION="${FEDORA_VERSION:-43}"
## Enable repos
dnf5 -y install dnf5-plugins
dnf5 -y copr enable bieszczaders/kernel-cachyos fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable bieszczaders/kernel-cachyos-addons fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable sentry/xpadneo fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable atim/heroic-games-launcher fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable ilyaz/LACT fedora-${FEDORA_VERSION}-x86_64
dnf5 -y install \
    https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA_VERSION}.noarch.rpm \
    https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA_VERSION}.noarch.rpm
    
#remove fedora kernel and zram config
dnf5 -y remove --no-autoremove kernel kernel-core kernel-modules kernel-modules-core kernel-modules-extra kernel-tools kernel-tools-libs zram-generator-defaults

# Install cachyos kernel
dnf5 -y --setopt=tsflags=noscripts install kernel-cachyos kernel-cachyos-devel-matched

# install packages
dnf5 -y install ananicy-cpp \
  cachyos-ananicy-rules \
  cachyos-settings \
  bore-sysctl \
  scx-scheds \
  scx-tools \
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
  mokutil \
  openssl \
  freerdp \
  libnotify \
  inotify-tools \
  podman-compose \
  webkit2gtk4.1 \
  python3-flask \
  python3-pip \
  appstream \
  appstream-data \
  fwupd \
  python3-pyqt6 \
  python3-dbus \
  python3-gobject \
  steam-devices \
  openrgb-udev-rules \
  nodejs \
  nodejs-npm \
  fuse \
  squashfuse \
  virtualbox-guest-additions \
  v4l-utils \
  glibc-langpack-en

## Remove packages
dnf5 -y remove firefox

# enable flathub
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

pip3 install pywebview --break-system-packages

# Disable services
systemctl disable flatpak-add-fedora-repos.service
systemctl mask akmods-keygen@akmods-keygen.service
systemctl mask systemd-remount-fs.service

#enable enable services
systemctl enable \
  rakuos-updater.timer \
  rakuos-overlay-mount.service \
  rakuos-overlay-sync.service \
  rakuos-flatpaks.service \
  rakuos-flatpak-watcher.service \
  flatpak-cleanup.timer \
  flatpak-repair.timer \
  rpm-ostree-clean-metadata.timer \
  rpm-ostree-clean-deployments.timer \
  podman-prune.timer

systemctl enable --global \
  rakuos-user.service

mkdir -p /var/log//var/log/akmods
touch /var/log//var/log/akmods/akmods.log
KVER="$(dnf5 repoquery --installed --qf '%{VERSION}-%{RELEASE}.%{ARCH}' kernel-cachyos)"
akmods --force --kernels "$KVER"

#Build initramfs
# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)

# Generate module dependencies
depmod "$QUALIFIED_KERNEL"

# Generate initramfs for that kernel
/usr/bin/dracut --no-hostonly --kver "$QUALIFIED_KERNEL" --reproducible --zstd -v \
    --add ostree --add fido2 -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img