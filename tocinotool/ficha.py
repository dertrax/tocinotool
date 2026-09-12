"""Ficha BBCode para el foro (sustituye a TemplateFill/fill_dt.py).

Por cada release (mkv suelto o carpeta de temporada) genera `<release>.txt` con
la plantilla de config/tracker.yaml (`ficha.pelicula` / `ficha.serie`) rellena con:
título, año/episodio, grupo, usuario, fuentes, lista de audios y subtítulos y
el MediaInfo completo en castellano. Además escribe `info.txt` con los nombres
de todos los releases procesados.
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple

from . import metadatos, probe, tools, ui

ES_CSV = Path(__file__).with_name("es.csv")

_RE_SERIE_EP = re.compile(r"^(.*?)\.(S\d{2}E\d{1,3})(?:\.|$)", re.IGNORECASE)
_RE_SERIE_TEMP = re.compile(r"^(.*?)\.(S\d{2})(?:\.|$)", re.IGNORECASE)
_RE_PELI = re.compile(r"^(.*?)\.(\d{4})\.")
_RE_FUENTE_DISCO = re.compile(r"\.(BluRay|UHDRemux|UHDRip|BDRip|BDRemux|WEB-DL|WEBRip)(?:\.|$)", re.IGNORECASE)


def _mediainfo():
    from pymediainfo import MediaInfo  # import perezoso
    return MediaInfo


def _parse_mediainfo(mkv: Path, **opciones):
    """Usa la DLL portable incluida en Windows cuando esté disponible."""
    return _mediainfo().parse(str(mkv), library_file=tools.biblioteca_mediainfo(), **opciones)


def _primer_mkv(entrada: Path) -> Optional[Path]:
    if entrada.is_file():
        return entrada
    return next((p for p in sorted(entrada.rglob("*.mkv"))), None)


def _nombre_release(nombre: str) -> str:
    """'Peli.2024.1080p.NF.WEB-DL.DD+5.1.H264-TMd' -> 'Peli 2024 1080p NF WEB-DL DD+5.1 H264 - TMd'"""
    nombre = re.sub(r"\.mkv$", "", nombre, flags=re.IGNORECASE)
    # proteger canales (5.1, 2.0, 7.1): un digito, punto, un digito
    marca = chr(1)
    protegido = re.sub(r"(?<!\d)(\d)\.(\d)(?!\d)", lambda m: m.group(1) + marca + m.group(2), nombre)
    protegido = re.sub(r"-(\w+)$", lambda m: " - " + m.group(1), protegido)  # separar solo el grupo
    return protegido.replace(".", " ").replace(marca, ".")


def _fuente(cfg, nombre: str) -> str:
    tags = "|".join(re.escape(str(t)) for t in cfg["plataformas"])
    m = re.search(rf"\.({tags})\.(WEB-DL|WEBRip)(?:\.|$)", nombre, re.IGNORECASE)
    if m:
        return f"{cfg.nombre_plataforma(m.group(1))} {m.group(2)}"
    m = _RE_FUENTE_DISCO.search(nombre)
    return m.group(1) if m else ""


def _idioma_pista(cfg, pista) -> str:
    titulo = (pista.title or "").lower()
    if "latino" in titulo:
        return cfg.nombre_idioma("spal")
    if "español" in titulo or "castellano" in titulo:
        return cfg.nombre_idioma("spa")
    codigos = [x for x in (pista.other_language or []) if len(x) == 3]
    return cfg.nombre_idioma(codigos[0] if codigos else (pista.language or "und"))


def audios(cfg, mkv: Path) -> str:
    mi = _parse_mediainfo(mkv)
    lineas = []
    for a in mi.audio_tracks:
        codec_id = (a.codec_id or "").upper()
        # A_EAC3 → eac3, A_AAC-2 → aac, A_DTS → dts, A_TRUEHD → truehd
        codec = re.sub(r"^A_", "", codec_id).split("-")[0].lower()
        codec = {"mpeg/l3": "mp3", "mpeg/l2": "mp2", "mlp fba": "truehd"}.get(codec, codec)
        perfil = a.format_profile or a.commercial_name
        nombre = cfg.nombre_codec_audio(codec, perfil)
        if "atmos" in (a.commercial_name or "").lower():
            nombre += " Atmos"
        canales = cfg.etiqueta_canales(int(a.channel_s)) if a.channel_s else "?"
        kbps = int(round((a.bit_rate or 0) / 1000)) if a.bit_rate else "?"
        lineas.append(f"AUDIO: {_idioma_pista(cfg, a)} {nombre} {canales} @ {kbps} Kbps")
    return "\n".join(lineas)


def subtitulos(cfg, mkv: Path) -> str:
    mi = _parse_mediainfo(mkv)
    formatos = {"UTF-8": "srt", "PGS": "pgs", "ASS": "ass", "SSA": "ssa", "VobSub": "sub", "WebVTT": "vtt"}
    grupos = {"forced": [], "complete": [], "sdh": []}
    for s in mi.text_tracks:
        lang = _idioma_pista(cfg, s)
        fmt = formatos.get(s.format or "", (s.format or "?").lower())
        titulo = (s.title or "").lower()
        if s.forced == "Yes" or "forz" in titulo:
            grupos["forced"].append(f"{lang} ({fmt})")
        elif "sordos" in titulo or "sdh" in titulo:
            grupos["sdh"].append(f"{lang} ({fmt})")
        else:
            grupos["complete"].append(f"{lang} ({fmt})")
    etiquetas = {"forced": "Subtítulos Forzados", "complete": "Subtítulos Completos", "sdh": "Subtítulos Para Sordos"}
    return "\n".join(f"{etiquetas[k]}: {' , '.join(v)}" for k, v in grupos.items() if v)


def mediainfo_texto(mkv: Path) -> str:
    """MediaInfo para la ficha; la traducción nunca impide generarla.

    ``es.csv`` solo es presentación. Si un CSV antiguo o una clave nueva de
    MediaInfo no puede cargarse, se conserva la salida original de MediaInfo.
    """
    try:
        mediainfo = _mediainfo()
    except ImportError as ex:
        raise RuntimeError("MediaInfo Python no está disponible; ejecuta el Asistente de instalación.") from ex
    try:
        csv = ES_CSV.read_text(encoding="utf-8")
        txt = mediainfo.parse(str(mkv), library_file=tools.biblioteca_mediainfo(), output="", full=False,
                              mediainfo_options={"Language": csv})
    except Exception as ex:  # la ficha debe sobrevivir a una traducción obsoleta
        ui.aviso(f"No se pudo aplicar la traducción de MediaInfo ({ex}); se usa la salida original.")
        txt = mediainfo.parse(str(mkv), library_file=tools.biblioteca_mediainfo(), output="", full=False)
    txt = str(txt).replace("\r\n", "\n")
    # solo el nombre del fichero, sin la ruta completa
    return txt.replace(str(mkv.parent) + ("\\" if "\\" in str(mkv) else "/"), "").strip()


def generar(cfg, entrada: Path, fuentes: Optional[Tuple[str, str]] = None, silencioso: bool = False,
            fuente_defecto: str = "", enlaces: Optional[metadatos.Enlaces] = None) -> Optional[Tuple[Path, str]]:
    mkv = _primer_mkv(entrada)
    if mkv is None:
        ui.aviso(f"{entrada.name}: sin mkv dentro.")
        return None
    nombre = entrada.name
    grupo = re.sub(r"\.mkv$", "", nombre, flags=re.IGNORECASE).split("-")[-1]
    fuente = _fuente(cfg, nombre) or fuente_defecto

    if entrada.is_dir():
        m = _RE_SERIE_TEMP.match(nombre)
        if not m:
            ui.aviso(f"{nombre}: no parece una carpeta de temporada (Sxx).")
            return None
        plantilla, titulo = cfg["ficha"]["serie"], m.group(1)
        episodio = f"Temporada {int(m.group(2)[1:])}"
        anio = ""
    elif _RE_SERIE_EP.match(nombre):
        m = _RE_SERIE_EP.match(nombre)
        plantilla, titulo, episodio, anio = cfg["ficha"]["serie"], m.group(1), m.group(2).upper(), ""
    elif _RE_PELI.match(nombre):
        m = _RE_PELI.match(nombre)
        plantilla, titulo, episodio, anio = cfg["ficha"]["pelicula"], m.group(1), "", m.group(2)
    else:
        ui.aviso(f"{nombre}: no reconozco si es serie o película.")
        return None
    titulo = titulo.replace(".", " ")
    if fuentes:
        fuente_video, fuente_audio = fuentes
    else:
        ui.info(f"{titulo} {anio or episodio} · grupo {grupo}")
        fuente_video = _preguntar_fuente(cfg, fuente, "Fuente de vídeo")
        fuente_audio = fuente_video if ui.preguntar_sn("¿El audio y los subtítulos vienen de la misma fuente?", True) \
            else _preguntar_fuente(cfg, "", "Fuente de audio y subtítulos")

    v = probe.analizar(mkv, cfg).video
    base = re.sub(r"\.mkv$", "", nombre, flags=re.IGNORECASE)
    campos = dict(
        titulo=titulo, anio=anio, episodio=episodio, grupo=grupo, usuario=cfg.get("usuario", ""),
        fuente_video=fuente_video, fuente_audio=fuente_audio,
        audios=audios(cfg, mkv), subtitulos=subtitulos(cfg, mkv), mediainfo=mediainfo_texto(mkv),
        release=base, enlaces=chr(10).join(enlaces.lineas()) if enlaces else "",
        resolucion=f"{v.ancho}x{v.alto}" if v else "",
        codec_video=cfg.nombre_codec_video(v.codec, preguntar=False) if v else "",
    )
    destino = entrada.parent / (nombre + ".txt")
    destino.write_text(plantilla.format(**campos), encoding="utf-8")
    if cfg.get("nfo"):
        (entrada.parent / (base + ".nfo")).write_text(str(cfg["nfo"]).format(**campos), encoding="utf-8")
    ui.ok((destino.name + (" + .nfo" if cfg.get("nfo") else "")) if silencioso else f"Ficha: {destino.name}")
    return destino, _nombre_release(nombre)


_RE_DIR_TEMPORADA = re.compile(r"\.S\d{2}(?:\.|$)", re.IGNORECASE)


def _entradas(carpeta: Path) -> List[Path]:
    """Releases de la carpeta, detectando la estructura: mkv sueltos y carpetas
    de temporada (Sxx) son releases; cualquier otra carpeta es una carpeta de
    release (estructura antigua carpeta/<release>/<mkv>) y se mira dentro."""
    res: List[Path] = []
    for p in sorted(carpeta.iterdir()):
        if p.name.lower() in ("temporal", "originals", "originales", "capturas"):
            continue
        if p.suffix.lower() == ".mkv":
            res.append(p)
        elif p.is_dir():
            if _RE_DIR_TEMPORADA.search(p.name):
                res.append(p)
            else:
                res += [q for q in sorted(p.iterdir())
                        if q.suffix.lower() == ".mkv" or (q.is_dir() and _RE_DIR_TEMPORADA.search(q.name))]
    return res


def _preguntar_fuente(cfg, propuesta: str, texto: str = "Fuente de vídeo") -> str:
    """Selector: la propuesta (deducida del nombre o del contexto), plataforma +
    tipo del listado, o escribir."""
    opciones = []
    if propuesta:
        opciones.append(("prop", propuesta))
    opciones += [("web", "plataforma del listado + WEB-DL / WEBRip"), ("disco", "BluRay / UHDRemux / UHDRip / BDRip / BDRemux"),
                 ("otro", "escribir")]
    r = ui.preguntar_opcion(texto, opciones, defecto="prop" if propuesta else "web")
    if r == "prop":
        return propuesta
    if r == "web":
        from .renombrar import preguntar_plataforma
        tag = preguntar_plataforma(cfg)
        tipo = ui.preguntar_opcion("Tipo", [("WEB-DL", "WEB-DL"), ("WEBRip", "WEBRip")], defecto="WEB-DL")
        return f"{cfg.nombre_plataforma(tag)} {tipo}"
    if r == "disco":
        return ui.preguntar_opcion("Tipo", [(t, t) for t in ("BluRay", "UHDRemux", "UHDRip", "BDRip", "BDRemux")], defecto="BluRay")
    return ui.preguntar(texto, obligatorio=True)


def _escribir_info(carpeta: Path, bloques: List[str]) -> None:
    """info.txt: por release, el título tal como va en la ficha del tracker y sus enlaces."""
    (carpeta / "info.txt").write_text((chr(10) * 2).join(bloques) + chr(10), encoding="utf-8")


def _bloque_info(nombre: str, enlaces: Optional[metadatos.Enlaces]) -> str:
    return chr(10).join([_nombre_release(nombre)] + (enlaces.lineas() if enlaces else []))


def generar_todas(cfg, carpeta: Path, fuente_defecto: str = "", serie: bool = False) -> List[Path]:
    """Ficha de cada release de la carpeta sin preguntar: la fuente se deduce
    del nombre (ya renombrado) o del contexto del flujo; solo pregunta si no
    puede deducirla."""
    entradas = _entradas(carpeta)
    if not entradas:
        return []
    fuente = _fuente(cfg, entradas[0].name) or fuente_defecto
    if not fuente:
        fuente = _preguntar_fuente(cfg, "", "Fuente de vídeo y audio (no se ha podido deducir)")
    ui.seccion(f"Generando {len(entradas)} ficha(s) · fuente: {fuente}")
    res, bloques = [], []
    for e in entradas:
        enl = metadatos.enlaces_release(cfg, e, serie)
        r = generar(cfg, e, fuentes=(fuente, fuente), silencioso=True, enlaces=enl)
        if r:
            res.append(r[0])
            bloques.append(_bloque_info(e.name, enl))
    if bloques:
        _escribir_info(carpeta, bloques)
    return res


def flujo(cfg, carpeta: Optional[Path] = None, estructura: Optional[str] = None,
          fuente_defecto: str = "") -> Optional[Path]:
    ui.titulo("FICHA (info) para el foro")
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "De qué generar la ficha", admitir_fichero=True)
    if carpeta.is_file():
        serie = bool(_RE_SERIE_EP.match(carpeta.name))
        enl = metadatos.enlaces_release(cfg, carpeta, serie)
        r = generar(cfg, carpeta, fuente_defecto=fuente_defecto, enlaces=enl)
        if r:
            _escribir_info(carpeta.parent, [_bloque_info(carpeta.name, enl)])
        return carpeta.parent
    entradas = _entradas(carpeta)   # la estructura se detecta (mkv sueltos, temporadas o carpetas de release)
    if not entradas:
        ui.error("No hay releases.")
        return None

    nombres = []
    serie = any(_RE_SERIE_EP.match(e.name) or e.is_dir() for e in entradas)
    if len(entradas) == 1:
        enl = metadatos.enlaces_release(cfg, entradas[0], serie)
        r = generar(cfg, entradas[0], fuente_defecto=fuente_defecto, enlaces=enl)
        if r:
            nombres.append(_bloque_info(entradas[0].name, enl))
    else:
        # varias entradas: las fuentes se preguntan una vez (propuesta según el primer nombre)
        ui.info(f"{len(entradas)} releases. Primero: {entradas[0].name}")
        propuesta = _fuente(cfg, entradas[0].name) or fuente_defecto
        fv = _preguntar_fuente(cfg, propuesta, "Fuente de vídeo (para todos)")
        fa = fv if ui.preguntar_sn("¿El audio y los subtítulos vienen de la misma fuente?", True) \
            else _preguntar_fuente(cfg, "", "Fuente de audio y subtítulos (para todos)")
        ui.seccion(f"Generando {len(entradas)} fichas")
        for e in entradas:
            enl = metadatos.enlaces_release(cfg, e, serie)
            r = generar(cfg, e, fuentes=(fv, fa), silencioso=True, enlaces=enl)
            if r:
                nombres.append(_bloque_info(e.name, enl))
    if nombres:
        _escribir_info(carpeta, nombres)
        ui.ok(f"info.txt con {len(nombres)} release(s)")
    return carpeta
