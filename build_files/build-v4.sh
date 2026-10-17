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

# Same switch for the kernel: on staging, track kernel-staging's -staging
# tagged builds (kernel-p03-v4-staging) instead of the stable kernel repo's
# kernel-p03-v4, so staging images pick up in-flight kernel changes.
KERNEL_PKG="kernel-rakuos-v4"
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    KERNEL_PKG="kernel-rakuos-v4-staging"
fi

## Enable the rakuos repo first — rum itself lives in it, so this has to
## happen before anything else, using the base image's real dnf5 since rum
## doesn't exist yet.
dnf5 -y install dnf5-plugins
rpm --import https://repo.rakuos.org/pubkey.gpg
dnf5 -y config-manager addrepo --from-repofile=https://repo.rakuos.org/rakuos.repo
sed -i '/^\[rakuos-v3\]/,/^\[/ s/^enabled=0/enabled=1/' /etc/yum.repos.d/rakuos.repo
sed -i '/^\[rakuos-v4\]/,/^\[/ s/^enabled=0/enabled=1/' /etc/yum.repos.d/rakuos.repo

## Install rum + the dnf/dnf5 shims as the very first packages — from here
## on, every install/remove/upgrade/swap in this script goes through rum
## directly instead of dnf5 (rum-dnf-shim also Obsoletes/Conflicts the real
## dnf5/dnf packages, so they're gone from the image after this point
## regardless).
dnf5 -y install rakuos-rum rum-dnf-shim

## Move every repo file into rum's shipped dir, /usr/share/rum/repos.d, so
## the image's repos all live there and /etc stays free for users' own repos
## and changes. Packages that own repo files (fedora-repos etc., installed by
## dnf into /usr/share/dnf5/repos.d or /etc/yum.repos.d) are reinstalled
## with rum, which installs repo files there itself, so the rpmdb stays
## right. Anything left, like the rakuos.repo dnf5 added above, is moved.
REPO_OWNERS=$(rpm -qf --qf '%{NAME}\n' /usr/share/dnf5/repos.d/*.repo /etc/yum.repos.d/*.repo 2>/dev/null | grep -v 'not owned' | sort -u || true)
if [ -n "$REPO_OWNERS" ]; then
    rum reinstall -y $REPO_OWNERS || echo "WARNING: couldn't reinstall $REPO_OWNERS; moving their repo files instead"
fi
mkdir -p /usr/share/rum/repos.d
for repo in /usr/share/dnf5/repos.d/*.repo /etc/yum.repos.d/*.repo; do
    [ -e "$repo" ] || continue
    mv -f "$repo" /usr/share/rum/repos.d/
done

# Repo files that came with packages. rum installs a package's repo files
# into /usr/share/rum/repos.d (relocated from /etc/yum.repos.d and
# /usr/share/dnf5/repos.d); ones dnf installed are still in those dirs. Lists
# the files matching a pattern across all three, so the edits below change the
# shipped defaults in place and /etc/rum.repos.d stays empty for users' own
# changes.
shipped_repo_files() {
    local dir
    for dir in /usr/share/rum/repos.d /etc/yum.repos.d /usr/share/dnf5/repos.d; do
        ls $dir/$1 2>/dev/null || true
    done
}

## rpmfusion release RPMs
rum install -y https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA_VERSION}.noarch.rpm \
              https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA_VERSION}.noarch.rpm

# Keep RPM Fusion's NVIDIA driver stack out of every RPM Fusion repo,
# updates included: the NVIDIA driver comes from the rakuos repo, and RPM
# Fusion ships packages under the same names (nvidia-settings,
# nvidia-modprobe, nvidia-persistenced). These patterns don't match
# libva-nvidia-driver or the egl-* libraries, so those still resolve.
RPMFUSION_REPO_FILES=$(shipped_repo_files 'rpmfusion-*.repo')
[ -n "$RPMFUSION_REPO_FILES" ] || { echo "ERROR: no rpmfusion repo files found"; exit 1; }
sed -i '/^\[.*\]/a excludepkgs=akmod-nvidia* kmod-nvidia* xorg-x11-drv-nvidia* nvidia-* steam' $RPMFUSION_REPO_FILES

rm /etc/dnf/protected.d/selinux-policy-targeted.conf
rum remove -y 'selinux-policy*' 'policycoreutils-gui'
rum upgrade -y --best --allowerasing 'rpm*' 'ostree*'

rpm --import https://repos.fyralabs.com/terra${FEDORA_VERSION}/key.asc

rum install -y --no-gpgchecks --repofrompath "terra,https://repos.fyralabs.com/terra${FEDORA_VERSION}" terra-release

# Edit Terra's shipped repo files in place (see shipped_repo_files above).
TERRA_REPO_FILES=$(shipped_repo_files 'terra*.repo')
[ -n "$TERRA_REPO_FILES" ] || { echo "ERROR: no terra repo files found"; exit 1; }

# Remove hardcoded priority=80 from terra repo files so our config-manager priorities take effect
sed -i '/^priority=/d' $TERRA_REPO_FILES
sed -i '/^\[terra\]/a excludepkgs=apparmor apparmor-devel apparmor-libs apparmor-parser apparmor-profiles apparmor-utils mod_apparmor pam_apparmor python3-apparmor python3-LibAppArmor scx-scheds scx-scheds-git scx-tools scx-tools-git' $(shipped_repo_files terra.repo)


# Download Terra AppStream data for rakuos-software
TERRA_BASE="https://repos.fyralabs.com/appstream"
TERRA_REPOS="terra${FEDORA_VERSION}"
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
rum remove -y --no-autoremove kernel kernel-core kernel-modules kernel-modules-core kernel-modules-extra kernel-tools kernel-tools-libs zram-generator-defaults
rm -rf /boot/* /usr/lib/modules/* /lib/modules/*

# Install P03 kernel
rum install -y --setopt=tsflags=noscripts ${KERNEL_PKG} ${KERNEL_PKG}-devel ${KERNEL_PKG}-devel-matched

rum install -y --skip-unavailable libva-intel-media-driver \
libopenjph \
pipewire-libs-extra \
heif-pixbuf-loader

rum swap -y ffmpeg-free ffmpeg --allowerasing
rum swap -y fdk-aac-free libfdk-aac --allowerasing
rum swap -y libavcodec-free libavcodec --allowerasing
rum swap -y libavformat-free libavformat --allowerasing
rum swap -y libavutil-free libavutil --allowerasing
rum swap -y libavfilter-free libavfilter --allowerasing
rum swap -y libswscale-free libswscale --allowerasing
rum swap -y libavdevice-free libavdevice --allowerasing

rum install -y gstreamer1-plugin-dav1d \
  gstreamer1-plugin-libav \
  gstreamer1-plugins-bad \
  gstreamer1-plugins-good \
  gstreamer1-plugins-ugly

rum install -y mesa-dri-drivers mesa-vulkan-drivers mesa-libEGL mesa-libGL mesa-dri-drivers.i686 mesa-vulkan-drivers.i686 mesa-libEGL.i686 mesa-libGL.i686 libheif libva

rum upgrade -y --best --allowerasing 'mesa-*' 'pipewire*'

rum install -y pipewire-libs.i686 pipewire-alsa.i686

rum upgrade -y --best --allowerasing 'systemd*'

# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' ${KERNEL_PKG})

# Install cpak (https://cpak.it/docs/install) — download the latest release's
# binaries and verify against the published SHA256SUMS before installing;
# cpak looks for cpak-storaged beside cpak itself, so both go into /usr/bin.
CPAK_VERSION=$(curl -fsSL https://api.github.com/repos/Containerpak/cpak/releases/latest | grep -oP '"tag_name":\s*"\K[^"]+')
CPAK_BASE="https://github.com/Containerpak/cpak/releases/download/${CPAK_VERSION}"
curl -fsSL -o /tmp/cpak-linux-amd64 "${CPAK_BASE}/cpak-linux-amd64"
curl -fsSL -o /tmp/cpak-storaged-linux-amd64 "${CPAK_BASE}/cpak-storaged-linux-amd64"
curl -fsSL -o /tmp/cpak-SHA256SUMS "${CPAK_BASE}/SHA256SUMS"
(cd /tmp && sha256sum -c --ignore-missing cpak-SHA256SUMS)
install -Dm755 /tmp/cpak-linux-amd64 /usr/bin/cpak
install -Dm755 /tmp/cpak-storaged-linux-amd64 /usr/bin/cpak-storaged
rm -f /tmp/cpak-linux-amd64 /tmp/cpak-storaged-linux-amd64 /tmp/cpak-SHA256SUMS

# install packages
rum install -y --skip-unavailable @fonts @hardware-support \
7zip \
alsa-firmware \
alsa-sof-firmware \
alsa-ucm \
alsa-utils \
amd-gpu-firmware \
amd-ucode-firmware \
ananicy-cpp \
apparmor-libs \
apparmor-parser \
apparmor-profiles \
apparmor-utils \
appstream \
appstream-data \
apr \
apr-util \
aria2 \
at-spi2-atk \
at-spi2-core \
atheros-firmware \
attr \
audit \
audit-rules \
b43-fwcutter \
b43-openfwwf \
bash-color-prompt \
bash-completion \
bat \
bat-extras \
bc \
bpftool \
bibata-cursor-theme \
bind \
bind-utils \
bluez-cups \
bootc \
brcmfmac-firmware \
brltty \
btop \
btrfs-progs \
buildah \
c2esp \
cachyos-ananicy-rules \
cava \
cbonsai \
chrony \
cifs-utils \
cirrus-audio-firmware \
colord \
compsize \
coreutils \
cowsay \
cpio \
cracklib-dicts \
criu \
cryptsetup \
cups \
cups-browsed \
cups-client \
cups-filters \
cups-filters-driverless \
cups-ipptool \
curl \
cyrus-sasl-plain \
default-fonts-cjk-mono \
default-fonts-cjk-sans \
default-fonts-cjk-serif \
default-fonts-core-emoji \
default-fonts-core-math \
default-fonts-core-mono \
default-fonts-core-sans \
default-fonts-core-serif \
default-fonts-other-mono \
default-fonts-other-sans \
default-fonts-other-serif \
device-mapper-persistent-data \
distrobox \
dmemcg-booster \
dns-root-data \
dnsmasq \
dosfstools \
du-dust \
dwarves \
dymo-cups-drivers \
dysk \
e2fsprogs \
enchant2 \
ethtool \
exfatprogs \
fastfetch \
fedora-repos-archive \
ffmpegthumbnailer \
figlet \
file \
filesystem \
firewalld \
fish \
flatpak \
flatpak-spawn \
fpaste \
fresh \
fuse \
fuse-libs \
fuse-overlayfs \
fwupd \
fzf \
gamemode \
git \
glibc-all-langpacks \
gnupg2-scdaemon \
google-noto-sans-balinese-fonts \
google-noto-sans-cjk-fonts \
google-noto-sans-javanese-fonts \
google-noto-sans-myanmar-fonts \
google-noto-sans-sundanese-fonts \
google-noto-serif-myanmar-fonts \
grub2-efi-ia32 \
grub2-tools-extra \
gutenprint \
gutenprint-cups \
gvfs-fuse \
gvfs-mtp \
gvfs-nfs \
gvfs-smb \
hfsplus-tools \
hostname \
hplip \
htop \
hunspell \
hunspell-en \
hunspell-en-AU \
hunspell-en-CA \
hunspell-en-GB \
hyperv-daemons \
ibus-anthy \
ibus-chewing \
ibus-gtk3 \
ibus-gtk4 \
ibus-hangul \
ibus-libpinyin \
ibus-m17n \
ibus-typing-booster \
inotify-tools \
intel-audio-firmware \
intel-gpu-firmware \
intel-lpmd \
intel-vsc-firmware \
iptables-nft \
iptstate \
iwlegacy-firmware \
iwlwifi-dvm-firmware \
iwlwifi-mvm-firmware \
just \
kmscon \
kpartx \
langpacks-en \
lazygit \
libcamera \
libcamera-gstreamer \
libcamera-ipa \
libcamera-tools \
liberation-sans-fonts \
liberation-serif-fonts \
libertas-firmware \
libimobiledevice-utils \
libnotify \
libratbag-ratbagd \
libva-intel-driver \
libxcrypt-compat \
linux-firmware \
lm_sensors \
lolcat \
lrzsz \
lsb_release \
lsd \
lshw \
lsof \
lvm2 \
maple-fonts \
mcelog \
mdadm \
memstrack \
mesa-dri-drivers \
mesa-vulkan-drivers \
microcode_ctl \
mkpasswd \
mpage \
mt7xxx-firmware \
mtr \
nano \
nano-default-editor \
net-tools \
NetworkManager \
NetworkManager-bluetooth \
NetworkManager-config-connectivity-fedora \
NetworkManager-wifi \
NetworkManager-wwan \
nfs-utils \
nss-altfiles \
nss-mdns \
ntfs-3g \
ntfsprogs \
nvidia-gpu-firmware \
nvme-cli \
nvtop \
nxpwireless-firmware \
open-vm-tools-desktop \
opendoas \
openrgb-udev-rules \
opensc \
openssh-askpass \
openssh-server \
openssl \
orca \
os-prober \
oversteer-udev \
pam-u2f \
pam_afs_session \
pam_apparmor \
pam_yubico \
pamu2fcfg \
paps \
passwdqc \
pciutils \
pinentry \
pinfo \
pipewire-alsa \
pipewire-config-raop \
pipewire-gstreamer \
pipewire-jack-audio-connection-kit \
pipewire-plugin-libcamera \
pipewire-pulseaudio \
pipewire-utils \
pkcs11-provider \
plymouth \
plymouth-plugin-two-step \
podman \
podman-compose \
powerstat \
prefixdevname \
printer-driver-brlaser \
procs \
ptouch-driver \
pulseaudio-utils \
python3-apparmor \
python3-LibAppArmor \
python3-pip \
python3-setuptools \
python3-tkinter \
qcom-wwan-firmware \
qemu-guest-agent \
qemu-user-static-aarch64 \
quota \
rakuos-branding \
rakuos-core \
${RAKUOS_RELEASE_PKG} \
rakuos-settings \
rakuos-wallpapers \
realmd \
realtek-firmware \
ripgrep \
rsms-inter-fonts \
rsync \
samba-client \
scx-scheds \
scx-tools \
ShellCheck \
shim-ia32 \
skopeo \
slirp4netns \
solaar-udev \
sos \
speech-dispatcher \
speech-dispatcher-utils \
spice-vdagent \
spice-webdavd \
splix \
sqlite3 \
squashfs-tools \
squashfuse \
sssd-common \
sssd-kcm \
starship \
sudo-rs \
surge \
symlinks \
system-config-printer-udev \
systemd-container \
systemd-resolved \
tcpdump \
tealdeer \
termflix \
thermald \
tiwilink-firmware \
tmux \
traceroute \
tree \
tuned \
udisks2 \
unrar \
unzip \
uresourced \
usb_modeswitch \
usbmuxd \
usbutils \
util-linux \
uutils-coreutils \
v4l-utils \
vim \
virtualbox-guest-additions \
wget2 \
wget2-libs \
wget2-wget \
whois \
wireguard-tools \
wireplumber \
wl-clipboard \
wlctl \
words \
wpa_supplicant \
xdg-desktop-portal \
xdg-desktop-portal-gtk \
xfsprogs \
xhost \
xorg-x11-server-Xwayland \
xorg-x11-xauth \
xrdb \
yubikey-manager \
zellij \
zip \
zoxide \
zsh \
zstd

rum swap -y ocl-icd OpenCL-ICD-Loader --allowerasing

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
#systemctl mask systemd-oomd.service
systemctl mask rpm-ostreed-automatic.timer
# bootupd's bootloader updater fails on RakuOS; rakuos-bootloader-update.service
# (rakuos-core, enabled below) keeps shim and GRUB on the ESP current instead.
systemctl mask bootloader-update.service

# Statically enable getty on tty2-6 -- confirmed on real hardware that
# systemd-logind's on-demand autovt@ auto-start (which is supposed to spawn
# a getty the moment you switch to an unallocated VT) does not reliably fire
# on this kernel/image, leaving Ctrl+Alt+F<n> landing on a dead console with no login prompt.
systemctl enable getty@tty2.service getty@tty3.service getty@tty4.service getty@tty5.service getty@tty6.service

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
rakuos-setup.service \
rakuos-flatpak-watcher.service \
rakuos-grub-theme.service \
rakuos-bootloader-update.service \
rakuos-rescue-entries.service \
rakuos-rescue-entries.path \
rakuos-os-entries.timer \
dmemcg-booster.service \
ananicy-cpp.service \
nix.mount \
flatpak-cleanup.timer \
flatpak-repair.timer \
podman-prune.timer

systemctl enable --global \
rakuos-user.service

# Enable os-prober so grub detects other OSes (e.g. Windows) in dual-boot setups
echo 'GRUB_DISABLE_OS_PROBER=false' >> /etc/default/grub

# ## Add custom icons
# git clone https://github.com/vinceliuice/Colloid-icon-theme.git /tmp/Colloid-icon-theme
# /tmp/Colloid-icon-theme/install.sh -s all -t all -a -p -b
# rm -rf /tmp/Colloid-icon-theme
