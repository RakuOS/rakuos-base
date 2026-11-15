#!/bin/bash
# build-minimal.sh: the minimal image's package installs and setup (the
# Containerfile runs it instead of build.sh when RAKUOS_VARIANT=minimal).
# It starts from build.sh and is cut down for a system that boots to a tty
# and gets its desktop later: packages here are picked for minimal, so a
# change to build.sh doesn't carry over by itself.
#
# Not here: rakuos-branding (the minimal image only has the logos and the
# Plymouth, GRUB and fastfetch branding, all from the bootstrap root),
# rakuos-wallpapers, and ananicy-cpp with cachyos-ananicy-rules (process
# priority rules for desktop apps; `rum install cachyos-ananicy-rules` adds
# both, then `systemctl enable --now ananicy-cpp`).

set -ouex pipefail
FEDORA_VERSION=$(rpm -E %fedora)

# rakuos-release (or -staging) and rakuos-core (or -staging) are already in
# the bootstrapped root (bootstrap/bootstrap.sh).

# x86-64 ISA level (RAKUOS_ISA_LEVEL = v2, v3 or v4, a --build-arg from CI):
# picks the rakuos-v3/-v4 repos below. The kernels for it are already in the
# bootstrapped root (bootstrap.sh, kernels.sh).
RAKUOS_ISA_LEVEL="${RAKUOS_ISA_LEVEL:-v2}"
case "${RAKUOS_ISA_LEVEL}" in
    v2|v3|v4) ;;
    *) echo "Unknown RAKUOS_ISA_LEVEL '${RAKUOS_ISA_LEVEL}' (want v2, v3 or v4)" >&2; exit 1 ;;
esac

## Enable the rakuos repo first — rum itself lives in it, so this has to
## happen before anything else, using the base image's real dnf5 since rum
## doesn't exist yet.
dnf5 -y install dnf5-plugins
rpm --import https://repo.rakuos.org/pubkey.gpg
dnf5 -y config-manager addrepo --from-repofile=https://repo.rakuos.org/rakuos.repo
# v3 images also use the rakuos-v3 repo; v4 images use both v3 and v4.
case "${RAKUOS_ISA_LEVEL}" in
    v3) isa_repos="v3" ;;
    v4) isa_repos="v3 v4" ;;
    *)  isa_repos="" ;;
esac
for isa in ${isa_repos}; do
    sed -i "/^\[rakuos-${isa}\]/,/^\[/ s/^enabled=0/enabled=1/" /etc/yum.repos.d/rakuos.repo
done

## Install rum + the dnf/dnf5 shims as the very first packages — from here
## on, every install/remove/upgrade/swap in this script goes through rum
## directly instead of dnf5 (rum-dnf-shim also Obsoletes/Conflicts the real
## dnf5/dnf packages, so they're gone from the image after this point
## regardless). rakuos-rum-repo-overrides ships rum's repo overrides
## (/usr/share/rum/repos.override.d/20-rakuos.repo): the excludepkgs= that
## keep Fedora's goverlay, RPM Fusion's NVIDIA driver stack and steam, and
## Terra's AppArmor and sched_ext packages from replacing the RakuOS builds,
## so the repo files themselves are left as their packages ship them.
##
## On staging (RAKUOS_STAGING=1) the staging rum goes in instead:
## rakuos-rum-staging, rum-dnf-shim-staging and
## rakuos-rum-repo-overrides-staging, built from rum's staging branch. They
## provide the stable names, so anything that requires rakuos-rum is still
## satisfied. If the repo has no staging build yet, the stable rum is
## installed so the image still builds.
RUM_SUFFIX=""
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    if dnf5 -q repoquery --available rakuos-rum-staging 2>/dev/null | grep -q .; then
        RUM_SUFFIX="-staging"
    else
        echo "WARNING: the repo has no rakuos-rum-staging yet; installing the stable rum"
    fi
fi
dnf5 -y install "rakuos-rum${RUM_SUFFIX}" "rum-dnf-shim${RUM_SUFFIX}" "rakuos-rum-repo-overrides${RUM_SUFFIX}"

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
# From RPM Fusion's main server, not the mirrors.rpmfusion.org redirector:
# for a release still in development (45) it sent every request to one
# mirror whose hostname didn't resolve, failing the build.
rum install -y https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA_VERSION}.noarch.rpm \
              https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA_VERSION}.noarch.rpm

# SELinux: the bootstrapped root never has it (RakuOS uses AppArmor); a root
# built FROM Fedora's bootc image does.
rm -f /etc/dnf/protected.d/selinux-policy-targeted.conf
if rpm -q selinux-policy >/dev/null 2>&1; then
    rum remove -y 'selinux-policy*' 'policycoreutils-gui'
fi
rum upgrade -y --best --allowerasing 'rpm*' 'ostree*'

rpm --import https://repos.fyralabs.com/terra${FEDORA_VERSION}/key.asc

rum install -y --no-gpgchecks --repofrompath "terra,https://repos.fyralabs.com/terra${FEDORA_VERSION}" terra-release


# Edit Terra's shipped repo files in place (see shipped_repo_files above).
TERRA_REPO_FILES=$(shipped_repo_files 'terra*.repo')
[ -n "$TERRA_REPO_FILES" ] || { echo "ERROR: no terra repo files found"; exit 1; }

# Remove hardcoded priority=80 from terra repo files so our config-manager priorities take effect
sed -i '/^priority=/d' $TERRA_REPO_FILES

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

# Remove Fedora's kernel and zram config, where the root has them (the
# bootstrapped root has neither).
FEDORA_KERNEL_PKGS=$(rpm -q --qf '%{NAME}\n' kernel kernel-core kernel-modules kernel-modules-core \
    kernel-modules-extra kernel-tools kernel-tools-libs zram-generator-defaults 2>/dev/null | grep -v 'not installed' || true)
if [ -n "$FEDORA_KERNEL_PKGS" ]; then
    rum remove -y --no-autoremove $FEDORA_KERNEL_PKGS
fi
# The RakuOS kernels are already installed (bootstrap.sh), so
# /usr/lib/modules stays.
rm -rf /boot/*

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

# cpak install disabled for now: GitHub keeps answering 503/504 for the
# release downloads and the releases API from CI. Uncomment to bring it back.
# Install cpak (https://cpak.it/docs/install) — download the latest release's
# binaries and verify against the published SHA256SUMS before installing;
# cpak looks for cpak-storaged beside cpak itself, so both go into /usr/bin.
# releases/latest/download/<asset> redirects straight to the file, so no
# version lookup is needed. github.com's release download URLs sometimes
# answer 504 for a while (the API's asset endpoint keeps working), so when a
# download fails, fetch that asset through the API instead. The API is rate
# limited per IP for unauthenticated use, which is why it's only the fallback.
# CURL_RETRY=(--retry 3 --retry-all-errors --retry-delay 10)
# CPAK_BASE="https://github.com/Containerpak/cpak/releases/latest/download"
# CPAK_API="https://api.github.com/repos/Containerpak/cpak/releases/latest"
# CPAK_RELEASE_JSON=""
# fetch_cpak() {  # fetch_cpak <asset> <dest>
#     curl -fsSL "${CURL_RETRY[@]}" -o "$2" "${CPAK_BASE}/$1" && return 0
#     echo "github.com download of $1 failed; trying the releases API"
#     [ -n "${CPAK_RELEASE_JSON}" ] || CPAK_RELEASE_JSON=$(curl -fsSL "${CURL_RETRY[@]}" "${CPAK_API}")
#     local url
#     url=$(awk -v want="$1" '/"url": ".*\/releases\/assets\/[0-9]+"/ { u = $2 }
#         /"name": / { n = $2; gsub(/[",]/, "", n); if (n == want) { gsub(/[",]/, "", u); print u; exit } }' \
#         <<< "${CPAK_RELEASE_JSON}")
#     [ -n "${url}" ] || { echo "ERROR: cpak release has no asset $1"; return 1; }
#     curl -fsSL "${CURL_RETRY[@]}" -H 'Accept: application/octet-stream' -o "$2" "${url}"
# }
# fetch_cpak cpak-linux-amd64 /tmp/cpak-linux-amd64
# fetch_cpak cpak-storaged-linux-amd64 /tmp/cpak-storaged-linux-amd64
# fetch_cpak SHA256SUMS /tmp/cpak-SHA256SUMS
# (cd /tmp && sha256sum -c --ignore-missing cpak-SHA256SUMS)
# install -Dm755 /tmp/cpak-linux-amd64 /usr/bin/cpak
# install -Dm755 /tmp/cpak-storaged-linux-amd64 /usr/bin/cpak-storaged
# rm -f /tmp/cpak-linux-amd64 /tmp/cpak-storaged-linux-amd64 /tmp/cpak-SHA256SUMS

# install packages
rum install -y --skip-unavailable @hardware-support \
7zip \
alsa-firmware \
alsa-sof-firmware \
alsa-ucm \
alsa-utils \
amd-gpu-firmware \
amd-ucode-firmware \
apparmor-libs \
apparmor-parser \
apparmor-profiles \
apparmor-utils \
aria2 \
atheros-firmware \
attr \
audit \
audit-rules \
bash-color-prompt \
bash-completion \
bat \
bc \
bpftool \
bind-utils \
bootc \
brcmfmac-firmware \
brltty \
btop \
btrfs-progs \
buildah \
chrony \
cifs-utils \
cirrus-audio-firmware \
compsize \
coreutils \
cpio \
cracklib-dicts \
cryptsetup \
curl \
cyrus-sasl-plain \
default-fonts-core-mono \
device-mapper-persistent-data \
distrobox \
dmemcg-booster \
dns-root-data \
dnsmasq \
dosfstools \
dwarves \
e2fsprogs \
ethtool \
exfatprogs \
fastfetch \
fedora-repos-archive \
ffmpegthumbnailer \
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
git \
glibc-all-langpacks \
gnupg2-scdaemon \
grub2-efi-ia32 \
grub2-tools-extra \
hfsplus-tools \
hostname \
hyperv-daemons \
inotify-tools \
intel-audio-firmware \
intel-gpu-firmware \
intel-lpmd \
intel-vsc-firmware \
iptables-nft \
iputils \
iwlegacy-firmware \
iwlwifi-dvm-firmware \
iwlwifi-mvm-firmware \
just \
kmscon \
kpartx \
langpacks-en \
libcamera \
libcamera-gstreamer \
libcamera-ipa \
libcamera-tools \
libva-intel-driver \
libxcrypt-compat \
linux-firmware \
lm_sensors \
lsb_release \
lsd \
lshw \
lsof \
lvm2 \
mdadm \
mesa-dri-drivers \
mesa-vulkan-drivers \
microcode_ctl \
mkpasswd \
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
nxpwireless-firmware \
oo7-daemon \
oo7-portal \
opendoas \
opensc \
openssh-server \
openssl \
openssl3-libs \
os-prober \
pam-u2f \
pam_apparmor \
pam_oo7 \
pam_yubico \
pamu2fcfg \
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
pulseaudio-utils \
python3-apparmor \
python3-LibAppArmor \
python3-pip \
python3-setuptools \
qcom-wwan-firmware \
qemu-guest-agent \
quota \
rakuos-settings \
realtek-firmware \
ripgrep \
rsync \
samba-client \
scx-scheds \
scx-tools \
ShellCheck \
shim-ia32 \
skopeo \
sqlite3 \
squashfs-tools \
squashfuse \
starship \
sudo-rs \
symlinks \
systemd-container \
systemd-resolved \
tcpdump \
tealdeer \
thermald \
tmux \
traceroute \
tree \
tuned \
udisks2 \
unrar \
unzip \
usb_modeswitch \
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
wlctl \
wpa_supplicant \
xfsprogs \
yubikey-manager \
zip \
zoxide \
zstd

rum swap -y ocl-icd OpenCL-ICD-Loader --allowerasing

# Clean up some .desktops for command line utils
rm /usr/share/applications/btop.desktop
rm /usr/share/applications/io.github.sinelaw.fresh.desktop

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

# Statically enable the console on tty2-6 -- confirmed on real hardware that
# systemd-logind's on-demand autovt@ auto-start (which is supposed to spawn
# a login the moment you switch to an unallocated VT) does not reliably fire
# on this kernel/image, leaving Ctrl+Alt+F<n> landing on a dead console with no login prompt.
# On 45 the console is kmscon (autovt@ is an alias of kmsconvt@), so enable
# kmsconvt@ rather than plain getty@ to match tty1.
systemctl enable kmsconvt@tty2.service kmsconvt@tty3.service kmsconvt@tty4.service kmsconvt@tty5.service kmsconvt@tty6.service

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
rakuos-overlay-sync.service \
rakuos-setup.service \
rakuos-account-ids.service \
rakuos-grub-theme.service \
rakuos-bootloader-update.service \
rakuos-rescue-entries.service \
rakuos-rescue-entries.path \
rakuos-kernel-select.service \
rakuos-kernel-select-sync.service \
rakuos-kernel-select.path \
rakuos-layers-boot-ok.service \
var-lib-rakuos-layers.mount \
rum-layer-repair.service \
rum-layer-gc.timer \
rakuos-os-entries.timer \
dmemcg-booster.service \
nix.mount \
flatpak-cleanup.timer \
flatpak-repair.timer \
podman-prune.timer

# oo7 is the Secret Service (org.freedesktop.secrets). Nothing else starts
# it: the package has no D-Bus activation file and no preset enables it, so
# without this pam_oo7 times out at login and apps have no secrets store.
# oo7 has no SSH agent, so OpenSSH's own takes over from GNOME Keyring's
# gcr-ssh-agent; SSH_AUTH_SOCK is set in
# /usr/lib/environment.d/50-rakuos-ssh-agent.conf.
systemctl enable --global \
oo7-daemon.service \
ssh-agent.socket

# Keep the oo7 keyring password in step with the login password: pam_oo7
# must also be in the password stack, or after passwd/chpasswd the keyring
# keeps the old password and login auto-unlock fails. Fedora's shadow-utils
# files only list pam_gnome_keyring there.
sed -i '/pam_gnome_keyring.so use_authtok/a -password   optional\tpam_oo7.so' /etc/pam.d/passwd /etc/pam.d/chpasswd
grep -q pam_oo7.so /etc/pam.d/passwd && grep -q pam_oo7.so /etc/pam.d/chpasswd \
    || { echo "ERROR: pam_oo7 not added to /etc/pam.d/passwd and chpasswd"; exit 1; }

# Enable os-prober so grub detects other OSes (e.g. Windows) in dual-boot setups
echo 'GRUB_DISABLE_OS_PROBER=false' >> /etc/default/grub

# ## Add custom icons
# git clone https://github.com/vinceliuice/Colloid-icon-theme.git /tmp/Colloid-icon-theme
# /tmp/Colloid-icon-theme/install.sh -s all -t all -a -p -b
# rm -rf /tmp/Colloid-icon-theme
