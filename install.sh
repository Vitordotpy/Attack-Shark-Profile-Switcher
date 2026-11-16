#!/usr/bin/env bash
# Attack Shark Profile Switcher - Linux installer.
#
#   ./install.sh            interactive
#   ./install.sh --yes      accept the defaults (autostart on, desktop icon on)
#
# Installs for the current user into ~/.local/share/attack-shark (code + a
# private Python virtualenv), adds a menu entry, an optional desktop icon and
# start at login, and - with sudo, once - a udev rule so the mouse can be
# talked to without root. Running it again updates in place; settings in
# ~/.config/attack-shark are kept.
set -euo pipefail

YES=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes) YES=1 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    esac
done

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
APP_HOME="$DATA_HOME/attack-shark"
APP_DIR="$APP_HOME/app"
VENV="$APP_HOME/venv"
LAUNCHER="$HOME/.local/bin/attack-shark"
DESKTOP_FILE="$DATA_HOME/applications/attack-shark.desktop"
AUTOSTART_FILE="$CONFIG_HOME/autostart/attack-shark.desktop"
UDEV_RULE="/etc/udev/rules.d/70-attack-shark.rules"

if [ -t 1 ]; then
    B=$'\e[1m'; DIM=$'\e[2m'; BLUE=$'\e[38;5;75m'; GREEN=$'\e[38;5;78m'
    YELLOW=$'\e[38;5;221m'; RED=$'\e[38;5;203m'; R=$'\e[0m'
else
    B=""; DIM=""; BLUE=""; GREEN=""; YELLOW=""; RED=""; R=""
fi
step() { printf '\n%s==>%s %s%s%s\n' "$BLUE" "$R" "$B" "$1" "$R"; }
ok()   { printf '    %s✔%s %s\n' "$GREEN" "$R" "$1"; }
warn() { printf '    %s!%s %s\n' "$YELLOW" "$R" "$1"; }
fail() { printf '\n%s✖ %s%s\n' "$RED" "$1" "$R" >&2; exit 1; }
ask() {  # ask "question" default(y/n) -> returns 0 for yes
    local q="$1" def="$2" reply
    if [ "$YES" = 1 ]; then [ "$def" = y ]; return; fi
    local hint="[S/n]"; [ "$def" = n ] && hint="[s/N]"
    read -r -p "    $q $hint " reply || reply=""
    reply="${reply:-$def}"
    [[ "$reply" =~ ^[sSyY] ]]
}

pkg_hint() {  # pkg_hint debian fedora arch
    if command -v apt-get >/dev/null 2>&1; then echo "sudo apt install $1"
    elif command -v dnf >/dev/null 2>&1; then echo "sudo dnf install $2"
    elif command -v pacman >/dev/null 2>&1; then echo "sudo pacman -S $3"
    elif command -v zypper >/dev/null 2>&1; then echo "sudo zypper install $2"
    else echo "instale: $1 (nome varia por distro)"; fi
}

printf '%s\n' "${B}${BLUE}"
printf '    Attack Shark Profile Switcher%s\n' "$R"
printf '    %sTroca de perfil automatica para mouses Attack Shark V8 e X6%s\n' "$DIM" "$R"

# -- 1. requirements ----------------------------------------------------------
step "Verificando o sistema"
command -v python3 >/dev/null 2>&1 || fail "Python 3 nao encontrado. $(pkg_hint python3 python3 python)"
python3 - <<'EOF' || fail "Precisa do Python 3.9 ou mais novo."
import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)
EOF
ok "Python $(python3 -c 'import platform; print(platform.python_version())')"
python3 -c "import venv, ensurepip" 2>/dev/null \
    || fail "Falta o modulo venv do Python. $(pkg_hint python3-venv python3 python)"
python3 -c "import tkinter" 2>/dev/null \
    || fail "Falta o tkinter (usado nas janelas). $(pkg_hint python3-tk python3-tkinter tk)"
ok "tkinter e venv"
if python3 - 2>/dev/null <<'EOF'
import gi
for name in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(name, "0.1"); break
    except ValueError:
        pass
else:
    raise SystemExit(1)
EOF
then
    ok "suporte a icone na bandeja (AppIndicator)"
else
    warn "Sem AppIndicator: o icone da bandeja pode nao aparecer em alguns desktops (GNOME)."
    warn "Recomendado: $(pkg_hint 'gir1.2-ayatanaappindicator3-0.1 python3-gi' 'libappindicator-gtk3 python3-gobject' 'libappindicator-gtk3 python-gobject')"
    warn "No GNOME, ative tambem a extensao 'AppIndicator and KStatusNotifierItem Support'."
fi

# -- 2. stop a running copy ---------------------------------------------------
pkill -f "$APP_DIR/switcher.py" 2>/dev/null && ok "versao anterior fechada" || true

# -- 3. files -----------------------------------------------------------------
step "Copiando o programa para $APP_HOME"
mkdir -p "$APP_DIR"
find "$APP_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp "$SRC"/*.py "$SRC/config.json" "$SRC/requirements.txt" "$APP_DIR/"
cp -r "$SRC/assets" "$APP_DIR/"
[ -f "$SRC/LICENSE" ] && cp "$SRC/LICENSE" "$APP_DIR/"
cp "$SRC/uninstall.sh" "$APP_HOME/uninstall.sh" && chmod +x "$APP_HOME/uninstall.sh"
ok "arquivos copiados"

step "Instalando dependencias (ambiente Python proprio)"
if [ ! -x "$VENV/bin/python" ]; then
    # --system-site-packages: reuse the distro's PyGObject for the tray icon.
    python3 -m venv --system-site-packages "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check -q --upgrade pip >/dev/null
"$VENV/bin/python" -m pip install --disable-pip-version-check -q -r "$APP_DIR/requirements.txt" \
    || fail "pip falhou ao instalar as dependencias (veja acima)."
ok "psutil, pystray e Pillow"

# -- 4. mouse permission ------------------------------------------------------
step "Permissao para falar com o mouse"
RULES='# Attack Shark mice: let the logged-in user configure them (no root needed).
KERNEL=="hidraw*", ATTRS{idVendor}=="1d57", ATTRS{idProduct}=="fa60", MODE="0660", TAG+="uaccess"
KERNEL=="hidraw*", ATTRS{idVendor}=="1d57", ATTRS{idProduct}=="fa61", MODE="0660", TAG+="uaccess"
KERNEL=="hidraw*", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="f517", MODE="0660", TAG+="uaccess"'
if [ -f "$UDEV_RULE" ] && [ "$(cat "$UDEV_RULE")" = "$RULES" ]; then
    ok "regra udev ja instalada"
elif ask "Instalar a regra udev do mouse? (pede a senha do sudo uma vez)" y; then
    printf '%s\n' "$RULES" | sudo tee "$UDEV_RULE" >/dev/null
    sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw
    ok "regra instalada - se o mouse nao responder, reconecte o receptor"
else
    warn "sem a regra, o programa nao consegue mudar as configuracoes do mouse"
fi

# -- 5. launcher, menu entry, desktop icon, autostart -------------------------
step "Atalhos"
mkdir -p "$(dirname "$LAUNCHER")"
cat > "$LAUNCHER" <<EOF
#!/bin/sh
exec "$VENV/bin/python" "$APP_DIR/switcher.py" "\$@"
EOF
chmod +x "$LAUNCHER"

desktop_entry() {
    cat <<EOF
[Desktop Entry]
Type=Application
Name=Attack Shark
GenericName=Mouse profile switcher
Comment=Troca o perfil do mouse Attack Shark automaticamente nos jogos
Exec=$LAUNCHER
Icon=$APP_DIR/assets/logo.png
Terminal=false
Categories=Utility;Settings;HardwareSettings;
StartupNotify=false
EOF
}
mkdir -p "$(dirname "$DESKTOP_FILE")"
desktop_entry > "$DESKTOP_FILE"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$(dirname "$DESKTOP_FILE")" || true
ok "menu de aplicativos"

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESKTOP_DIR" ] && ask "Criar icone na area de trabalho?" y; then
    desktop_entry > "$DESKTOP_DIR/attack-shark.desktop"
    chmod +x "$DESKTOP_DIR/attack-shark.desktop"
    command -v gio >/dev/null 2>&1 && gio set "$DESKTOP_DIR/attack-shark.desktop" metadata::trusted true 2>/dev/null || true
    ok "icone na area de trabalho"
fi

if ask "Iniciar junto com o sistema? (recomendado)" y; then
    mkdir -p "$(dirname "$AUTOSTART_FILE")"
    { desktop_entry; echo "X-GNOME-Autostart-enabled=true"; echo "X-GNOME-Autostart-Delay=5"; } > "$AUTOSTART_FILE"
    ok "inicia com o sistema"
else
    rm -f "$AUTOSTART_FILE"
fi

# -- 6. start -----------------------------------------------------------------
step "Abrindo o Attack Shark"
nohup "$LAUNCHER" >/dev/null 2>&1 &
ok "rodando - procure o icone na bandeja; clique nele para abrir as configuracoes"

printf '\n%s%sPronto!%s Para desinstalar: %s\n\n' "$GREEN" "$B" "$R" "$APP_HOME/uninstall.sh"
