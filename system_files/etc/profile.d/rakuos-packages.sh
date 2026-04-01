#!/usr/bin/env bash
# RakuOS package root environment integration.
# Adds /var/lib/rakuos/packages paths to the session environment so that
# packages installed via 'rakuos install' are visible to shells and GUI sessions.

RAKUOS_ROOT="/var/lib/rakuos/packages"

if [[ -d "$RAKUOS_ROOT/usr" ]]; then
    export PATH="$RAKUOS_ROOT/usr/bin:$RAKUOS_ROOT/usr/sbin:$PATH"
    export XDG_DATA_DIRS="$RAKUOS_ROOT/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
    export MANPATH="$RAKUOS_ROOT/usr/share/man${MANPATH:+:$MANPATH}"
    # GObject introspection typelibs (GTK/GLib apps installed via package root)
    export GI_TYPELIB_PATH="$RAKUOS_ROOT/usr/lib64/girepository-1.0:$RAKUOS_ROOT/usr/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
fi
