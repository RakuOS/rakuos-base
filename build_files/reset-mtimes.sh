#!/usr/bin/env bash
#
# Reset file modification times to the Unix epoch so unchanged files give
# identical layers from build to build. Otherwise every file a build touches
# (regenerated caches, the rpm database, the initramfs, files copied in) gets
# a new mtime, chunkah's layers holding them get new digests, and users
# download them again even though nothing in them changed.
#
# chunkah's SOURCE_DATE_EPOCH would also clamp mtimes, but it changes the
# layer plan too (see https://github.com/coreos/chunkah/issues/160), so it's
# done here. Booted bootc/OSTree systems show epoch mtimes anyway.
#
# Run at the end of each build step: a file a step changed is still in that
# step's own layer, where resetting it is cheap. Touching a file from a lower
# layer makes overlayfs copy all of it up. Files already at the epoch are
# left alone.
set -euo pipefail

find /usr /etc /opt -newermt '1970-01-01T00:00:00Z' \
    -exec touch -h -a -m -d '1970-01-01T00:00:00Z' {} +
