#!/usr/bin/env python3

import curses
import os
import re
import subprocess
import sys
import time
from pathlib import Path


# ============================================================
# CONFIGURACIÓN
# ============================================================

CONFIG_DIR = Path(
    os.environ.get(
        "XDG_CONFIG_HOME",
        str(Path.home() / ".config"),
    )
) / "ps2-manager"

CONFIG_FILE = CONFIG_DIR / "config.conf"

DEFAULT_CONFIG = {
    "source": str(Path.home() / "ps2" / "DVD"),
    "art_source": str(Path.home() / "ps2" / "ART"),
    # Deliberately empty: never assume a device path like
    # /dev/sdb, which on another machine could be a system
    # disk. The user must set this explicitly (F3) before
    # anything destructive can happen.
    "device": "",
    "opl_partition": "+OPL",
    # Bare command names: resolved via PATH by find_executable().
    # Users can still point these at an absolute path in F3 if
    # the binary isn't installed system-wide.
    "hdl_dump": "hdl_dump",
    "pfsshell": "pfsshell",
}


# ============================================================
# CONFIG
# ============================================================

def load_config():

    config = DEFAULT_CONFIG.copy()

    if CONFIG_FILE.exists():

        try:

            for line in CONFIG_FILE.read_text().splitlines():

                line = line.strip()

                if (
                    not line
                    or line.startswith("#")
                    or "=" not in line
                ):
                    continue

                key, value = line.split(
                    "=",
                    1,
                )

                key = key.strip()
                value = value.strip()

                if key in config:
                    config[key] = value

        except Exception:
            pass

    return config


def save_config(config):

    CONFIG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = [
        "# PS2 Manager configuration",
        "",
    ]

    for key, value in config.items():

        lines.append(
            f"{key}={value}"
        )

    CONFIG_FILE.write_text(
        "\n".join(lines) + "\n"
    )


# ============================================================
# UTILIDADES
# ============================================================

def run_command(
    command,
    input_data=None,
    timeout=None,
):

    try:

        result = subprocess.run(
            command,
            input=input_data,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )

        return (
            result.returncode,
            result.stdout,
        )

    except FileNotFoundError:

        return (
            127,
            f"Command not found: {command[0]}",
        )

    except subprocess.TimeoutExpired:

        return (
            124,
            "Command timed out",
        )


_EXECUTABLE_CACHE = {}


def find_executable(name):

    if name in _EXECUTABLE_CACHE:
        return _EXECUTABLE_CACHE[name]

    if (
        os.path.isabs(name)
        and os.access(name, os.X_OK)
    ):

        _EXECUTABLE_CACHE[name] = name

        return name

    path = subprocess.run(
        ["which", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    result = (
        path.stdout.strip()
        if path.returncode == 0
        else None
    )

    _EXECUTABLE_CACHE[name] = result

    return result


def clear_executable_cache():

    _EXECUTABLE_CACHE.clear()


def device_looks_valid(device):

    if not device:
        return False

    try:

        return os.path.exists(device)

    except Exception:

        return False


def device_info(device):

    # Best-effort human-readable size/model of the target
    # device, shown in confirmation prompts so the user can
    # double-check they're not about to write to the wrong
    # disk. Returns None if lsblk isn't available or fails.

    try:

        result = subprocess.run(
            [
                "lsblk",
                "-ndo",
                "SIZE,MODEL",
                device,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:

            info = result.stdout.strip()

            if info:
                return info

    except Exception:
        pass

    return None


# ============================================================
# GAME ID
# ============================================================

GAME_ID_RE = re.compile(
    r"\b([A-Z]{4})[_-]?(\d{3})[._-]?(\d{2})\b",
    re.IGNORECASE,
)


def normalize_game_id(value):

    match = GAME_ID_RE.search(value)

    if not match:
        return None

    return (
        f"{match.group(1).upper()}_"
        f"{match.group(2)}."
        f"{match.group(3)}"
    )


def find_game_id_from_iso(iso):

    game_id = normalize_game_id(
        iso.name
    )

    if game_id:
        return game_id

    try:

        result = subprocess.run(
            [
                "isoinfo",
                "-i",
                str(iso),
                "-d",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
        )

        output = result.stdout

        patterns = [
            r"Volume id:\s*([A-Z]{4}[_-]?\d{3}[._-]?\d{2})",
            r"Application id:\s*([A-Z]{4}[_-]?\d{3}[._-]?\d{2})",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                output,
                re.IGNORECASE,
            )

            if match:

                game_id = normalize_game_id(
                    match.group(1)
                )

                if game_id:
                    return game_id

    except Exception:
        pass

    return None


# ============================================================
# NOMBRE DEL JUEGO
# ============================================================

LANGUAGE_WORDS = {
    "PAL",
    "NTSC",
    "USA",
    "EUR",
    "EU",
    "UK",
    "EN",
    "ES",
    "DE",
    "FR",
    "IT",
    "PT",
    "NL",
    "MULTI",
    "MULTILINGUAL",
    "SPANISH",
    "ENGLISH",
    "GERMAN",
    "FRENCH",
    "ITALIAN",
    "PORTUGUESE",
    "EUROPE",
    "EUROPEAN",
    "JAPAN",
    "JPN",
    "JAP",
}


def clean_game_name(
    name,
    game_id=None,
):

    name = Path(name).stem

    if game_id:

        name = re.sub(
            re.escape(game_id),
            "",
            name,
            flags=re.IGNORECASE,
        )

    name = GAME_ID_RE.sub(
        "",
        name,
    )

    name = name.replace(
        "_",
        " ",
    )

    name = name.replace(
        ".",
        " ",
    )

    name = name.replace(
        "-",
        " ",
    )

    name = re.sub(
        r"\[[^\]]*\]",
        " ",
        name,
    )

    name = re.sub(
        r"\([^)]*\)",
        " ",
        name,
    )

    name = re.sub(
        r"\bREV\s*\d+\b",
        "",
        name,
        flags=re.I,
    )

    name = re.sub(
        r"\bVERSION\s*\d+\b",
        "",
        name,
        flags=re.I,
    )

    words = []

    for word in name.split():

        clean = re.sub(
            r"[^A-Za-z0-9]",
            "",
            word,
        )

        if clean.upper() in LANGUAGE_WORDS:
            continue

        words.append(word)

    name = " ".join(words)

    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    return name


# ============================================================
# SCAN ISO
# ============================================================

def scan_isos(source):

    source = Path(source)

    if not source.exists():
        return []

    isos = []

    for path in sorted(
        source.iterdir()
    ):

        if not path.is_file():
            continue

        if path.suffix.lower() not in (
            ".iso",
            ".bin",
            ".img",
        ):
            continue

        game_id = find_game_id_from_iso(
            path
        )

        if not game_id:
            game_id = "UNKNOWN"

        name = clean_game_name(
            path.name,
            game_id,
        )

        isos.append({
            "path": path,
            "id": game_id,
            "name": name,
        })

    return isos


# ============================================================
# HDL-DUMP
# ============================================================

def hdl_command(config):

    executable = find_executable(
        config["hdl_dump"]
    )

    if not executable:
        return None

    return executable


def get_hdd_games(config):

    executable = hdl_command(
        config
    )

    if not executable:

        return (
            [],
            "hdl_dump no encontrado",
        )

    device = config["device"]

    commands = [
        [
            executable,
            "toc",
            device,
        ],
        [
            executable,
            "hdl_toc",
            device,
        ],
        [
            executable,
            "dump_toc",
            device,
        ],
    ]

    output = None

    for command in commands:

        code, text = run_command(
            command
        )

        if code == 0:

            output = text

            break

    if output is None:

        return (
            [],
            "No se pudo leer el HDD con hdl_dump",
        )

    games = []

    for line in output.splitlines():

        line = line.strip()

        if not line:
            continue

        game_id = normalize_game_id(
            line
        )

        if not game_id:
            continue

        pos = re.search(
            re.escape(game_id),
            line,
            flags=re.I,
        )

        name = line

        if pos:

            name = line[
                pos.end():
            ].strip()

        name = name.strip(
            " -:\t"
        )

        games.append({
            "id": game_id,
            "name": name,
            "raw": line,
        })

    unique = {}

    for game in games:

        unique[
            game["id"]
        ] = game

    result = sorted(
        unique.values(),
        key=lambda g: g["id"],
    )

    return result, None


# ============================================================
# INYECCIÓN
# ============================================================

def inject_game(
    config,
    game,
    progress_callback=None,
):

    executable = hdl_command(
        config
    )

    if not executable:

        return (
            False,
            "hdl_dump no encontrado",
        )

    iso = str(
        game["path"]
    )

    name = (
        game.get("name") or ""
    ).strip()

    if not name:
        name = game["id"]

    name = name[:32]

    command = [
        executable,
        "inject_dvd",
        config["device"],
        name,
        iso,
        game["id"],
    ]

    try:

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )

        output = []

        current = bytearray()

        while True:

            char = (
                process.stdout.read(1)
            )

            if not char:
                break

            if char in (
                b"\r",
                b"\n",
            ):

                if current:

                    line = (
                        current
                        .decode(
                            errors="replace"
                        )
                        .strip()
                    )

                    if line:

                        output.append(
                            line
                        )

                        if progress_callback:

                            progress_callback(
                                line
                            )

                    current.clear()

            else:

                current.extend(
                    char
                )

        if current:

            line = (
                current
                .decode(
                    errors="replace"
                )
                .strip()
            )

            if line:

                output.append(
                    line
                )

                if progress_callback:

                    progress_callback(
                        line
                    )

        code = process.wait()

        return (
            code == 0,
            "\n".join(output),
        )

    except Exception as e:

        return (
            False,
            str(e),
        )


# ============================================================
# DELETE
# ============================================================

def delete_game(
    config,
    game,
    log_callback=None,
):

    executable = hdl_command(
        config
    )

    if not executable:

        return (
            False,
            "hdl_dump no encontrado",
        )

    device = config["device"]

    name = (
        game.get("raw")
        or game["id"]
    )

    commands = [
        [
            executable,
            "delete",
            device,
            name,
        ],
        [
            executable,
            "delete",
            device,
            game["id"],
        ],
        [
            executable,
            "del",
            device,
            game["id"],
        ],
    ]

    output = ""

    for command in commands:

        if log_callback:

            log_callback(
                "Ejecutando:\n"
                + " ".join(command)
            )

        code, text = run_command(
            command,
            timeout=60,
        )

        output = text

        if code == 0:

            return (
                True,
                output,
            )

    return (
        False,
        output,
    )


# ============================================================
# ART
# ============================================================

ART_TYPES = [
    "_COV.png",
    "_COV2.png",
    "_BG.png",
    "_ICO.png",
    "_LAB.png",
    "_LGO.png",
    "_SCR.png",
    "_SCR2.png",
]


# ============================================================
# SERVIDOR DE ART DE OPL-PC-TOOLS
# ============================================================

ART_URL = (
    "https://ia903209.us.archive.org/"
    "view_archive.php?"
    "archive=/34/items/ps2-opl-cover-art-set/"
    "PS2_OPL_ART_kira.7z"
    "&file=ART/{game_id}{art_type}"
)


def find_art(
    game_id,
    art_source,
):

    art_source = Path(
        art_source
    )

    result = []

    for suffix in ART_TYPES:

        path = (
            art_source
            / f"{game_id}{suffix}"
        )

        if path.exists():

            result.append(
                path
            )

    return result


def missing_art_types(
    game_id,
    art_source,
):

    art_source = Path(
        art_source
    )

    missing = []

    for art_type in ART_TYPES:

        path = (
            art_source
            / f"{game_id}{art_type}"
        )

        if not path.exists():

            missing.append(
                path.name
            )

    return missing


def download_art(
    game_id,
    art_source,
    log_callback=None,
):

    art_source = Path(
        art_source
    )

    art_source.mkdir(
        parents=True,
        exist_ok=True,
    )

    downloaded = []

    for art_type in ART_TYPES:

        filename = (
            f"{game_id}{art_type}"
        )

        destination = (
            art_source / filename
        )

        url = ART_URL.format(
            game_id=game_id,
            art_type=art_type,
        )

        if log_callback:

            log_callback(
                f"Descargando {filename}..."
            )

        try:

            result = subprocess.run(
                [
                    "curl",
                    "-L",
                    "-f",
                    "--silent",
                    "--show-error",
                    "--retry",
                    "2",
                    "-o",
                    str(destination),
                    url,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:

                if destination.exists():

                    destination.unlink()

                if log_callback:

                    log_callback(
                        f"No disponible: "
                        f"{filename}"
                    )

                continue

            if (
                not destination.exists()
                or destination.stat().st_size == 0
            ):

                if destination.exists():

                    destination.unlink()

                if log_callback:

                    log_callback(
                        f"Archivo vacío: "
                        f"{filename}"
                    )

                continue

            downloaded.append(
                destination
            )

            if log_callback:

                log_callback(
                    f"OK: {filename}"
                )

        except Exception as e:

            if destination.exists():

                destination.unlink()

            if log_callback:

                log_callback(
                    f"Error descargando "
                    f"{filename}: {e}"
                )

    return downloaded


def upload_art(
    config,
    game_id,
    log_callback=None,
):

    pfsshell = find_executable(
        config["pfsshell"]
    )

    if not pfsshell:

        return (
            False,
            "pfsshell no encontrado",
        )

    art_source = Path(
        config["art_source"]
    )

    files = find_art(
        game_id,
        art_source,
    )

    if not files:

        return (
            False,
            f"No hay ART para {game_id}",
        )

    commands = [
        f"device {config['device']}",
        f"mount {config['opl_partition']}",
        "cd ART",
        f"lcd {art_source}",
    ]

    for file in files:

        commands.append(
            f"put {file.name}"
        )

    commands.append(
        "exit"
    )

    input_data = (
        "\n".join(commands)
        + "\n"
    )

    if log_callback:

        log_callback(
            f"Subiendo {len(files)} ART "
            f"de {game_id}..."
        )

    code, output = run_command(
        [pfsshell],
        input_data=input_data,
        timeout=300,
    )

    if log_callback:

        log_callback(output)

    return (
        code == 0,
        output,
    )


def download_and_upload_art(
    config,
    game_id,
    log_callback=None,
):

    # --------------------------------------------------------
    # DESCARGAR (siempre, se sobreescribe lo que hubiera)
    # --------------------------------------------------------

    if log_callback:

        log_callback(
            f"Descargando ART de {game_id}..."
        )

    files = download_art(
        game_id,
        config["art_source"],
        log_callback,
    )

    if not files:

        message = (
            f"No se pudo descargar ningún ART "
            f"para {game_id}"
        )

        if log_callback:

            log_callback(message)

        return (
            False,
            message,
        )

    # --------------------------------------------------------
    # COMPROBAR LAS 8
    # --------------------------------------------------------

    missing = missing_art_types(
        game_id,
        config["art_source"],
    )

    if log_callback:

        log_callback(
            f"Descargadas {len(files)}/"
            f"{len(ART_TYPES)} imágenes"
        )

        if missing:

            log_callback(
                "No disponibles: "
                + ", ".join(missing)
            )

    # --------------------------------------------------------
    # SUBIR (solo lo que se ha descargado, upload_art usa
    # find_art, que solo recoge lo que existe en disco)
    # --------------------------------------------------------

    success, output = upload_art(
        config,
        game_id,
        log_callback,
    )

    if not success:

        return (
            False,
            output,
        )

    return (
        True,
        output,
    )


def ensure_art_and_upload(
    config,
    game_id,
    log_callback=None,
):

    art_source = Path(
        config["art_source"]
    )

    # --------------------------------------------------------
    # ¿YA ESTÁ DESCARGADO?
    # --------------------------------------------------------

    existing = find_art(
        game_id,
        art_source,
    )

    if existing:

        if log_callback:

            log_callback(
                f"ART de {game_id} ya descargado "
                f"({len(existing)}/{len(ART_TYPES)} "
                "archivos), subiendo..."
            )

    else:

        # ----------------------------------------------------
        # NO ESTÁ: DESCARGAR
        # ----------------------------------------------------

        if log_callback:

            log_callback(
                f"ART de {game_id} no encontrado "
                "localmente, descargando..."
            )

        files = download_art(
            game_id,
            config["art_source"],
            log_callback,
        )

        if not files:

            message = (
                f"No se pudo descargar ningún ART "
                f"para {game_id}"
            )

            if log_callback:

                log_callback(message)

            return (
                False,
                message,
            )

        missing = missing_art_types(
            game_id,
            config["art_source"],
        )

        if log_callback:

            log_callback(
                f"Descargadas {len(files)}/"
                f"{len(ART_TYPES)} imágenes"
            )

            if missing:

                log_callback(
                    "No disponibles: "
                    + ", ".join(missing)
                )

    # --------------------------------------------------------
    # SUBIR (solo lo que hay en disco, sea lo ya existente o
    # lo recién descargado)
    # --------------------------------------------------------

    success, output = upload_art(
        config,
        game_id,
        log_callback,
    )

    if not success:

        return (
            False,
            output,
        )

    return (
        True,
        output,
    )


# ============================================================
# TUI
# ============================================================

class PS2Manager:

    def __init__(
        self,
        stdscr,
    ):

        self.stdscr = stdscr

        self.config = load_config()

        self.isos = []
        self.hdd_games = []

        self.selected = set()

        self.mode = "source"

        self.cursor = 0
        self.scroll = 0

        self.message = (
            "Iniciando..."
        )

        self.search_term = ""

        self.refresh_all()

        curses.curs_set(0)

    # --------------------------------------------------------
    # SAFE DRAW
    # --------------------------------------------------------

    def safe_addstr(
        self,
        y,
        x,
        text,
        attr=0,
    ):

        height, width = (
            self.stdscr.getmaxyx()
        )

        if (
            y < 0
            or y >= height
            or x < 0
            or x >= width
        ):

            return

        max_len = (
            width - x - 1
        )

        if max_len <= 0:
            return

        try:

            self.stdscr.addstr(
                y,
                x,
                text[:max_len],
                attr,
            )

        except curses.error:

            pass

    # --------------------------------------------------------
    # CONFIRM
    # --------------------------------------------------------

    def confirm(
        self,
        prompt,
    ):

        height, width = (
            self.stdscr.getmaxyx()
        )

        text = (
            f"{prompt} (s/N): "
        )

        self.safe_addstr(
            height - 1,
            2,
            text,
            curses.A_REVERSE,
        )

        self.stdscr.refresh()

        key = self.stdscr.getch()

        return key in (
            ord("s"),
            ord("S"),
            ord("y"),
            ord("Y"),
        )

    # --------------------------------------------------------
    # REFRESH
    # --------------------------------------------------------

    def refresh_all(self):

        self.message = (
            "Escaneando..."
        )

        self.isos = scan_isos(
            self.config["source"]
        )

        (
            self.hdd_games,
            error,
        ) = get_hdd_games(
            self.config
        )

        if error:

            self.message = error

        else:

            self.message = (
                f"{len(self.isos)} ISOs / "
                f"{len(self.hdd_games)} "
                "juegos en HDD"
            )

        self.cursor = 0
        self.scroll = 0

    # --------------------------------------------------------
    # EXISTING
    # --------------------------------------------------------

    def installed_ids(self):

        return {
            game["id"]
            for game in self.hdd_games
        }

    # --------------------------------------------------------
    # DRAW
    # --------------------------------------------------------

    def draw(self):

        self.stdscr.erase()

        height, width = (
            self.stdscr.getmaxyx()
        )

        title = " PS2 MANAGER "

        self.safe_addstr(
            0,
            max(
                0,
                (width - len(title)) // 2,
            ),
            title,
            curses.A_BOLD,
        )

        source = self.config[
            "source"
        ]

        device = self.config[
            "device"
        ]

        self.safe_addstr(
            1,
            2,
            f"Fuente: {source}",
        )

        self.safe_addstr(
            2,
            2,
            f"HDD: {device}",
        )

        tabs = (
            "[F1] Juegos fuente   "
            "[F2] Juegos HDD   "
            "[F3] Configuración"
        )

        self.safe_addstr(
            4,
            2,
            tabs,
            curses.A_BOLD,
        )

        if self.mode == "source":

            games = self.isos

        else:

            games = self.hdd_games

        available_height = (
            height - 8
        )

        start = self.scroll

        end = min(
            len(games),
            start + available_height,
        )

        installed = (
            self.installed_ids()
        )

        for index in range(
            start,
            end,
        ):

            game = games[index]

            y = 6 + (
                index - start
            )

            if self.mode == "source":

                game_id = game["id"]
                name = game["name"]

                if game_id in installed:

                    status = "[INST]"

                elif index in self.selected:

                    status = "[ X ]"

                else:

                    status = "[   ]"

                text = (
                    f"{status} "
                    f"{game_id:<12} "
                    f"{name}"
                )

            else:

                text = (
                    f"{game['id']:<12} "
                    f"{game['name']}"
                )

            if index == self.cursor:

                self.safe_addstr(
                    y,
                    2,
                    text[:width - 3],
                    curses.A_REVERSE,
                )

            else:

                self.safe_addstr(
                    y,
                    2,
                    text[:width - 3],
                )

        footer_y = height - 2

        self.safe_addstr(
            footer_y,
            2,
            self.message[:width - 4],
        )

        if self.mode == "hdd":

            keys_help = (
                "[A] descargar/subir ART  "
                "[D] borrar  [/] buscar  "
                "[N] siguiente  [R] refrescar  "
                "[Q] salir"
            )

        else:

            keys_help = (
                "[SPACE] seleccionar  "
                "[ENTER] instalar  "
                "[A] descargar/subir ART  "
                "[/] buscar  "
                "[N] siguiente  [R] refrescar  "
                "[Q] salir"
            )

        self.safe_addstr(
            height - 1,
            2,
            keys_help,
            curses.A_DIM,
        )

        self.stdscr.refresh()

    # --------------------------------------------------------
    # INSTALL PROGRESS
    # --------------------------------------------------------

    def show_install_progress(
        self,
        game,
        progress="",
        current=1,
        total=1,
    ):

        self.stdscr.erase()

        height, width = (
            self.stdscr.getmaxyx()
        )

        title = " PS2 MANAGER "

        self.safe_addstr(
            0,
            max(
                0,
                (width - len(title)) // 2,
            ),
            title,
            curses.A_BOLD,
        )

        self.safe_addstr(
            3,
            2,
            "SUBIENDO AL HDD",
            curses.A_BOLD,
        )

        counter = (
            f"[{current}/{total}]"
        )

        self.safe_addstr(
            5,
            2,
            counter,
            curses.A_BOLD,
        )

        self.safe_addstr(
            5,
            12,
            f"Juego: {game['name']}",
        )

        self.safe_addstr(
            6,
            12,
            f"ID:    {game['id']}",
        )

        self.safe_addstr(
            9,
            2,
            "Progreso:",
            curses.A_BOLD,
        )

        game_name = (
            game["name"]
            or game["id"]
        )

        name_width = 28

        if len(game_name) > name_width:

            game_name = (
                game_name[
                    :name_width - 3
                ]
                + "..."
            )

        if not progress:

            progress = (
                "Preparando transferencia..."
            )

        progress = (
            progress
            .replace("\r", "")
            .replace("\n", "")
            .strip()
        )

        prefix = (
            f"{game_name:<{name_width}} "
        )

        available_width = (
            width
            - 4
            - len(prefix)
        )

        if available_width < 1:
            available_width = 1

        if len(progress) > available_width:

            progress = progress[
                -available_width:
            ]

        progress_line = (
            prefix + progress
        )

        self.safe_addstr(
            11,
            2,
            progress_line,
            curses.A_BOLD,
        )

        self.safe_addstr(
            14,
            2,
            f"HDD: {self.config['device']}",
            curses.A_DIM,
        )

        self.safe_addstr(
            15,
            2,
            f"ISO: {game['path']}",
            curses.A_DIM,
        )

        self.safe_addstr(
            height - 2,
            2,
            (
                f"Juego {current} de {total} · "
                "Transferencia en curso..."
            ),
            curses.A_DIM,
        )

        self.safe_addstr(
            height - 1,
            2,
            "NO desconectes el HDD ni cierres el programa",
            curses.A_REVERSE,
        )

        self.stdscr.refresh()

    # --------------------------------------------------------
    # MOVE
    # --------------------------------------------------------

    def move_cursor(
        self,
        direction,
    ):

        games = (
            self.isos
            if self.mode == "source"
            else self.hdd_games
        )

        if not games:
            return

        self.cursor += direction

        self.cursor = max(
            0,
            min(
                self.cursor,
                len(games) - 1,
            ),
        )

        height, _ = (
            self.stdscr.getmaxyx()
        )

        visible = (
            height - 8
        )

        if self.cursor < self.scroll:

            self.scroll = self.cursor

        elif (
            self.cursor
            >= self.scroll + visible
        ):

            self.scroll = (
                self.cursor
                - visible
                + 1
            )

    # --------------------------------------------------------
    # SELECT
    # --------------------------------------------------------

    def toggle_selection(self):

        if self.mode != "source":
            return

        if not self.isos:
            return

        game = self.isos[
            self.cursor
        ]

        if (
            game["id"]
            in self.installed_ids()
        ):

            self.message = (
                "Ese juego ya está instalado"
            )

            return

        if (
            self.cursor
            in self.selected
        ):

            self.selected.remove(
                self.cursor
            )

        else:

            self.selected.add(
                self.cursor
            )

    # --------------------------------------------------------
    # INSTALL
    # --------------------------------------------------------

    def install_selected(self):

        if not self.selected:

            self.message = (
                "No hay juegos seleccionados"
            )

            return

        if not device_looks_valid(
            self.config["device"]
        ):

            self.message = (
                f"El dispositivo "
                f"{self.config['device']} "
                "no existe, revisa la configuración (F3)"
            )

            return

        games = [
            self.isos[index]
            for index in sorted(
                self.selected
            )
        ]

        installed = (
            self.installed_ids()
        )

        pending = [
            game
            for game in games
            if game["id"] not in installed
        ]

        if not pending:

            self.message = (
                "Todos los juegos seleccionados "
                "ya están instalados"
            )

            self.selected.clear()

            return

        names = ", ".join(
            game["id"]
            for game in pending
        )

        disk = device_info(
            self.config["device"]
        )

        disk_label = (
            f"{self.config['device']} "
            f"[{disk}]"
            if disk
            else self.config["device"]
        )

        if not self.confirm(
            f"¿Instalar {len(pending)} juego(s) "
            f"({names}) en "
            f"{disk_label}?"
        ):

            self.message = (
                "Instalación cancelada"
            )

            return

        total = len(pending)

        uploaded = 0

        for game in pending:

            current = (
                uploaded + 1
            )

            self.show_install_progress(
                game,
                "Preparando transferencia...",
                current=current,
                total=total,
            )

            def progress_callback(
                line,
                current_game=game,
                current_number=current,
            ):

                self.show_install_progress(
                    current_game,
                    line,
                    current=current_number,
                    total=total,
                )

            success, output = inject_game(
                self.config,
                game,
                progress_callback,
            )

            if success:

                uploaded += 1

                self.message = (
                    f"[{uploaded}/{total}] "
                    f"{game['id']} "
                    "instalado correctamente"
                )

            else:

                self.message = (
                    f"ERROR instalando "
                    f"{game['id']} "
                    f"([{current}/{total}])"
                )

                self.show_output(
                    output
                )

            self.draw()

            time.sleep(1)

        self.selected.clear()

        self.message = (
            f"Instalación terminada: "
            f"{uploaded}/{total} juegos subidos"
        )

        self.refresh_all()

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    def log(
        self,
        text,
    ):

        lines = text.splitlines()

        if lines:

            self.message = (
                lines[-1]
            )

        self.draw()

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    def show_output(
        self,
        output,
    ):

        height, width = (
            self.stdscr.getmaxyx()
        )

        lines = output.splitlines()

        if not lines:
            return

        self.stdscr.erase()

        self.safe_addstr(
            0,
            2,
            "SALIDA",
            curses.A_BOLD,
        )

        for i, line in enumerate(
            lines[-height + 3:]
        ):

            self.safe_addstr(
                i + 2,
                2,
                line[:width - 4],
            )

        self.safe_addstr(
            height - 1,
            2,
            "Pulsa una tecla para continuar...",
            curses.A_DIM,
        )

        self.stdscr.refresh()

        self.stdscr.getch()

    # --------------------------------------------------------
    # ART
    # --------------------------------------------------------

    def upload_current_art(self):

        if self.mode == "source":

            if not self.isos:

                self.message = (
                    "No hay juegos disponibles"
                )

                return

            game = self.isos[
                self.cursor
            ]

            game_id = game["id"]

        elif self.mode == "hdd":

            if not self.hdd_games:

                self.message = (
                    "No hay juegos en el HDD"
                )

                return

            game = self.hdd_games[
                self.cursor
            ]

            game_id = game["id"]

        else:

            return

        if game_id == "UNKNOWN":

            self.message = (
                "No se puede descargar ART: "
                "ID desconocido"
            )

            return

        if not device_looks_valid(
            self.config["device"]
        ):

            self.message = (
                f"El dispositivo "
                f"{self.config['device']} "
                "no existe, revisa la configuración (F3)"
            )

            return

        # ----------------------------------------------------
        # En "source" (F1) comprobamos si el ART ya está
        # descargado localmente para no volver a descargarlo.
        # En "hdd" (F2) se mantiene el comportamiento
        # original: siempre descarga y sube.
        # ----------------------------------------------------

        if self.mode == "source":

            already = find_art(
                game_id,
                self.config["art_source"],
            )

            if already:

                prompt = (
                    f"¿Subir ART ya descargado de "
                    f"{game_id} "
                    f"({len(already)}/{len(ART_TYPES)} "
                    "archivos)?"
                )

            else:

                prompt = (
                    f"¿Descargar y subir ART de "
                    f"{game_id}?"
                )

        else:

            prompt = (
                f"¿Descargar y subir ART de "
                f"{game_id}?"
            )

        if not self.confirm(prompt):

            self.message = (
                "Operación cancelada"
            )

            return

        self.message = (
            f"Procesando ART de "
            f"{game_id}..."
        )

        self.draw()

        if self.mode == "source":

            success, output = (
                ensure_art_and_upload(
                    self.config,
                    game_id,
                    self.log,
                )
            )

        else:

            success, output = (
                download_and_upload_art(
                    self.config,
                    game_id,
                    self.log,
                )
            )

        if success:

            self.message = (
                f"ART de {game_id} "
                "subido correctamente"
            )

        else:

            self.message = (
                f"ERROR con ART de "
                f"{game_id}"
            )

            self.show_output(
                output
            )

    # --------------------------------------------------------
    # DELETE
    # --------------------------------------------------------

    def delete_current(self):

        if self.mode != "hdd":
            return

        if not self.hdd_games:
            return

        if not device_looks_valid(
            self.config["device"]
        ):

            self.message = (
                f"El dispositivo "
                f"{self.config['device']} "
                "no existe, revisa la configuración (F3)"
            )

            return

        game = self.hdd_games[
            self.cursor
        ]

        disk = device_info(
            self.config["device"]
        )

        disk_label = (
            f"{self.config['device']} "
            f"[{disk}]"
            if disk
            else self.config["device"]
        )

        if not self.confirm(
            f"¿BORRAR {game['id']} "
            f"({game['name']}) del HDD "
            f"{disk_label}? "
            "Esto no se puede deshacer"
        ):

            self.message = (
                "Borrado cancelado"
            )

            return

        self.message = (
            f"Borrando "
            f"{game['id']}..."
        )

        self.draw()

        success, output = delete_game(
            self.config,
            game,
            self.log,
        )

        if success:

            self.message = (
                f"{game['id']} "
                "borrado correctamente"
            )

        else:

            self.message = (
                f"ERROR borrando "
                f"{game['id']}"
            )

            self.show_output(
                output
            )

        self.refresh_all()

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    def search_prompt(self):

        height, width = (
            self.stdscr.getmaxyx()
        )

        curses.echo()

        try:

            curses.curs_set(1)

        except curses.error:

            pass

        self.safe_addstr(
            height - 1,
            2,
            "Buscar: ",
            curses.A_REVERSE,
        )

        self.stdscr.refresh()

        try:

            raw = (
                self.stdscr
                .getstr(
                    height - 1,
                    10,
                )
                .decode(
                    errors="ignore"
                )
            )

        except curses.error:

            raw = ""

        curses.noecho()

        try:

            curses.curs_set(0)

        except curses.error:

            pass

        if raw:

            self.search_term = raw

            self.jump_to_match(
                start_from=0
            )

        else:

            self.message = (
                "Búsqueda cancelada"
            )

    def search_next(self):

        if not self.search_term:

            self.message = (
                "No hay término de búsqueda "
                "(pulsa /)"
            )

            return

        self.jump_to_match(
            start_from=self.cursor + 1
        )

    def jump_to_match(
        self,
        start_from,
    ):

        games = (
            self.isos
            if self.mode == "source"
            else self.hdd_games
        )

        if not games:
            return

        term = (
            self.search_term.lower()
        )

        n = len(games)

        for offset in range(n):

            index = (
                start_from + offset
            ) % n

            game = games[index]

            haystack = (
                f"{game['id']} "
                f"{game['name']}"
            ).lower()

            if term in haystack:

                self.cursor = index

                height, _ = (
                    self.stdscr.getmaxyx()
                )

                visible = (
                    height - 8
                )

                self.scroll = max(
                    0,
                    index - visible // 2,
                )

                self.message = (
                    f"Encontrado: "
                    f"{game['id']} "
                    f"{game['name']}"
                )

                return

        self.message = (
            f"Sin resultados para "
            f"'{self.search_term}'"
        )

    # --------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------

    def configuration(self):

        curses.echo()

        fields = [
            (
                "source",
                "Carpeta de ISOs",
            ),
            (
                "art_source",
                "Carpeta ART",
            ),
            (
                "device",
                "Dispositivo HDD",
            ),
            (
                "opl_partition",
                "Partición OPL",
            ),
            (
                "hdl_dump",
                "Ruta hdl_dump",
            ),
            (
                "pfsshell",
                "Ruta pfsshell",
            ),
        ]

        while True:

            self.stdscr.erase()

            height, width = (
                self.stdscr.getmaxyx()
            )

            self.safe_addstr(
                1,
                2,
                "CONFIGURACIÓN",
                curses.A_BOLD,
            )

            for i, (
                key,
                label,
            ) in enumerate(fields):

                y = 4 + i

                self.safe_addstr(
                    y,
                    2,
                    f"{i + 1}. {label}: "
                    f"{self.config[key]}",
                )

            self.safe_addstr(
                height - 3,
                2,
                "Introduce número para modificar "
                "(ENTER para salir): ",
            )

            self.stdscr.refresh()

            key = self.stdscr.getch()

            if key in (
                10,
                13,
                27,
            ):

                break

            if (
                ord("1")
                <= key
                <= ord("6")
            ):

                index = (
                    key - ord("1")
                )

                config_key, label = (
                    fields[index]
                )

                self.safe_addstr(
                    height - 2,
                    2,
                    "Nuevo valor: ",
                )

                self.stdscr.refresh()

                value = (
                    self.stdscr
                    .getstr(
                        height - 2,
                        16,
                    )
                    .decode(
                        errors="ignore"
                    )
                )

                if value:

                    self.config[
                        config_key
                    ] = value

        curses.noecho()

        save_config(
            self.config
        )

        clear_executable_cache()

        self.refresh_all()

    # --------------------------------------------------------
    # KEYBOARD
    # --------------------------------------------------------

    def run(self):

        if not self.config.get("device"):

            self.message = (
                "Configura el dispositivo HDD "
                "antes de continuar"
            )

            self.configuration()

        while True:

            self.draw()

            key = self.stdscr.getch()

            if key in (
                ord("q"),
                ord("Q"),
            ):

                break

            elif key == curses.KEY_UP:

                self.move_cursor(-1)

            elif key == curses.KEY_DOWN:

                self.move_cursor(1)

            elif key == curses.KEY_PPAGE:

                self.move_cursor(-10)

            elif key == curses.KEY_NPAGE:

                self.move_cursor(10)

            elif key == curses.KEY_F1:

                self.mode = "source"

                self.cursor = 0
                self.scroll = 0

            elif key == curses.KEY_F2:

                self.mode = "hdd"

                self.cursor = 0
                self.scroll = 0

            elif key == curses.KEY_F3:

                self.configuration()

            elif key == ord(" "):

                self.toggle_selection()

            elif key in (
                10,
                13,
            ):

                if self.mode == "source":

                    if self.selected:

                        self.install_selected()

                    else:

                        before = len(
                            self.selected
                        )

                        self.toggle_selection()

                        if (
                            len(self.selected)
                            > before
                        ):

                            self.install_selected()

            elif key in (
                ord("a"),
                ord("A"),
            ):

                self.upload_current_art()

            elif key in (
                ord("d"),
                ord("D"),
            ):

                if self.mode == "hdd":

                    self.delete_current()

            elif key == ord("/"):

                self.search_prompt()

            elif key in (
                ord("n"),
                ord("N"),
            ):

                self.search_next()

            elif key in (
                ord("r"),
                ord("R"),
            ):

                self.refresh_all()


# ============================================================
# DEPENDENCIAS
# ============================================================

def check_dependencies():

    required = []
    optional = []

    if not find_executable("hdl_dump"):

        required.append((
            "hdl_dump",
            "necesario para leer, instalar y borrar "
            "juegos del HDD. Compílalo o descárgalo "
            "(por ejemplo desde "
            "github.com/w-vekony/hdl_dump o similar) "
            "y añádelo al PATH, o indica la ruta "
            "completa en la configuración (F3).",
        ))

    if not find_executable("pfsshell"):

        optional.append((
            "pfsshell",
            "necesario para subir el ART al HDD "
            "(tecla A). Sin él no podrás subir "
            "carátulas.",
        ))

    if not find_executable("curl"):

        optional.append((
            "curl",
            "necesario para descargar el ART "
            "automáticamente.",
        ))

    if not find_executable("isoinfo"):

        optional.append((
            "isoinfo",
            "opcional: mejora la detección del ID "
            "de juego cuando el nombre del archivo "
            "no lo incluye (paquete genisoimage o "
            "cdrtools).",
        ))

    if required:

        print(
            "Faltan dependencias necesarias:\n"
        )

        for name, hint in required:

            print(f"  - {name}: {hint}")

        print()

    if optional:

        print(
            "Dependencias opcionales no encontradas:\n"
        )

        for name, hint in optional:

            print(f"  - {name}: {hint}")

        print()

    if required:

        try:

            input(
                "Pulsa ENTER para continuar de "
                "todos modos, o Ctrl+C para salir..."
            )

        except KeyboardInterrupt:

            print()

            sys.exit(1)

    elif optional:

        time.sleep(2)


# ============================================================
# MAIN
# ============================================================

def main():

    if os.geteuid() != 0:

        print(
            "Este programa necesita acceso "
            "al HDD de PS2."
        )

        print()

        print(
            "Ejecuta:"
        )

        print()

        print(
            f"  sudo {sys.executable} "
            f"{Path(__file__).resolve()}"
        )

        print()

        sys.exit(1)

    check_dependencies()

    curses.wrapper(
        lambda stdscr:
        PS2Manager(stdscr).run()
    )


if __name__ == "__main__":

    main()
