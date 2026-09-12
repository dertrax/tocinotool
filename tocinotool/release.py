"""PREPARAR RELEASE: el flujo continuo de la v1 (AC3 → AutoMuxer → dogtool)
en una sola pasada sobre la carpeta de trabajo.

Las decisiones se toman AL PRINCIPIO (con propuesta automática) y el resto
del flujo ya no pregunta salvo para supervisar:

  * origen: WEB-DL / Blu-ray Rip / encode  (propuesto por el contenido del fichero:
        settings de x264/x265/SVT-AV1 → encode; DTS/TrueHD/PCM → Blu-ray;
        un AV1 sin ajustes de encoder y un nombre WEB-DL → WEB-DL)
        WEB-DL y Blu-ray → se conservan los audios originales y se añaden los AC3
        encode       → una sola pista por idioma: solo los AC3
  * contenido: película / capítulo(s) / temporada(s)  (propuesto por SxxExx)
  * plataforma, si es WEB-DL (del listado del config; siempre se pregunta)

Después:  convertir → muxer (plan a confirmar) → verificar → renombrar (nombre a
confirmar) → torrent → ficha → capturas, todo automático. Los derivados de
``temporal/`` se limpian tras verificar; las fuentes se conservan en
``originales/`` solo después de validar el MKV final.
"""
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import ac3, capturas, ficha, mux, probe, renombrar, tools, torrent, ui, verificar, workspace


@dataclass
class Contexto:
    origen: str          # webdl | bluray | encode | manual
    contenido: str       # capitulo | temporada | pelicula
    vod: str = ""        # tag de plataforma si WEB-DL

    @property
    def modo_ac3(self) -> str:
        return "solo_ac3" if self.origen == "encode" else "todas"

    @property
    def conservar_originales(self) -> bool:
        return bool((self.perfiles or {}).get(self.origen, {}).get("conservar_originales", self.origen != "encode"))

    perfiles: dict = field(default_factory=dict)

    def opciones_renombrado(self) -> renombrar.Opciones:
        return renombrar.Opciones(serie=self.contenido != "pelicula", web=self.origen == "webdl", vod=self.vod,
                                  temporada_completa=self.contenido == "temporada")


def detectar_origen(cfg, video: Path, nombres: str) -> str:
    """Propuesta de origen: el nombre manda si dice WEB-DL/WEBRip; si no,
    settings de x264/x265/SVT-AV1 en el vídeo → encode; DTS/TrueHD/PCM →
    Blu-ray; nombre BluRay/Remux → Blu-ray; en otro caso WEB-DL."""
    if renombrar._RE_WEB.search(nombres):
        return "webdl"
    if video.suffix.lower() in (".mp4", ".m4v"):
        return "webdl"   # un mp4 de una plataforma (Crunchyroll, Amazon…) es WEB-DL, aunque lleve settings de x264
    try:
        from pymediainfo import MediaInfo
        mi = MediaInfo.parse(str(video), library_file=tools.biblioteca_mediainfo())
        v = mi.video_tracks[0] if mi.video_tracks else None
        if v is not None:
            encoder = ((v.encoded_library_name or "") + " " + (v.encoded_library_settings or "")).lower()
            if any(x in encoder for x in ("x264", "x265", "svt-av1", "rav1e", "libaom")):
                return "encode"
    except Exception:  # noqa: BLE001 — sin libmediainfo se decide por codecs y nombre
        pass
    m = probe.analizar(video, cfg)
    # AV1 también llega desde plataformas WEB-DL. Sin marca de encoder de un
    # encode y sin señales Blu-ray se clasifica como WEB-DL, no como HEVC/x265.
    if m.video and m.video.codec == "av1":
        return "webdl"
    if any(a.codec in ("dts", "truehd", "flac", "pcm_s16le", "pcm_s24le", "mlp") for a in m.audios):
        return "bluray"
    if renombrar._RE_DISCO.search(nombres):
        return "bluray"
    return "webdl"


def _ac3_ya_hechos(cfg, carpeta: Path) -> bool:
    """True si en todos los vídeos cada idioma de audio ya tiene una pista AC3."""
    for v in probe.listar_videos(carpeta, cfg, recursivo=False):
        audios = probe.analizar(v, cfg).audios
        if not audios:
            return False
        idiomas = {cfg.canon_idioma(a.idioma) for a in audios}
        con_ac3 = {cfg.canon_idioma(a.idioma) for a in audios if a.codec == "ac3"}
        if idiomas - con_ac3:
            return False
    return True


def _resumen(cfg, carpeta: Path) -> None:
    videos = probe.listar_videos(carpeta, cfg, recursivo=False)
    ui.seccion(f"{len(videos)} vídeo(s) en {carpeta.name}")
    m = probe.analizar(videos[0], cfg)
    filas = []
    for p in m.pistas:
        if p.tipo in ("video", "audio", "subtitle"):
            filas.append([p.tipo, p.idioma, p.describir(), p.titulo, ("D" if p.defecto else "-") + ("F" if p.forzado else "-")])
    ui.tabla(["tipo", "idioma", "detalle", "título", "D/F"], filas)
    if len(videos) > 1:
        ui.info(f"(se muestra {videos[0].name}; el resto se procesa igual)")


def _listar(entradas, maximo: int = 8) -> None:
    ui.info(f"{sum(1 for e in entradas if e.is_dir())} carpeta(s), {sum(1 for e in entradas if e.is_file())} fichero(s)")
    for e in entradas[:maximo]:
        ui.info("  " + e.name + ("/" if e.is_dir() else ""))
    if len(entradas) > maximo:
        ui.info(f"  ... y {len(entradas) - maximo} más")


def preguntar_perfil_inicial(cfg) -> str:
    """Se pregunta antes de analizar archivos; `auto` sigue siendo explícito."""
    ui.seccion("¿Con qué trabajamos?")
    return ui.preguntar_opcion("Tipo de release", [
        ("webdl", "WEB-DL: audios originales + AC3"),
        ("bluray", "Blu-ray Rip / Remux: compatible + pista original si existe"),
        ("encode", "encode (mHD, x264/x265…): una sola pista por idioma, solo AC3"),
        ("auto", "detectar automáticamente y confirmar"),
    ], defecto="auto")


def preguntar_contexto(cfg, carpeta: Path, grupos, origen: str) -> Contexto:
    episodios = [g for g in grupos if g.es_episodio]
    contenido = ui.preguntar_opcion("Contenido de la carpeta", [
        ("pelicula", "película"),
        ("capitulo", "capítulo(s) suelto(s) de serie"),
        ("temporada", "temporada(s) completa(s): una carpeta por temporada"),
    ], defecto="temporada" if len(episodios) > 1 else "capitulo" if episodios else "pelicula")
    vod = renombrar.preguntar_plataforma(cfg) if origen == "webdl" else ""
    ctx = Contexto(origen=origen, contenido=contenido, vod=vod, perfiles=cfg.get("perfiles_release", {}))
    ui.tabla(["origen", "contenido", "plataforma", "audios"],
             [[origen, contenido, vod or "-", "solo AC3" if ctx.modo_ac3 == "solo_ac3" else "originales + AC3"]])
    return ctx


def flujo(cfg, carpeta: Optional[Path] = None) -> Optional[Path]:
    ui.titulo("PREPARAR RELEASE — convertir → muxer → renombrar → torrent → ficha → capturas")
    from . import asistente
    estado_filebot, detalle_filebot = asistente.estado_filebot(cfg)
    sin_licencia_filebot = estado_filebot != asistente.FILEBOT_CON_LICENCIA
    if sin_licencia_filebot:
        ui.aviso(detalle_filebot)
        ui.info("El flujo puede convertir, muxear y verificar, pero se detendrá antes del renombrado automático.")
        ui.info(asistente.nota_licencia_filebot())
        if not ui.preguntar_sn("¿Continuar hasta ese punto conservando el trabajo realizado?", True):
            return carpeta
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "Carpeta de trabajo (contenedores o componentes sueltos)", admitir_fichero=True)
    entrada_directa = carpeta if carpeta.is_file() else None
    raiz = carpeta.parent if entrada_directa else carpeta
    elegido = preguntar_perfil_inicial(cfg)
    ws = workspace.analizar(carpeta, cfg)
    workspace.mostrar(ws, cfg)
    if not ws.valido:
        ui.aviso("Corrige los archivos no asociados o desincronizados antes de preparar el release.")
        return carpeta
    nombres = " ".join(str(g.video.ruta.name) for g in ws.grupos)
    detectado = detectar_origen(cfg, ws.grupos[0].video.ruta, nombres)
    origen = detectado if elegido == "auto" else elegido
    if elegido == "auto":
        ui.info(f"Tipo detectado: {cfg.get('perfiles_release', {}).get(origen, {}).get('nombre', origen)}")
        origen = ui.preguntar_opcion("Confirmar tipo de release", [
            ("webdl", "WEB-DL"), ("encode", "Encode / MicroHD"), ("bluray", "Blu-ray Rip / Remux")
        ], defecto=origen)
    ctx = preguntar_contexto(cfg, raiz, ws.grupos, origen)
    if sin_licencia_filebot and ctx.contenido != "pelicula":
        from . import series
        ui.info("FileBot no disponible: parser propio ACTIVO para analizar la correlación.")
        series.flujo(cfg, carpeta, pedir_fallback=True)

    # Estado de las pistas: si el mkv viene ya preparado (p. ej. de "Juntar" con un
    # release anterior) no hay nada que convertir ni muxear.
    ui.titulo("ESTADO DE LAS PISTAS")
    ac3_hechos = all(g.video.ruta.suffix.lower() == ".mkv" and verificar.verificar(g.video.ruta, cfg, ctx.origen)[0]
                      for g in ws.grupos)
    preparado = ac3_hechos
    if preparado:
        ui.ok("Pistas ya preparadas: AC3 de cada idioma, orden, nombres y flags correctos. Se salta convertir y muxer.")
        todo_ok = True
    else:
        if ac3_hechos:
            # solo hay que ordenar/nombrar: muxer
            ui.titulo("MUXER (orden, nombres, flags)")
            ui.ok("Ya hay una pista AC3 por cada idioma: no hay nada que convertir.")
            mux.procesar_carpeta(cfg, raiz, preguntar_opciones=False, conservar_audio=ctx.conservar_originales,
                                 conservar_subs=True, preguntar_borrado=False, solo=entrada_directa)
        else:
            # Conversor y muxer comparten Workspace/ReleaseGroup: funciona igual
            # con un MKV de entrada que con vídeo elemental y archivos sueltos.
            ui.titulo("CONVERTIR a AC3 y MUXEAR")
            try:
                ac3.procesar_grupos(cfg, ws.grupos, ctx.origen)
            except RuntimeError as e:
                ui.error(str(e))
                return carpeta
        if entrada_directa:
            todo_ok = all(verificar.verificar(g.video.ruta, cfg, ctx.origen)[0] for g in ws.grupos)
        else:
            todo_ok = verificar.verificar_carpeta(cfg, raiz, recursivo=True, perfil=ctx.origen)
    if not todo_ok and not ui.preguntar_sn("La verificación ha encontrado problemas. ¿Continuar igualmente?", False):
        ui.aviso("Se para aquí. Los ficheros de origen están en originales/ (y los derivados en temporal/).")
        return carpeta

    # 3. Renombrar ------------------------------------------------------------
    ui.titulo("RENOMBRAR")
    if sin_licencia_filebot:
        ui.aviso("No se ha detectado una licencia válida de FileBot. El trabajo realizado se conserva.")
        ui.info("Puedes activar la licencia y usar la opción 4, o renombrar manualmente el resultado.")
        ui.info("Después usa la opción 6 (Ficha): pedirá TMDb para películas e IMDb para series.")
        ui.info(asistente.nota_licencia_filebot())
        return raiz
    mkv_antes = set(raiz.glob("*.mkv")) if entrada_directa else set()
    if tools.buscar("filebot", cfg):
        renombrar.renombrar_carpeta(cfg, entrada_directa or raiz, fijas=ctx.opciones_renombrado())
    else:
        ui.aviso("FileBot no está disponible: se salta el renombrado.")
        ui.info(asistente.nota_licencia_filebot())
    if entrada_directa:
        nuevos = set(raiz.glob("*.mkv")) - mkv_antes
        release_final = next(iter(nuevos)) if len(nuevos) == 1 else entrada_directa
        entradas = [release_final] if release_final.exists() else []
    else:
        entradas = renombrar.entradas_carpeta(raiz)
    ui.seccion("Resultado")
    _listar(entradas)

    # 4. Torrent, ficha y capturas: automáticos --------------------------------
    ui.titulo("TORRENT · FICHA · CAPTURAS")
    torrents = [torrent.crear(cfg, entradas[0])] if entrada_directa and entradas else torrent.crear_todos(cfg, raiz)
    torrents = [t for t in torrents if t]
    fuente = f"{cfg.nombre_plataforma(ctx.vod)} WEB-DL" if ctx.origen == "webdl" and ctx.vod else ""
    if entrada_directa and entradas:
        ficha.flujo(cfg, entradas[0], fuente_defecto=fuente)
        fichas = [entradas[0].with_suffix(entradas[0].suffix + ".txt")]
        imagenes = capturas.capturar(entradas[0], cfg)
    else:
        fichas = ficha.generar_todas(cfg, raiz, fuente_defecto=fuente, serie=(ctx.contenido != "pelicula"))
        imagenes = capturas.capturar_releases(cfg, raiz)

    # Limpieza: solo lo derivado (temporal/: .ac3 sueltos, srt limpiados). Los
    # originales NUNCA se borran: quedan en originales/ hasta que el usuario decida.
    temporales = sorted(d for d in raiz.rglob("*") if d.is_dir() and d.name == "temporal")
    if temporales and todo_ok:
        for d in temporales:
            shutil.rmtree(d, ignore_errors=True)
    originales = sorted(d for d in raiz.rglob("*") if d.is_dir() and d.name == "originales")
    if originales:
        ui.info("Ficheros de origen conservados en: " + ", ".join(str(d.relative_to(raiz)) + "/" for d in originales))
        ui.info("Bórralos a mano cuando hayas comprobado el release.")

    ui.seccion("Release terminado")
    ui.info(f"Carpeta:   {raiz}")
    ui.info(f"Releases:  {len(entradas)}   torrents: {len(torrents)}   fichas: {len(fichas)}   capturas: {len(imagenes)}")
    return raiz
