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

# ── rum ───────────────────────────────────────────────────────────────────────
# rum's --bootstrap mode (rakuos-rum-staging, from rum's staging branch)
# installs into the empty root with that root's own rpmdb.
# RUM=/path/to/rum uses that binary instead (local testing).
if [ -z "${RUM:-}" ]; then
    rpm --import https://repo.rakuos.org/pubkey.gpg
    dnf -y install dnf5-plugins
    dnf -y config-manager addrepo --from-repofile=https://repo.rakuos.org/rakuos.repo
    dnf -y install rakuos-rum-staging
    RUM=rum
fi
if ! "${RUM}" --help 2>/dev/null | grep -q -- '--bootstrap'; then
    echo "ERROR: the repo's rakuos-rum-staging has no --bootstrap; build rum's staging branch first" >&2
    exit 1
fi

# ── Packages ──────────────────────────────────────────────────────────────────
mapfile -t PACKAGES < <(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "${HERE}/packages.txt")
# Fedora's kernel-install would try to build an initramfs for a kernel
# package; with layout=ostree it leaves that to the image build (drivers.sh
# runs dracut for kernel-rakuos). Set it before anything is installed.
mkdir -p "${ROOT}/usr/lib/kernel/install.conf.d"
printf '%s\n' "# Leave the initramfs to the image build; one kernel per image." "layout=ostree" \
    | tee "${ROOT}/usr/lib/kernel/install.conf" "${ROOT}/usr/lib/kernel/install.conf.d/00-bootc-kernel-layout.conf" >/dev/null
"${RUM}" --installroot "${ROOT}" --bootstrap --no-recommends install -y "${PACKAGES[@]}"

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
# Everything but root moves to /usr/lib/passwd and /usr/lib/group, which
# update with the image. /etc keeps root and the groups local users get
# added to (postprocess-conf.yaml etc-group-members).
ETC_GROUPS="root wheel systemd-journal tss kvm adm"
awk -F: '$1 != "root"' "${ROOT}/etc/passwd" > "${ROOT}/usr/lib/passwd"
awk -F: '$1 == "root"' "${ROOT}/etc/passwd" > "${ROOT}/etc/passwd.new"
awk -F: -v keep="${ETC_GROUPS}" 'BEGIN { n = split(keep, k, " "); for (i = 1; i <= n; i++) want[k[i]] = 1 } !($1 in want)' \
    "${ROOT}/etc/group" > "${ROOT}/usr/lib/group"
awk -F: -v keep="${ETC_GROUPS}" 'BEGIN { n = split(keep, k, " "); for (i = 1; i <= n; i++) want[k[i]] = 1 } ($1 in want)' \
    "${ROOT}/etc/group" > "${ROOT}/etc/group.new"
awk -F: '$1 == "root"' "${ROOT}/etc/shadow" > "${ROOT}/etc/shadow.new"
awk -F: -v keep="${ETC_GROUPS}" 'BEGIN { n = split(keep, k, " "); for (i = 1; i <= n; i++) want[k[i]] = 1 } ($1 in want)' \
    "${ROOT}/etc/gshadow" > "${ROOT}/etc/gshadow.new"
for f in passwd group shadow gshadow; do
    mode=$(stat -c %a "${ROOT}/etc/${f}")
    mv "${ROOT}/etc/${f}.new" "${ROOT}/etc/${f}"
    chmod "${mode}" "${ROOT}/etc/${f}"
done
chmod 0644 "${ROOT}/usr/lib/passwd" "${ROOT}/usr/lib/group"
rm -f "${ROOT}"/etc/passwd- "${ROOT}"/etc/group- "${ROOT}"/etc/shadow- "${ROOT}"/etc/gshadow-
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
