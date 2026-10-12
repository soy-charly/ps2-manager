#!/bin/bash
set -e

# ============================================================
# CONFIGURACIÓN
# ============================================================

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/ps2-manager"
CONFIG_FILE="$CONFIG_DIR/launcher.conf"
CRED_FILE="$CONFIG_DIR/nas-credentials"

# Valores por defecto (se usan si no hay config o falta alguna clave)
NAS=""
NAS_USER=""
MOUNT="$HOME/.local/share/ps2-manager/nas"
OPL="$HOME/.local/share/oplpctools/bin/oplpctools"
LOCAL="$HOME/ps2"
PS2_MANAGER="/usr/local/bin/ps2-manager.py"

NAS_MONTADO_POR_SCRIPT=false

if [ -f "$CONFIG_FILE" ]; then
    # shellcheck source=/dev/null
    source "$CONFIG_FILE"
fi

# ============================================================
# PRIMERA EJECUCIÓN
# ============================================================

primera_config() {

    echo "Parece que es la primera vez que ejecutas esto."
    echo "Vamos a configurar las rutas (se guardarán en $CONFIG_FILE)."
    echo

    read -rp "Ruta del recurso NAS (ej: //192.168.1.10/PS2) [vacío = no usar NAS]: " NAS

    if [ -n "$NAS" ]; then

        read -rp "Usuario del NAS: " NAS_USER
        read -rsp "Contraseña del NAS (no se mostrará): " NAS_PASS
        echo

        mkdir -p "$CONFIG_DIR"
        umask 077

        cat > "$CRED_FILE" <<EOF
username=$NAS_USER
password=$NAS_PASS
EOF

        chmod 600 "$CRED_FILE"
    fi

    read -rp "Ruta local para ISOs [$LOCAL]: " INPUT_LOCAL
    [ -n "$INPUT_LOCAL" ] && LOCAL="$INPUT_LOCAL"

    read -rp "Ruta del ejecutable de OPL PC Tools [$OPL]: " INPUT_OPL
    [ -n "$INPUT_OPL" ] && OPL="$INPUT_OPL"

    read -rp "Ruta de ps2-manager.py [$PS2_MANAGER]: " INPUT_PS2M
    [ -n "$INPUT_PS2M" ] && PS2_MANAGER="$INPUT_PS2M"

    mkdir -p "$CONFIG_DIR"

    cat > "$CONFIG_FILE" <<EOF
# Configuración del launcher de ps2-manager
NAS="$NAS"
NAS_USER="$NAS_USER"
MOUNT="$MOUNT"
OPL="$OPL"
LOCAL="$LOCAL"
PS2_MANAGER="$PS2_MANAGER"
EOF

    echo
    echo "Configuración guardada en $CONFIG_FILE"
    echo "(puedes editarla a mano o borrarla para repetir este asistente)"
    echo
}

if [ ! -f "$CONFIG_FILE" ]; then
    primera_config
fi

# ============================================================
# DEPENDENCIAS DEL SISTEMA
# ============================================================

comprobar_dependencias() {

    local faltan=()

    command -v mount.cifs >/dev/null 2>&1 || faltan+=("cifs-utils (mount.cifs)")
    command -v mountpoint >/dev/null 2>&1 || faltan+=("util-linux (mountpoint)")

    if [ ${#faltan[@]} -gt 0 ]; then

        echo "Faltan dependencias del sistema:"

        for dep in "${faltan[@]}"; do
            echo "  - $dep"
        done

        echo
        echo "Instálalas con el gestor de paquetes de tu distro y vuelve a intentarlo."

        exit 1
    fi
}

comprobar_dependencias

# ============================================================
# MENÚ
# ============================================================

echo "¿Dónde quieres trabajar?"
echo
echo "  1) NAS"
echo "  2) Local"
echo "  3) HDD PS2"
echo

while true; do
    read -rp "Selecciona una opción [1-3]: " OPCION
    case "$OPCION" in
        1) DESTINO="NAS"; break ;;
        2) DESTINO="LOCAL"; break ;;
        3) DESTINO="HDD"; break ;;
        *) echo "Opción no válida." ;;
    esac
done

# ============================================================
# HDD PS2
# ============================================================

if [ "$DESTINO" = "HDD" ]; then

    echo

    if [ ! -f "$PS2_MANAGER" ]; then
        echo "ERROR: no se encuentra ps2-manager.py en:"
        echo "  $PS2_MANAGER"
        echo "Revisa la ruta en $CONFIG_FILE"
        exit 1
    fi

    echo "Abriendo PS2 Manager..."
    sudo python3 "$PS2_MANAGER"

    exit 0
fi

# ============================================================
# NAS
# ============================================================

if [ "$DESTINO" = "NAS" ]; then

    if [ -z "$NAS" ]; then
        echo "ERROR: no hay ruta de NAS configurada."
        echo "Edita $CONFIG_FILE o bórralo para repetir el asistente."
        exit 1
    fi

    mkdir -p "$MOUNT"

    if ! mountpoint -q "$MOUNT"; then

        echo
        echo "Montando NAS..."

        if [ -f "$CRED_FILE" ]; then

            sudo mount -t cifs "$NAS" "$MOUNT" \
                -o "credentials=$CRED_FILE,uid=$(id -u),gid=$(id -g),file_mode=0664,dir_mode=0775"
        else

            sudo mount -t cifs "$NAS" "$MOUNT" \
                -o "username=$NAS_USER,uid=$(id -u),gid=$(id -g),file_mode=0664,dir_mode=0775"
        fi

        NAS_MONTADO_POR_SCRIPT=true
    fi

    if ! touch "$MOUNT/.ps2manager_test" 2>/dev/null; then

        echo "ERROR: el recurso SMB no tiene permisos de escritura."

        if [ "$NAS_MONTADO_POR_SCRIPT" = true ]; then
            sudo umount "$MOUNT"
        fi

        exit 1
    fi

    rm -f "$MOUNT/.ps2manager_test"

    echo
    echo "Destino: NAS"
    echo "Ruta: $MOUNT"

# ============================================================
# LOCAL
# ============================================================

else

    mkdir -p "$LOCAL"

    echo
    echo "Destino: LOCAL"
    echo "Ruta: $LOCAL"
fi

# ============================================================
# OPL PC TOOLS
# ============================================================

if [ ! -x "$OPL" ]; then

    echo
    echo "ERROR: no se encuentra OPL PC Tools en:"
    echo "  $OPL"
    echo "Descárgalo y revisa la ruta en $CONFIG_FILE"

    if [ "$DESTINO" = "NAS" ] && [ "$NAS_MONTADO_POR_SCRIPT" = true ]; then
        sudo umount "$MOUNT"
    fi

    exit 1
fi

encontrar_lib() {
    local nombre="$1"
    ldconfig -p 2>/dev/null | grep "$nombre" | head -1 | awk '{print $NF}'
}

SSL_LIB=$(encontrar_lib "libssl.so.3")
CRYPTO_LIB=$(encontrar_lib "libcrypto.so.3")

echo
echo "Abriendo OPL PC Tools..."

OPL_DIR=$(dirname "$(dirname "$OPL")")
cd "$OPL_DIR"

if [ -n "$SSL_LIB" ] && [ -n "$CRYPTO_LIB" ]; then

    LD_LIBRARY_PATH="$PWD/bin" \
    LD_PRELOAD="$SSL_LIB:$CRYPTO_LIB" \
    "$OPL"
else

    echo "AVISO: no se han encontrado libssl.so.3/libcrypto.so.3 del sistema."
    echo "OPL PC Tools puede fallar al arrancar; instala openssl si es así."

    LD_LIBRARY_PATH="$PWD/bin" "$OPL"
fi

echo
echo "OPL PC Tools cerrado."

# ============================================================
# DESMONTAR NAS
# ============================================================

if [ "$DESTINO" = "NAS" ] && [ "$NAS_MONTADO_POR_SCRIPT" = true ]; then
    echo "Desmontando NAS..."
    sudo umount "$MOUNT"
fi
