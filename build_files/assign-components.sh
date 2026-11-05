#!/usr/bin/env bash
#
# Assign files no RPM owns to their own chunkah components, so they get
# stable layers of their own instead of sharing catch-all layers with
# unrelated files. A build that only regenerates the rpm database or the
# manifest then changes just those layers, not the kernel or the prebaked
# Firefox next to them. chunkah reads the user.component and
# user.update-interval xattrs (https://github.com/coreos/chunkah#customizing-the-layers);
# files RPMs own are already grouped by package.
#
#   assign-components.sh generated          files the build generates (end of the build step)
#   assign-components.sh files <name> <dir> this repo's system_files, mounted at <dir>, as
#                                           component <name> (end of the cleanup step)
set -euo pipefail

# tag COMPONENT INTERVAL PATH...: every regular file and directory under the
# paths (symlinks can't carry user xattrs). A group that already carries the
# component (an edition image built on rakuos-base) is left as it is, since
# rewriting xattrs on files from a lower layer copies them up.
tag() {
    local component="$1" interval="$2" path first
    shift 2
    for path in "$@"; do
        [[ -e "$path" && ! -L "$path" ]] || continue
        first=$(find "$path" -type f -print -quit)
        if [[ -n "$first" ]] && [[ "$(getfattr --only-values -n user.component "$first" 2>/dev/null)" == "$component" ]]; then
            continue
        fi
        find "$path" \( -type f -o -type d \) -exec setfattr -n user.component -v "$component" {} +
        find "$path" \( -type f -o -type d \) -exec setfattr -n user.update-interval -v "$interval" {} +
    done
}

case "${1:-}" in
generated)
    shopt -s nullglob
    for kdir in /usr/lib/modules/*/; do
        kver=$(basename "$kdir")
        # The initramfs is rebuilt more often than the kernel itself.
        tag "initramfs-${kver}" weekly "${kdir}initramfs.img"
        # Everything else in the module tree (modules.dep and friends,
        # vmlinuz, System.map) goes with the kernel.
        find "$kdir" -mindepth 1 -maxdepth 1 ! -name initramfs.img -print0 \
            | while IFS= read -r -d '' p; do tag "kernel-${kver}" weekly "$p"; done
    done
    # The prebaked packages new installs start with (Firefox).
    tag rakuos-factory monthly /usr/share/factory/var
    # Package databases and manifests: rewritten by nearly every build.
    tag rpmdb daily /usr/share/rpm /usr/lib/sysimage/rpm /usr/lib/sysimage/rpm-ostree-base-db
    tag rakuos-manifests daily \
        /usr/share/rakuos/base-manifest.txt /usr/share/rakuos/protected-packages.txt
    # Downloaded or moved binaries.
    tag cpak monthly /usr/bin/cpak /usr/bin/cpak-storaged
    tag bootc monthly /usr/bin/bootc.real
    # Generated caches and databases.
    tag hwdb monthly /etc/udev/hwdb.bin /usr/lib/udev/hwdb.bin
    tag fontconfig-cache daily /usr/lib/fontconfig/cache
    tag ca-trust weekly /etc/pki/ca-trust/extracted
    ;;
files)
    name="${2:?component name}" src="${3:?system_files mount}"
    [[ -d "$src" ]] || exit 0
    # Each file this repo copies in, at its path in the image.
    (cd "$src" && find . -type f -printf '%P\0') \
        | while IFS= read -r -d '' rel; do tag "$name" quarterly "/$rel"; done
    ;;
*)
    echo "usage: $0 generated | files <name> <system_files dir>" >&2
    exit 2
    ;;
esac
