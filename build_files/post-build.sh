#!/bin/bash

set -ouex pipefail

# Rename real dnf5 and dnf binaries
mv /usr/bin/dnf5 /usr/bin/dnf5.real
mv /usr/bin/dnf /usr/bin/dnf.real

# Mark all base image packages as dependency so PackageKit only manages overlay packages
dnf5.real -y mark dependency $(rpm -qa --qf '%{NAME} ') --skip-unavailable

# Create dnf5 wrapper
cat > /usr/bin/dnf5 << 'WRAPPER'
#!/usr/bin/env bash
COMMAND="${1:-}"
case "$COMMAND" in
    install)
        shift
        exec rakuos install "$@"
        ;;
    update)
        shift
        exec rakuos update "$@"
        ;;
    remove|erase)
        shift
        exec rakuos remove "$@"
        ;;
    *)
        exec /usr/bin/dnf5.real "$@"
        ;;
esac
WRAPPER

# Create dnf wrapper
cat > /usr/bin/dnf << 'WRAPPER'
#!/usr/bin/env bash
exec /usr/bin/dnf5 "$@"
WRAPPER

# Make all wrappers executable
chmod +x /usr/bin/dnf5 /usr/bin/dnf

# Wire up /etc/zshrc.d/ fragment sourcing (Fedora's zsh doesn't do this by default).
mkdir -p /etc/zshrc.d
if ! grep -q 'zshrc.d' /etc/zshrc 2>/dev/null; then
    cat >> /etc/zshrc << 'ZSHRC'

# Source RakuOS zsh configuration fragments
for _f in /etc/zshrc.d/*.zsh; do [[ -r "$_f" ]] && source "$_f"; done
unset _f
ZSHRC
fi

# Point fastfetch system config to the RakuOS preset.
mkdir -p /etc/fastfetch
ln -sf /usr/share/fastfetch/presets/rakuos/rakuos-fastfetch.jsonc /etc/fastfetch/config.jsonc

# Remove ostree boot condition from PackageKit so it starts on RakuOS
#sed -i '/ConditionPathExists=!\/run\/ostree-booted/d' /usr/lib/systemd/system/packagekit.service

echo "RakuOS post-build complete."

# ── Build protected-packages.txt ──────────────────────────────────────────────
# nvidia.sh writes this file first (if it ran) with nvidia packages + deps.
# We append the base build.sh packages either way.
# If nvidia.sh did NOT run this is a normal build — create the file fresh.
PROTECTED_FILE="/usr/share/rakuos/protected-packages.txt"
mkdir -p /usr/share/rakuos

if [[ -f "$PROTECTED_FILE" ]]; then
    echo "nvidia build detected — appending base packages to existing protected-packages.txt..."
else
    echo "Normal build — creating protected-packages.txt with base packages..."
    > "$PROTECTED_FILE"
fi

cat >> "$PROTECTED_FILE" << 'EOF'

# Base image packages (from rakuos-base/build_files/build.sh)
dnf5-plugins
kernel-cachyos
kernel-cachyos-devel-matched
intel-vaapi-driver
libopenjph
libva-utils
libva
libheif
pipewire-libs-extra
heif-pixbuf-loader
OpenCL-ICD-Loader
alsa-firmware
ananicy-cpp
appstream
appstream-data
apr
apr-util
aria2
bat
bat-extras
bibata-cursor-theme
bind
bind-utils
bootc
bore-sysctl
btop
cachyos-ananicy-rules
cachyos-settings
cava
cbonsai
cowsay
distrobox
dmemcg-booster
du-dust
dysk
fastfetch
fedora-repos-archive
ffmpeg
ffmpegthumbnailer
figlet
fish
flatpak
flatpak-spawn
fresh
fuse
fwupd
fzf
git
google-noto-sans-balinese-fonts
google-noto-sans-cjk-fonts
google-noto-sans-javanese-fonts
google-noto-sans-myanmar-fonts
google-noto-sans-sundanese-fonts
google-noto-serif-myanmar-fonts
grub2-tools-extra
gvfs-fuse
gvfs-mtp
gvfs-nfs
gvfs-smb
htop
inotify-tools
just
lazygit
libcamera
libcamera-gstreamer
libcamera-ipa
libcamera-tools
libimobiledevice-utils
libnotify
libratbag-ratbagd
libxcrypt-compat
lm_sensors
lolcat
lshw
lsd
maple-fonts
mesa-dri-drivers.i686
mesa-vulkan-drivers.i686
mesa-libEGL.i686
mesa-libGL.i686
net-tools
nvme-cli
nvtop
opendoas
openrgb-udev-rules
openssh-askpass
openssl
oversteer-udev
pam-u2f
pam_yubico
pamu2fcfg
pipewire-plugin-libcamera
podman
podman-compose
powerstat
procs
pulseaudio-utils
python3-pip
python3-setuptools
ripgrep
rsms-inter-fonts
rsync
scx-scheds
scx-tools
selinux-policy-targeted
ShellCheck
solaar-udev
sqlite3
squashfs-tools
squashfuse
starship
sudo-rs
surge
symlinks
tcpdump
termflix
tmux
traceroute
ublue-os-udev-rules
unrar
unzip
usbmuxd
v4l-utils
vim
virtualbox-guest-additions
wireguard-tools
wl-clipboard
xhost
xorg-x11-xauth
yubikey-manager
zellij
zoxide
zsh
zstd
EOF

echo "protected-packages.txt ready ($(grep -c '^[^#]' "$PROTECTED_FILE") packages)."

echo "Generating base file manifest..."
/usr/libexec/rakuos/generate-base-manifest