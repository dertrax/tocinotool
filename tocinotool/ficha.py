"""Ficha BBCode y NFO de identificación (sustituye a TemplateFill/fill_dt.py).

Por cada release (mkv suelto o carpeta de temporada) genera `<release>.txt` con
la plantilla de config/tracker.yaml (`ficha.pelicula` / `ficha.serie`) rellena con:
título, año/episodio, grupo, usuario, fuentes, lista de audios y subtítulos y
el MediaInfo completo en castellano. Además escribe `info.txt` con los nombres
de todos los releases procesados y NFO XML para que bibliotecas y paneles
identifiquen el tipo de contenido.
"""
import re
import xml.etree.ElementTree as ET
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


def _nfo_habilitado(cfg) -> bool:
    """La configuración antigua guardaba aquí una plantilla de texto.

    Desde v2.1.7 el .nfo es XML estándar. Las instalaciones que todavía tengan
    esa plantilla se consideran activadas para no requerir ninguna acción del
    usuario tras actualizar.
    """
    nfo = cfg.get("nfo", {})
    return not isinstance(nfo, dict) or bool(nfo.get("identificacion", True))


def _texto_xml(nodo: ET.Element, etiqueta: str, texto: object) -> None:
    if texto not in (None, ""):
        ET.SubElement(nodo, etiqueta).text = str(texto)


def _anadir_ids_nfo(nodo: ET.Element, enlaces: Optional[metadatos.Enlaces], orden: Tuple[str, ...]) -> bool:
    """Añade IDs reales de FileBot, sin convertir el ID de una serie en el de
    un episodio. Devuelve si se escribió al menos uno.
    """
    if not enlaces:
        return False
    encontrados = [(servicio, getattr(enlaces, servicio + "id", "")) for servicio in orden]
    encontrados = [(servicio, valor) for servicio, valor in encontrados if valor]
    for indice, (servicio, valor) in enumerate(encontrados):
        ET.SubElement(nodo, "uniqueid", type=servicio, default="true" if indice == 0 else "false").text = valor
    return bool(encontrados)


def _guardar_xml(ruta: Path, raiz: ET.Element) -> None:
    """Escribe XML legible y UTF-8, formato compatible con lectores NFO."""
    ET.indent(raiz, space="  ")
    ET.ElementTree(raiz).write(ruta, encoding="utf-8", xml_declaration=True)


def _nfo_serie(ruta: Path, titulo: str, anio: str, enlaces: Optional[metadatos.Enlaces]) -> bool:
    raiz = ET.Element("tvshow")
    _texto_xml(raiz, "title", titulo)
    _texto_xml(raiz, "year", anio)
    # Para una serie TVDB suele ser el identificador más específico; los otros
    # quedan disponibles como alternativas para Emby, Plex y los paneles.
    hay_ids = _anadir_ids_nfo(raiz, enlaces, ("tvdb", "tmdb", "imdb"))

    # No se pisan metadatos de otra serie en una carpeta mezclada.
    if ruta.exists():
        try:
            previo = ET.parse(ruta).getroot()
            titulo_previo = (previo.findtext("title") or "").strip()
            if previo.tag == "tvshow" and titulo_previo and titulo_previo.casefold() != titulo.casefold():
                ui.aviso(f"{ruta.parent.name}: no se reemplaza tvshow.nfo de otra serie ({titulo_previo}).")
                return hay_ids
        except ET.ParseError:
            ui.aviso(f"{ruta.name}: no era un XML válido; se reemplaza por el NFO de identificación.")
    _guardar_xml(ruta, raiz)
    return hay_ids


def _nfo_episodio(ruta: Path, titulo: str, temporada: int, episodio: int) -> None:
    """NFO de capítulo. Los IDs de FileBot son de la *serie*, por lo que se
    guardan correctamente en tvshow.nfo y no se falsean como si fuesen IDs del
    episodio individual.
    """
    raiz = ET.Element("episodedetails")
    _texto_xml(raiz, "title", f"{titulo} - S{temporada:02d}E{episodio:02d}")
    _texto_xml(raiz, "showtitle", titulo)
    _texto_xml(raiz, "season", temporada)
    _texto_xml(raiz, "episode", episodio)
    _guardar_xml(ruta, raiz)


def _nfo_temporada(ruta: Path, titulo: str, temporada: int) -> None:
    raiz = ET.Element("season")
    _texto_xml(raiz, "title", f"Temporada {temporada}")
    _texto_xml(raiz, "showtitle", titulo)
    _texto_xml(raiz, "seasonnumber", temporada)
    _guardar_xml(ruta, raiz)


def _generar_nfo_identificacion(entrada: Path, tipo: str, titulo: str, anio: str,
                                 temporada: int, episodio: int,
                                 enlaces: Optional[metadatos.Enlaces]) -> Tuple[List[Path], bool]:
    """Genera NFO sidecar estándar según película, capítulo o temporada.

    - película: ``<video>.nfo`` con ``<movie>`` e IDs de película;
    - capítulo: ``<video>.nfo`` con ``<episodedetails>`` y ``tvshow.nfo`` con
      los IDs de serie;
    - temporada: ``tvshow.nfo`` + ``season.nfo`` y un sidecar por capítulo.

    Esta separación es importante: FileBot da IDs de *serie*, no IDs únicos de
    cada episodio. Así no se generan identificadores falsos.
    """
    escritos: List[Path] = []
    if tipo == "pelicula":
        raiz = ET.Element("movie")
        _texto_xml(raiz, "title", titulo)
        _texto_xml(raiz, "year", anio)
        hay_ids = _anadir_ids_nfo(raiz, enlaces, ("tmdb", "imdb", "tvdb"))
        ruta = entrada.with_suffix(".nfo")
        _guardar_xml(ruta, raiz)
        return [ruta], hay_ids

    carpeta = entrada if entrada.is_dir() else entrada.parent
    hay_ids = _nfo_serie(carpeta / "tvshow.nfo", titulo, anio, enlaces)
    escritos.append(carpeta / "tvshow.nfo")
    if tipo == "capitulo":
        ruta = entrada.with_suffix(".nfo")
        _nfo_episodio(ruta, titulo, temporada, episodio)
        return escritos + [ruta], hay_ids

    ruta_temporada = carpeta / "season.nfo"
    _nfo_temporada(ruta_temporada, titulo, temporada)
    escritos.append(ruta_temporada)
    sin_numerar = []
    for mkv in sorted(carpeta.rglob("*.mkv")):
        m = _RE_SERIE_EP.match(mkv.name)
        if not m:
            sin_numerar.append(mkv.name)
            continue
        token = m.group(2).upper()
        nums = re.match(r"S(\d{2})E(\d{1,3})", token)
        if not nums:  # defensa ante un nombre que cumplía el patrón antiguo
            sin_numerar.append(mkv.name)
            continue
        ruta = mkv.with_suffix(".nfo")
        _nfo_episodio(ruta, titulo, int(nums.group(1)), int(nums.group(2)))
        escritos.append(ruta)
    if sin_numerar:
        ui.aviso("No se creó NFO de capítulo para: " + ", ".join(sin_numerar[:3]) +
                 ("…" if len(sin_numerar) > 3 else ""))
    return escritos, hay_ids


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
        temporada_nfo = int(m.group(2)[1:])
        episodio_nfo = 0
        tipo_nfo = "temporada"
        episodio = f"Temporada {temporada_nfo}"
        anio = ""
    elif _RE_SERIE_EP.match(nombre):
        m = _RE_SERIE_EP.match(nombre)
        token = m.group(2).upper()
        nums = re.match(r"S(\d{2})E(\d{1,3})", token)
        assert nums is not None
        temporada_nfo, episodio_nfo = int(nums.group(1)), int(nums.group(2))
        tipo_nfo = "capitulo"
        plantilla, titulo, episodio, anio = cfg["ficha"]["serie"], m.group(1), token, ""
    elif _RE_PELI.match(nombre):
        m = _RE_PELI.match(nombre)
        tipo_nfo, temporada_nfo, episodio_nfo = "pelicula", 0, 0
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
    campos = dict(
        titulo=titulo, anio=anio, episodio=episodio, grupo=grupo, usuario=cfg.get("usuario", ""),
        fuente_video=fuente_video, fuente_audio=fuente_audio,
        audios=audios(cfg, mkv), subtitulos=subtitulos(cfg, mkv), mediainfo=mediainfo_texto(mkv),
        release=re.sub(r"\.mkv$", "", nombre, flags=re.IGNORECASE), enlaces=chr(10).join(enlaces.lineas()) if enlaces else "",
        resolucion=f"{v.ancho}x{v.alto}" if v else "",
        codec_video=cfg.nombre_codec_video(v.codec, preguntar=False) if v else "",
    )
    destino = entrada.parent / (nombre + ".txt")
    destino.write_text(plantilla.format(**campos), encoding="utf-8")
    nfos: List[Path] = []
    if _nfo_habilitado(cfg):
        anio_nfo = anio or (enlaces.anio if enlaces else "")
        nfos, hay_ids = _generar_nfo_identificacion(entrada, tipo_nfo, titulo, anio_nfo, temporada_nfo,
                                                     episodio_nfo, enlaces)
        if not hay_ids:
            ui.aviso("NFO creado sin ID externo: el panel podrá ver el tipo y el título, "
                     "pero no identificarlo automáticamente. Añade el enlace solicitado al generar la ficha.")
    sufijo_nfo = " + NFO de identificación" if nfos else ""
    ui.ok((destino.name + sufijo_nfo) if silencioso else f"Ficha: {destino.name}{sufijo_nfo}")
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
