#!/bin/bash

set -ouex pipefail
CENTOS_VERSION=$(rpm -E %rhel)
## Enable repos
dnf -y install dnf-plugins
dnf -y copr enable tohur/RakuOS epel-${CENTOS_VERSION}-x86_64
dnf -y copr enable bieszczaders/kernel-cachyos epel-${CENTOS_VERSION}-x86_64
dnf -y copr enable bieszczaders/kernel-cachyos-addons epel-${CENTOS_VERSION}-x86_64

dnf -y install \
https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-${CENTOS_VERSION}.noarch.rpm \
https://mirrors.rpmfusion.org/nonfree/el/rpmfusion-nonfree-release-${CENTOS_VERSION}.noarch.rpm

dnf -y config-manager addrepo --from-repofile=https://negativo17.org/repos/epel-nvidia.repo
rpm --import https://repos.fyralabs.com/terrael${CENTOS_VERSION}/key.asc

dnf -y install --nogpgcheck --repofrompath 'terra,https://repos.fyralabs.com/terrael${CENTOS_VERSION}' terra-release

# Remove hardcoded priority=80 from terra repo files so our config-manager priorities take effect
sed -i '/^priority=/d' /etc/yum.repos.d/terra*.repo

# Download Terra AppStream data for rakuos-software
TERRA_BASE="https://repos.fyralabs.com/appstream"
TERRA_REPOS="terrael${CENTOS_VERSION}"
mkdir -p /usr/share/swcatalog/xml
for REPO in $TERRA_REPOS; do
    BASE_URL="${TERRA_BASE}/${REPO}/latest/appstream"
    # AppStream XML
    curl -fsSL "${BASE_URL}/${REPO}.xml.gz" -o "/usr/share/swcatalog/xml/${REPO}.xml.gz" \
        && echo "Terra AppStream: ${REPO}.xml.gz" || echo "Warning: failed to download AppStream for ${REPO}"
    # Icons — 64x64 and 128x128
    mkdir -p "/usr/share/swcatalog/icons/${REPO}/64x64"
    mkdir -p "/usr/share/swcatalog/icons/${REPO}/128x128"
    curl -fsSL "${BASE_URL}/${REPO}-icons-64x64.tar.gz" \
        | tar -xz -C "/usr/share/swcatalog/icons/${REPO}/64x64" --strip-components=1 2>/dev/null || true
    curl -fsSL "${BASE_URL}/${REPO}-icons-128x128.tar.gz" \
        | tar -xz -C "/usr/share/swcatalog/icons/${REPO}/128x128" --strip-components=1 2>/dev/null || true
done

# VS Code
rpm --import https://packages.microsoft.com/keys/microsoft.asc &&
echo -e "[code]\nname=Visual Studio Code\nbaseurl=https://packages.microsoft.com/yumrepos/vscode\nenabled=1\nautorefresh=1\ntype=rpm-md\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc" | sudo tee /etc/yum.repos.d/vscode.repo > /dev/null
# MS Edge
rpm --import https://packages.microsoft.com/keys/microsoft.asc &&
echo -e "[edge]\nname=Microsoft Edge\nbaseurl=https://packages.microsoft.com/yumrepos/edge\nenabled=1\nautorefresh=1\ntype=rpm-md\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc" | sudo tee /etc/yum.repos.d/edge.repo > /dev/null


#remove fedora kernel and zram config
dnf -y remove --no-autoremove kernel kernel-core kernel-modules kernel-modules-core kernel-modules-extra kernel-tools kernel-tools-libs zram-generator-defaults

# Install cachyos kernel
dnf -y --setopt=tsflags=noscripts install kernel-cachyos kernel-cachyos-devel-matched


# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)

# install packages
dnf -y install ananicy-cpp \
cachyos-ananicy-rules \
cachyos-settings \
cabextract \
bore-sysctl \
scx-scheds \
scx-tools \
pulseaudio-utils \
dkms \
akmods \
kernel-cachyos-devel-${QUALIFIED_KERNEL} \
elfutils-libelf-devel \
openssl-devel \
git \
flatpak \
libxcrypt-compat \
rsync \
podman \
distrobox \
mokutil \
lm_sensors \
sqlite3 \
openssl \
libnotify \
inotify-tools \
podman-compose \
python3-pip \
python3-setuptools \
appstream \
appstream-data \
fwupd \
fuse \
squashfuse \
virtualbox-guest-additions \
v4l-utils \
unzip

## Remove packages
dnf -y remove firefox* nss

# enable flathub
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# Disable services
systemctl disable flatpak-add-fedora-repos.service
systemctl mask akmods-keygen@akmods-keygen.service
systemctl mask systemd-remount-fs.service

# sudo requires drop-in files to be owned by root and not be writable by others
chown root:root /etc/sudoers.d/rakuos-software
chmod 0440 /etc/sudoers.d/rakuos-software

# Clone rakuos-scripts repo
rm -rf /tmp/rakuos-scripts
git clone --depth 1 https://gitlab.com/rakuos/images/rakuos-scripts.git /tmp/rakuos-scripts

# Make target dirs
mkdir -p /usr/bin
mkdir -p /usr/share/rakuos
mkdir -p /usr/libexec/rakuos
mkdir -p /usr/lib/systemd/system
mkdir -p /usr/lib/systemd/user

#copy to /usr/bin
cp -a /tmp/rakuos-scripts/bin/* /usr/bin/
rm -rf /tmp/rakuos-scripts/bin

# Copy systemd units into the proper locations
if [ -d /tmp/rakuos-scripts/systemd/system ]; then
    cp -a /tmp/rakuos-scripts/systemd/system/. /usr/lib/systemd/system/
fi

if [ -d /tmp/rakuos-scripts/systemd/user ]; then
    cp -a /tmp/rakuos-scripts/systemd/user/. /usr/lib/systemd/user/
fi
rm -rf /tmp/rakuos-scripts/systemd

# Copy everything except the systemd folder into /usr/libexec/rakuos
cp -a /tmp/rakuos-scripts/. /usr/libexec/rakuos/

# Copy systemd units into the proper locations
if [ -d /tmp/rakuos-scripts/systemd/system ]; then
    cp -a /tmp/rakuos-scripts/systemd/system/. /usr/lib/systemd/system/
fi

if [ -d /tmp/rakuos-scripts/systemd/user ]; then
    cp -a /tmp/rakuos-scripts/systemd/user/. /usr/lib/systemd/user/
fi

# Clean up
rm -rf /tmp/rakuos-scripts

#enable enable services
systemctl enable \
rakuos-base-protect.service \
rakuos-overlay-mount.service \
rakuos-overlay-sync.service \
rakuos-overlay-services.service \
rakuos-setup.service \
rakuos-flatpak-watcher.service \
rakuos-cache-clean.timer \
fix-dkms.service \
flatpak-cleanup.timer \
flatpak-repair.timer \
rpm-ostree-clean-metadata.timer \
rpm-ostree-clean-deployments.timer \
podman-prune.timer

systemctl enable --global \
rakuos-user.service


# Override CachyOS io scheduler defaults for RakuOS
cat > /usr/lib/udev/rules.d/60-ioschedulers.rules <<'EOF'
# HDD
ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/rotational}=="1", \
    ATTR{queue/scheduler}="bfq"

# SSD
ACTION=="add|change", KERNEL=="sd[a-z]*|mmcblk[0-9]*", ATTR{queue/rotational}=="0", \
    ATTR{queue/scheduler}="adios"

# NVMe SSD
ACTION=="add|change", KERNEL=="nvme[0-9]*", ATTR{queue/rotational}=="0", \
    ATTR{queue/scheduler}="adios"
EOF