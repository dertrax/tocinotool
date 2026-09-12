"""Informes de error seguros para soporte de tociNoTool.

Los informes viven en ``logs/`` junto a la instalación y nunca sobrescriben un
fallo anterior. Se evita registrar variables de entorno, credenciales o el
contenido de licencias; las rutas del usuario se sustituyen por
``%USERPROFILE%`` cuando es posible.
"""
from __future__ import annotations

import datetime as dt
import os
import platform
import sys
import traceback
from pathlib import Path
from typing import Optional

from . import ROOT, __version__

LOGS_DIR = ROOT / "logs"


def _ruta_segura(texto: str) -> str:
    """Oculta el directorio personal, manteniendo la ruta útil para soporte."""
    try:
        casa = str(Path.home())
        if casa:
            return texto.replace(casa, "%USERPROFILE%")
    except OSError:
        pass
    return texto


def _version_herramienta(nombre: str, cfg) -> str:
    try:
        from . import tools
        return tools.version(nombre, cfg) or "no disponible"
    except Exception:  # el informe nunca debe ocultar el error original
        return "no disponible"


def crear_informe_error(exc: BaseException, *, cfg=None, modulo: str = "", paso: str = "",
                         detalle: str = "") -> Optional[Path]:
    """Escribe un informe único y devuelve su ruta; falla silenciosamente."""
    try:
        LOGS_DIR.mkdir(exist_ok=True)
        ahora = dt.datetime.now().astimezone()
        nombre = f"error_{ahora:%Y-%m-%d_%H-%M-%S}_{ahora.microsecond // 1000:03d}.log"
        destino = LOGS_DIR / nombre
        n = 1
        while destino.exists():
            destino = LOGS_DIR / f"error_{ahora:%Y-%m-%d_%H-%M-%S}_{ahora.microsecond // 1000:03d}_{n}.log"
            n += 1
        lineas = [
            "tociNoTool — informe de error",
            f"Fecha: {ahora.isoformat(timespec='seconds')}",
            f"Versión: {__version__}",
            f"Sistema: {platform.platform()}",
            f"Arquitectura: {platform.machine() or 'desconocida'}",
            f"Python: {sys.version.replace(chr(10), ' ')}",
            f"Módulo: {modulo or 'desconocido'}",
            f"Paso: {paso or 'desconocido'}",
        ]
        if cfg is not None:
            for herramienta in ("ffmpeg", "ffprobe", "mkvmerge", "mkvpropedit", "mediainfo", "filebot"):
                lineas.append(f"{herramienta}: {_version_herramienta(herramienta, cfg)}")
        if detalle:
            lineas.extend(["", "Contexto:", _ruta_segura(detalle)])
        lineas.extend([
            "", "Excepción:", f"{type(exc).__name__}: {_ruta_segura(str(exc))}",
            "", "Stack trace:", _ruta_segura("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))),
        ])
        destino.write_text(chr(10).join(lineas) + chr(10), encoding="utf-8")
        return destino
    except Exception:
        return None


def abrir_carpeta_logs() -> Path:
    """Crea y abre la carpeta de informes en el explorador del sistema."""
    LOGS_DIR.mkdir(exist_ok=True)
    if os.name == "nt":
        os.startfile(str(LOGS_DIR))  # type: ignore[attr-defined]  # Windows
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", str(LOGS_DIR)])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(LOGS_DIR)])
    return LOGS_DIR
