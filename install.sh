#!/usr/bin/env bash
# Install the W11 Xcursor theme from this repository.
set -euo pipefail

THEME="W11-Light-default"
SIZE="${1:-24}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/theme/$THEME"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/icons/$THEME"

if [ ! -d "$SRC/cursors" ]; then
    echo "error: missing theme files at $SRC" >&2
    exit 1
fi

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -a "$SRC" "$DEST"
echo "installed: $DEST"

if command -v gsettings >/dev/null 2>&1; then
    if gsettings set org.gnome.desktop.interface cursor-theme "$THEME" 2>/dev/null; then
        gsettings set org.gnome.desktop.interface cursor-size "$SIZE" 2>/dev/null || true
        echo "gsettings: cursor-theme=$THEME cursor-size=$SIZE"
    else
        echo "note: gsettings unavailable (no D-Bus session?), set the theme manually"
    fi
fi

cat <<EOF

niri users: add this to ~/.config/niri/config.kdl

    cursor {
        xcursor-theme "$THEME"
        xcursor-size $SIZE
    }

Then log out and back in (compositors cache cursor images).
EOF
