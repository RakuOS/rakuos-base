#!/bin/bash
# Move the image's system accounts into nss-altfiles (/usr/lib/passwd and
# /usr/lib/group), the way rpm-ostree composes do. /etc keeps only root and
# the groups local users get added to (postprocess-conf.yaml
# etc-group-members), so a machine's own /etc/passwd and /etc/group never
# hide accounts a later image adds.
#
# Account IDs are pinned in bootstrap/static-ids/{passwd,group}: bootstrap.sh
# seeds every one of them before it installs packages, so package scriptlets
# (here and in the desktop images, which see them through altfiles) find the
# account and keep its ID. An account that isn't in the lists gets whatever
# ID is free when it's created, which can differ from build to build; this
# script prints those so they can be added to the lists.
#
# Usage: finalize-accounts.sh [ROOT]   (default /)
# bootstrap.sh runs it on the new root; post-build.sh installs it as
# /usr/libexec/rakuos/finalize-accounts for the desktop images' post-build.sh.
set -euo pipefail

ROOT="${1:-}"
ETC_GROUPS="root wheel systemd-journal tss kvm adm"

keep_group() { awk -F: -v keep="${ETC_GROUPS}" -v want="$1" \
    'BEGIN { n = split(keep, k, " "); for (i = 1; i <= n; i++) w[k[i]] = 1 } (($1 in w) == want)'; }

touch "${ROOT}/usr/lib/passwd" "${ROOT}/usr/lib/group"

# An account in both places with different IDs means a pinned ID was ignored.
for f in passwd group; do
    awk -F: -v f="${f}" 'NR == FNR { id[$1] = $3; next } ($1 in id) && id[$1] != $3 {
        print "ERROR: " f " entry " $1 " is " $3 " in /etc but pinned as " id[$1] " in /usr/lib"; bad = 1 } END { exit bad }' \
        "${ROOT}/usr/lib/${f}" "${ROOT}/etc/${f}"
done

# Accounts the scriptlets created in /etc that the pinned lists don't know.
new_users=$(awk -F: 'NR == FNR { known[$1] = 1; next } $1 != "root" && !($1 in known)' \
    "${ROOT}/usr/lib/passwd" "${ROOT}/etc/passwd")
new_groups=$(awk -F: 'NR == FNR { known[$1] = 1; next } !($1 in known)' \
    "${ROOT}/usr/lib/group" "${ROOT}/etc/group" | keep_group 0)
if [ -n "${new_users}${new_groups}" ]; then
    echo "WARNING: system accounts without a pinned ID (they can get a different ID in the next build)."
    echo "Add these lines to rakuos-base build_files/bootstrap/static-ids/:"
    [ -z "${new_users}" ] || sed 's/^/passwd: /' <<< "${new_users}"
    [ -z "${new_groups}" ] || sed 's/^/group:  /' <<< "${new_groups}"
fi

# /etc/passwd -> root only; everything else is appended to /usr/lib/passwd
# (an account already there keeps its altfiles entry).
awk -F: 'NR == FNR { have[$1] = 1; next } $1 != "root" && !($1 in have)' \
    "${ROOT}/usr/lib/passwd" "${ROOT}/etc/passwd" >> "${ROOT}/usr/lib/passwd"
awk -F: 'NR == FNR { have[$1] = 1; next } !($1 in have)' \
    "${ROOT}/usr/lib/group" "${ROOT}/etc/group" | keep_group 0 >> "${ROOT}/usr/lib/group"

awk -F: '$1 == "root"' "${ROOT}/etc/passwd" > "${ROOT}/etc/passwd.new"
keep_group 1 < "${ROOT}/etc/group" > "${ROOT}/etc/group.new"
# shadow keeps an entry for every account, the altfiles ones included: their
# passwd field is "x", so pam_unix looks them up in /etc/shadow and fails
# with AUTHINFO_UNAVAIL when there's none (the plasmalogin/gdm greeter's
# user@.service can't start: black screen). Existing entries are kept; a
# seeded account that never went through useradd gets a locked one. This is
# how rpm-ostree images ship /etc/shadow.
{
    awk -F: '$1 == "root"' "${ROOT}/etc/shadow"
    awk -F: 'NR == FNR { sh[$1] = $0; next } $1 != "root" && !seen[$1]++ {
        print ($1 in sh) ? sh[$1] : $1 ":!*:::::::" }' \
        "${ROOT}/etc/shadow" "${ROOT}/usr/lib/passwd"
} > "${ROOT}/etc/shadow.new"
# gshadow: the kept groups, adding a locked entry for any that lack one
# (seeded groups never went through groupadd).
{
    keep_group 1 < "${ROOT}/etc/gshadow"
    awk -F: 'NR == FNR { have[$1] = 1; next } !($1 in have) { print $1 ":!::" }' \
        "${ROOT}/etc/gshadow" "${ROOT}/etc/group.new"
} > "${ROOT}/etc/gshadow.new"

for f in passwd group shadow gshadow; do
    mode=$(stat -c %a "${ROOT}/etc/${f}")
    mv "${ROOT}/etc/${f}.new" "${ROOT}/etc/${f}"
    chmod "${mode}" "${ROOT}/etc/${f}"
done
chmod 0644 "${ROOT}/usr/lib/passwd" "${ROOT}/usr/lib/group"
rm -f "${ROOT}"/etc/passwd- "${ROOT}"/etc/group- "${ROOT}"/etc/shadow- "${ROOT}"/etc/gshadow-
