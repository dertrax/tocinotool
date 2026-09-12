"""Localización y ejecución de herramientas externas (ffmpeg, mkvmerge, filebot…).

Orden de búsqueda: ruta en config/tool.yaml → PATH del sistema → rutas conocidas
(binaries/ en Windows, /opt/filebot en Linux…). Así la misma tool funciona en
Windows con los .exe de la carpeta y en un servidor Linux con los paquetes
del sistema.
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import ROOT, ui

ES_WINDOWS = os.name == "nt"
BINARIES = ROOT / "binaries"
MEDIAINFO_BINARIES = BINARIES / "mediainfo"

# Rutas conocidas fuera del PATH, por herramienta y sistema
_CANDIDATOS: Dict[str, Dict[str, List[str]]] = {
    "ffmpeg": {
        "nt": [str(BINARIES / "ffmpeg.exe")],
        "posix": ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"],
    },
    "ffprobe": {
        "nt": [str(BINARIES / "ffprobe.exe")],
        "posix": ["/usr/bin/ffprobe", "/usr/local/bin/ffprobe", "/opt/homebrew/bin/ffprobe"],
    },
    "mkvmerge": {
        "nt": [str(BINARIES / "mkvmerge.exe"), r"C:\Program Files\MKVToolNix\mkvmerge.exe"],
        "posix": ["/usr/bin/mkvmerge", "/usr/local/bin/mkvmerge", "/opt/homebrew/bin/mkvmerge"],
    },
    "mkvpropedit": {
        "nt": [str(BINARIES / "mkvpropedit.exe"), r"C:\Program Files\MKVToolNix\mkvpropedit.exe"],
        "posix": ["/usr/bin/mkvpropedit", "/usr/local/bin/mkvpropedit"],
    },
    "mediainfo": {
        "nt": [str(MEDIAINFO_BINARIES / "MediaInfo.exe"), str(BINARIES / "mediainfo.exe"),
               str(BINARIES / "_legacy" / "dogtool" / "TemplateFill" / "MediaInfo.exe"),
               r"C:\Program Files\MediaInfo\MediaInfo.exe"],
        "posix": ["/usr/bin/mediainfo", "/usr/local/bin/mediainfo", "/opt/homebrew/bin/mediainfo"],
    },
    "filebot": {
        "nt": [r"C:\Program Files\FileBot\filebot.exe", r"C:\Program Files\FileBot\filebot.launcher.exe"],
        "posix": ["/usr/bin/filebot", "/usr/local/bin/filebot", "/opt/filebot/filebot.sh",
                  "/Applications/FileBot.app/Contents/MacOS/filebot.sh"],
    },
}

# Cómo instalar cada herramienta, por gestor de paquetes
INSTALACION = {
    "winget": {
        "ffmpeg": "Gyan.FFmpeg",
        "ffprobe": "Gyan.FFmpeg",
        "mkvmerge": "MoritzBunkus.MKVToolNix",
        "mkvpropedit": "MoritzBunkus.MKVToolNix",
        "mediainfo": "MediaArea.MediaInfo.CLI",
        "filebot": "PointPlanck.FileBot",
    },
    "apt": {
        "ffmpeg": "ffmpeg",
        "ffprobe": "ffmpeg",
        "mkvmerge": "mkvtoolnix",
        "mkvpropedit": "mkvtoolnix",
        "mediainfo": "mediainfo",
        "filebot": None,  # no está en apt: https://www.filebot.net/#download
    },
    "brew": {
        "ffmpeg": "ffmpeg",
        "ffprobe": "ffmpeg",
        "mkvmerge": "mkvtoolnix",
        "mkvpropedit": "mkvtoolnix",
        "mediainfo": "media-info",
        "filebot": "filebot",
    },
}

_cache: Dict[str, Optional[str]] = {}
DETALLADO = False   # True → se imprimen las líneas de comando (config: mostrar_comandos)


def buscar(nombre: str, cfg=None, obligatorio: bool = False) -> Optional[str]:
    """Devuelve la ruta ejecutable de `nombre` o None."""
    if nombre in _cache and _cache[nombre]:
        return _cache[nombre]

    ruta: Optional[str] = None
    manual = cfg.ruta_herramienta(nombre) if cfg is not None else ""
    if manual and Path(manual).exists():
        ruta = manual
    if ruta is None:
        ruta = shutil.which(nombre)
    if ruta is None:
        for cand in _CANDIDATOS.get(nombre, {}).get(os.name, []):
            if Path(cand).exists():
                ruta = cand
                break
    _cache[nombre] = ruta
    if ruta is None and obligatorio:
        raise RuntimeError(f"No se encuentra la herramienta '{nombre}'. Ejecuta el asistente de instalación.")
    return ruta


def olvidar_cache() -> None:
    _cache.clear()


def biblioteca_mediainfo(cfg=None) -> Optional[str]:
    """DLL que debe cargar pymediainfo.

    La distribución Windows incluye una copia portable de la DLL oficial en
    ``binaries/mediainfo/``. Así la ficha no depende de una instalación global
    de MediaInfo. Como compatibilidad, se prueba junto al ejecutable localizado
    si la distribución portable no está disponible.
    """
    candidatas = [MEDIAINFO_BINARIES / "MediaInfo.dll"]
    exe = buscar("mediainfo", cfg)
    if exe:
        candidatas.append(Path(exe).with_name("MediaInfo.dll"))
    for ruta in candidatas:
        if ruta.is_file():
            return str(ruta)
    return None


def version(nombre: str, cfg=None) -> Optional[str]:
    """Primera línea de la salida de versión, o None si no está."""
    exe = buscar(nombre, cfg)
    if not exe:
        return None
    # En Windows el instalador gráfico y el CLI pueden llamarse ambos
    # MediaInfo.exe. El gráfico abre una ventana ante --Version y se queda
    # esperando a que el usuario la cierre. La versión es informativa: no
    # ejecutar nunca MediaInfo desde aquí; pymediainfo ya verifica la librería
    # nativa que realmente utiliza la tool.
    if nombre == "mediainfo" and ES_WINDOWS:
        return None
    flags = {"ffmpeg": ["-version"], "ffprobe": ["-version"], "mkvmerge": ["--version"],
             "mkvpropedit": ["--version"], "mediainfo": ["--Version"], "filebot": ["-version"]}
    try:
        r = subprocess.run([exe] + flags.get(nombre, ["--version"]), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
        salida = (r.stdout or r.stderr).strip().splitlines()
        for linea in salida:
            if linea.strip():
                return linea.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def gestor_paquetes() -> Optional[str]:
    if ES_WINDOWS:
        return "winget" if shutil.which("winget") else None
    if platform.system() == "Darwin":
        return "brew" if shutil.which("brew") else None
    return "apt" if shutil.which("apt-get") else None


def comando_instalacion(nombre: str) -> Optional[List[str]]:
    gestor = gestor_paquetes()
    if not gestor:
        return None
    paquete = INSTALACION[gestor].get(nombre)
    if not paquete:
        return None
    if gestor == "winget":
        return ["winget", "install", "--id", paquete, "-e", "--accept-source-agreements",
                "--accept-package-agreements"]
    if gestor == "apt":
        return ["sudo", "apt-get", "install", "-y", paquete]
    return ["brew", "install", paquete]


def ejecutar(cmd: Sequence[str], capturar: bool = False, comprobar: bool = True,
             mostrar: bool = True, cwd: Optional[Path] = None,
             codificacion: Optional[str] = None) -> subprocess.CompletedProcess:
    """Ejecuta un comando. Con `mostrar` imprime la línea de comando en gris."""
    if mostrar and DETALLADO:
        print(ui.gris("   $ " + " ".join(_citar(c) for c in cmd)))
    sys.stdout.flush()
    r = subprocess.run(list(cmd), capture_output=capturar, text=capturar,
                       encoding=codificacion or "utf-8" if capturar else None,
                       errors="replace" if capturar else None,
                       cwd=str(cwd) if cwd else None)
    if comprobar and r.returncode != 0:
        detalle = (r.stderr or r.stdout or "").strip() if capturar else ""
        raise RuntimeError(f"Fallo ejecutando {Path(cmd[0]).name} (código {r.returncode}). {detalle[-800:]}")
    return r


def ejecutar_silencioso(cmd: Sequence[str]) -> None:
    """Ejecuta sin mostrar la salida; si falla, enseña las últimas líneas del error."""
    r = ejecutar(cmd, capturar=True, comprobar=False)
    if r.returncode != 0:
        salida = (r.stderr or "") + (r.stdout or "")
        lineas = [l for l in salida.splitlines() if l.strip()][-8:]
        raise RuntimeError(f"Fallo ejecutando {Path(cmd[0]).name}:" + "".join(chr(10) + "   " + l for l in lineas))


def ejecutar_mkvmerge(cmd: Sequence[str], etiqueta: str = "") -> None:
    """Ejecuta mkvmerge mostrando una barra de progreso en una sola línea
    (lee sus 'Progress: N%'). Si falla, enseña las últimas líneas del error."""
    import re
    if DETALLADO:
        print(ui.gris("   $ " + " ".join(_citar(c) for c in cmd)))
    sys.stdout.flush()
    proc = subprocess.Popen(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf = b""
    salida = []
    ultimo = -1
    barra = ui.Barra(etiqueta)
    while True:
        trozo = proc.stdout.read(256)
        if not trozo:
            break
        buf += trozo
        partes = re.split(rb"[\r\n]", buf)
        buf = partes.pop()
        for parte in partes:
            m = re.search(rb"Progress:\s*(\d+)%", parte)
            if m:
                pct = int(m.group(1))
                if pct != ultimo:
                    ultimo = pct
                    barra.avanzar(pct)
            elif parte.strip():
                salida.append(parte.decode("utf-8", "replace"))
    proc.wait()
    barra.terminar(proc.returncode == 0)
    if proc.returncode != 0:
        raise RuntimeError(f"Fallo ejecutando {Path(cmd[0]).name}:" + "".join(chr(10) + "   " + l for l in salida[-8:]))


def _citar(c: str) -> str:
    return f'"{c}"' if (" " in c or c == "") else c


def ffmpeg_tiene_filtro(nombre_filtro: str, cfg=None) -> bool:
    exe = buscar("ffmpeg", cfg)
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(f" {nombre_filtro} " in linea for linea in r.stdout.splitlines())


def python_actual() -> str:
    return f"Python {platform.python_version()} ({sys.executable})"
