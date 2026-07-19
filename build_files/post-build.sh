#!/bin/bash

set -ouex pipefail

# Rename real dnf5 and dnf binaries
mv /usr/bin/dnf5 /usr/bin/dnf5.real
mv /usr/bin/dnf /usr/bin/dnf.real
mv /usr/bin/rpm-ostree /usr/bin/rpm-ostree.real

# Mark all base image packages as dependency so PackageKit only manages overlay packages
dnf5.real -y mark dependency $(rpm -qa --qf '%{NAME} ') --skip-unavailable

# Create rpm-ostree wrapper
cat > /usr/bin/rpm-ostree << 'WRAPPER'
#!/usr/bin/env bash
COMMAND="${1:-}"
case "$COMMAND" in
    reset)
        shift
        exec rakuos reset-overlay --confirm
        ;; 
    status)
        shift
        exec bootc status "$@"
        ;;    
    install)
        shift
        exec rakuos install "$@"
        ;;
    upgrade)
        shift
        exec bootc upgrade "$@"
        ;;
    rollback)
        shift
        exec bootc rollback "$@"
        ;;
    rebase)
        shift
        exec bootc switch "$@"
        ;;
    uninstall)
        shift
        exec rakuos remove "$@"
        ;;
    search)
        shift
        exec /usr/bin/dnf5.real search "$@"
        ;;
    *)
        exec rpm-ostree.real "$@"
        ;;
esac
WRAPPER

# Create dnf5 wrapper
cat > /usr/bin/dnf5 << 'WRAPPER'
#!/usr/bin/env bash
COMMAND="${1:-}"
case "$COMMAND" in
    install)
        shift
        exec rakupkg install "$@"
        ;;
    update)
        shift
        exec rakupkg update "$@"
        ;;
    remove|erase)
        shift
        exec rakupkg remove "$@"
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
chmod +x /usr/bin/dnf5 /usr/bin/dnf /usr/bin/rpm-ostree

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

# ── sudo-rs bootstrap ─────────────────────────────────────────────────────────
# Preserve the originals under .og so setup-sudo can register them with
# `alternatives`, then wire sudo-rs as the system default.
for bin in sudo su visudo; do
    _bin="/usr/bin/${bin}"
    if [[ -f "$_bin" && ! -f "/usr/bin/gnu_${bin}" ]]; then
        mv "$_bin" "/usr/bin/gnu_${bin}"
        chown root:root "/usr/bin/gnu_${bin}"
        chmod 4755 "/usr/bin/gnu_${bin}"
    fi
done
unset bin _bin
/usr/libexec/rakuos/setup-sudo sudo-rs

# Belt-and-suspenders: explicitly stamp uid 0 + setuid on the sudo-rs binaries
# so the bits are correct in the committed image regardless of how alternatives
# or the RPM installed them.
for _bin in /usr/bin/sudo-rs /usr/bin/su-rs; do
    [[ -f "$_bin" ]] || continue
    chown root:root "$_bin"
    chmod 4755 "$_bin"
done
[[ -f /usr/bin/visudo-rs ]] && chown root:root /usr/bin/visudo-rs && chmod 0755 /usr/bin/visudo-rs

# Remove ostree boot condition from PackageKit so it starts on RakuOS
#sed -i '/ConditionPathExists=!\/run\/ostree-booted/d' /usr/lib/systemd/system/packagekit.service

# ── uutils-coreutils bootstrap ────────────────────────────────────────────────
# Move ALL GNU coreutils to .og so setup-uutils can register them with
# alternatives. Explicit list — don't rely on uu_* iteration which misses bins
# that exist in GNU but have no uu_ counterpart or vice versa.
_GNU_COREUTILS=(
    '[' arch b2sum base32 base64 basename basenc cat chcon chgrp chmod chown
    chroot cksum comm cp csplit cut date dd df dir dircolors dirname du
    echo env expand expr factor false fmt fold groups head hostid hostname
    id install join kill link ln logname ls md5sum mkdir mkfifo mknod mktemp
    more mv nice nl nohup nproc numfmt od paste pathchk pinky pr printenv
    printf ptx pwd readlink realpath rm rmdir runcon seq sha1sum sha224sum
    sha256sum sha384sum sha512sum shred shuf sleep sort split stat stdbuf
    stty sum sync tac tail tee test timeout touch tr true truncate tsort tty uname
    unexpand uniq unlink uptime users vdir wc who whoami yes
)
# Move mv first so the loop can use uu_mv for all subsequent renames.
[[ -f /usr/bin/mv && ! -L /usr/bin/mv && ! -f /usr/bin/gnu_mv ]] && /usr/bin/mv /usr/bin/mv /usr/bin/gnu_mv
for _name in "${_GNU_COREUTILS[@]}"; do
    _gnu="/usr/bin/${_name}"
    [[ -f "$_gnu" && ! -L "$_gnu" && ! -f "/usr/bin/gnu_${_name}" ]] && /usr/bin/uu_mv "$_gnu" "/usr/bin/gnu_${_name}"
done
unset _GNU_COREUTILS _name _gnu
/usr/libexec/rakuos/setup-uutils image-default

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
kernel-p03-v3
kernel-p03-v3-devel-matched
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
apparmor-libs
apparmor-parser
apparmor-utils
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
mod_apparmor
pipewire-libs.i686
pipewire-alsa.i686
net-tools
nvme-cli
nvtop
opendoas
openrgb-udev-rules
openssh-askpass
openssl
oversteer-udev
pam_apparmor
pam-u2f
pam_yubico
pamu2fcfg
pipewire-plugin-libcamera
podman
podman-compose
powerstat
procs
pulseaudio-utils
python3-apparmor
python3-LibAppArmor
python3-pip
python3-setuptools
rakuos-apparmor-profiles
rakuos-core
ripgrep
rsms-inter-fonts
rsync
scx-scheds
scx-tools
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

# selinux-policy is fully removed on RakuOS (AppArmor is the sole MAC), but the
# baked-in rpm-ostree treefile still defaults "selinux": true. rpm-ostree reads
# that flag on every deploy-time layering operation and tries to load a policy
# from / that no longer exists, causing spurious sepolicy-mismatch failures.
if [ -f /usr/share/rpm-ostree/treefile.json ]; then
    sed -i 's/"selinux": *true/"selinux": false/' /usr/share/rpm-ostree/treefile.json
fi
