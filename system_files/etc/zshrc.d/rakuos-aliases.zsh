#!/usr/bin/env zsh

# ============================================================================ #
# Origami shell convenience layer (Zsh Port)
# ============================================================================ #

# --- Environment guard -------------------------------------------------------
[[ -n "${DISTROBOX_ENTER_PATH:-}" ]] && return

# --- Helper utilities --------------------------------------------------------
_command_exists() { command -v "$1" >/dev/null 2>&1; }

_should_nag() {
    local config_dir="${XDG_CONFIG_HOME:-$HOME/.config}"
    [[ -f "$config_dir/rakuos/nags_disabled" ]] && return 1
    [[ ! -o interactive ]] && return 1
    [[ ! -t 2 ]] && return 1
    for arg in "$@"; do
        [[ "$arg" == "--help" ]] && return 1
    done
    return 0
}

_nag_and_exec() {
    local tip="$1"; shift
    local target="$1"; shift
    _should_nag "$@" && printf '%s\n' "$tip" >&2
    command "$target" "$@"
}

nag() {
    local config_dir="${XDG_CONFIG_HOME:-$HOME/.config}"
    case "${1:-}" in
        off) mkdir -p "$config_dir/rakuos"; touch "$config_dir/rakuos/nags_disabled"; echo "Nags disabled." ;;
        on)  rm -f "$config_dir/rakuos/nags_disabled"; echo "Nags enabled." ;;
        *)   echo "Usage: nag {on|off}" ;;
    esac
}

# --- Wrappers ----------------------------------------------------------------
fastfetch() {
    if [[ $# -eq 0 ]]; then
        local config_dir="/usr/share/fastfetch/presets/rakuos"
        if [[ -f "$config_dir/rakuos-ascii.txt" && -f "$config_dir/rakuos-fastfetch.jsonc" ]]; then
            command fastfetch \
                -l "$config_dir/rakuos-ascii.txt" \
                --logo-color-1 blue \
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
