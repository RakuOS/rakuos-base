#!/bin/bash

set -ouex pipefail

# Third-party repos are opt-in — we only ship the main Terra repo definition,
# not the repo enabled by default. Desktop images enable it temporarily in
# their own build.sh if they need Terra-sourced packages, then disable it
# again in their post-build.sh, matching this same disabled end state.
rum config-manager --default --set-disabled terra

# RPM Fusion is opt-in the same way. Record its package repos (the release
# repos and -updates; never -updates-testing, -debuginfo or -source), so
# desktop images turn exactly those back on in their build.sh and the welcome
# app turns them on when the user opts in, then disable every RPM Fusion
# repo. Not what the release packages enable: on a branched Fedora that's
# -updates-testing, which users would then run without asking for it.
mkdir -p /usr/share/rakuos
rum repo list --all | awk '$1 ~ /^rpmfusion-/ && $1 !~ /-(debuginfo|source)$/ && $1 !~ /-testing/ {print $1}' > /usr/share/rakuos/rpmfusion-default-repos
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

# ── Legacy CA bundle paths ────────────────────────────────────────────────────
# Fedora 45's ca-certificates no longer ships the old Red Hat paths
# /etc/pki/tls/certs/ca-bundle.crt, ca-bundle.trust.crt and /etc/pki/tls/cert.pem
# (only /etc/ssl/ and /etc/pki/ca-trust/). Vendor repo files and apps that name
# them break: Cloudsmith's repos (Devolutions RDM) set sslcacert= to
# ca-bundle.crt, and librepo then fails with curl error 77. Link them to the
# bundles update-ca-trust maintains, so they follow trust changes.
mkdir -p /etc/pki/tls/certs
for _link in \
    /etc/pki/tls/certs/ca-bundle.crt:/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem \
    /etc/pki/tls/cert.pem:/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem \
    /etc/pki/tls/certs/ca-bundle.trust.crt:/etc/pki/ca-trust/extracted/openssl/ca-bundle.trust.crt; do
    _path=${_link%%:*}; _target=${_link#*:}
    if [ ! -e "$_path" ] && [ -e "$_target" ]; then
        ln -s "$_target" "$_path"
    fi
done
unset _link _path _target

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

# bootc upgrade/switch stage a new image, after which RakuOS has to prepare
# the package layers for it (rum layer-prepare, through rakuos-core's
# after-image-staged) before the reboot, or its first boot runs the layers
# made for the old image. Wrap bootc so that happens however it's run (a
# terminal, scripts, the update tools). Every other bootc command goes
# straight to the real binary, bootc.real.
if [ -x /usr/bin/bootc ] && [ ! -e /usr/bin/bootc.real ]; then
    mv /usr/bin/bootc /usr/bin/bootc.real
    cat > /usr/bin/bootc << 'EOF'
#!/usr/bin/bash
# RakuOS: `bootc upgrade` and `bootc switch` prepare the package layers for
# the image they staged (/usr/libexec/rakuos/after-image-staged). Every
# other command, and --check/--help, runs the real bootc (bootc.real)
# unchanged.
real=/usr/bin/bootc.real
case "$1" in
    upgrade|switch) ;;
    *) exec "$real" "$@" ;;
esac
for arg in "$@"; do
    case "$arg" in
        --check|-h|--help) exec "$real" "$@" ;;
    esac
done
# --apply would reboot before the layers are prepared, and a soft reboot
# skips the initrd that switches to the new image's layers: stage first,
# prepare, then reboot normally.
args=()
apply=0
skip=0
for arg in "$@"; do
    if [ "$skip" = 1 ]; then skip=0; continue; fi
    case "$arg" in
        --apply) apply=1 ;;
        --soft-reboot) skip=1 ;;
        --soft-reboot=*) ;;
        *) args+=("$arg") ;;
    esac
done
staged() {
    "$real" status --json 2>/dev/null | jq -r '.status.staged // empty | "\(.ostree.checksum) \(.ostree.deploySerial)"' 2>/dev/null
}
before=$(staged)
"$real" "${args[@]}"
rc=$?
after=$(staged)
# Prepared only for a newly staged image; "no changes" leaves nothing to do.
if [ "$rc" = 0 ] && [ -n "$after" ] && [ "$after" != "$before" ]; then
    /usr/libexec/rakuos/after-image-staged
    if [ "$apply" = 1 ]; then
        echo "Rebooting into the new image..."
        systemctl reboot
    fi
fi
exit "$rc"
EOF
    chmod 0755 /usr/bin/bootc
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

# The kernels this image installed: both variants for its ISA level and
# channel (kernels.sh, installed by bootstrap.sh).
source "$(dirname "$(readlink -f "$0")")/kernels.sh"
load_kernel_releases
echo "Protecting kernel packages ${KERNEL_PKGS[*]}"

cat >> "$PROTECTED_FILE" << EOF

# Base image packages (from rakuos-base/build_files/build.sh)
dnf5-plugins
${KERNEL_PKG}
${KERNEL_PKG}-devel-matched
${KERNEL_AC_PKG}
${KERNEL_AC_PKG}-devel-matched
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
rakuos-logos
rakuos-plymouth-theme
rakuos-grub-theme
rakuos-fastfetch-preset
rakuos-core
rakuos-release
rakuos-settings
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

# Only the base image has the full branding and the wallpapers (the minimal
# image ships the logos, Plymouth, GRUB and fastfetch branding only).
if [ "${RAKUOS_VARIANT:-base}" != "minimal" ]; then
    printf '%s\n' rakuos-branding rakuos-gtk-theme rakuos-icon-theme rakuos-fonts-config rakuos-wallpapers >> "$PROTECTED_FILE"
fi

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

# System accounts this build's package installs created go to nss-altfiles
# with the rest (and any without a pinned ID in bootstrap/static-ids/ are
# listed in the log). Installed into the image so the desktop images'
# post-build.sh can run the same step after their own package installs.
install -Dm0755 /ctx/finalize-accounts.sh /usr/libexec/rakuos/finalize-accounts
/usr/libexec/rakuos/finalize-accounts
