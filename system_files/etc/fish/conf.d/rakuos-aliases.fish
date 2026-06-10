#!/usr/bin/env fish

# ============================================================================ #
# RakuOS shell convenience layer (Fish Port) ported from Origami Linux
# ============================================================================ #

# --- Environment guard -------------------------------------------------------
if set -q DISTROBOX_ENTER_PATH
    return
end

# --- Helper utilities --------------------------------------------------------
function _command_exists
    command -v "$argv[1]" >/dev/null 2>&1
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

# --- uutils-coreutils aliases ------------------------------------------------
function _register_uutils_aliases
    for uu_bin in /usr/bin/uu-*
        if test -e "$uu_bin"
            set -l base_cmd (basename "$uu_bin")
            set -l std_cmd (string replace -r '^uu-' '' "$base_cmd")
            switch "$std_cmd"
                case ls cat test \[
                    continue
            end
            alias "$std_cmd" "$uu_bin"
        end
    end
end
_register_uutils_aliases

# --- Modern replacements -----------------------------------------------------
alias cat='bat'
alias ls='lsd'
alias l='lsd -l'
alias la='lsd -a'
alias lla='lsd -la'
alias lt='lsd --tree'

alias sudoedit="sudoedit-rs"

# -- Convience Alias's --------------------------------------------------------
alias update="sudo rakuos system-upgrade"

# --- Interactive tooling -----------------------------------------------------
if status is-interactive
    set -g fish_greeting "" # Disable welcome message

    if _command_exists fzf; fzf --fish | source; end
    if _command_exists starship; starship init fish | source; end
    if _command_exists zoxide; zoxide init fish --cmd cd | source; end
end
