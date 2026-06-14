#!/usr/bin/env bash

# ============================================================================ #
# RakuOS shell convenience layer (Bash Port) ported from Origami Linux
# ============================================================================ #

# --- Environment guard -------------------------------------------------------
[[ -n "${DISTROBOX_ENTER_PATH:-}" ]] && return

# --- Helper utilities --------------------------------------------------------
_command_exists() { command -v "$1" >/dev/null 2>&1; }

# --- Wrappers ----------------------------------------------------------------
fastfetch() {
    if [[ $# -eq 0 ]]; then
        local config_dir="/usr/share/fastfetch/presets/rakuos"
        if [[ -f "$config_dir/rakuos-ascii.txt" && -f "$config_dir/rakuos-fastfetch.jsonc" ]]; then
            command fastfetch \
                -c "$config_dir/rakuos-fastfetch.jsonc"
        else
            command fastfetch
        fi
    else
        command fastfetch "$@"
    fi
}

neofetch() {
    fastfetch "$@"
}


alias sudoedit='sudoedit-rs'

# --- Interactive tooling -----------------------------------------------------
if [[ $- == *i* ]]; then
    _command_exists fzf      && eval "$(fzf --bash)"
    _command_exists starship && eval "$(starship init bash)"
    _command_exists zoxide   && eval "$(zoxide init bash --cmd cd)"
fi
