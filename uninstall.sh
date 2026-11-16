#!/usr/bin/env bash
# Attack Shark Profile Switcher - Linux uninstaller.
set -uo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
APP_HOME="$DATA_HOME/attack-shark"
UDEV_RULE="/etc/udev/rules.d/70-attack-shark.rules"

ask() {
    local reply
    read -r -p "    $1 [s/N] " reply || reply=""
    [[ "$reply" =~ ^[sSyY] ]]
}

echo "Removendo o Attack Shark..."
pkill -f "$APP_HOME/app/switcher.py" 2>/dev/null || true
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
rm -f "$HOME/.local/bin/attack-shark" \
      "$DATA_HOME/applications/attack-shark.desktop" \
      "$CONFIG_HOME/autostart/attack-shark.desktop" \
      "$DESKTOP_DIR/attack-shark.desktop"
rm -rf "$APP_HOME"
echo "    programa e atalhos removidos"

if [ -d "$CONFIG_HOME/attack-shark" ] && ask "Apagar tambem seus perfis e a lista de jogos?"; then
    rm -rf "$CONFIG_HOME/attack-shark"
    echo "    configuracoes apagadas"
fi
if [ -f "$UDEV_RULE" ] && ask "Remover a regra udev do mouse (pede sudo)?"; then
    sudo rm -f "$UDEV_RULE" && sudo udevadm control --reload-rules
    echo "    regra udev removida"
fi
echo "Pronto."
