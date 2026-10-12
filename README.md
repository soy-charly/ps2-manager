# ps2-manager

Herramientas para gestionar el HDD interno de una PS2 (vía red doméstica,
OPL/FreeHDBoot) desde Linux: un launcher en bash que te deja elegir dónde
trabajar (NAS, carpeta local o el propio HDD) y una TUI en Python para
instalar/borrar juegos y subir carátulas (ART) directamente al disco.

> Solo Linux. Usa `curses` y acceso directo a dispositivos de bloque
> (`/dev/sdX`), así que no funciona en Windows/macOS tal cual.

## Componentes

- **`launcher.sh`** — punto de entrada. Pregunta si quieres trabajar desde
  el NAS (monta el recurso SMB), una carpeta local, o directamente sobre el
  HDD de la PS2. Para NAS/local abre **OPL PC Tools**; para el HDD lanza
  `ps2-manager.py`.
- **`ps2-manager.py`** — TUI que lista las ISOs de tu carpeta de origen,
  las compara con lo que ya hay instalado en el HDD (vía `hdl_dump`),
  permite instalar/borrar juegos y descargar+subir el ART (carátulas)
  usando `pfsshell`.
- **`install.sh`** — instala las dependencias del sistema, compila
  `hdl_dump` y `pfsshell`, descarga OPL PC Tools, y coloca todo en su
  sitio. Ver más abajo.

## Instalación automática

```bash
git clone https://github.com/soy-charly/ps2-manager.git
cd ps2-manager
./install.sh
```

El script:

1. Instala dependencias del sistema (con `sudo`, detecta `apt`, `pacman`,
   `dnf` o `zypper`).
2. Compila [`hdl_dump`](https://github.com/ps2homebrew/hdl-dump) y
   [`pfsshell`](https://github.com/ps2homebrew/pfsshell) desde fuente y
   los instala en `/usr/local/bin`.
3. Descarga el binario Linux de la última release de
   [OPL PC Tools](https://github.com/brainstream/OPL-PC-Tools) en
   `~/.local/share/oplpctools` (no se compila: es una app Qt6 grande y
   la release ya trae binarios listos para usar).
4. Instala `ps2-manager.py` y `launcher.sh` en `/usr/local/bin` como
   `ps2-manager.py` y `ps2-manager-launcher.sh`.
5. Crea una configuración inicial en `~/.config/ps2-manager/`.

Si algún paso falla (por ejemplo, si cambia la estructura de una release
o tu distro no tiene un paquete con el nombre esperado), el script no
aborta: avisa por pantalla qué ha fallado y cómo solucionarlo a mano.

## Instalación manual

Si prefieres no ejecutar `install.sh` o quieres revisar qué hace antes:

```bash
# Dependencias (ejemplo para Debian/Ubuntu)
sudo apt install build-essential git curl meson ninja-build \
    pkg-config cifs-utils genisoimage unzip

# hdl_dump
git clone https://github.com/ps2homebrew/hdl-dump.git
cd hdl-dump && make
sudo install -m755 hdl_dump /usr/local/bin/hdl_dump
cd ..

# pfsshell
git clone --recursive https://github.com/ps2homebrew/pfsshell.git
cd pfsshell && meson setup build && ninja -C build
sudo install -m755 build/pfsshell /usr/local/bin/pfsshell
cd ..

# OPL PC Tools: descarga el binario Linux desde
# https://github.com/brainstream/OPL-PC-Tools/releases
# y descomprímelo en ~/.local/share/oplpctools

# Scripts de este repo
sudo install -m755 ps2-manager.py /usr/local/bin/ps2-manager.py
sudo install -m755 launcher.sh /usr/local/bin/ps2-manager-launcher.sh
```

## Primer uso

Ejecuta el launcher:

```bash
ps2-manager-launcher.sh
```

Si no lo has generado con `install.sh`, la primera vez te preguntará por:

- Ruta del NAS (opcional, déjala vacía si no vas a usar esa opción).
- Usuario y contraseña del NAS (la contraseña se guarda en
  `~/.config/ps2-manager/nas-credentials` con permisos `600`, nunca en el
  script ni en el fichero de configuración principal).
- Carpeta local para ISOs.
- Ruta del ejecutable de OPL PC Tools.
- Ruta de `ps2-manager.py`.

Todo se guarda en `~/.config/ps2-manager/launcher.conf`. Puedes editarlo a
mano o borrarlo para repetir el asistente.

Al elegir la opción **HDD PS2**, `ps2-manager.py` te pedirá configurar el
dispositivo (`/dev/sdX`) la primera vez — por seguridad, el programa
**nunca asume un dispositivo por defecto**. Antes de instalar o borrar
nada te mostrará el tamaño y modelo del disco detectado para que
confirmes que es el correcto.

## Configuración de `ps2-manager.py`

Se guarda en `~/.config/ps2-manager/config.conf` y se edita desde la
propia TUI (tecla `F3`):

| Campo            | Descripción                                       |
|------------------|---------------------------------------------------|
| `source`         | Carpeta con las ISOs de origen                    |
| `art_source`     | Carpeta donde se descarga/cachea el ART           |
| `device`         | Dispositivo de bloque del HDD de la PS2           |
| `opl_partition`  | Partición OPL en el HDD (normalmente `+OPL`)      |
| `hdl_dump`       | Comando o ruta de `hdl_dump`                      |
| `pfsshell`       | Comando o ruta de `pfsshell`                      |

## Uso de la TUI

- `F1` / `F2` — cambiar entre juegos de origen y juegos ya en el HDD.
- `F3` — configuración.
- `↑`/`↓`, `RePág`/`AvPág` — moverse.
- `ESPACIO` — seleccionar juego(s) en la vista de origen.
- `ENTER` — instalar los seleccionados (o el actual si no hay ninguno).
- `A` — descargar y subir el ART del juego bajo el cursor. En la vista de
  origen, si el ART ya está descargado localmente no se vuelve a
  descargar, solo se sube.
- `D` — borrar el juego bajo el cursor (solo en la vista del HDD).
- `/` y `N` — buscar y saltar al siguiente resultado.
- `R` — refrescar listas.
- `Q` — salir.

## Aviso

Este programa escribe y borra datos en dispositivos de bloque reales.
Revisa siempre que el dispositivo mostrado en `F3` y en los mensajes de
confirmación es el HDD de la PS2 y no un disco del sistema. No hay
manera de deshacer un borrado.

## Licencia

MIT — ver [`LICENSE`](LICENSE).
