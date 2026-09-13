#!/usr/bin/env bash
# post-build-overlay.sh
# Runs inside the container build (Containerfile RUN step / GitHub Actions).
#
# Does NOT install packages — that's impossible inside a container build
# because overlayfs on /usr requires CAP_SYS_ADMIN and a real kernel mount.
#
# Instead, this script seeds /usr/share/factory/var/lib/rakuos/ so the first
# deployed system gets a populated /var/lib/rakuos/ state:
#   - packages.list populated from /usr/share/rakuos/packages.list
#   - overlay upper/work dirs created and empty
#   - overlay.state intentionally absent
#
# On first boot, rakuos-overlay-sync.service sees the missing state file,
# treats it as a fresh/reset system, and performs a full install into the
# overlay automatically — no user interaction needed.
#
# Usage (from your Containerfile):
#   RUN /usr/libexec/rakuos/build/post-build-overlay.sh

set -euo pipefail

FACTORY_VAR_ROOT="/usr/share/factory/var"
PACKAGES_LIST="$FACTORY_VAR_ROOT/lib/rakuos/packages.list"
UPPER_DIR="$FACTORY_VAR_ROOT/lib/rakuos/overlay/upper"
WORK_DIR="$FACTORY_VAR_ROOT/lib/rakuos/overlay/work"
STATE_FILE="$FACTORY_VAR_ROOT/lib/rakuos/overlay.state"
DIRTY_FILE="$FACTORY_VAR_ROOT/lib/rakuos/overlay.dirty"
FACTORY_RUM_RPMDB="$FACTORY_VAR_ROOT/lib/rakuos/rum-rpmdb"


echo "[rakuos] Seeding overlay state for first-boot install..."

prebake_overlay_from_installroot() {
    local installroot

    installroot="$(mktemp -d /var/tmp/rakuos-overlay-installroot.XXXXXX)"
    trap 'rm -rf "$installroot"' RETURN

    echo "[rakuos] Prebaking overlay packages into installroot via rum..."
    # No base rpmdb snapshot exists yet inside a build container, so rum's
    # OverlayPaths::detect() picks Standalone and resolves "already
    # installed" against the build container's own default rpmdb — exactly
    # the base image content this layer is being built on top of. --installroot
    # still redirects package files under $installroot/usr and creates a
    # fresh, disposable overlay rpmdb at $installroot/var/lib/rakuos/rum-rpmdb,
    # applying --nodeps/tsflags=noscripts automatically.
    rum install --installroot "$installroot" -y --refresh firefox
    rum remove --installroot "$installroot" -y firefox
    rm -f "$installroot/usr/share/icons/default/index.theme"

    echo "[rakuos] Copying prebaked /usr payload into overlay upper..."
    rm -rf "$UPPER_DIR" "$WORK_DIR"
    mkdir -p "$UPPER_DIR" "$WORK_DIR"
    cp -a "$installroot/usr/." "$UPPER_DIR/"

    echo "[rakuos] Copying prebaked rum overlay rpmdb into factory seed..."
    rm -rf "$FACTORY_RUM_RPMDB"
    mkdir -p "$(dirname "$FACTORY_RUM_RPMDB")"
    cp -a "$installroot/var/lib/rakuos/rum-rpmdb" "$FACTORY_RUM_RPMDB"

    if [[ -d "$installroot/etc" ]] && [[ -n "$(ls -A "$installroot/etc" 2>/dev/null)" ]]; then
        echo "[rakuos] Copying prebaked /etc payload into image..."
        cp -a "$installroot/etc/." /etc/
    fi

    echo "prebaked-installroot" > "$STATE_FILE"
    rm -f "$DIRTY_FILE"

    echo "[rakuos] Overlay prebake complete."
}


# ── Create runtime dirs ───────────────────────────────────────────────────────

mkdir -p "$FACTORY_VAR_ROOT/lib/rakuos"
mkdir -p "$UPPER_DIR"
mkdir -p "$WORK_DIR"

# ── Seed packages.list ────────────────────────────────────────────────────────

touch "$PACKAGES_LIST"
echo "[rakuos] packages.list is empty — no packages will be installed on first boot."

# ── Ensure stale state is cleared before prebake writes fresh state ───────────
rm -f "$STATE_FILE" "$DIRTY_FILE"

# Ensure packages.list ends with newline
sed -i -e '$a\' "$PACKAGES_LIST"

echo "[rakuos] stale overlay state cleared — prebake will write fresh first-boot state."
echo "[rakuos] Post-build seed complete."

echo "Appending minimal protected packages to protected-packages.txt..."
cat >> /usr/share/rakuos/protected-packages.txt << 'EOF'

# Minimal packages (from rakuos-minimal/build_files/build.sh)

EOF
# Protect the akmods/rpm-build chain from getting autoremoved as "unused
# deps" of selinux-policy — the chain itself (akmod-wl -> akmods -> rpm-build)
# has no real selinux Requires, it's just dnf's install-reason bookkeeping
# treating them as orphans once selinux-policy (which pulled rpm-plugin-selinux)
# is gone. mark install only flips reason=dependency -> reason=user in the
# local db; it does not install/reinstall anything.

rum remove -y 'selinux-policy*' 'policycoreutils-gui'
rum install -y libselinux

# selinux-policy is fully removed on RakuOS (AppArmor is the sole MAC), but the
# baked-in rpm-ostree treefile still defaults "selinux": true. rpm-ostree reads
# that flag on every deploy-time layering operation and tries to load a policy
# from / that no longer exists, causing spurious sepolicy-mismatch failures.
if [ -f /usr/share/rpm-ostree/treefile.json ]; then
    sed -i 's/"selinux": *true/"selinux": false/' /usr/share/rpm-ostree/treefile.json
fi

echo "Generating base file manifest..."
/usr/libexec/rakuos/generate-base-manifest

echo "Prebaking minimal overlay payload..."
prebake_overlay_from_installroot
