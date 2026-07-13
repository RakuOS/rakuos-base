#!/bin/bash

set -ouex pipefail
FEDORA_VERSION=$(rpm -E %fedora)

## DNF5 Speedup
sed -i '/^\[main\]/a max_parallel_downloads=10' /etc/dnf/dnf.conf

## Enable repos
dnf5 -y install dnf5-plugins

dnf5 -y install \
https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA_VERSION}.noarch.rpm \
https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA_VERSION}.noarch.rpm

rpm --import https://repo.rakuos.org/pubkey.gpg

dnf5 -y config-manager addrepo --from-repofile=https://repo.rakuos.org/rakuos.repo
sed -i '/^\[rakuos-v3\]/,/^\[/ s/^enabled=0/enabled=1/' /etc/yum.repos.d/rakuos.repo

rm /etc/dnf/protected.d/selinux-policy-targeted.conf
dnf5 -y upgrade --best --allowerasing 'rpm*' 'ostree*'
dnf5 -y remove selinux-policy\* selinux-policy-targeted selinux-policy-devel policycoreutils-gui

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

#remove fedora kernel and zram config
dnf5 -y remove --no-autoremove kernel kernel-core kernel-modules kernel-modules-core kernel-modules-extra kernel-tools kernel-tools-libs zram-generator-defaults
rm -rf /boot/* /usr/lib/modules/* /lib/modules/*

# Install cachyos kernel
dnf5 -y --setopt=tsflags=noscripts install kernel-p03 kernel-p03-devel kernel-p03-devel-matched

dnf5 -y install --skip-unavailable intel-vaapi-driver \
libopenjph \
pipewire-libs-extra \
heif-pixbuf-loader


dnf5 -y swap ffmpeg-free ffmpeg --allowerasing
dnf5 -y install libfdk-aac
dnf5 -y swap libavcodec-free libavcodec --allowerasing
dnf5 -y swap libavformat-free libavformat --allowerasing
dnf5 -y swap libavutil-free libavutil --allowerasing
dnf5 -y swap libavfilter-free libavfilter --allowerasing
dnf5 -y swap libswscale-free libswscale --allowerasing

dnf5 -y install mesa-dri-drivers.i686 mesa-vulkan-drivers.i686 mesa-libEGL.i686 mesa-libGL.i686 libheif

dnf5 -y upgrade --best 'mesa-*' 'pipewire*'

dnf5 -y upgrade --best 'pipewire*'

dnf5 -y install pipewire-libs.i686 pipewire-alsa.i686

dnf5 -y upgrade --best --allowerasing 'systemd*'

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-p03)

# install packages
dnf5 -y install @fonts @hardware-support \
7zip \
alsa-firmware \
ananicy-cpp \
appstream \
appstream-data \
apr \
apr-util \
aria2 \
bat \
bat-extras \
bibata-cursor-theme \
bind \
bind-utils \
bootc \
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
fedora-logos \
fedora-repos-archive \
ffmpegthumbnailer \
figlet \
fish \
flatpak \
flatpak-spawn \
fresh \
fuse \
fwupd \
fzf \
git \
google-noto-sans-balinese-fonts \
google-noto-sans-cjk-fonts \
google-noto-sans-javanese-fonts \
google-noto-sans-myanmar-fonts \
google-noto-sans-sundanese-fonts \
google-noto-serif-myanmar-fonts \
grub2-tools-extra \
gvfs-fuse \
gvfs-mtp \
gvfs-nfs \
gvfs-smb \
htop \
inotify-tools \
just \
lazygit \
libcamera \
libcamera-gstreamer \
libcamera-ipa \
libcamera-tools \
libimobiledevice-utils \
libnotify \
libratbag-ratbagd \
libxcrypt-compat \
lm_sensors \
lolcat \
lshw \
lsd \
maple-fonts \
net-tools \
nvme-cli \
nvtop \
opendoas \
openrgb-udev-rules \
openssh-askpass \
openssl \
oversteer-udev \
pam_apparmor \
pam-u2f \
pam_yubico \
pamu2fcfg \
pipewire-plugin-libcamera \
podman \
podman-compose \
polly \
powerstat \
procs \
pulseaudio-utils \
python3-apparmor \
python3-LibAppArmor \
python3-pip \
python3-setuptools \
os-prober \
ripgrep \
rsms-inter-fonts \
rsync \
ShellCheck \
solaar-udev \
sqlite3 \
squashfs-tools \
squashfuse \
starship \
sudo-rs \
surge \
symlinks \
tcpdump \
tealdeer \
termflix \
tmux \
traceroute \
ublue-os-udev-rules \
udisks2 \
unrar \
unzip \
usbmuxd \
uutils-coreutils \
v4l-utils \
vim \
virtualbox-guest-additions \
wireguard-tools \
wl-clipboard \
xhost \
xorg-x11-xauth \
yubikey-manager \
zellij \
zoxide \
zsh \
zstd

## Remove packages
dnf5 -y remove firefox* \
toolbox \
fedora-flathub-remote \
fedora-third-party \
fedora-workstation-repositories

dnf5 -y swap ocl-icd OpenCL-ICD-Loader --allowerasing

# use CoreOS' generator for emergency/rescue boot
# see detail: https://github.com/ublue-os/main/issues/653
CSFG="/usr/lib/systemd/system-generators/coreos-sulogin-force-generator"
curl -sSLo ${CSFG} https://raw.githubusercontent.com/coreos/fedora-coreos-config/refs/heads/stable/overlay.d/05core/usr/lib/systemd/system-generators/coreos-sulogin-force-generator
chmod +x ${CSFG}

# Clean up some .desktops for command line utils
rm /usr/share/applications/btop.desktop
rm /usr/share/applications/io.github.sinelaw.fresh.desktop
rm /usr/share/applications/htop.desktop
rm /usr/share/applications/nvtop.desktop

# enable flathub
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# Disable services
systemctl disable flatpak-add-fedora-repos.service
systemctl mask akmods-keygen@akmods-keygen.service
systemctl mask systemd-remount-fs.service
systemctl mask auditd.service
systemctl mask systemd-oomd.service
systemctl mask rpm-ostreed-automatic.timer

# sudo requires the drop-in directory to be root-owned, non-world-writable,
# and executable (0750), and drop-in files to be 0440.
chown root:root /etc/sudoers.d
chmod 0750 /etc/sudoers.d
chown root:root /etc/sudoers.d/rakuos-software
chmod 0440 /etc/sudoers.d/rakuos-software
chown root:root /etc/sudoers.d/pwfeedback
chmod 0440 /etc/sudoers.d/pwfeedback

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
dmemcg-booster.service \
nix.mount \
flatpak-cleanup.timer \
flatpak-repair.timer \
rpm-ostree-clean-metadata.timer \
rpm-ostree-clean-deployments.timer \
podman-prune.timer

systemctl enable --global \
rakuos-user.service

# Enable os-prober so grub detects other OSes (e.g. Windows) in dual-boot setups
echo 'GRUB_DISABLE_OS_PROBER=false' >> /etc/default/grub

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
