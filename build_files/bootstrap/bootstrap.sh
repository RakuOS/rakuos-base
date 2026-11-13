#!/bin/bash
# Bootstrap the root filesystem rakuos-base and rakuos-minimal are built on,
# from nothing: rum installs packages.txt into an empty directory, then this
# script does what Fedora's bootc image build does after its package install.
#
# Modeled on Fedora's bootc base images (gitlab.com/fedora/bootc/base-images,
# MIT licensed, Copyright Fedora CoreOS Authors): the steps below follow its
# "minimal" manifest (minimal/*.yaml) and its finalize.d script, and the
# rpm-ostree compose rootfs steps those rely on (users in nss-altfiles, /var
# as tmpfiles.d, the ostree directory layout). No rpm-ostree is used.
#
# Runs in a plain Fedora container with the RakuOS repo; usage:
#   bootstrap.sh TARGET_DIR
set -xeuo pipefail

ROOT="$1"
HERE="$(dirname "$(readlink -f "$0")")"
mkdir -p "${ROOT}"

# ── RakuOS repo and rum ───────────────────────────────────────────────────────
# rum's --bootstrap mode (rakuos-rum-staging, from rum's staging branch)
# installs into the empty root with that root's own rpmdb, from the repos of
# this build container (/etc/yum.repos.d), set up the way build.sh sets up
# the image's: the RakuOS repo, plus rakuos-v3 for v3 images and rakuos-v3
# and rakuos-v4 for v4 images (RAKUOS_ISA_LEVEL, a --build-arg from CI), and
# rum's repo overrides (the excludepkgs= that keep Fedora's builds of
# packages RakuOS rebuilds out).
# RUM=/path/to/rum uses that binary instead and skips the repo setup (local
# testing; the ISA repos are still enabled if rakuos.repo is there).
RAKUOS_ISA_LEVEL="${RAKUOS_ISA_LEVEL:-v2}"
case "${RAKUOS_ISA_LEVEL}" in
    v2) isa_repos="" ;;
    v3) isa_repos="v3" ;;
    v4) isa_repos="v3 v4" ;;
    *) echo "Unknown RAKUOS_ISA_LEVEL '${RAKUOS_ISA_LEVEL}' (want v2, v3 or v4)" >&2; exit 1 ;;
esac
if [ -z "${RUM:-}" ]; then
    rpm --import https://repo.rakuos.org/pubkey.gpg
    dnf -y install dnf5-plugins
    dnf -y config-manager addrepo --from-repofile=https://repo.rakuos.org/rakuos.repo
fi
if [ -f /etc/yum.repos.d/rakuos.repo ]; then
    for isa in ${isa_repos}; do
        sed -i "/^\[rakuos-${isa}\]/,/^\[/ s/^enabled=0/enabled=1/" /etc/yum.repos.d/rakuos.repo
        grep -A3 "^\[rakuos-${isa}\]" /etc/yum.repos.d/rakuos.repo | grep -q '^enabled=1' \
            || { echo "ERROR: couldn't enable rakuos-${isa} in /etc/yum.repos.d/rakuos.repo" >&2; exit 1; }
    done
fi
if [ -z "${RUM:-}" ]; then
    dnf -y install rakuos-rum-staging rakuos-rum-repo-overrides-staging
    RUM=rum
fi
if ! "${RUM}" --help 2>/dev/null | grep -q -- '--bootstrap'; then
    echo "ERROR: the repo's rakuos-rum-staging has no --bootstrap; build rum's staging branch first" >&2
    exit 1
fi

# ── Packages ──────────────────────────────────────────────────────────────────
mapfile -t PACKAGES < <(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "${HERE}/packages.txt")
# RakuOS's release and branding packages from the start, never Fedora's:
# rakuos-release-common replaces fedora-release/-common (and provides the
# system-release(<version>) fedora-repos needs), rakuos-logos replaces
# fedora-logos/redhat-logos/system-logos. Of the rest of rakuos-branding
# only what both base and minimal ship: the Plymouth and GRUB themes and the
# fastfetch preset. The base image adds the rakuos-branding meta package
# (GTK theme, icon theme, fonts config) in build.sh. Staging images (RAKUOS_STAGING=1)
# get rakuos-release-staging, as in build.sh. The Fedora packages are
# excluded outright so nothing can pull them in.
RAKUOS_RELEASE_PKG="rakuos-release"
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    RAKUOS_RELEASE_PKG="rakuos-release-staging"
fi
BRANDING=(rakuos-logos rakuos-plymouth-theme rakuos-grub-theme rakuos-fastfetch-preset)
# rakuos-core too (the overlay/layer initrd, updater, rakuos command), which
# every image ships: rakuos-core-staging on staging, built from rakuos-core's
# staging branch (it provides rakuos-core). Its %post dracut run finds no
# kernel yet; drivers.sh builds the initramfs once the image is complete.
RAKUOS_CORE_PKG="rakuos-core"
if [ "${RAKUOS_STAGING:-0}" = "1" ]; then
    RAKUOS_CORE_PKG="rakuos-core-staging"
fi
PACKAGES+=("${RAKUOS_RELEASE_PKG}" "${BRANDING[@]}" "${RAKUOS_CORE_PKG}")
FEDORA_BRANDING="fedora-release,fedora-release-common,fedora-release-identity-*,fedora-release-container,fedora-logos,fedora-logos-*,redhat-logos,generic-release,generic-logos"
# Fedora's kernel-install would try to build an initramfs for a kernel
# package; with layout=ostree it leaves that to the image build (drivers.sh
# runs dracut for each kernel). Set it before anything is installed.
mkdir -p "${ROOT}/usr/lib/kernel/install.conf.d"
printf '%s\n' "# Leave the initramfs to the image build." "layout=ostree" \
    | tee "${ROOT}/usr/lib/kernel/install.conf" "${ROOT}/usr/lib/kernel/install.conf.d/00-bootc-kernel-layout.conf" >/dev/null

# ── Pinned account IDs ────────────────────────────────────────────────────────
# Package scriptlets create system accounts with the next free ID, so the
# same account can get a different ID in each build, and a file the image
# ships owned by it then belongs to someone else on a machine installed from
# an older build. static-ids/{passwd,group} pin every account the images use.
# setup goes first (it ships /etc/passwd and /etc/group with the fixed
# Fedora IDs); the pinned accounts are added before anything else installs,
# so scriptlets find them and keep their IDs. They're also written to
# /usr/lib/passwd and /usr/lib/group (altfiles), where the desktop images'
# package installs see them. finalize-accounts.sh then reports any account
# that isn't pinned.
"${RUM}" --installroot "${ROOT}" --bootstrap --no-recommends install -y setup
for f in passwd group; do
    awk -F: -v f="${f}" 'NR == FNR { id[$1] = $3; next } ($1 in id) && id[$1] != $3 {
        print "ERROR: setup has " f " entry " $1 " as " $3 ", static-ids pins it as " id[$1]; bad = 1 } END { exit bad }' \
        "${HERE}/static-ids/${f}" "${ROOT}/etc/${f}"
    awk -F: 'NR == FNR { have[$1] = 1; next } !($1 in have)' "${ROOT}/etc/${f}" "${HERE}/static-ids/${f}" >> "${ROOT}/etc/${f}"
done
mkdir -p "${ROOT}/usr/lib"
awk -F: '$1 != "root"' "${HERE}/static-ids/passwd" > "${ROOT}/usr/lib/passwd"
awk -F: '$1 !~ /^(root|wheel|systemd-journal|tss|kvm|adm)$/' "${HERE}/static-ids/group" > "${ROOT}/usr/lib/group"

"${RUM}" --installroot "${ROOT}" --bootstrap --no-recommends --exclude "${FEDORA_BRANDING}" install -y "${PACKAGES[@]}"
fedora_left=$(rpm --root "${ROOT}" -qa --qf '%{NAME}\n' | grep -E '^(fedora-release|fedora-logos|redhat-logos|generic-release|generic-logos)' || true)
if [ -n "${fedora_left}" ]; then
    echo "ERROR: Fedora release/branding packages got installed: ${fedora_left}" >&2
    exit 1
fi
rpm --root "${ROOT}" -q "${RAKUOS_RELEASE_PKG}" rakuos-release-common "${BRANDING[@]}" "${RAKUOS_CORE_PKG}"

# ── Kernels ───────────────────────────────────────────────────────────────────
# Both kernel variants for this ISA level and channel (see kernels.sh), with
# their -devel and -devel-matched. Without scriptlets: they'd run depmod and
# dracut, which drivers.sh does for each kernel once the image is complete.
source "${HERE}/../kernels.sh"
# shellcheck disable=SC2046 # one word per package
"${RUM}" --installroot "${ROOT}" --bootstrap --no-recommends --setopt=tsflags=noscripts \
    install -y $(kernel_install_pkgs)
rpm --root "${ROOT}" -q "${KERNEL_PKGS[@]}"

# rpm, systemd and ostree are RakuOS's own builds (RPM 6 without the SELinux
# plugin, our systemd and ostree); rum's repo overrides keep Fedora's builds
# out. Check every installed package of theirs is a version the RakuOS repos
# publish, so a Fedora build can never slip in unnoticed.
if [ -f /etc/yum.repos.d/rakuos.repo ]; then
    rakuos_builds=$(dnf -q repoquery --repo 'rakuos*' --qf '%{name}-%{evr}.%{arch}\n' 2>/dev/null | sort -u)
    [ -n "${rakuos_builds}" ] || { echo "ERROR: couldn't list the RakuOS repos' packages" >&2; exit 1; }
    # Installed rpm*/systemd*/ostree* packages the RakuOS repos also build
    # (rpm-sequoia, say, is Fedora's and stays out of the check).
    rakuos_names=$(sed -E 's/-[^-]+-[^-]+$//' <<< "${rakuos_builds}" | sort -u)
    own_pkgs=$(rpm --root "${ROOT}" -qa --qf '%{name} %{name}-%{evr}.%{arch}\n' \
        | awk 'NR == FNR { ours[$1] = 1; next } ($1 ~ /^(rpm|python3-rpm|systemd|ostree)/) && ($1 in ours) { print $2 }' \
            <(echo "${rakuos_names}") - | sort)
    for pkg in rpm systemd ostree; do
        grep -q "^${pkg}-[0-9]" <<< "${own_pkgs}" || { echo "ERROR: ${pkg} isn't installed" >&2; exit 1; }
    done
    not_ours=$(comm -23 <(echo "${own_pkgs}") <(echo "${rakuos_builds}"))
    if [ -n "${not_ours}" ]; then
        echo "ERROR: these aren't the RakuOS repo's builds:" >&2
        echo "${not_ours}" >&2
        exit 1
    fi
    echo "rpm/systemd/ostree from the RakuOS repo:"
    echo "${own_pkgs}"
else
    echo "WARNING: no rakuos.repo in the build container; can't check where rpm/systemd/ostree came from"
fi

in_root() { chroot "${ROOT}" "$@"; }

# ── Files packages ship that a bootc image doesn't want ───────────────────────
# (minimal/manifest.yaml, minimal/grub2-removals.yaml)
rm -f "${ROOT}/usr/lib/systemd/system/sysinit.target.wants/systemd-firstboot.service"
rm -f "${ROOT}/etc/grub.d/08_fallback_counting" "${ROOT}/etc/grub.d/10_reset_boot_success" \
      "${ROOT}/etc/grub.d/12_menu_auto_hide"
in_root rpm -ql grub2-tools | grep '^/usr/lib/systemd/' | while read -r f; do
    [ -d "${ROOT}${f}" ] || rm -f "${ROOT}${f}"
done

# ── ostree / composefs (minimal/ostree.yaml) ──────────────────────────────────
mkdir -p "${ROOT}/usr/lib/ostree"
cat > "${ROOT}/usr/lib/ostree/prepare-root.conf" <<'EOF'
[composefs]
enabled = yes
[sysroot]
readonly = true
EOF

# ── initramfs (minimal/initramfs.yaml) ────────────────────────────────────────
mkdir -p "${ROOT}/usr/lib/dracut/dracut.conf.d"
cat > "${ROOT}/usr/lib/dracut/dracut.conf.d/20-bootc-base.conf" <<'EOF'
# A generic image; hostonly makes no sense in a server-side build.
hostonly=no
# Dracut can't set security.* xattrs at build time.
export DRACUT_NO_XATTR=1
add_dracutmodules+=" kernel-modules dracut-systemd systemd-initrd base ostree bootc "
EOF
cat > "${ROOT}/usr/lib/dracut/dracut.conf.d/22-bootc-generic.conf" <<'EOF'
add_dracutmodules+=" virtiofs "
EOF
cat > "${ROOT}/usr/lib/dracut/dracut.conf.d/49-bootc-tpm2-tss.conf" <<'EOF'
# For systemd-cryptsetup TPM2 unlocking.
add_dracutmodules+=" tpm2-tss "
EOF
cat > "${ROOT}/usr/lib/dracut/dracut.conf.d/59-altfiles.conf" <<'EOF'
# Users and groups live in nss-altfiles (/usr/lib/passwd, /usr/lib/group).
install_items+=" /usr/lib/passwd /usr/lib/group "
EOF

# ── dnf: one kernel, no running-kernel protection (minimal/kernel-install.yaml)
mkdir -p "${ROOT}/usr/share/dnf5/libdnf.conf.d"
printf '[main]\ninstallonlypkgs=\x27\x27\n' > "${ROOT}/usr/share/dnf5/libdnf.conf.d/20-ostree-installonlypkgs.conf"
printf '[main]\nprotect_running_kernel=False\n' > "${ROOT}/usr/share/dnf5/libdnf.conf.d/20-ostree-protect_running_kernel.conf"

# ── tmpfiles and basic fixes (minimal/tmpfiles.yaml, minimal/basic-fixes.yaml)
cat > "${ROOT}/usr/lib/tmpfiles.d/bootc-base-rpmstate.conf" <<'EOF'
d /var/lib/rpm-state 0755 - - -
EOF
rm -f "${ROOT}/usr/lib/tmpfiles.d/home.conf"
# tmpfs on /tmp: / is read-only with composefs.
mkdir -p "${ROOT}/usr/lib/systemd/system/local-fs.target.wants"
[ -e "${ROOT}/usr/lib/systemd/system/local-fs.target.wants/tmp.mount" ] \
    || ln -sf ../tmp.mount "${ROOT}/usr/lib/systemd/system/local-fs.target.wants/tmp.mount"
if [ -f "${ROOT}/usr/lib/tmpfiles.d/provision.conf" ]; then
    sed -i -e 's, /root, /var/roothome,' -e '/^d- \/var\/roothome /d' "${ROOT}/usr/lib/tmpfiles.d/provision.conf"
fi

# ── CA trust refresh after updates (minimal/ca-trust.yaml) ────────────────────
install -m 0644 "${HERE}/atomic-update-ca-trust.service" "${ROOT}/usr/lib/systemd/system/atomic-update-ca-trust.service"
mkdir -p "${ROOT}/usr/lib/systemd/system/sysinit.target.wants"
ln -sf ../atomic-update-ca-trust.service "${ROOT}/usr/lib/systemd/system/sysinit.target.wants/atomic-update-ca-trust.service"

# ── bootupd update payload (minimal/bootupd.yaml) ─────────────────────────────
# Not here: bootupctl needs /proc, which this chroot doesn't have, and the
# metadata has to describe the final grub2/shim anyway. post-build.sh runs
# `bootupctl backend generate-update-metadata /` at the end of the build.
rm -rf "${ROOT}/usr/lib/ostree-boot/loader"

# ── Presets are canonical (minimal/systemd-presets.yaml) ──────────────────────
cat > "${ROOT}/usr/lib/systemd/system-preset/85-bootc.preset" <<'EOF'
# Disable dnf-makecache.timer on bootc/image mode systems
disable dnf-makecache.timer
EOF
echo "enable bootloader-update.service" > "${ROOT}/usr/lib/systemd/system-preset/85-bootc-bootloader-update.preset"
# Undo package scriptlets enabling units directly.
rm -rf "${ROOT}"/etc/systemd/system/* "${ROOT}"/etc/systemd/user/*
in_root systemctl preset-all
in_root systemctl --global preset-all

# ── Hardware database (its scriptlet can't run without /proc in the root) ─────
in_root systemd-hwdb update --usr

# ── Users and groups in nss-altfiles (rpm-ostree's passwd handling) ───────────
# Everything but root and the groups local users join moves to
# /usr/lib/passwd and /usr/lib/group, which update with the image.
"${HERE}/../finalize-accounts.sh" "${ROOT}"
# nsswitch.conf is generated by authselect (it's a symlink into
# /etc/authselect), so an edit to it is lost the next time authselect
# regenerates it, e.g. when a package enables a feature. Turn on the
# profile's with-altfiles feature instead, which puts altfiles on the
# passwd and group lines for good.
if in_root authselect current >/dev/null 2>&1; then
    in_root authselect enable-feature with-altfiles
else
    in_root authselect select local with-altfiles --force
fi
in_root grep -qE '^passwd:.*altfiles' /etc/nsswitch.conf && in_root grep -qE '^group:.*altfiles' /etc/nsswitch.conf \
    || { echo "ERROR: altfiles isn't in nsswitch.conf after enabling with-altfiles" >&2; exit 1; }

# ── Image identity and layout ─────────────────────────────────────────────────
# Empty machine-id: systemd sets it on first boot (machineid-compat).
: > "${ROOT}/etc/machine-id"
# The ostree layout: /sysroot holds the deployments; the mutable top-level
# directories live in /var (or /run for /media). /opt and /usr/local are
# handled by the Containerfile.
mkdir -p "${ROOT}/sysroot"
ln -sfn sysroot/ostree "${ROOT}/ostree"
for pair in home:var/home root:var/roothome srv:var/srv mnt:var/mnt media:run/media; do
    dir="${pair%%:*}"; target="${pair#*:}"
    rm -rf "${ROOT:?}/${dir}"
    ln -s "${target}" "${ROOT}/${dir}"
done
# rpm's database is in /usr/lib/sysimage/rpm; older tools look in /usr/share/rpm.
[ -e "${ROOT}/usr/share/rpm" ] || ln -s ../lib/sysimage/rpm "${ROOT}/usr/share/rpm"

# ── /var: tmpfiles.d entries instead of content (rpm-ostree autovar) ──────────
# A bootc image's /var is only the initial state of the machine's own /var;
# systemd-tmpfiles creates what packages expect there at boot.
AUTOVAR="${ROOT}/usr/lib/tmpfiles.d/rakuos-bootstrap-var.conf"
echo "# Directories the bootstrapped packages ship in /var (generated)." > "${AUTOVAR}"
(cd "${ROOT}" && find var -mindepth 1 \( -type d -o -type l \) -printf '%y %m %U %G /%p %l\n') | sort -k5 \
    | while read -r type mode uid gid path link; do
        case "${path}" in /var/run|/var/lock|/var/tmp) continue ;; esac
        if [ "${type}" = "l" ]; then
            echo "L ${path} - - - - ${link}"
        else
            echo "d ${path} ${mode} ${uid} ${gid} - -"
        fi
    done >> "${AUTOVAR}"
(cd "${ROOT}" && find var -mindepth 1 -type f -printf 'Dropping /%p (file in /var)\n')
rm -rf "${ROOT:?}"/var/*
# finalize.d/01-var.sh
ln -s ../run "${ROOT}/var/run"
mkdir -p "${ROOT}/var/lib/rpm-state"
mkdir -m 1777 "${ROOT}/var/tmp"

# rpm-ostree workaround: the root directory must be world-readable.
chmod a+rx "${ROOT}"

echo "Bootstrapped ${ROOT}: $(rpm --root "${ROOT}" -qa | wc -l) packages"

# Last, after every rpm call: sqlite's shared-memory and write-ahead files
# aren't part of the database once it's closed (rpm-ostree's
# rpmdb-normalize). A WAL that still holds data would be lost, so fail.
DB="${ROOT}/usr/lib/sysimage/rpm"
if [ -s "${DB}/rpmdb.sqlite-wal" ]; then
    echo "ERROR: ${DB}/rpmdb.sqlite-wal isn't empty" >&2
    exit 1
fi
rm -f "${DB}/rpmdb.sqlite-shm" "${DB}/rpmdb.sqlite-wal"
