#!/usr/bin/env zsh

# ============================================================================ #
# RakuOS shell convenience layer (Zsh Port) ported from Origami Linux
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

# --- Modern replacements -----------------------------------------------------
alias docker='podman'
alias docker-compose='podman-compose'
alias sudo='sudo-rs'
alias su='su-rs'

# --- Interactive tooling -----------------------------------------------------
if [[ -o interactive ]]; then
    _command_exists fzf      && eval "$(fzf --zsh)"
    _command_exists starship && eval "$(starship init zsh)"
    _command_exists zoxide   && eval "$(zoxide init zsh --cmd cd)"
fi
