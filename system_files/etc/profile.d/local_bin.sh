#!/usr/bin/env bash
# Add the user's ~/.local/bin to PATH
LOCAL_BIN="$HOME/.local/bin"

if [ -d "$LOCAL_BIN" ] && [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    export PATH="$LOCAL_BIN:$PATH"
fi
