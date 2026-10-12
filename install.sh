#!/bin/bash
set -e

# ============================================================
# ps2-manager · install.sh
#
# Instala dependencias del sistema, compila/descarga las
# herramientas externas (hdl_dump, pfsshell, OPL PC Tools) y
# coloca ps2-manager.py y el launcher en su sitio.
#
# hdl_dump y pfsshell se compilan desde fuente (proyectos en C
# ligeros, sin dependencias pesadas). OPL PC Tools es una app
# Qt6 grande: en vez de compilarla (requeriría Qt6 completo +
# submódulos), se descarga el binario Linux ya compilado desde
# la última release de GitHub.
# ============================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${TMPDIR:-/tmp}/ps2-manager-build"
BIN_DIR="/usr/local/bin"
SHARE_DIR="$HOME/.local/share/oplpctools"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/ps2-manager"

HDL_DUMP_REPO="https://github.com/ps2homebrew/hdl-dump.git"
PFSSHELL_REPO="https://github.com/ps2homebrew/pfsshell.git"
OPL_PC_TOOLS_SLUG="brainstream/OPL-PC-Tools"

mkdir -p "$BUILD_DIR"

# ============================================================
# DEPENDENCIAS DEL SISTEMA
# ============================================================

detectar_gestor_paquetes() {

    if command -v apt-get >/dev/null 2>&1; then
        echo "apt"
    elif command -v pacman >/dev/null 2>&1; then
        echo "pacman"
    elif command -v dnf >/dev/null 2>&1; then
        echo "dnf"
    elif command -v zypper >/dev/null 2>&1; then
        echo "zypper"
    else
        echo "unknown"
    fi
}

instalar_dependencias_sistema() {

    local pm
    pm=$(detectar_gestor_paquetes)

    echo "Gestor de paquetes detectado: $pm"
    echo

    case "$pm" in

        apt)
            sudo apt-get update
            sudo apt-get install -y \
                build-essential git curl \
                meson ninja-build pkg-config \
                cifs-utils genisoimage unzip
            ;;

        pacman)
            sudo pacman -Sy --needed --noconfirm \
                base-devel git curl \
                meson ninja pkgconf \
                cifs-utils cdrtools unzip
            ;;

        dnf)
            sudo dnf install -y \
                gcc gcc-c++ make git curl \
                meson ninja-build pkgconf-pkg-config \
                cifs-utils genisoimage unzip
            ;;

        zypper)
            sudo zypper install -y -t pattern devel_basis
            sudo zypper install -y \
                git curl meson ninja pkgconf \
                cifs-utils genisoimage unzip
            ;;

        *)
            echo "No se reconoce el gestor de paquetes de esta distro."
            echo "Instala manualmente antes de continuar:"
            echo "  gcc, make, git, curl, meson, ninja, pkg-config,"
            echo "  cifs-utils, genisoimage/cdrtools (isoinfo), unzip"
            echo

            read -rp "Pulsa ENTER para continuar de todos modos, o Ctrl+C para salir..." _
            ;;
    esac

    echo
}

# ============================================================
# HDL_DUMP (compilado desde fuente)
# ============================================================

instalar_hdl_dump() {

    if command -v hdl_dump >/dev/null 2>&1; then
        echo "hdl_dump ya está instalado, se omite."
        return
    fi

    echo "Compilando hdl_dump..."

    rm -rf "$BUILD_DIR/hdl-dump"

    git clone --depth 1 "$HDL_DUMP_REPO" "$BUILD_DIR/hdl-dump"

    (
        cd "$BUILD_DIR/hdl-dump"
        make
    )

    if [ -f "$BUILD_DIR/hdl-dump/hdl_dump" ]; then

        sudo install -m755 "$BUILD_DIR/hdl-dump/hdl_dump" "$BIN_DIR/hdl_dump"

        echo "hdl_dump instalado en $BIN_DIR/hdl_dump"

    else

        echo "AVISO: no se generó el binario hdl_dump."
        echo "Revisa los errores de compilación arriba, o compílalo a mano:"
        echo "  $BUILD_DIR/hdl-dump"
    fi

    echo
}

# ============================================================
# PFSSHELL (compilado desde fuente, con submódulos)
# ============================================================

instalar_pfsshell() {

    if command -v pfsshell >/dev/null 2>&1; then
        echo "pfsshell ya está instalado, se omite."
        return
    fi

    echo "Compilando pfsshell..."

    rm -rf "$BUILD_DIR/pfsshell"

    git clone --recursive --depth 1 "$PFSSHELL_REPO" "$BUILD_DIR/pfsshell"

    (
        cd "$BUILD_DIR/pfsshell"
        meson setup build
        ninja -C build
    )

    if [ -f "$BUILD_DIR/pfsshell/build/pfsshell" ]; then

        sudo install -m755 "$BUILD_DIR/pfsshell/build/pfsshell" "$BIN_DIR/pfsshell"

        echo "pfsshell instalado en $BIN_DIR/pfsshell"

    else

        echo "AVISO: no se generó el binario pfsshell."
        echo "Revisa los errores de compilación arriba, o compílalo a mano:"
        echo "  $BUILD_DIR/pfsshell"
    fi

    echo
}

# ============================================================
# OPL PC TOOLS (release Linux prebuilt de GitHub)
# ============================================================

instalar_opl_pc_tools() {

    if [ -x "$SHARE_DIR/bin/oplpctools" ] || [ -x "$SHARE_DIR/oplpctools.AppImage" ]; then
        echo "OPL PC Tools ya está instalado en $SHARE_DIR, se omite."
        return
    fi

    echo "Buscando la última versión de OPL PC Tools para Linux..."

    local api_url="https://api.github.com/repos/$OPL_PC_TOOLS_SLUG/releases/latest"
    local release_json

    if ! release_json=$(curl -sL "$api_url"); then

        echo "AVISO: no se pudo consultar la API de GitHub."
        echo "Descárgalo manualmente de https://github.com/$OPL_PC_TOOLS_SLUG/releases"
        echo

        return
    fi

    local asset_url
    asset_url=$(
        echo "$release_json" \
        | grep -oP '"browser_download_url":\s*"\K[^"]*[Ll]inux[^"]*\.(tar\.gz|tar\.xz|zip|AppImage)' \
        | head -1
    )

    if [ -z "$asset_url" ]; then

        echo "AVISO: no se ha encontrado un paquete Linux en la última release."
        echo "Descárgalo manualmente de https://github.com/$OPL_PC_TOOLS_SLUG/releases"
        echo "y descomprímelo en: $SHARE_DIR"
        echo

        return
    fi

    echo "Descargando: $asset_url"

    mkdir -p "$BUILD_DIR/oplpctools"

    local archive="$BUILD_DIR/oplpctools/$(basename "$asset_url")"

    curl -Lo "$archive" "$asset_url"

    mkdir -p "$SHARE_DIR"

    case "$archive" in

        *.tar.gz|*.tgz)
            tar -xzf "$archive" -C "$SHARE_DIR" --strip-components=1
            ;;

        *.tar.xz)
            tar -xJf "$archive" -C "$SHARE_DIR" --strip-components=1
            ;;

        *.zip)
            unzip -oq "$archive" -d "$SHARE_DIR"
            ;;

        *.AppImage)
            cp "$archive" "$SHARE_DIR/oplpctools.AppImage"
            chmod +x "$SHARE_DIR/oplpctools.AppImage"
            ;;
    esac

    find "$SHARE_DIR" -maxdepth 3 -iname "oplpctools*" -exec chmod +x {} \; 2>/dev/null || true

    echo "OPL PC Tools instalado en $SHARE_DIR"
    echo "(si la estructura de carpetas no coincide con lo esperado,"
    echo " revisa $SHARE_DIR y ajusta la ruta OPL en la configuración)"
    echo
}

# ============================================================
# SCRIPTS PROPIOS
# ============================================================

instalar_scripts() {

    echo "Instalando ps2-manager.py y el launcher en $BIN_DIR..."

    sudo install -m755 "$REPO_DIR/ps2-manager.py" "$BIN_DIR/ps2-manager.py"
    sudo install -m755 "$REPO_DIR/launcher.sh" "$BIN_DIR/ps2-manager-launcher.sh"

    echo "Instalados: $BIN_DIR/ps2-manager.py y $BIN_DIR/ps2-manager-launcher.sh"
    echo
}

# ============================================================
# CONFIGURACIÓN INICIAL
# ============================================================

sembrar_configuracion() {

    mkdir -p "$CONFIG_DIR"

    local conf="$CONFIG_DIR/launcher.conf"

    local opl_path="$SHARE_DIR/bin/oplpctools"

    if [ ! -x "$opl_path" ] && [ -x "$SHARE_DIR/oplpctools.AppImage" ]; then
        opl_path="$SHARE_DIR/oplpctools.AppImage"
    fi

    if [ ! -f "$conf" ]; then

        cat > "$conf" <<EOF
# Configuración del launcher de ps2-manager
NAS=""
NAS_USER=""
MOUNT="$HOME/.local/share/ps2-manager/nas"
OPL="$opl_path"
LOCAL="$HOME/ps2"
PS2_MANAGER="$BIN_DIR/ps2-manager.py"
EOF

        echo "Configuración inicial guardada en $conf"
        echo "(vuelve a lanzar ps2-manager-launcher.sh para completar NAS/usuario)"
        echo

        return
    fi

    # --------------------------------------------------------
    # Ya existe un launcher.conf (de una instalación anterior,
    # de una prueba manual, o de una versión antigua de este
    # proyecto). No lo pisamos entero porque puede tener NAS,
    # usuario, carpeta local, etc. que el usuario ya configuró
    # a mano. Pero si PS2_MANAGER u OPL apuntan a una ruta que
    # ya no existe mientras que acabamos de instalar el binario
    # real en otro sitio, es un bug esperando a pasar (exacta-
    # mente lo que le pasó a este usuario: un launcher.conf
    # viejo seguía apuntando a ~/.local/bin/ps2-manager.py
    # aunque el instalador siempre ha puesto el binario en
    # /usr/local/bin). Reparamos solo esas dos líneas si hace
    # falta, dejando el resto del fichero intacto.

    echo "Ya existe $conf, comprobando que las rutas sigan siendo válidas..."

    local cambios=0
    # shellcheck source=/dev/null
    local PS2_MANAGER OPL
    source "$conf"

    if [ -n "$PS2_MANAGER" ] && [ ! -f "$PS2_MANAGER" ] && [ -f "$BIN_DIR/ps2-manager.py" ]; then

        sed -i "s|^PS2_MANAGER=.*|PS2_MANAGER=\"$BIN_DIR/ps2-manager.py\"|" "$conf"

        echo "  - PS2_MANAGER no existía en '$PS2_MANAGER', corregido a $BIN_DIR/ps2-manager.py"

        cambios=1
    fi

    if [ -n "$OPL" ] && [ ! -x "$OPL" ] && [ -x "$opl_path" ]; then

        sed -i "s|^OPL=.*|OPL=\"$opl_path\"|" "$conf"

        echo "  - OPL no era ejecutable en '$OPL', corregido a $opl_path"

        cambios=1
    fi

    if [ "$cambios" -eq 1 ]; then
        echo "Configuración actualizada en $conf"
    else
        echo "Las rutas de $conf siguen siendo válidas, no se toca."
    fi

    echo
}

# ============================================================
# MAIN
# ============================================================

echo "============================================================"
echo " ps2-manager · instalación"
echo "============================================================"
echo
echo "Esto va a:"
echo "  1. Instalar dependencias del sistema (con sudo)"
echo "  2. Compilar e instalar hdl_dump y pfsshell en $BIN_DIR"
echo "  3. Descargar OPL PC Tools en $SHARE_DIR"
echo "  4. Instalar ps2-manager.py y el launcher en $BIN_DIR"
echo "  5. Crear una configuración inicial en $CONFIG_DIR"
echo

read -rp "¿Continuar? (s/N): " CONFIRMAR

case "$CONFIRMAR" in
    s|S|y|Y) ;;
    *) echo "Cancelado."; exit 0 ;;
esac

echo

instalar_dependencias_sistema
instalar_hdl_dump
instalar_pfsshell
instalar_opl_pc_tools
instalar_scripts
sembrar_configuracion

echo "============================================================"
echo " Instalación terminada"
echo "============================================================"
echo
echo "Ejecuta:"
echo "  ps2-manager-launcher.sh"
echo
echo "La primera vez que elijas NAS te pedirá usuario/contraseña"
echo "(se guardan en $CONFIG_DIR/nas-credentials con permisos 600)."
