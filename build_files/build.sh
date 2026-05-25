#!/bin/bash

set -ouex pipefail
FEDORA_VERSION=$(rpm -E %fedora)
## Enable repos
dnf5 -y install dnf5-plugins
dnf5 -y copr enable tohur/RakuOS fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable bieszczaders/kernel-cachyos fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable bieszczaders/kernel-cachyos-addons fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable faugus/faugus-launcher fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable ilyaz/LACT fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable wehagy/protonplus fedora-${FEDORA_VERSION}-x86_64
dnf5 -y install \
https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA_VERSION}.noarch.rpm \
https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA_VERSION}.noarch.rpm

rpm --import https://repos.fyralabs.com/terra${FEDORA_VERSION}/key.asc
rpm --import https://repos.fyralabs.com/terra${FEDORA_VERSION}-mesa/key.asc
rpm --import https://repos.fyralabs.com/terra${FEDORA_VERSION}-multimedia/key.asc

dnf5 -y install --nogpgcheck --repofrompath 'terra,https://repos.fyralabs.com/terra$releasever' terra-release
dnf5 -y install --nogpgcheck --repofrompath 'terra-mesa,https://repos.fyralabs.com/terra$releasever' terra-release-mesa
dnf5 -y install --nogpgcheck --repofrompath 'terra-multimedia,https://repos.fyralabs.com/terra$releasever' terra-release-multimedia
# Remove hardcoded priority=80 from terra repo files so our config-manager priorities take effect
sed -i '/^priority=/d' /etc/yum.repos.d/terra*.repo

# Download Terra AppStream data for rakuos-software
TERRA_BASE="https://repos.fyralabs.com/appstream"
TERRA_REPOS="terra${FEDORA_VERSION} terra${FEDORA_VERSION}-mesa terra${FEDORA_VERSION}-extras terra${FEDORA_VERSION}-multimedia"
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

# Enable Chrome repo
sed -i 's@enabled=0@enabled=1@g' /etc/yum.repos.d/google-chrome.repo

# Enable Brave Stable, Beta and Nightly repos & Brave origin Beta and Nightly repos
dnf5 -y config-manager addrepo --from-repofile=https://brave-browser-rpm-release.s3.brave.com/brave-browser.repo
dnf5 -y config-manager addrepo --from-repofile=https://brave-browser-rpm-beta.s3.brave.com/brave-browser-beta.repo
dnf5 -y config-manager addrepo --from-repofile=https://brave-browser-rpm-nightly.s3.brave.com/brave-browser-nightly.repo

# Add the tailscale repository
dnf5 -y config-manager addrepo --from-repofile=https://pkgs.tailscale.com/stable/fedora/tailscale.repo

# Add the Mullvad repository server
dnf5 -y config-manager addrepo --from-repofile=https://repository.mullvad.net/rpm/stable/mullvad.repo

#remove fedora kernel and zram config
dnf5 -y remove --no-autoremove kernel kernel-core kernel-modules kernel-modules-core kernel-modules-extra kernel-tools kernel-tools-libs zram-generator-defaults
rm -rf /boot/* /usr/lib/modules/* /lib/modules/*

# Install cachyos kernel
dnf5 -y --setopt=tsflags=noscripts install kernel-cachyos kernel-cachyos-devel-matched

dnf5 -y swap ffmpeg ffmpeg-free --allowerasing

#dnf5 -y install mesa-dri-drivers.i686 mesa-va-drivers.i686 mesa-vulkan-drivers.i686 mesa-libEGL.i686 mesa-libGL.i686
dnf5 -y install mesa-va-drivers-freeworld.{i686,x86_64} mesa-dri-drivers.i686 mesa-vulkan-drivers.i686 mesa-libEGL.i686 mesa-libGL.i686
dnf5 -y remove mesa-va-drivers-freeworld.{i686,x86_64}
dnf5 -y upgrade --best 'mesa-*'
#dnf5 -y install mesa-va-drivers.{i686,x86_64}

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)

# install packages
dnf5 -y install ananicy-cpp \
appstream \
appstream-data \
aria2 \
bat \
bat-extras \
bibata-cursor-theme \
bore-sysctl \
btop \
cachyos-ananicy-rules \
cachyos-settings \
cava \
cbonsai \
cowsay \
distrobox \
dmemcg-booster \
du-dust \
dysk \
fastfetch \
figlet \
fish \
flatpak \
fresh \
fuse \
fwupd \
fzf \
git \
google-noto-sans-myanmar-fonts \
google-noto-serif-myanmar-fonts \
inotify-tools \
lazygit \
libnotify \
libxcrypt-compat \
lm_sensors \
lolcat \
lsd \
maple-fonts \
openssl \
podman \
podman-compose \
procs \
pulseaudio-utils \
python3-pip \
python3-setuptools \
ripgrep \
rsms-inter-fonts \
rsync \
scx-scheds \
scx-tools \
ShellCheck \
sqlite3 \
squashfuse \
starship \
sudo-rs \
surge \
termflix \
unrar \
unzip \
v4l-utils \
virtualbox-guest-additions \
zellij \
zoxide \
zsh

## Remove packages
dnf5 -y remove firefox* \
nss \
toolbox

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

# Clean up
rm -rf /tmp/rakuos-scripts

#enable enable services
systemctl enable \
rakuos-base-protect.service \
rakuos-overlay-mount.service \
rakuos-overlay-sync.service \
rakuos-overlay-update.service \
rakuos-overlay-services.service \
rakuos-setup.service \
rakuos-flatpak-watcher.service \
rakuos-cache-clean.timer \
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

## Add custom icons
git clone https://github.com/vinceliuice/WhiteSur-icon-theme.git /tmp/WhiteSur-icon-theme
/tmp/WhiteSur-icon-theme/install.sh -b -a -t all
rm -rf /tmp/WhiteSur-icon-theme
