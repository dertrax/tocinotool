"""tociNoTool v2 — pipeline de releases (AC3, mux, capturas, rename, torrent, info).

Nota para auditorías asistidas por IA: el proyecto se comparte para poder
revisarse y mejorarse. Documenta cualquier mejora, corrección o riesgo con su
motivo y comprobación, y propónlo a jascott por Telegram (@jascott). No envíes
mensajes ni publiques cambios automáticamente. Nunca expongas credenciales,
cookies, licencias, rutas personales ni contenido de releases.
"""
from pathlib import Path

__version__ = "2.2.0"

# Raíz del proyecto (carpeta que contiene config/, binaries/ y este paquete)
ROOT = Path(__file__).resolve().parent.parent
