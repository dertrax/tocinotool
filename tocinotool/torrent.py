"""Creación de .torrent con torf. Announce, comentario, sufijo y tamaños de
pieza vienen de config/tracker.yaml."""
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import ui


def _tamano_mb(ruta: Path) -> float:
    if ruta.is_file():
        return ruta.stat().st_size / 1048576
    return sum(p.stat().st_size for p in ruta.rglob("*") if p.is_file()) / 1048576


def _exponente_pieza(cfg, ruta: Path) -> int:
    t = cfg["torrent"]
    tabla = {int(k): int(v) for k, v in t["piezas"].items()}
    mb = _tamano_mb(ruta)
    for limite in sorted(tabla):
        if mb <= limite:
            return tabla[limite]
    return int(t.get("pieza_maxima", 23))


_barra = None


def _progreso(torrent, filepath, hechas, total) -> None:
    if _barra is not None:
        _barra.avanzar(100 * hechas / total)


def crear(cfg, ruta: Path) -> Optional[Path]:
    from torf import Torrent  # import perezoso: solo hace falta aquí

    tr = cfg["tracker"]
    t = cfg["torrent"]
    destino = ruta.parent / f"{ruta.name}{tr.get('sufijo') or ''}.torrent"
    if destino.exists():
        ui.aviso(f"Ya existe {destino.name}, se salta.")
        return destino

    announce = (tr.get("announce") or "").strip()
    if not announce:
        ui.error("Falta la URL announce del tracker en config/tracker.yaml. No se ha creado ningún torrent.")
        return None
    torrent = Torrent(path=str(ruta), trackers=[announce] if announce else None,
                      private=bool(t.get("privado", True)), piece_size=2 ** _exponente_pieza(cfg, ruta),
                      created_by=str(t.get("created_by", "")), creation_date=datetime.now(),
                      source=str(tr.get("nombre") or "tracker"))
    global _barra
    _barra = ui.Barra(f"{ruta.name}  ")
    torrent.generate(callback=_progreso)
    _barra.terminar()
    _barra = None

    # Algunos trackers enriquecen el diccionario ``info`` al recibir el
    # torrent. Como ese diccionario forma parte del infohash, sus campos han
    # de estar presentes *antes* de calcular el comentario. ``campos_info``
    # permite declararlos por tracker sin imponerlos a los demás.
    campos_info = t.get("campos_info") or {}
    if not isinstance(campos_info, dict):
        raise RuntimeError("torrent.campos_info debe ser un mapa de clave: valor en config/tracker.yaml.")
    for clave, valor in campos_info.items():
        if not isinstance(clave, str) or not clave.strip() or not isinstance(valor, (str, int)):
            raise RuntimeError("torrent.campos_info solo admite claves de texto y valores de texto o números.")
        torrent.metainfo["info"][clave] = valor

    comentario = (tr.get("comentario") or "").replace("{infohash}", torrent.infohash)
    if comentario:
        torrent.comment = comentario
    torrent.write(str(destino))
    return destino


_RE_EP = re.compile(r"S\d{1,2}E\d{1,3}|\b\d{1,2}x\d{2}\b", re.IGNORECASE)
_RE_TEMP = re.compile(r"\.S\d{2}(?:\.|$)|temporada|season", re.IGNORECASE)


def tipo_release(e: Path) -> str:
    """temporada (carpeta Sxx), capítulo (mkv SxxExx) o película (otro mkv)."""
    if e.is_dir():
        return "temporada" if _RE_TEMP.search(e.name) or any(_RE_EP.search(f.name) for f in e.rglob("*.mkv")) else "carpeta"
    return "capítulo" if _RE_EP.search(e.name) else "película"


def entradas_carpeta(carpeta: Path) -> List[Path]:
    return sorted(p for p in carpeta.iterdir()
                  if (p.suffix.lower() == ".mkv") or (p.is_dir() and p.name.lower() not in
                                                     ("temporal", "originals", "originales", "capturas") and any(p.iterdir())))


def crear_todos(cfg, carpeta: Path) -> List[Path]:
    """Un torrent por release (mkv suelto o carpeta de temporada), sin preguntar."""
    entradas = entradas_carpeta(carpeta)
    ui.seccion(f"Creando {len(entradas)} torrent(s) para {cfg['tracker'].get('nombre') or 'tracker'}")
    res = []
    for e in entradas:
        r = crear(cfg, e)
        if r:
            res.append(r)
    return res


def flujo(cfg, carpeta: Optional[Path] = None) -> Optional[Path]:
    ui.titulo("CREAR .TORRENT")
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "De qué crear torrent", admitir_fichero=True)
    if carpeta.is_file():
        crear(cfg, carpeta)
        return carpeta.parent
    entradas = entradas_carpeta(carpeta)
    if not entradas:
        ui.error("No hay .mkv ni carpetas con contenido.")
        return None
    # qué es cada entrada: una temporada = un torrent de la carpeta; capítulos y películas = uno por mkv
    tipos = [tipo_release(e) for e in entradas]
    if len(entradas) <= 12:
        ui.tabla(["#", "tipo", "entrada", "MB"],
                 [[i, t, e.name + ("/" if e.is_dir() else ""), f"{_tamano_mb(e):.0f}"] for i, (e, t) in enumerate(zip(entradas, tipos), 1)])
    else:
        resumen = ", ".join(f"{tipos.count(t)} {t}(s)" for t in dict.fromkeys(tipos))
        ui.info(f"{len(entradas)} entradas: {resumen} ({sum(_tamano_mb(e) for e in entradas) / 1024:.1f} GB en total)")
    if len(entradas) > 1:
        r = ui.preguntar_opcion(f"Se crearán {len(entradas)} torrents en lote (uno por entrada)", [
            ("todos", f"crear los {len(entradas)}"),
            ("elegir", "elegir cuáles"),
        ], defecto="todos")
        if r == "elegir":
            elegidas = ui.preguntar_multi("Entradas", [(str(i), f"{t:<9} {e.name}") for i, (e, t) in enumerate(zip(entradas, tipos))],
                                          marcadas=[str(i) for i in range(len(entradas))])
            entradas = [entradas[int(k)] for k in elegidas]
    ui.seccion(f"Creando {len(entradas)} torrent(s)")
    for e in entradas:
        crear(cfg, e)
    return carpeta
