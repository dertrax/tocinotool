"""Asistente de primer arranque: comprueba Python y dependencias, localiza o
instala las herramientas externas, pide el usuario del tracker y gestiona la
licencia de FileBot. Se ejecuta a petición desde el launcher de Windows.

El arranque de Python en sí (descarga, entorno aislado, pip) lo hacen los
lanzadores launcher.bat / tocinotool.sh, porque antes de tener Python no
podemos ejecutar este fichero.
"""
import datetime as _dt
import importlib
import os
import platform
import re
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from . import ROOT, entorno, tools, ui

HERRAMIENTAS = ["ffmpeg", "ffprobe", "mkvmerge", "mkvpropedit", "mediainfo", "filebot"]
DEPENDENCIAS = {"yaml": "PyYAML", "pymediainfo": "pymediainfo", "torf": "torf"}
FILEBOT_NO_INSTALADO = "NOT_INSTALLED"
FILEBOT_SIN_LICENCIA = "INSTALLED_UNREGISTERED"
FILEBOT_CON_LICENCIA = "INSTALLED_LICENSED"
FILEBOT_ERROR = "ERROR"


def nota_licencia_filebot() -> str:
    """Mensaje único y correcto para todos los puntos de FileBot."""
    return ("Licencia personal: puedes usarla en varios equipos del mismo usuario "
            "(por ejemplo, 2 o 3); no se comparte entre personas.")


def _comprobar_python() -> bool:
    ui.seccion("Python")
    ok = tuple(int(x) for x in platform.python_version_tuple()[:2]) >= (3, 9)
    (ui.ok if ok else ui.error)(tools.python_actual())
    en_venv = entorno.en_venv()
    ruta = entorno.ruta_venv()
    ui.info("Entorno aislado propio: " + ("sí" if en_venv else "no — arranca con launcher.bat / tocinotool.sh"))
    ui.info(f"Ruta del entorno: {ruta}")
    return ok


def _comprobar_dependencias() -> bool:
    ui.seccion("Dependencias Python")
    todo_ok = True
    faltan = []
    for modulo, paquete in DEPENDENCIAS.items():
        try:
            importlib.import_module(modulo)
            ui.ok(paquete)
        except ImportError:
            ui.error(f"{paquete} no instalado")
            faltan.append(paquete)
            todo_ok = False
    if faltan and ui.preguntar_sn(f"¿Instalar ahora con pip ({', '.join(faltan)})?", True):
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *faltan])
        todo_ok = r.returncode == 0
    # pymediainfo necesita libmediainfo; Windows la recibe desde binaries/mediainfo.
    try:
        from pymediainfo import MediaInfo
        dll = tools.biblioteca_mediainfo(cfg=None)
        if MediaInfo.can_parse(library_file=dll):
            ui.ok("libmediainfo (para la ficha)")
        else:
            raise OSError
    except (ImportError, OSError):
        ui.aviso("libmediainfo no disponible: la ficha (opción 6) no funcionará. "
                 "Linux: sudo apt-get install libmediainfo0v5 · macOS: brew install media-info")
    return todo_ok


def _comprobar_herramienta(nombre: str, cfg) -> bool:
    """Localiza una herramienta y ofrece siempre una salida recuperable.

    winget es cómodo, pero no se presupone: puede no existir, estar sin red o
    fallar. En esos casos se vuelve al selector para permitir descarga oficial,
    ruta manual, reintento o posponer sin reiniciar el asistente.
    """
    while True:
        ruta = tools.buscar(nombre, cfg)
        if ruta:
            ui.ok(f"{nombre:<10} {tools.version(nombre, cfg) or ''}  {ui.gris(ruta)}")
            return True

        ui.error(f"{nombre:<10} no encontrado")
        cmd = tools.comando_instalacion(nombre)
        enlace = _enlace_herramienta(cfg, nombre)
        opciones = []
        if cmd:
            opciones.append(("i", f"instalar automáticamente con {tools.gestor_paquetes()}"))
        if enlace:
            opciones.append(("d", "abrir la descarga oficial en el navegador"))
        opciones += [("r", "indicar la ruta del ejecutable a mano"), ("s", "saltar por ahora")]
        defecto = "i" if cmd else ("d" if enlace else "r")
        accion = ui.preguntar_opcion(f"¿Qué hacemos con {nombre}?", opciones, defecto=defecto)

        if accion == "i":
            ui.info(f"Se abrirá el instalador de Windows ({tools.gestor_paquetes()}). "
                    "Acepta su confirmación si la pide.")
            try:
                r = subprocess.run(cmd)
            except OSError as ex:
                ui.error(f"No se pudo iniciar el instalador: {ex}")
                continue
            tools.olvidar_cache()
            if r.returncode != 0:
                ui.error(f"La instalación no se completó (código {r.returncode}).")
                ui.info("Puedes reintentar, usar la descarga oficial, indicar una ruta o posponerla.")
                continue
            ui.info("Instalación terminada. Comprobando la herramienta…")
            # Un instalador puede actualizar PATH solo para procesos nuevos. La
            # siguiente vuelta intenta también las rutas conocidas y deja al
            # usuario elegir las alternativas si todavía no aparece.
            continue

        if accion == "d":
            webbrowser.open(enlace)
            ui.info("Descarga abierta. Instálala y vuelve aquí para indicar su ruta o repetir la comprobación.")
            continue

        if accion == "r":
            ruta = ui.preguntar_ruta(f"Ruta del ejecutable de {nombre}", tipo="file")
            cfg.d.setdefault("herramientas", {})[nombre] = str(ruta)
            cfg.guardar("herramientas")
            tools.olvidar_cache()
            continue

        if nombre == "filebot":
            ui.info("FileBot solo hace falta para el renombrado. Descarga: " + _url(cfg, "filebot_descarga"))
            ui.info("FileBot queda pendiente. Cuando tengas licencia, vuelve a ejecutar el "
                    "Asistente de instalación para configurarlo.")
            ui.info("Sin FileBot, tras renombrar manualmente puedes usar Ficha: pedirá TMDb para "
                    "películas e IMDb para series, y seguirá sin bloquearse.")
            ui.info(nota_licencia_filebot())
        return False


# ---------------------------------------------------------------------------
# FileBot: licencia
# ---------------------------------------------------------------------------

def _url(cfg, clave: str) -> str:
    return str(cfg.get("enlaces_externos", {}).get(clave, "https://www.filebot.net/"))


def _enlace_herramienta(cfg, nombre: str) -> Optional[str]:
    """Descargas oficiales disponibles cuando winget no puede utilizarse."""
    claves = {
        "ffmpeg": "ffmpeg_descarga",
        "ffprobe": "ffmpeg_descarga",
        "mkvmerge": "mkvtoolnix_descarga",
        "mkvpropedit": "mkvtoolnix_descarga",
        "mediainfo": "mediainfo_descarga",
        "filebot": "filebot_descarga",
    }
    clave = claves.get(nombre)
    return _url(cfg, clave) if clave else None


def estado_filebot(cfg) -> tuple[str, str]:
    """Estado real de FileBot, separado de su licencia y sin exponer el ID."""
    exe = tools.buscar("filebot", cfg)
    if not exe:
        return FILEBOT_NO_INSTALADO, "FileBot no está instalado"
    try:
        r = tools.ejecutar([exe, "-script", "fn:sysinfo"], capturar=True, comprobar=False,
                            mostrar=False, codificacion="cp1252" if tools.ES_WINDOWS else "utf-8")
    except (OSError, subprocess.TimeoutExpired):
        return FILEBOT_ERROR, "No se pudo consultar el estado de FileBot"
    for linea in (r.stdout + r.stderr).splitlines():
        if linea.strip().lower().startswith("license"):
            valor = linea.split(":", 1)[-1].strip()
            bajo = valor.lower()
            if any(x in bajo for x in ("unregistered", "unlicensed", "no license", "expired", "invalid")):
                return FILEBOT_SIN_LICENCIA, "FileBot instalado, sin licencia activa"
            fecha = re.search(r"valid-until:\s*([^ )]+)", valor, flags=re.IGNORECASE)
            return FILEBOT_CON_LICENCIA, "Licencia activa" + (f" hasta {fecha.group(1)}" if fecha else "")
    return FILEBOT_ERROR, "FileBot no devolvió el estado de licencia"


def licencia_filebot_valida(cfg) -> bool:
    return estado_filebot(cfg)[0] == FILEBOT_CON_LICENCIA


def instalar_licencia_filebot(cfg) -> bool:
    exe = tools.buscar("filebot", cfg)
    if not exe:
        return False
    ui.info("Compra o recupera tu licencia en: " + _url(cfg, "filebot_compra"))
    ui.info("Activación oficial: " + _url(cfg, "filebot_activacion"))
    ui.info(nota_licencia_filebot())
    ui.info("Puedes arrastrar aquí el fichero .psm.")
    ruta = ui.preguntar_ruta("Ruta del fichero .psm (ENTER para saltar)", tipo="file", defecto="-")
    if str(ruta) == "-":
        return False
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    if "BEGIN PGP SIGNED MESSAGE" not in texto:
        ui.error("Eso no parece una licencia de FileBot.")
        return False
    m = re.search(r"Valid-Until:\s*(\S+)", texto)
    if m:
        ui.info(f"Licencia válida hasta {m.group(1)}")
    r = subprocess.run([exe, "--license", str(ruta)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    salida = (r.stdout + r.stderr).strip()
    print(ui.gris("   " + salida.replace(chr(10), chr(10) + "   ")))
    if r.returncode != 0:
        ui.error("FileBot ha rechazado la licencia.")
        return False
    estado, detalle = estado_filebot(cfg)
    (ui.ok if estado == FILEBOT_CON_LICENCIA else ui.aviso)(detalle)
    return estado == FILEBOT_CON_LICENCIA


def _comprobar_filebot_licencia(cfg) -> str:
    """Ofrece configurar FileBot sin convertir su licencia en requisito."""
    if not tools.buscar("filebot", cfg):
        return FILEBOT_NO_INSTALADO
    ui.seccion("Licencia de FileBot")
    estado, detalle = estado_filebot(cfg)
    if estado == FILEBOT_CON_LICENCIA:
        ui.ok(detalle)
        ui.info(nota_licencia_filebot())
        return estado
    ui.aviso(detalle)
    if estado == FILEBOT_SIN_LICENCIA:
        ui.info("La tool puede usarse sin licencia; solo el renombrado automático quedará desactivado.")
        ui.info(nota_licencia_filebot())
        accion = ui.preguntar_opcion("¿Qué quieres hacer con FileBot?", [
            ("c", "Abrir la compra oficial; dejar FileBot pendiente"),
            ("a", "Activar un fichero de licencia .psm"),
            ("p", "Continuar sin licencia; configurarlo más adelante"),
        ], defecto="p")
        if accion == "c":
            webbrowser.open(_url(cfg, "filebot_compra"))
            ui.info("Se ha abierto la compra oficial. FileBot queda pendiente.")
        elif accion == "a" and instalar_licencia_filebot(cfg):
            estado, detalle = estado_filebot(cfg)
            ui.ok(detalle)
            ui.info(nota_licencia_filebot())
            return estado
        ui.info("Puedes volver a ejecutar el Asistente de instalación cuando tengas la licencia.")
        return FILEBOT_SIN_LICENCIA
    ui.aviso("FileBot queda pendiente. Puedes volver a ejecutar el Asistente de instalación más adelante.")
    ui.info(nota_licencia_filebot())
    return estado


# ---------------------------------------------------------------------------

def ejecutar(cfg, forzar: bool = False) -> bool:
    """Ejecuta el asistente. Devuelve True si todo lo esencial está listo."""
    ui.titulo("ASISTENTE DE INSTALACIÓN")
    ui.info(f"Carpeta de la tool: {ROOT}")
    ui.info(f"Sistema: {platform.system()} {platform.release()} · gestor de paquetes: {tools.gestor_paquetes() or 'ninguno'}")

    ok_py = _comprobar_python()
    ok_dep = _comprobar_dependencias()

    ui.seccion("Herramientas externas")
    if tools.ES_WINDOWS and (ROOT / "binaries").is_dir():
        ui.info("En Windows se usan los ejecutables de binaries/ si no hay otros en el PATH.")
    estado = {h: _comprobar_herramienta(h, cfg) for h in HERRAMIENTAS}

    ui.seccion("Usuario del tracker")
    cfg.d["usuario"] = ui.preguntar("Tu usuario (aparece en las fichas: Release: Grupo X @usuario)",
                                    defecto=cfg.d.get("usuario") or None, obligatorio=True)
    cfg.guardar("usuario")
    ui.ok(f"Usuario: {cfg.d['usuario']}")

    estado_filebot_actual = _comprobar_filebot_licencia(cfg)

    esenciales = ok_py and ok_dep and all(estado[h] for h in ("ffmpeg", "ffprobe", "mkvmerge", "mkvpropedit"))
    ui.seccion("Resumen")
    for h, v in estado.items():
        (ui.ok if v else ui.aviso)(h)
    if esenciales:
        cfg.d["instalacion"] = {
            "completado": True,
            "fecha": _dt.date.today().isoformat(),
            "filebot": "licenciado" if estado_filebot_actual == FILEBOT_CON_LICENCIA else "pendiente",
        }
        cfg.guardar("instalacion")
        ui.ok("Todo listo. Configuración en config/*.yaml")
        if estado_filebot_actual != FILEBOT_CON_LICENCIA:
            ui.info("FileBot está pendiente: la tool funciona, pero el renombrado automático se activará "
                    "cuando vuelvas al Asistente de instalación con una licencia.")
            ui.info("Alternativa sin FileBot: renombra manualmente y genera la ficha; la tool pedirá "
                    "TMDb para películas o IMDb para series.")
    else:
        ui.error("Faltan herramientas esenciales (ffmpeg, ffprobe, mkvmerge o mkvpropedit). Repite el asistente cuando las tengas.")
    ui.pausa()
    return esenciales
