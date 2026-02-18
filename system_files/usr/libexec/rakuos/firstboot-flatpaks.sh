#!/usr/bin/env bash
set -euo pipefail

FLATPAK_LIST="/usr/share/rakuos/flatpaks.list"
MARKER_DIR="/var/lib/rakuos"
MARKER_FILE="$MARKER_DIR/default-flatpaks-installed"

echo "RakuOS: Checking default Flatpak installation state..."

# If marker exists, exit silently
if [[ -f "$MARKER_FILE" ]]; then
    echo "Default Flatpaks already installed. Skipping."
    exit 0
fi

echo "RakuOS: Installing default Flatpaks..."

# Exit cleanly if no list exists
if [[ ! -f "$FLATPAK_LIST" ]]; then
    echo "No flatpaks.list found, skipping."
    exit 0
fi

# Ensure marker directory exists
mkdir -p "$MARKER_DIR"

# Ensure Flathub exists
if ! flatpak remote-list | awk '{print $1}' | grep -qx "flathub"; then
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
fi

# Install apps
while read -r app; do
    [[ -z "$app" || "$app" =~ ^# ]] && continue
    flatpak install -y --noninteractive --system flathub "$app"
done < "$FLATPAK_LIST"

# Create marker only after successful install
mkdir -p /var/lib/rakuos
touch "$MARKER_FILE"

echo "RakuOS: Default Flatpak installation complete."