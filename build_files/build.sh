#!/bin/bash

set -ouex pipefail
FEDORA_VERSION="${FEDORA_VERSION:-43}"
## Enable repos
dnf5 -y install dnf5-plugins
dnf5 -y copr enable tohur/RakuOS fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable bieszczaders/kernel-cachyos fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable bieszczaders/kernel-cachyos-addons fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable faugus/faugus-launcher fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable ilyaz/LACT fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable garecrow/ExtensionManager fedora-${FEDORA_VERSION}-x86_64
dnf5 -y copr enable wehagy/protonplus fedora-${FEDORA_VERSION}-x86_64
dnf5 -y install \
https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA_VERSION}.noarch.rpm \
https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA_VERSION}.noarch.rpm

dnf5 -y install --nogpgcheck --repofrompath 'terra,https://repos.fyralabs.com/terra$releasever' terra-release
dnf5 -y install --nogpgcheck --repofrompath 'terra-mesa,https://repos.fyralabs.com/terra$releasever' terra-release-mesa
dnf5 -y install --nogpgcheck --repofrompath 'terra-multimedia,https://repos.fyralabs.com/terra$releasever' terra-release-multimedia
dnf5 -y install --nogpgcheck --repofrompath 'terra-nvidia,https://repos.fyralabs.com/terra$releasever' terra-release-nvidia

dnf5 -y config-manager setopt "*terra*".priority=3 "*terra*".exclude="nerd-fonts topgrade scx-tools scx-scheds steam python3-protobuf zlib-devel"
dnf5 -y config-manager setopt "*rpmfusion*".priority=5 "*rpmfusion*".exclude="akmod-nvidia* kmod-nvidia* xorg-x11-drv-nvidia* nvidia-settings nvidia-persistenced nvidia-modprobe"
#dnf5 -y config-manager setopt "*fedora*".exclude="mesa-*"

# VS Code
rpm --import https://packages.microsoft.com/keys/microsoft.asc &&
echo -e "[code]\nname=Visual Studio Code\nbaseurl=https://packages.microsoft.com/yumrepos/vscode\nenabled=1\nautorefresh=1\ntype=rpm-md\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc" | sudo tee /etc/yum.repos.d/vscode.repo > /dev/null
# MS Edge
rpm --import https://packages.microsoft.com/keys/microsoft.asc &&
echo -e "[edge]\nname=Microsoft Edge\nbaseurl=https://packages.microsoft.com/yumrepos/edge\nenabled=1\nautorefresh=1\ntype=rpm-md\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc" | sudo tee /etc/yum.repos.d/edge.repo > /dev/null

# Enable Chrome repo
sed -i 's@enabled=0@enabled=1@g' /etc/yum.repos.d/google-chrome.repo

#remove fedora kernel and zram config
dnf5 -y remove --no-autoremove kernel kernel-core kernel-modules kernel-modules-core kernel-modules-extra kernel-tools kernel-tools-libs zram-generator-defaults

# Install cachyos kernel
dnf5 -y --setopt=tsflags=noscripts install kernel-cachyos kernel-cachyos-devel-matched

dnf5 -y swap ffmpeg-free ffmpeg --allowerasing

dnf5 -y swap mesa-va-drivers mesa-va-drivers-freeworld

dnf5 -y swap mesa-va-drivers.i686 mesa-va-drivers-freeworld.i686

# install packages
dnf5 -y install ananicy-cpp \
cachyos-ananicy-rules \
cachyos-settings \
bore-sysctl \
scx-scheds \
scx-tools \
gamemode \
gamemode.i686 \
pulseaudio-utils \
git \
flatpak \
libxcrypt-compat \
rsync \
podman \
distrobox \
xpadneo \
xone \
xone-firmware \
xpad-noone \
mokutil \
lm_sensors \
sqlite3 \
openssl \
libnotify \
inotify-tools \
podman-compose \
python3-pip \
appstream \
appstream-data \
fwupd \
python3-pyqt6 \
python3-dbus \
python3-gobject \
nodejs \
nodejs-npm \
fuse \
squashfuse \
virtualbox-guest-additions \
v4l-utils \
unzip \
glibc-langpack-en

## Remove packages
dnf5 -y remove firefox*

# enable flathub
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# Install RakuOS Software
cd /tmp
git clone https://github.com/RakuOS/rakuos-software.git
cd rakuos-software
mkdir -p /usr/libexec/rakuos/software
mkdir -p /usr/share/rakuos/webapps
mkdir -p /usr/share/rakuos/appstream/data
mkdir -p /usr/share/rakuos/appstream/icons
mkdir -p /etc/xdg/autostart
cp resources/appstream/appstream-overrides.json /usr/share/rakuos/appstream/appstream-overrides.json
cp resources/appstream/flatpak-to-rpm.json /usr/share/rakuos/appstream/flatpak-to-rpm.json
cp resources/appstream/data/* /usr/share/rakuos/appstream/data/
cp resources/appstream/icons/* /usr/share/rakuos/appstream/icons/
cp resources/webapps/*.json /usr/share/rakuos/webapps/
cp resources/rakuos-webapp-launcher /usr/bin/rakuos-webapp-launcher
cp resources/rakuos-software /usr/bin/rakuos-software
cp resources/rakuos-software.desktop /usr/share/applications/rakuos-software.desktop
cp resources/rakuos-software-tray.desktop /etc/xdg/autostart/rakuos-software-tray.desktop
cp -r src/backend src/ui_gtk src/ui_qt /usr/libexec/rakuos/software/
cp src/rakuos-software /usr/libexec/rakuos/software/rakuos-software
cp src/rakuos-webapp-launcher /usr/libexec/rakuos/software/rakuos-webapp-launcher

# ── Register RakuOS Software Center as default handler for package types ──────
MIMEAPPS="/usr/share/applications/mimeapps.list"

# Ensure sections exist then append entries if not already present
for section in "Default Applications" "Added Associations"; do
    if ! grep -q "^\[${section}\]" "$MIMEAPPS"; then
        printf '\n[%s]\n' "$section" >> "$MIMEAPPS"
    fi
    for mime in \
        "application/vnd.appimage=rakuos-software.desktop" \
        "application/x-rpm=rakuos-software.desktop" \
        "application/vnd.flatpak=rakuos-software.desktop" \
        "application/vnd.flatpak.ref=rakuos-software.desktop"; do
        if ! grep -q "^${mime}$" "$MIMEAPPS"; then
            sed -i "/^\[${section}\]/a ${mime}" "$MIMEAPPS"
        fi
    done
done

# -----------------------------
# castlabs Electron for RakuOS WebApps (includes Widevine hooks)
# -----------------------------
ECS_VERSION="v40.7.0+wvcus"
ECS_URL="https://github.com/castlabs/electron-releases/releases/download/v40.7.0%2Bwvcus/electron-v40.7.0+wvcus-linux-x64.zip"
ELECTRON_DIR="/usr/lib/rakuos-electron"

echo "Downloading castlabs Electron ${ECS_VERSION}..."
curl -fL "${ECS_URL}" -o /tmp/electron.zip
mkdir -p "${ELECTRON_DIR}"
unzip -q /tmp/electron.zip -d "${ELECTRON_DIR}"
chmod +x "${ELECTRON_DIR}/electron"
rm /tmp/electron.zip
echo "Electron installed at ${ELECTRON_DIR}"

# -----------------------------
# Extract WidevineCDM from Chrome RPM
# Electron (castlabs ECS) has the hooks to load it but doesn't bundle the CDM
# -----------------------------
CHROME_RPM_URL="https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm"
WIDEVINE_DIR="${ELECTRON_DIR}/WidevineCdm"
TMP_DIR=$(mktemp -d)

echo "Downloading Chrome RPM to extract WidevineCDM..."
curl -fL "$CHROME_RPM_URL" -o "${TMP_DIR}/chrome.rpm"

echo "Extracting WidevineCDM..."
mkdir -p "$WIDEVINE_DIR"
cd "$TMP_DIR" || exit 1
rpm2cpio chrome.rpm | cpio -idmv

if [ -d "./opt/google/chrome/WidevineCdm" ]; then
    cp -r ./opt/google/chrome/WidevineCdm/* "$WIDEVINE_DIR/"
    if [ -f "${WIDEVINE_DIR}/manifest.json" ]; then
        WV_VERSION=$(grep '"version"' "$WIDEVINE_DIR/manifest.json" | head -n1 | awk -F '"' '{print $4}')
        echo "WidevineCDM installed in ${WIDEVINE_DIR} (version ${WV_VERSION})"
    else
        echo "WARNING: manifest.json not found in WidevineCDM folder"
    fi
else
    echo "Error: WidevineCdm directory not found in Chrome RPM."
    exit 1
fi

rm -rf "$TMP_DIR"
echo "Electron + WidevineCDM installation complete!"

# Disable services
systemctl disable flatpak-add-fedora-repos.service
systemctl mask akmods-keygen@akmods-keygen.service
systemctl mask systemd-remount-fs.service

#enable enable services
systemctl enable \
rakuos-base-protect.service \
rakuos-overlay-mount.service \
rakuos-overlay-sync.service \
rakuos-overlay-services.service \
rakuos-flatpaks.service \
rakuos-flatpak-watcher.service \
flatpak-cleanup.timer \
flatpak-repair.timer \
rpm-ostree-clean-metadata.timer \
rpm-ostree-clean-deployments.timer \
podman-prune.timer

systemctl enable --global \
rakuos-user.service

mkdir -p /var/log//var/log/akmods
touch /var/log//var/log/akmods/akmods.log
KVER="$(dnf5 repoquery --installed --qf '%{VERSION}-%{RELEASE}.%{ARCH}' kernel-cachyos)"
akmods --force --kernels "$KVER"

#Build initramfs
# Determine the installed kernel version
QUALIFIED_KERNEL=$(rpm -q --queryformat '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-cachyos)

# Generate module dependencies
depmod "$QUALIFIED_KERNEL"

# Generate initramfs for that kernel
/usr/bin/dracut --no-hostonly --kver "$QUALIFIED_KERNEL" --reproducible --zstd -v \
--add ostree --add fido2 -f "/usr/lib/modules/$QUALIFIED_KERNEL/initramfs.img"

chmod 0600 /usr/lib/modules/"$QUALIFIED_KERNEL"/initramfs.img
