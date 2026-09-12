"""Punto de entrada: `python -m tocinotool` (o launcher.bat / tocinotool.sh)."""
import datetime as _dt
import sys
import traceback
from pathlib import Path
from typing import Optional

from . import __version__, entorno, ui

OPCIONES = [
    ("1", "PREPARAR RELEASE: convertir → muxer → renombrar → torrent (flujo continuo)"),
    ("", ""),
    ("2", "Convertir audios a AC3"),
    ("3", "Muxer: ordenar, nombrar y flaggear pistas (+ audios/subs sueltos)"),
    ("4", "Renombrar con FileBot"),
    ("5", "Crear .torrent"),
    ("6", "Info para el tracker: ficha .txt (BBCode), .nfo e info.txt con enlaces"),
    ("v", "Verificar mkv (directrices: idiomas, orden, nombres, default, duración)"),
    ("", ""),
    ("7", "Limpieza de archivos"),
    ("9", "Juntar: imagen de un mkv extranjero + audios/subs de tu mkv preparado (4K ↔ 1080p)"),
    ("0", "Capturas (con tonemapping HDR)"),
    ("", ""),
    ("c", "Configuración"),
    ("l", "Abrir carpeta de informes de error"),
    ("q", "Salir (Ctrl+C o q en cualquier pregunta)"),
]


def menu(cfg) -> None:
    carpeta: Optional[Path] = None
    while True:
        ui.limpiar()
        ui.cabecera_principal(__version__, cfg.get("usuario") or "")
        ui.info(f"{_dt.datetime.now():%d/%m/%Y %H:%M}  ·  Selecciona el módulo de trabajo")
        if carpeta:
            ui.info(f"Última carpeta de trabajo: {carpeta}")
        op = ""
        try:
            op = ui.preguntar_opcion("Selecciona una opción", OPCIONES, defecto="1")
            if op == "1":
                from . import release
                carpeta = release.flujo(cfg) or carpeta
            elif op == "2":
                from . import ac3
                carpeta = ac3.flujo(cfg) or carpeta
            elif op == "3":
                from . import mux
                carpeta = mux.flujo(cfg) or carpeta
            elif op == "4":
                from . import renombrar
                carpeta = renombrar.flujo(cfg) or carpeta
            elif op == "5":
                from . import torrent
                carpeta = torrent.flujo(cfg) or carpeta
            elif op == "6":
                from . import ficha
                carpeta = ficha.flujo(cfg) or carpeta
            elif op == "7":
                from . import limpiar
                carpeta = limpiar.menu(cfg) or carpeta
            elif op == "9":
                from . import mux
                carpeta = mux.flujo_juntar(cfg) or carpeta
            elif op == "0":
                from . import capturas
                carpeta = capturas.flujo(cfg) or carpeta
            elif op.lower() == "v":
                from . import verificar
                carpeta = verificar.flujo(cfg) or carpeta
            elif op == "c":
                from . import configuracion
                configuracion.flujo(cfg)
            elif op.lower() == "l":
                from . import diagnostico
                ui.ok(f"Carpeta de informes: {diagnostico.abrir_carpeta_logs()}")
            elif op.lower() == "q":
                raise ui.Salir()
            else:
                ui.aviso(f"La opción '{op}' no es válida.")
        except ui.Salir:
            raise
        except ui.Cancelar:
            ui.aviso("Cancelado.")
        except Exception as e:  # noqa: BLE001 — cualquier fallo vuelve al menú sin cerrar la tool
            ui.error(str(e))
            from . import diagnostico
            informe = diagnostico.crear_informe_error(e, cfg=cfg, modulo=op or "menú")
            if informe:
                ui.aviso(f"Se ha generado un informe de error: {informe}")
                ui.info("Envía ese archivo al responsable de la herramienta.")
            else:
                print(ui.gris(traceback.format_exc()))
        ui.pausa()


def main() -> int:
    # salida UTF-8 pase lo que pase (consola cp1252, tuberías, servidores sin locale)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    try:
        # Cubre también creación del venv, pip y carga de configuración. Los
        # errores anteriores al menú deben dejar el mismo informe que un error
        # de trabajo normal.
        entorno.asegurar()  # crea el venv e instala dependencias si hace falta; relanza dentro
        from .config import Config  # (necesita PyYAML, que ya está en el venv)
        cfg = Config()
        from . import tools
        tools.DETALLADO = bool(cfg.get("mostrar_comandos"))
        if "--asistente-instalacion" in sys.argv[1:]:
            from . import asistente
            try:
                return 0 if asistente.ejecutar(cfg, forzar=True) else 1
            except ui.Salir:
                raise
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001 — soporte de primer arranque
                from . import diagnostico
                informe = diagnostico.crear_informe_error(e, cfg=cfg, modulo="asistente")
                ui.error(str(e))
                if informe:
                    ui.aviso(f"Se ha generado un informe de error: {informe}")
                    ui.info("Envía ese archivo al responsable de la herramienta.")
                return 1
        menu(cfg)
    except ui.Salir:
        print("\nHasta luego.")
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        return 130
    except Exception as e:  # último nivel: incluso fallos antes del menú
        from . import diagnostico
        informe = diagnostico.crear_informe_error(e, modulo="arranque", paso="entorno o configuración")
        ui.error(str(e))
        if informe:
            ui.aviso(f"Se ha generado un informe de error: {informe}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
