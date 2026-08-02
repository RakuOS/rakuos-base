#!/bin/bash

set -ouex pipefail
FEDORA_VERSION=$(rpm -E %fedora)

# On the staging branch (RAKUOS_STAGING=1, set via --build-arg from CI)
# install the staging os-release identity instead of the stable one, so
# staging images identify themselves as "RakuOS Staging" (see
# rakuos-release.spec's staging subpackages).
RAKUOS_RELEASE_PKG="rakuos-release"
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    RAKUOS_RELEASE_PKG="rakuos-release-staging"
fi

## DNF5 Speedup
sed -i '/^\[main\]/a max_parallel_downloads=10' /etc/dnf/dnf.conf

## Enable repos
dnf5 -y install dnf5-plugins

dnf5 -y install \
https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA_VERSION}.noarch.rpm \
https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA_VERSION}.noarch.rpm

rpm --import https://repo.rakuos.org/pubkey.gpg

dnf5 -y config-manager addrepo --from-repofile=https://repo.rakuos.org/rakuos.repo

rm /etc/dnf/protected.d/selinux-policy-targeted.conf
dnf5 -y upgrade --best --allowerasing 'rpm*' 'ostree*'
dnf5 -y remove selinux-policy\* selinux-policy-targeted selinux-policy-devel policycoreutils-gui

rpm --import https://repos.fyralabs.com/terra${FEDORA_VERSION}/key.asc
rpm --import https://repos.fyralabs.com/terra${FEDORA_VERSION}-mesa/key.asc
rpm --import https://repos.fyralabs.com/terra${FEDORA_VERSION}-multimedia/key.asc
rpm --import https://repos.fyralabs.com/terra${FEDORA_VERSION}-nvidia/key.asc
dnf5 -y install --nogpgcheck --repofrompath 'terra,https://repos.fyralabs.com/terra$releasever' terra-release
dnf5 -y install --nogpgcheck --repofrompath 'terra-mesa,https://repos.fyralabs.com/terra$releasever' terra-release-mesa
dnf5 -y install --nogpgcheck --repofrompath 'terra-nvidia,https://repos.fyralabs.com/terra$releasever' terra-release-nvidia
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

dnf5 -y install mesa-dri-drivers.i686 mesa-vulkan-drivers.i686 mesa-libEGL.i686 mesa-libGL.i686 libheif libheif.i686 libva.i686

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
btop \
cava \
cbonsai \
cowsay \
distrobox \
dmemcg-booster \
du-dust \
dysk \
fastfetch \
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
libXcursor.i686 \
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
pam-u2f \
pam_yubico \
pamu2fcfg \
pipewire-plugin-libcamera \
podman \
podman-compose \
powerstat \
procs \
pulseaudio-utils \
python3-pip \
python3-setuptools \
os-prober \
rakuos-branding \
rakuos-core \
${RAKUOS_RELEASE_PKG} \
rakuos-settings \
rakuos-wallpapers \
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
tuned \
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
systemctl mask systemd-oomd.service
systemctl mask rpm-ostreed-automatic.timer

# sudo requires the drop-in directory to be root-owned, non-world-writable,
# and executable (0750), and drop-in files to be 0440.
chown root:root /etc/sudoers.d
chmod 0750 /etc/sudoers.d
chown root:root /etc/sudoers.d/rakuos
chmod 0440 /etc/sudoers.d/rakuos
chown root:root /etc/sudoers.d/pwfeedback
chmod 0440 /etc/sudoers.d/pwfeedback

#enable enable services
systemctl enable \
rakuos-base-protect.service \
rakuos-overlay-sync.service \
rakuos-overlay-update.service \
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

## Add custom icons
git clone https://github.com/vinceliuice/WhiteSur-icon-theme.git /tmp/WhiteSur-icon-theme
/tmp/WhiteSur-icon-theme/install.sh -b -a -t all
rm -rf /tmp/WhiteSur-icon-theme
