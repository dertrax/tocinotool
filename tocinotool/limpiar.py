"""Limpieza segura de contenedores: conservar idiomas elegidos, quitar
adjuntos/títulos y normalizar la pista de vídeo. Los originales nunca se borran."""
import json
import shutil
from pathlib import Path
from typing import List, Optional

from . import probe, tools, ui


OPCIONES = [
    ("vo", "Limpiar mkv extranjero: conservar solo V.O. (audios y subtítulos)"),
    ("adjuntos", "Limpiar adjuntos, título y datos de la pista de vídeo"),
    ("volver", "Volver al menú principal"),
]


def menu(cfg) -> Optional[Path]:
    """Submenú común de las operaciones de limpieza."""
    ui.titulo("LIMPIEZA DE ARCHIVOS")
    modo = ui.preguntar_opcion("Qué quieres limpiar", OPCIONES, defecto="vo")
    if modo == "volver":
        return None
    return flujo(cfg, modo=modo)


def _resumen(medio: probe.Medio, cfg) -> None:
    filas = []
    for p in medio.pistas:
        if p.tipo in ("audio", "subtitle"):
            filas.append([p.indice, p.tipo, p.idioma, cfg.nombre_idioma(cfg.canon_idioma(p.idioma), preguntar=False),
                          p.describir(), p.titulo, "F" if p.forzado else ""])
    ui.tabla(["id", "tipo", "código", "idioma", "detalle", "título", ""], filas)
    if medio.adjuntos:
        ui.info(f"{len(medio.adjuntos)} adjunto(s) (fuentes, portadas…)")


def flujo(cfg, carpeta: Optional[Path] = None, modo: str = "todo") -> Optional[Path]:
    """modo: 'vo' (dejar solo los idiomas originales), 'adjuntos' (solo quitar
    adjuntos/título/idioma de vídeo) o 'todo' (pregunta ambas cosas)."""
    if modo == "vo":
        ui.titulo("LIMPIAR MKV EXTRANJERO — conservar solo V.O. (audios y subtítulos)")
    elif modo == "adjuntos":
        ui.titulo("LIMPIAR ADJUNTOS, TÍTULO E IDIOMA DE VÍDEO")
    else:
        ui.titulo("LIMPIAR CONTENEDOR — audios, subtítulos, adjuntos, título")
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "Qué limpiar", admitir_fichero=True)
    solo = carpeta if carpeta.is_file() else None
    carpeta = carpeta.parent if solo else carpeta
    videos = [solo] if solo else probe.listar_videos(carpeta, cfg, recursivo=False)
    videos = [v for v in videos if v.suffix.lower() == ".mkv"]
    if not videos:
        ui.error("No hay ficheros MKV en la ruta indicada.")
        return None

    primero = probe.analizar(videos[0], cfg)
    ui.seccion(f"Pistas de {videos[0].name}")
    _resumen(primero, cfg)

    subs: List[str] = []
    audios: List[str] = []
    if modo != "adjuntos":
        # idiomas que tiene el fichero, con nombre; se marcan todos y se desmarca lo que sobra
        def _opciones(pistas):
            vistos = {}
            for p in pistas:
                c = cfg.canon_idioma(p.idioma)
                vistos[c] = vistos.get(c, 0) + 1
            return [(c, f"{c:<5} {cfg.nombre_idioma(c, preguntar=False)}  ({n} pista{'s' if n > 1 else ''})") for c, n in vistos.items()]
        op_a = _opciones(primero.audios)
        op_s = _opciones(primero.subtitulos)
        if op_a:
            audios = ui.preguntar_multi("Audios a CONSERVAR (desmarca los que sobran)", op_a, marcadas=[k for k, _ in op_a]) or ["-"]
        if op_s:
            subs = ui.preguntar_multi("Subtítulos a CONSERVAR (desmarca los que sobran)", op_s, marcadas=[k for k, _ in op_s]) or ["-"]
    if modo == "todo":
        que = ui.preguntar_multi("¿Qué limpiar además?", [
            ("adjuntos", "quitar adjuntos (fuentes, portadas)"),
            ("titulo", "vaciar el título del contenedor"),
            ("und", "poner el idioma de la pista de vídeo a 'und'"),
        ], marcadas=["adjuntos", "titulo", "und"])
        sin_adjuntos, sin_titulo, idioma_video_und = "adjuntos" in que, "titulo" in que, "und" in que
    else:
        sin_adjuntos = sin_titulo = idioma_video_und = True

    mkvmerge = tools.buscar("mkvmerge", cfg, obligatorio=True)
    originales = carpeta / "originales"
    originales.mkdir(exist_ok=True)
    colisiones = [originales / v.name for v in videos if (originales / v.name).exists()]
    if colisiones:
        nombres = ", ".join(p.name for p in colisiones[:3])
        raise RuntimeError(f"Ya existe algún original protegido ({nombres}). Muévelo o renómbralo antes de repetir la limpieza.")
    for v in videos:
        ui.seccion(v.name)
        origen = originales / v.name
        shutil.move(str(v), origen)
        from . import mux
        pistas_origen = mux.pistas_contenedor(origen, cfg)
        cmd = [mkvmerge, "-o", str(carpeta / (v.stem + ".mkv"))]
        cmd += _seleccion("-s", "--no-subtitles", subs, cfg, pistas_origen, "subtitle")
        cmd += _seleccion("-a", "--no-audio", audios, cfg, pistas_origen, "audio")
        if sin_adjuntos:
            cmd.append("--no-attachments")
        if sin_titulo:
            cmd += ["--title", ""]
        if idioma_video_und:
            for idv, p in pistas_origen:
                if p.tipo == "video":
                    cmd += ["--language", f"{idv}:und", "--track-name", f"{idv}:"]
        cmd.append(str(origen))
        tools.ejecutar_mkvmerge(cmd)
        _verificar_limpieza(carpeta / (v.stem + ".mkv"), cfg, audios, subs,
                            sin_adjuntos, sin_titulo, idioma_video_und)
        ui.ok(f"{v.stem}.mkv")

    ui.info("Los ficheros de origen se conservan en originales/ (bórralos tú cuando hayas comprobado el resultado).")
    return carpeta


def _seleccion(flag: str, flag_ninguno: str, idiomas: List[str], cfg,
               pistas, tipo: str) -> List[str]:
    """Convierte la selección por idioma a ids reales de pista de mkvmerge."""
    if not idiomas:
        return []
    if idiomas == ["-"]:
        return [flag_ninguno]
    elegidos = {cfg.canon_idioma(i) for i in idiomas}
    ids = [str(tid) for tid, p in pistas if p.tipo == tipo and cfg.canon_idioma(p.idioma) in elegidos]
    return [flag, ",".join(ids)] if ids else [flag_ninguno]


def _verificar_limpieza(ruta: Path, cfg, audios: List[str], subs: List[str],
                        sin_adjuntos: bool, sin_titulo: bool, video_und: bool) -> None:
    """Guardia específica de limpieza; no exige nombres de release preparado."""
    mkvmerge = tools.buscar("mkvmerge", cfg, obligatorio=True)
    r = tools.ejecutar([mkvmerge, "-J", str(ruta)], capturar=True, mostrar=False, comprobar=False)
    try:
        info = json.loads(r.stdout or "{}")
    except ValueError as e:
        raise RuntimeError(f"{ruta.name}: no se puede verificar el resultado de la limpieza") from e
    if r.returncode != 0 or info.get("errors"):
        raise RuntimeError(f"{ruta.name}: el contenedor resultante no es legible")
    props = info.get("container", {}).get("properties", {})
    if sin_adjuntos and info.get("attachments"):
        raise RuntimeError(f"{ruta.name}: siguen presentes los adjuntos")
    if sin_titulo and props.get("title"):
        raise RuntimeError(f"{ruta.name}: sigue presente el título global")
    tracks = info.get("tracks", [])
    videos = [t for t in tracks if t.get("type") == "video"]
    if video_und and any(t.get("properties", {}).get("language", "und") != "und"
                         or t.get("properties", {}).get("track_name") for t in videos):
        raise RuntimeError(f"{ruta.name}: no se limpiaron los datos de la pista de vídeo")

    def comprobar_idiomas(tipo: str, seleccion: List[str]) -> None:
        if not seleccion:
            return
        permitidos = set() if seleccion == ["-"] else {cfg.canon_idioma(i) for i in seleccion}
        presentes = {cfg.canon_idioma(t.get("properties", {}).get("language_ietf")
                                      or t.get("properties", {}).get("language", "und"))
                     for t in tracks if t.get("type") == tipo}
        if not presentes.issubset(permitidos):
            raise RuntimeError(f"{ruta.name}: quedaron idiomas no seleccionados en {tipo}")

    comprobar_idiomas("audio", audios)
    comprobar_idiomas("subtitles", subs)
