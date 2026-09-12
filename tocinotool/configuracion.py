"""Opciones de configuración que se pueden cambiar dentro de la tool.

La instalación de Python, el venv, paquetes y herramientas externas vive en el
asistente del launcher. Aquí solo quedan datos y preferencias del usuario.
"""
from . import tools, ui


def _usuario(cfg) -> None:
    cfg.d["usuario"] = ui.preguntar("Usuario del tracker", defecto=cfg.d.get("usuario") or None, obligatorio=True)
    cfg.guardar("usuario")
    ui.ok(f"Usuario: {cfg.d['usuario']}")


def _mostrar_comandos(cfg) -> None:
    activo = bool(cfg.get("mostrar_comandos"))
    r = ui.preguntar_opcion("Mostrar los comandos técnicos", [
        ("si", "sí, para depurar"),
        ("no", "no, salida compacta"),
    ], defecto="si" if activo else "no")
    cfg.d["mostrar_comandos"] = r == "si"
    cfg.guardar("mostrar_comandos")
    tools.DETALLADO = bool(cfg.d["mostrar_comandos"])


def _rutas(cfg) -> None:
    nombres = ["ffmpeg", "ffprobe", "mkvmerge", "mkvpropedit", "mediainfo", "filebot"]
    opciones = [(n, f"{n:<12} {cfg.ruta_herramienta(n) or 'detección automática'}") for n in nombres]
    opciones.append(("volver", "volver"))
    nombre = ui.preguntar_opcion("Ruta manual de una herramienta", opciones, defecto="volver")
    if nombre == "volver":
        return
    accion = ui.preguntar_opcion(nombre, [
        ("auto", "usar detección automática"),
        ("ruta", "indicar ejecutable manualmente"),
    ], defecto="auto" if not cfg.ruta_herramienta(nombre) else "ruta")
    cfg.d.setdefault("herramientas", {})[nombre] = "" if accion == "auto" else str(
        ui.preguntar_ruta(f"Ruta de {nombre}", tipo="file"))
    cfg.guardar("herramientas")
    tools.olvidar_cache()


def flujo(cfg) -> None:
    ui.titulo("CONFIGURACIÓN")
    while True:
        op = ui.preguntar_opcion("Qué quieres configurar", [
            ("usuario", "usuario del tracker"),
            ("rutas", "rutas manuales de herramientas"),
            ("comandos", "mostrar comandos técnicos"),
            ("volver", "volver al menú principal"),
        ], defecto="volver")
        if op == "volver":
            return
        if op == "usuario":
            _usuario(cfg)
        elif op == "rutas":
            _rutas(cfg)
        else:
            _mostrar_comandos(cfg)
