#!/usr/bin/env fish

# ============================================================================ #
# Origami shell convenience layer (Fish Port)
# ============================================================================ #

# --- Environment guard -------------------------------------------------------
if set -q DISTROBOX_ENTER_PATH
    return
end

# --- Helper utilities --------------------------------------------------------
function _command_exists
    command -v "$argv[1]" >/dev/null 2>&1
end

function _should_nag
    # 0. Check user preference
    set -l config_dir (set -q XDG_CONFIG_HOME; and echo $XDG_CONFIG_HOME; or echo $HOME/.config)
    if test -f "$config_dir/rakuos/nags_disabled"
        return 1
    end

    # 1. Check if interactive
    if not status is-interactive
        return 1
    end

    # 2. Don't nag if stderr isn't a TTY (Fish uses 2 for stderr)
    if not test -t 2
        return 1
    end

    # 3. Don't nag if the user is asking for --help
    for arg in $argv
        if test "$arg" = "--help"
            return 1
        end
    end

    return 0
end

function _nag_and_exec
    set -l tip $argv[1]
    set -e argv[1]
    set -l target $argv[1]
    set -e argv[1]

    if _should_nag $argv
        printf '%s\n' "$tip" >&2
    end

    command "$target" $argv
end

function nag
    set -l config_dir (set -q XDG_CONFIG_HOME; and echo $XDG_CONFIG_HOME; or echo $HOME/.config)
    switch "$argv[1]"
        case off
            mkdir -p "$config_dir/rakuos"
            touch "$config_dir/rakuos/nags_disabled"
            echo "Nags disabled."
        case on
            rm -f "$config_dir/rakuos/nags_disabled"
            echo "Nags enabled."
        case '*'
            echo "Usage: nag {on|off}"
    end
end

# --- Wrappers ----------------------------------------------------------------
function fastfetch
    if test (count $argv) -eq 0
        set -l config_dir "/usr/share/fastfetch/presets/rakuos"
        if test -f "$config_dir/rakuos-ascii.txt"; and test -f "$config_dir/rakuos-fastfetch.jsonc"
            command fastfetch \
                -c "$config_dir/rakuos-fastfetch.jsonc"
        else
            command fastfetch
        end
    else
        command fastfetch $argv
    end
end

function neofetch
    if test (count $argv) -eq 0
        set -l config_dir "/usr/share/fastfetch/presets/rakuos"
        if test -f "$config_dir/rakuos-ascii.txt"; and test -f "$config_dir/rakuos-fastfetch.jsonc"
            command fastfetch \
                -c "$config_dir/rakuos-fastfetch.jsonc"
        else
            command fastfetch
        end
    else
        command fastfetch $argv
    end
end

# --- Modern replacements -----------------------------------------------------
# Note: These are applied early but will be overridden by nag functions if names overlap
alias docker podman
alias docker-compose podman-compose
alias sudo sudo-rs
alias su su-rs

# --- Interactive tooling -----------------------------------------------------
if status is-interactive
    set -g fish_greeting "" # Disable welcome message

    if _command_exists fzf; fzf --fish | source; end
    if _command_exists starship; starship init fish | source; end
    if _command_exists zoxide; zoxide init fish --cmd cd | source; end
end
