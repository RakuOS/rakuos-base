#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-unknown}"

RAKUOS_SHARE=/usr/share/rakuos
FIREFOX_DEPLOY_PATH="/var/lib/flatpak/app/org.mozilla.firefox/current/active/files/etc/firefox/policies"

if [[ "$ACTION" == "install" || "$ACTION" == "update" ]]; then

    echo "Applying Firefox policies"

    mkdir -p "$FIREFOX_DEPLOY_PATH"

    cp "$RAKUOS_SHARE/setup/firefox/policies.json" \
       "$FIREFOX_DEPLOY_PATH/policies.json"

fi

if [[ "$ACTION" == "uninstall" ]]; then

    echo "Cleaning Firefox overrides"

    flatpak override --system --reset org.mozilla.firefox || true

fi