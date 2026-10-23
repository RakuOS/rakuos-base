#!/bin/bash

set -ouex pipefail

# Third-party repos are opt-in — we only ship the main Terra repo definition,
# not the repo enabled by default. Desktop images enable it temporarily in
# their own build.sh if they need Terra-sourced packages, then disable it
# again in their post-build.sh, matching this same disabled end state.
rum config-manager --default --set-disabled terra

# RPM Fusion is opt-in the same way. Record which of its repos the release
# packages turn on by default (-updates on a stable Fedora, -updates-testing
# on a branched one; never -debuginfo/-source), so desktop images turn
# exactly those back on in their build.sh, then disable every RPM Fusion repo.
mkdir -p /usr/share/rakuos
rum repolist | awk '$1 ~ /^rpmfusion-/ && $2 == "enabled" {print $1}' > /usr/share/rakuos/rpmfusion-default-repos
[ -s /usr/share/rakuos/rpmfusion-default-repos ] || { echo "ERROR: no enabled RPM Fusion repos found"; exit 1; }
rum config-manager --default --set-disabled 'rpmfusion-*'

# Mark all base image packages as dependency so Rum only manages overlay packages
rum mark -y dependency '*'


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

# pam_oo7 forks /usr/libexec/oo7-daemon-login at login with the login
# process's stdout/stderr, and the helper logs at INFO to stderr. Under greetd
# (COSMIC, Niri, Hyprland) that's the VT, so "oo7_daemon_login: Starting ...",
# "Listening on ..." and "Secret delivered to daemon" were printed on the
# console at every login. Wrap the helper so its output goes to the journal
# (tag oo7-daemon-login); stdin, which carries the password, is untouched.
if [ -x /usr/libexec/oo7-daemon-login ] && [ ! -e /usr/libexec/oo7-daemon-login.real ]; then
    mv /usr/libexec/oo7-daemon-login /usr/libexec/oo7-daemon-login.real
    cat > /usr/libexec/oo7-daemon-login << 'EOF'
#!/bin/sh
# RakuOS: send oo7-daemon-login's log output to the journal instead of the
# login terminal. The real helper is oo7-daemon-login.real.
exec systemd-cat -t oo7-daemon-login /usr/libexec/oo7-daemon-login.real "$@"
EOF
    chmod 0755 /usr/libexec/oo7-daemon-login
fi

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

# The kernel this image installed: kernel-rakuos-v2/-v3/-v4, with -staging on
# the staging channel. build.sh, build-v3.sh and build-v4.sh each pick their
# own, so read it back from the rpmdb instead of hardcoding v2 (which left the
# v3/v4 kernels unprotected).
KERNEL_PKG=$(rpm -qa --qf '%{NAME}\n' 'kernel-rakuos-v*' | grep -E '^kernel-rakuos-v[0-9]+(-staging)?$' | head -n 1)
[ -n "$KERNEL_PKG" ] || { echo "ERROR: no kernel-rakuos-v* package installed"; exit 1; }
echo "Protecting kernel package ${KERNEL_PKG}"

cat >> "$PROTECTED_FILE" << EOF

# Base image packages (from rakuos-base/build_files/build.sh)
dnf5-plugins
${KERNEL_PKG}
${KERNEL_PKG}-devel-matched
intel-vaapi-driver
libopenjph
libva-utils
libva
libheif
pipewire-libs-extra
heif-pixbuf-loader
OpenCL-ICD-Loader
alsa-firmware
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
btop
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
iputils
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
pipewire-libs.i686
pipewire-alsa.i686
net-tools
nvme-cli
nvtop
oo7-daemon
oo7-portal
opendoas
openrgb-udev-rules
openssh-askpass
openssl
oversteer-udev
pam-u2f
pam_oo7
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
rakuos-branding
rakuos-core
rakuos-release
rakuos-settings
rakuos-wallpapers
ripgrep
rsms-inter-fonts
rsync
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
tuned
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

# Regenerate bootupd's update metadata (/usr/lib/bootupd/updates/EFI.json)
# from the bootloader this image actually ships. The copy from the Fedora
# bootc base image describes the grub2/shim it was built with; once this
# build has upgraded grub2 it names a /usr/lib/efi/grub2/<evr> directory that
# no longer exists, and rakuos-bootloader-update fails with "... missing
# although .../EFI.json lists grub2 ...". Same command Fedora's bootc image
# build runs; it only works with / as the root.
bootupctl backend generate-update-metadata /
