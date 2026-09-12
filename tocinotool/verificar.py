"""Verificación del mkv final: comprueba que cumple las directrices antes de
borrar los originales (lo que antes se hacía a ojo).

Comprobaciones:
  * mkvmerge puede leer el fichero y no hay errores de contenedor
  * sin título global ni adjuntos; vídeo con idioma 'und' y sin nombre
  * todas las pistas de audio/subtítulo tienen idioma (≠ und)
  * exactamente un audio default, y es el primero
  * solo los subtítulos forzados pueden ser default
  * orden de audios: por idioma (orden_idiomas) y calidad de códec
  * nombres de pista con el formato de las plantillas
  * duración de cada audio ≈ duración del vídeo (desincronía / audio cortado)
  * hay al menos un audio en castellano
"""
import json
import re
from pathlib import Path
from typing import List, Tuple

from . import probe, tools, ui


def verificar(mkv: Path, cfg, perfil: str = "manual") -> Tuple[bool, List[Tuple[bool, str]]]:
    res: List[Tuple[bool, str]] = []

    exe = tools.buscar("mkvmerge", cfg, obligatorio=True)
    r = tools.ejecutar([exe, "-J", str(mkv)], capturar=True, mostrar=False, comprobar=False)
    try:
        info = json.loads(r.stdout or "{}")
    except ValueError:
        return False, [(False, "mkvmerge no puede leer el fichero")]
    errores = info.get("errors") or []
    res.append((not errores and r.returncode == 0, "contenedor legible sin errores" + (f": {errores}" if errores else "")))

    props = info.get("container", {}).get("properties", {})
    res.append((not props.get("title"), "sin título global" + (f" (tiene: '{props.get('title')}')" if props.get("title") else "")))
    res.append((not info.get("attachments"), f"sin adjuntos ({len(info.get('attachments') or [])})"))

    tracks = info.get("tracks", [])
    videos = [t for t in tracks if t["type"] == "video"]
    audios = [t for t in tracks if t["type"] == "audio"]
    subs = [t for t in tracks if t["type"] == "subtitles"]
    res.append((len(videos) == 1, f"una pista de vídeo ({len(videos)})"))
    if videos:
        v = videos[0]["properties"]
        res.append((v.get("language", "und") == "und", f"vídeo con idioma 'und' (tiene '{v.get('language')}')"))
        res.append((not v.get("track_name"), "vídeo sin nombre de pista" + (f" (tiene '{v.get('track_name')}')" if v.get("track_name") else "")))

    sin_idioma = [t["id"] for t in audios + subs if t["properties"].get("language", "und") == "und"]
    res.append((not sin_idioma, "todas las pistas de audio/subs con idioma" + (f" (sin idioma: {sin_idioma})" if sin_idioma else "")))

    defaults = [i for i, t in enumerate(audios) if t["properties"].get("default_track")]
    res.append((defaults == [0], f"un solo audio default y es el primero (default: {[i + 1 for i in defaults]})"))
    if perfil == "encode":
        idiomas_repetidos = []
        vistos = set()
        for t in audios:
            idioma = t["properties"].get("language", "und")
            if idioma != "und" and idioma in vistos:
                idiomas_repetidos.append(idioma)
            vistos.add(idioma)
        res.append((not idiomas_repetidos,
                    "Encode: una pista de audio por idioma" + (f" (repetidos: {', '.join(idiomas_repetidos)})" if idiomas_repetidos else "")))
    # aviso, no error: un release solo con V.O. es válido
    hay_spa = any(t["properties"].get("language") == "spa" for t in audios)
    res.append((True if hay_spa else "aviso", "hay audio en castellano" if hay_spa else "sin audio en castellano (solo V.O.)"))

    malos = [t["id"] for t in subs if t["properties"].get("default_track") and not t["properties"].get("forced_track")]
    res.append((not malos, "solo los subtítulos forzados son default" + (f" (ids: {malos})" if malos else "")))

    # orden de audios
    orden_idiomas = [str(x) for x in cfg["orden_idiomas"]]
    orden_codecs = [str(x).lower() for x in cfg.get("orden_codecs_audio", [])]

    def clave(t):
        lang = t["properties"].get("language", "und")
        nombre = (t["properties"].get("track_name") or "").lower()
        ri = orden_idiomas.index(lang) if lang in orden_idiomas else len(orden_idiomas)
        rc = min([i for i, c in enumerate(orden_codecs) if f" {c} " in f" {nombre} "] or [len(orden_codecs)])
        return (ri, rc)
    claves = [clave(t) for t in audios]
    res.append((claves == sorted(claves), "audios ordenados por idioma y calidad de códec"))

    # nombres según plantilla
    patron_audio = re.compile(r"^\S.* .+ \d\.\d @ \d+ kbps$", re.IGNORECASE)
    patron_sub = re.compile(r"^\S.* \[(" + "|".join(re.escape(str(v)) for v in cfg["subtitulos"]["tipos"].values()) + r")\]")
    mal_nombre = [t["id"] for t in audios if not patron_audio.match(t["properties"].get("track_name") or "")]
    mal_nombre += [t["id"] for t in subs if not patron_sub.match(t["properties"].get("track_name") or "")]
    res.append((not mal_nombre, "nombres de pista según plantilla" + (f" (ids: {mal_nombre})" if mal_nombre else "")))

    # duraciones (ffprobe)
    m = probe.analizar(mkv, cfg)
    dur_v = m.duracion
    desfasados = []
    for t in audios:
        d = t["properties"].get("tag_duration") or ""
        seg = _segundos(d)
        if seg and dur_v and abs(seg - dur_v) > 2.0:
            desfasados.append(f"id {t['id']}: {seg:.0f}s vs {dur_v:.0f}s")
    res.append((not desfasados, "duración de los audios ≈ vídeo" + (f" ({'; '.join(desfasados)})" if desfasados else "")))

    ok = all(v is not False for v, _ in res)
    return ok, res


def _segundos(d: str) -> float:
    m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", d or "")
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def mostrar(mkv: Path, cfg, detallado: bool = True, perfil: str = "manual") -> bool:
    """Con `detallado` lista todas las comprobaciones; si no, una línea por
    fichero y solo el detalle de lo que falla."""
    ok, res = verificar(mkv, cfg, perfil)
    if detallado:
        ui.seccion(f"Verificación de {mkv.name}")
        for v, texto in res:
            (ui.ok if v is True else ui.aviso if v == "aviso" else ui.error)(texto)
        (ui.ok if ok else ui.aviso)("TODO CORRECTO" if ok else "Hay puntos que revisar")
    elif ok:
        ui.ok(mkv.name)
        for v, texto in res:
            if v == "aviso":
                print(f"       ! {texto}")
    else:
        ui.error(mkv.name)
        for v, texto in res:
            if v is not True:
                print(f"       {'!' if v == 'aviso' else '✖'} {texto}")
    return ok


def verificar_carpeta(cfg, carpeta: Path, recursivo: bool = False, perfil: str = "manual") -> bool:
    videos = probe.listar_videos(carpeta, cfg, recursivo=recursivo)
    ui.seccion(f"Verificación de {len(videos)} fichero(s)")
    correctos = 0
    for v in videos:
        correctos += mostrar(v, cfg, detallado=(len(videos) == 1), perfil=perfil)
    (ui.ok if correctos == len(videos) else ui.aviso)(f"{correctos}/{len(videos)} correctos")
    return correctos == len(videos)


def flujo(cfg, carpeta=None):
    ui.titulo("VERIFICAR mkv")
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "Qué verificar", admitir_fichero=True)
    if carpeta.is_file():
        return carpeta.parent if mostrar(carpeta, cfg) else None
    return carpeta if verificar_carpeta(cfg, carpeta, recursivo=True) else None
