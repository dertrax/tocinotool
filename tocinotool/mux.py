"""Muxer general: deja un mkv con las pistas ordenadas, nombradas y con los
flags correctos. Sustituye al AutoMuxerCli, al CUSTOMcode y a "Juntar vídeo y
audio" del tociNoTool.bat.

Fuentes de pistas, todas en el mismo plan:
  * las pistas que ya están dentro del mkv principal (lo normal en el flujo);
  * ficheros sueltos con el mismo nombre (Peli.es-ES.forced.srt, Peli.[spa].ac3…);
  * otro contenedor (mkv/mka) del que se cogen los audios y subtítulos
    ("juntar" un mkv extranjero limpio con el mkv/mka en castellano).

Antes de muxear se muestra el plan (orden, idioma, tipo, nombre, D/F) y se
puede corregir cualquier pista o quitarla.
"""
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import probe, tools, ui

_SEP = re.compile(r"[.\-_\[\]\(\) ]+")
_ORDEN_SUBTIPO = {"forced": 0, "complete": 1, "sdh": 2}


@dataclass
class PistaPlan:
    fichero: int              # índice en Plan.ficheros (0 = principal)
    tid: int                  # id de pista para mkvmerge
    tipo: str                 # video | audio | sub
    idioma: str = "und"       # canónico
    subtipo: str = "complete" # forced | complete | sdh (solo subs)
    nombre: str = ""
    defecto: bool = False
    forzado: bool = False
    incluir: bool = True
    detalle: str = ""         # codec / canales / kbps
    origen: str = ""          # nombre corto del fichero
    orden_original: int = 0
    pista: Optional[probe.Pista] = None   # datos de ffprobe (codec, canales, kbps…)


@dataclass
class Plan:
    ficheros: List[Path]
    salida: Path
    pistas: List[PistaPlan] = field(default_factory=list)
    extra_apartar: List[Path] = field(default_factory=list)   # sueltos originales sustituidos por una copia limpia


# ---------------------------------------------------------------------------
# Análisis de contenedores: pistas de ffprobe ↔ ids de mkvmerge
# ---------------------------------------------------------------------------

def pistas_contenedor(ruta: Path, cfg, incluir_no_muxeables: bool = False):
    """[(id_mkvmerge, Pista)] para vídeo/audio/subtítulos, en orden de fichero.
    Se emparejan por tipo (mkvmerge y ffprobe numeran distinto cuando hay
    portadas o pistas que mkvmerge no lee, p. ej. subtítulos mov_text de mp4).
    Con `incluir_no_muxeables`, las pistas que mkvmerge no ve van con id None.
    Si mkvmerge da idioma IETF (es-419), se usa ese como idioma de la pista."""
    medio = probe.analizar(ruta, cfg)
    streams = [p for p in medio.pistas if p.tipo in ("video", "audio", "subtitle")
               and not (p.tipo == "video" and p.codec in ("png", "mjpeg", "bmp", "gif"))]  # portadas
    exe = tools.buscar("mkvmerge", cfg, obligatorio=True)
    r = tools.ejecutar([exe, "-J", str(ruta)], capturar=True, mostrar=False, comprobar=False)
    tracks = []
    try:
        tracks = [t for t in json.loads(r.stdout or "{}").get("tracks", []) if t.get("type") in ("video", "audio", "subtitles")]
    except (ValueError, KeyError):
        pass
    tipo_mkv = {"video": "video", "audio": "audio", "subtitles": "subtitle"}
    pendientes = {"video": [], "audio": [], "subtitle": []}
    for t in tracks:
        pendientes[tipo_mkv[t["type"]]].append(t)
    res = []
    for p in streams:
        cola = pendientes[p.tipo]
        if cola:
            t = cola.pop(0)
            ietf = (t.get("properties") or {}).get("language_ietf")
            if ietf and cfg.es_idioma(ietf) and cfg.canon_idioma(ietf) != cfg.canon_idioma(p.idioma):
                p.idioma = ietf
            res.append((int(t["id"]), p))
        elif incluir_no_muxeables:
            res.append((None, p))
    return res


def _subtipo_interno(p: probe.Pista) -> str:
    t = p.titulo.lower()
    if p.forzado or "forz" in t or "forced" in t:
        return "forced"
    if p.sdh or "sordos" in t or "sdh" in t or "cc" in t.split():
        return "sdh"
    return "complete"


def _tokens(resto: str) -> List[str]:
    return [t for t in _SEP.split(resto.lower()) if t]


def _idioma_y_subtipo_de_nombre(resto: str, cfg) -> Tuple[str, str]:
    toks = _tokens(resto)
    idioma = "und"
    for i in range(len(toks)):
        par = "-".join(toks[i:i + 2])
        if i + 1 < len(toks) and cfg.es_idioma(par):
            idioma = cfg.canon_idioma(par)
            break
        if cfg.es_idioma(toks[i]):
            idioma = cfg.canon_idioma(toks[i])
            break
    tipos = set()
    for tipo, lista in cfg["subtitulos"]["palabras"].items():
        if any(t in [str(x).lower() for x in lista] for t in toks):
            tipos.add(tipo)
    # prioridad: forzados > completos (stripped_sdh = completos) > sordos
    subtipo = "forced" if "forced" in tipos else "complete" if "complete" in tipos else "sdh" if "sdh" in tipos else "complete"
    return idioma, subtipo


def buscar_sueltos(video: Path, carpeta: Path, cfg) -> List[Path]:
    """Ficheros de audio/subtítulo/contenedor de `carpeta` cuyo nombre empieza por el del vídeo."""
    exts = {e.lower() for e in cfg["extensiones"]["audio"]} | {e.lower() for e in cfg["extensiones"]["subtitulo"]}
    res = []
    for f in sorted(carpeta.iterdir()):
        if f.is_file() and f != video and f.suffix.lower().lstrip(".") in exts \
                and f.name.lower().startswith(video.stem.lower()):
            res.append(f)
    return res


# ---------------------------------------------------------------------------
# Construcción del plan
# ---------------------------------------------------------------------------

def _es_contenedor(ruta: Path, cfg) -> bool:
    return ruta.suffix.lower().lstrip(".") in ("mkv", "mka", "mp4", "m4v", "webm", "ts", "m2ts")


def _nombre_audio(cfg, idioma: str, p: probe.Pista) -> str:
    codec = cfg.nombre_codec_audio(p.codec, p.perfil) + (" Atmos" if p.atmos else "")
    return cfg["plantillas"]["pista_audio"].format(
        lang=cfg.nombre_idioma(idioma), codec=codec,
        channels=cfg.etiqueta_canales(p.canales), bitrate=p.kbps or "?")


def _formato_sub(codec_o_ext: str) -> str:
    """Nombre común de formato para codecs de contenedor y extensiones sueltas."""
    return {"subrip": "srt", "hdmv_pgs_subtitle": "sup", "dvd_subtitle": "idx",
            "dvdsub": "idx", "ass": "ass", "ssa": "ssa", "webvtt": "vtt"}.get(
                (codec_o_ext or "").lower(), (codec_o_ext or "").lower())


def _nombre_sub(cfg, idioma: str, subtipo: str, codec_o_ext: str) -> str:
    formatos = cfg["subtitulos"]["formatos"]
    clave = _formato_sub(codec_o_ext)
    sufijo = formatos.get(clave, "") or ""
    return cfg["plantillas"]["pista_subtitulo"].format(
        lang=cfg.nombre_idioma(idioma), type=cfg["subtitulos"]["tipos"][subtipo], codec=sufijo)


def _idioma_mkv(cfg, idioma: str) -> str:
    """Código que se pasa a mkvmerge: el canónico, salvo excepciones (spal → es-419)."""
    return str((cfg.get("codigos_mkv") or {}).get(idioma, idioma))


def construir_plan(video: Path, salida: Path, cfg, sueltos: List[Path] = (), conservar_audio: bool = True,
                   conservar_subs: bool = True, excluir_audio_idiomas: Sequence[str] = ()) -> Plan:
    """`excluir_audio_idiomas`: audios internos de esos idiomas se marcan como
    excluidos (modo 'sustituir' de la conversión a AC3)."""
    from . import subs as _subs
    plan = Plan(ficheros=[video], salida=salida)
    temporal = video.parent / "temporal"
    n = 0

    def anadir(fi: int, tid: int, p: probe.Pista, idioma: str, subtipo: str, incluir: bool, origen: str) -> PistaPlan:
        nonlocal n
        tipo = "sub" if p.tipo == "subtitle" else p.tipo
        pp = PistaPlan(fichero=fi, tid=tid, tipo=tipo, idioma=idioma, subtipo=subtipo, incluir=incluir,
                       detalle=p.describir(), origen=origen, orden_original=n, pista=p)
        n += 1
        plan.pistas.append(pp)
        return pp

    def anadir_fichero(ruta: Path, original: Optional[Path] = None) -> int:
        plan.ficheros.append(ruta)
        if original is not None and original != ruta:
            plan.extra_apartar.append(original)
        return len(plan.ficheros) - 1

    # 1) pistas internas del principal. Los subtítulos que mkvmerge no puede leer
    #    (mov_text de mp4) se extraen a srt con ffmpeg y entran como sueltos.
    hay_video = False
    spa_internos: List[PistaPlan] = []
    for tid, p in pistas_contenedor(video, cfg, incluir_no_muxeables=True):
        idioma = cfg.canon_idioma(p.idioma)
        if p.tipo == "video":
            if tid is None:
                continue
            anadir(0, tid, p, "und", "complete", not hay_video, video.name)
            hay_video = True
        elif p.tipo == "audio":
            if tid is None:
                ui.aviso(f"{video.name}: audio '{p.describir()}' no legible por mkvmerge, se ignora.")
                continue
            anadir(0, tid, p, idioma, "complete", conservar_audio and idioma not in excluir_audio_idiomas, video.name)
        else:
            if tid is None:
                temporal.mkdir(exist_ok=True)
                srt = temporal / f"{video.stem}.{idioma}.{p.indice}.srt"
                ffmpeg = tools.buscar("ffmpeg", cfg, obligatorio=True)
                tools.ejecutar_silencioso([ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                                           "-i", str(video), "-map", f"0:{p.indice}", "-c:s", "srt", str(srt)])
                srt.write_text(_subs.limpiar_texto_srt(_subs.leer_texto(srt)), encoding="utf-8")
                fi = anadir_fichero(srt)
                pp = anadir(fi, 0, p, idioma, _subtipo_interno(p), conservar_subs, f"{video.name} (extraído)")
                pp.detalle = "srt (extraído)"
            else:
                pp = anadir(0, tid, p, idioma, _subtipo_interno(p), conservar_subs, video.name)
            if idioma in ("spa", "und"):
                spa_internos.append(pp)

    # castellano / latino / idioma desconocido de los subtítulos internos: por el texto
    if spa_internos:
        textos = [_subs.texto_pista(video, pp.pista.indice, cfg) for pp in spa_internos]
        for pp, t in zip(spa_internos, textos):
            if pp.idioma == "und":
                pp.idioma = _subs.detectar_idioma(t) or "und"
        grupo = [(pp, t) for pp, t in zip(spa_internos, textos) if pp.idioma == "spa"]
        if grupo:
            for pp, variante in zip([g[0] for g in grupo], _subs.asignar_variantes([g[1] for g in grupo])):
                pp.idioma = variante

    # 2) ficheros sueltos: contenedores (mka/mkv → todas sus pistas de audio/subs) o pistas crudas
    for f in sueltos:
        if _es_contenedor(f, cfg):
            fi = anadir_fichero(f)
            for tid, p in pistas_contenedor(f, cfg):
                if p.tipo == "video":
                    continue
                anadir(fi, tid, p, cfg.canon_idioma(p.idioma),
                       _subtipo_interno(p) if p.tipo == "subtitle" else "complete", True, f.name)
            continue
        resto = f.name[len(video.stem):-len(f.suffix)] if f.name.lower().startswith(video.stem.lower()) else f.stem
        idioma, subtipo = _idioma_y_subtipo_de_nombre(resto, cfg)
        ext = f.suffix.lower().lstrip(".")
        # VobSub se entrega a mkvmerge mediante el .idx; su .sub binario debe
        # acompañarlo si apartamos los originales antes de crear el MKV.
        if ext == "idx":
            companero = f.with_suffix(".sub")
            if companero.exists():
                plan.extra_apartar.append(companero)
        listo = f
        if ext in [e.lower() for e in cfg["extensiones"]["subtitulo"]]:
            listo = _subs.preparar_suelto(f, temporal, cfg)   # ass/vtt → srt; etiquetas {\…} fuera
            if idioma == "und" or idioma == "spa":
                texto = _subs.leer_texto(listo)
                detectado = _subs.detectar_idioma(texto) if idioma == "und" else (_subs.detectar_variante_es(texto) or "spa")
                idioma = detectado or idioma
        # El formato ASS contiene estilos, posiciones y carteles que se perderían
        # en SRT. Para anime se incluyen el ASS original y el SRT limpio. Si el
        # ASS completo contiene carteles, se extraen también como SRT forzado.
        rutas = [(listo, subtipo, "limpiado")]
        if ext in ("ass", "ssa") and listo != f:
            rutas = [(f, subtipo, ""), (listo, subtipo, "convertido a SRT")]
            if subtipo != "forced":
                extraidos = _subs.extraer_carteles_ass(f, temporal)
                if extraidos:
                    srt_forzado, ass_forzado = extraidos
                    rutas.extend([
                        (srt_forzado, "forced", "carteles → SRT forzado"),
                        (ass_forzado, "forced", "carteles → ASS forzado"),
                    ])
        rutas_fisicas = [ruta for ruta, _, _ in rutas]
        for ruta, subtipo_ruta, proceso in rutas:
            m = probe.analizar(ruta, cfg)
            p = (m.audios or m.subtitulos or [None])[0]
            if p is None:
                ui.aviso(f"{f.name}: no contiene audio ni subtítulos, se ignora.")
                continue
            # Si el original ASS entra en el plan, _apartar lo moverá a
            # originales/. Para otros formatos, se aparta el original que fue
            # sustituido por su SRT limpio. No se aparta dos veces un ASS que
            # ya forma parte de las rutas del plan.
            original = f if ruta != f and f not in rutas_fisicas else None
            fi = anadir_fichero(ruta, original=original)
            etiqueta = f.name + (f" ({proceso})" if proceso else "")
            anadir(fi, 0, p, idioma, subtipo_ruta, True, etiqueta)

    completar_plan(plan, cfg)
    return plan


def completar_plan(plan: Plan, cfg) -> None:
    """Idiomas desconocidos → pregunta; nombres por plantilla; orden y flags D/F."""
    for pp in plan.pistas:
        if pp.tipo != "video" and pp.idioma == "und" and pp.incluir:
            ui.aviso(f"Pista sin idioma: {pp.origen} · {pp.tipo} · {pp.detalle}")
            pp.idioma = ui.preguntar_idioma(cfg, "¿Qué idioma es?")
        if pp.tipo == "video":
            pp.nombre = ""
            continue
        if pp.nombre:
            continue
        ruta = plan.ficheros[pp.fichero]
        if pp.tipo == "audio":
            pp.nombre = _nombre_audio(cfg, pp.idioma, pp.pista)
        elif _es_contenedor(ruta, cfg):
            pp.nombre = _nombre_sub(cfg, pp.idioma, pp.subtipo, pp.pista.codec)
        else:
            pp.nombre = _nombre_sub(cfg, pp.idioma, pp.subtipo, ruta.suffix.lower().lstrip("."))

    orden = [str(x) for x in cfg["orden_idiomas"]]

    def rango_idioma(i: str) -> int:
        return orden.index(i) if i in orden else len(orden)

    orden_codecs = [str(x).lower() for x in cfg.get("orden_codecs_audio", [])]

    def rango_codec(p: PistaPlan) -> int:
        # el nombre comercial (DD+, DD, TrueHD…) está al principio del nombre de pista, tras el idioma
        nombre = p.nombre.lower()
        candidatos = [i for i, c in enumerate(orden_codecs) if f" {c} " in f" {nombre} "]
        return min(candidatos) if candidatos else len(orden_codecs)

    orden_formatos = [str(x).lower() for x in cfg["subtitulos"].get("orden_formatos", ["srt", "ass", "ssa", "sup", "idx", "vtt"])]

    def rango_formato(p: PistaPlan) -> int:
        ruta = plan.ficheros[p.fichero]
        codec_o_ext = p.pista.codec if _es_contenedor(ruta, cfg) else ruta.suffix.lower().lstrip(".")
        formato = _formato_sub(codec_o_ext)
        return orden_formatos.index(formato) if formato in orden_formatos else len(orden_formatos)

    videos = [p for p in plan.pistas if p.tipo == "video"]
    audios = sorted((p for p in plan.pistas if p.tipo == "audio"),
                    key=lambda p: (rango_idioma(p.idioma), rango_codec(p), p.orden_original))
    subs = sorted((p for p in plan.pistas if p.tipo == "sub"),
                  key=lambda p: (rango_idioma(p.idioma), rango_formato(p),
                                 _ORDEN_SUBTIPO[p.subtipo], p.orden_original))
    plan.pistas = videos + audios + subs

    forzado_default = [str(x) for x in cfg["subtitulos"]["forzado_default"]]
    primero = True
    for p in audios:
        p.defecto = p.incluir and primero
        if p.incluir:
            primero = False
    idiomas_con_sub_default = set()
    for p in subs:
        p.forzado = p.subtipo == "forced"
        p.defecto = (p.incluir and p.forzado and p.idioma in forzado_default
                     and p.idioma not in idiomas_con_sub_default)
        if p.defecto:
            idiomas_con_sub_default.add(p.idioma)


# ---------------------------------------------------------------------------
# Presentación y edición
# ---------------------------------------------------------------------------

def mostrar_plan(plan: Plan, cfg) -> None:
    ui.seccion(f"Plan → {plan.salida.name}")
    filas = []
    for i, p in enumerate(plan.pistas, 1):
        flags = ("D" if p.defecto else "-") + ("F" if p.forzado else "-")
        fila = [str(i), "" if p.incluir else "✖", p.tipo, p.idioma if p.tipo != "video" else "-",
                p.subtipo if p.tipo == "sub" else "-", p.detalle, p.nombre, flags]
        # El fichero de procedencia solo sirve para diagnosticar un plan;
        # normalmente alarga mucho la tabla y no cambia lo que se muxea.
        if tools.DETALLADO:
            fila.append(p.origen if (p.fichero or p.origen in ("EXTRANJERO", "PREPARADO")) else "")
        filas.append(fila)
    cabeceras = ["#", "", "tipo", "idioma", "subtipo", "detalle", "nombre de pista", "D/F"]
    if tools.DETALLADO:
        cabeceras.append("de")
    ui.tabla(cabeceras, filas)
    ui.info("✖ = se excluye del mkv final")


def editar_plan(plan: Plan, cfg) -> None:
    while True:
        mostrar_plan(plan, cfg)
        opciones = [(str(i), f"{i:>2}  {'✖ ' if not p.incluir else ''}{p.tipo:<5} {p.idioma if p.tipo != 'video' else '-':<4} {p.nombre or p.detalle}")
                    for i, p in enumerate(plan.pistas, 1)] + [("fin", "terminar de editar")]
        r = ui.preguntar_opcion("Pista a editar", opciones, defecto="fin")
        if r == "fin":
            return
        p = plan.pistas[int(r) - 1]
        accion = ui.preguntar_opcion("Acción", [
            ("x", "excluir / volver a incluir"), ("i", "cambiar idioma"),
            ("t", "cambiar tipo de subtítulo (forced/complete/sdh)"), ("n", "cambiar nombre de pista"),
            ("d", "alternar default"), ("f", "alternar forced"), ("v", "volver"),
        ], defecto="x")
        if accion == "x":
            p.incluir = not p.incluir
            completar_plan(plan, cfg)
        elif accion == "i":
            p.idioma = ui.preguntar_idioma(cfg, "Idioma", defecto=p.idioma)
            p.nombre = ""
            completar_plan(plan, cfg)
        elif accion == "t" and p.tipo == "sub":
            p.subtipo = ui.preguntar_opcion("Tipo", [(k, v) for k, v in cfg["subtitulos"]["tipos"].items()], defecto=p.subtipo)
            p.nombre = ""
            completar_plan(plan, cfg)
        elif accion == "n":
            p.nombre = ui.preguntar("Nombre de pista", defecto=p.nombre)
        elif accion == "d":
            p.defecto = not p.defecto
        elif accion == "f":
            p.forzado = not p.forzado


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

def comando_mkvmerge(plan: Plan, cfg) -> List[str]:
    exe = tools.buscar("mkvmerge", cfg, obligatorio=True)
    cmd = [exe, "-o", str(plan.salida), "--no-attachments", "--title", ""]
    orden = []
    for fi, ruta in enumerate(plan.ficheros):
        mias = [p for p in plan.pistas if p.fichero == fi and p.incluir]
        v = [p.tid for p in mias if p.tipo == "video"]
        a = [p.tid for p in mias if p.tipo == "audio"]
        s = [p.tid for p in mias if p.tipo == "sub"]
        cmd += ["--video-tracks", ",".join(map(str, v))] if v else ["--no-video"]
        cmd += ["--audio-tracks", ",".join(map(str, a))] if a else ["--no-audio"]
        cmd += ["--subtitle-tracks", ",".join(map(str, s))] if s else ["--no-subtitles"]
        for p in mias:
            cmd += ["--language", f"{p.tid}:{'und' if p.tipo == 'video' else _idioma_mkv(cfg, p.idioma)}",
                    "--track-name", f"{p.tid}:{p.nombre}",
                    "--default-track", f"{p.tid}:{'yes' if (p.defecto or p.tipo == 'video') else 'no'}"]
            if p.tipo == "sub":
                cmd += ["--forced-track", f"{p.tid}:{'yes' if p.forzado else 'no'}"]
        cmd.append(str(ruta))
    for p in plan.pistas:
        if p.incluir:
            orden.append(f"{p.fichero}:{p.tid}")
    cmd += ["--track-order", ",".join(orden)]
    return cmd


def ejecutar_plan(plan: Plan, cfg, etiqueta: str = "") -> Path:
    plan.salida.parent.mkdir(parents=True, exist_ok=True)
    tools.ejecutar_mkvmerge(comando_mkvmerge(plan, cfg), f"{etiqueta}{plan.salida.name}  ")
    # guardia: si el resultado no tiene exactamente las pistas del plan, algo se ha perdido
    esperadas = sum(1 for p in plan.pistas if p.incluir)
    obtenidas = len(pistas_contenedor(plan.salida, cfg))
    if obtenidas != esperadas:
        raise RuntimeError(f"{plan.salida.name}: el mkv tiene {obtenidas} pistas y el plan tenía {esperadas}. "
                           "Se para para no perder nada; los originales están en originales/.")
    return plan.salida


def _fuentes_reales(plan: Plan) -> List[Path]:
    """Entradas físicas que hay que conservar, sin derivados de ``temporal``."""
    vistas, fuentes = set(), []
    for ruta in [*plan.ficheros, *plan.extra_apartar]:
        try:
            clave = ruta.resolve()
        except OSError:
            clave = ruta
        if clave in vistas or not ruta.exists() or "temporal" in {p.lower() for p in ruta.parts}:
            continue
        vistas.add(clave)
        fuentes.append(ruta)
    return fuentes


def _destino_original(ruta: Path) -> Path:
    """Destino sin sobrescrituras: conserva cada episodio junto a sus fuentes."""
    carpeta = ruta.parent / "originales"
    carpeta.mkdir(exist_ok=True)
    candidato = carpeta / ruta.name
    n = 1
    while candidato.exists():
        candidato = carpeta / f"{ruta.stem}.{n}{ruta.suffix}"
        n += 1
    return candidato


def _archivar_fuentes(rutas: List[Path]) -> List[tuple[Path, Path]]:
    """Mueve, nunca borra, las fuentes ya usadas tras validar el MKV."""
    movimientos = []
    for ruta in rutas:
        destino = _destino_original(ruta)
        shutil.move(str(ruta), str(destino))
        movimientos.append((ruta, destino))
    return movimientos


def ejecutar_plan_con_originales(plan: Plan, cfg, etiqueta: str = "") -> Path:
    """Mux seguro: valida primero y solo entonces archiva las fuentes.

    Si el nombre de salida coincide con el contenedor de entrada, se genera en
    ``temporal/``. Así un error de mux o validación deja intactas las fuentes.
    """
    from . import diagnostico

    salida_final = plan.salida
    fuentes = _fuentes_reales(plan)
    conflicto = any(ruta.resolve() == salida_final.resolve() for ruta in fuentes)
    salida_temporal = None
    if conflicto:
        temporal = salida_final.parent / "temporal"
        temporal.mkdir(exist_ok=True)
        salida_temporal = temporal / f"{salida_final.stem}.final.mkv"
        if salida_temporal.exists():
            raise RuntimeError(f"Ya existe una salida temporal: {salida_temporal.name}. Revísala antes de continuar.")
        plan.salida = salida_temporal
    try:
        salida_validada = ejecutar_plan(plan, cfg, etiqueta)
    finally:
        plan.salida = salida_final

    try:
        movimientos = _archivar_fuentes(fuentes)
    except OSError as exc:
        informe = diagnostico.crear_informe_error(exc, cfg=cfg, modulo="mux", paso="archivar originales",
                                                    detalle="No se han podido mover todos los archivos fuente.")
        ui.aviso("Release generado correctamente, pero no se pudieron reorganizar todos los originales.")
        if informe:
            ui.info(f"Informe: {informe}")
        if salida_temporal:
            ui.info(f"El MKV validado queda en temporal/: {salida_validada.name}")
        return salida_validada

    if salida_temporal:
        shutil.move(str(salida_temporal), str(salida_final))
        salida_validada = salida_final
    if movimientos:
        ui.info(f"{len(movimientos)} fuente(s) conservada(s) en originales/.")
    return salida_validada


def procesar_carpeta(cfg, carpeta: Path, carpeta_sueltos: Optional[Path] = None,
                     conservar_audio: bool = True, conservar_subs: bool = True,
                     preguntar_opciones: bool = True, preguntar_borrado: bool = True,
                     solo: Optional[Path] = None) -> List[Path]:
    """Normaliza/muxea todos los vídeos de `carpeta` (o solo `solo`). Devuelve las salidas."""
    from . import workspace

    grupos = None
    if solo is None and carpeta_sueltos is None:
        # El mismo analizador se usa desde PREPARAR RELEASE: una carpeta puede
        # contener varios episodios con vídeo/audio/subtítulos separados.
        ws = workspace.analizar(carpeta, cfg)
        workspace.mostrar(ws, cfg)
        if not ws.valido:
            ui.aviso("No se muxea nada mientras haya archivos ambiguos, sin vídeo o desincronizados.")
            return []
        grupos = ws.grupos
        videos = [g.video.ruta for g in grupos]
    else:
        videos = [solo] if solo else probe.listar_videos(carpeta, cfg, recursivo=True)
    if not videos:
        ui.error("No hay vídeos en la carpeta.")
        return []
    carpeta_sueltos = carpeta_sueltos or carpeta
    ui.info(f"{len(videos)} vídeo(s) detectado(s), analizando...")
    if preguntar_opciones:
        conservar_audio = ui.preguntar_sn("¿Conservar los audios que ya tiene el vídeo?", conservar_audio)
        conservar_subs = ui.preguntar_sn("¿Conservar los subtítulos que ya tiene el vídeo?", conservar_subs)

    planes: List[Plan] = []
    for n, v in enumerate(videos):
        # los sueltos se buscan junto al vídeo (o en la carpeta indicada); la salida va junto al vídeo
        if grupos is not None:
            sueltos = grupos[n].componentes_sueltos
        else:
            sueltos = buscar_sueltos(v, carpeta_sueltos if carpeta_sueltos != carpeta else v.parent, cfg)
        planes.append(construir_plan(v, v.parent / (v.stem + ".mkv"), cfg, sueltos, conservar_audio, conservar_subs))

    revisar_todos = False
    for i, plan in enumerate(planes):
        if i > 0 and not revisar_todos:
            break
        mostrar_plan(plan, cfg)
        if not ui.preguntar_sn("¿Correcto?", True):
            editar_plan(plan, cfg)
        if i == 0 and len(planes) > 1:
            revisar_todos = not ui.preguntar_sn(f"Hay {len(planes)} vídeos. ¿Aplicar el mismo criterio sin revisar uno a uno?", True)

    salidas = []
    ui.seccion(f"Muxeando {len(planes)} fichero(s)")
    for i, plan in enumerate(planes, 1):
        salidas.append(ejecutar_plan_con_originales(plan, cfg, f"[{i}/{len(planes)}] "))
    ui.info("Los ficheros de origen se conservan en originales/ (bórralos tú cuando hayas comprobado el release).")
    return salidas


def flujo(cfg, carpeta: Optional[Path] = None) -> Optional[Path]:
    ui.titulo("MUXER — ordenar, nombrar y flaggear pistas (+ audios/subs sueltos)")
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "Qué muxear", admitir_fichero=True)
    solo = carpeta if carpeta.is_file() else None
    carpeta = carpeta.parent if carpeta.is_file() else carpeta
    perfil = ui.preguntar_opcion("Perfil de release", [
        ("manual", "Manual / avanzado: conservar las pistas seleccionadas"),
        ("webdl", "WEB-DL: originales + AC3"),
        ("encode", "Encode / MicroHD: una pista AC3 por idioma"),
        ("bluray", "Blu-ray Rip / Remux: originales + AC3 compatible"),
    ], defecto="manual")
    d = ui.preguntar_opcion("Los audios/subtítulos sueltos (si los hay) están en…", [
        ("misma", "la misma carpeta que el vídeo"),
        ("otra", "otra carpeta (arrastrarla)"),
    ], defecto="misma")
    sueltos = ui.preguntar_ruta("Carpeta con los sueltos") if d == "otra" else None
    if perfil != "manual" and sueltos is None:
        from . import ac3, workspace
        ws = workspace.analizar(carpeta, cfg)
        if solo:
            ws.grupos = [g for g in ws.grupos if g.video.ruta == solo]
        workspace.mostrar(ws, cfg)
        if not ws.valido:
            ui.aviso("No se aplica el perfil mientras haya componentes ambiguos o desincronizados.")
        else:
            ac3.procesar_grupos(cfg, ws.grupos, perfil)
    else:
        if perfil != "manual":
            ui.aviso("Con sueltos en otra carpeta se usa modo manual para no asociar archivos de forma insegura.")
        procesar_carpeta(cfg, carpeta, sueltos, solo=solo)
    return carpeta


def _videos_de(ruta: Path, cfg) -> List[Path]:
    return [ruta] if ruta.is_file() else probe.listar_videos(ruta, cfg, recursivo=True)


def _pareja(v: Path, fuente: Path, candidatos: List[Path]) -> Optional[Path]:
    """Fichero de audios/subs que corresponde a `v`: el mismo fichero si se dio
    uno suelto; si no, por nombre; si solo hay uno, ese."""
    if fuente.is_file():
        return fuente
    for f in candidatos:
        if f.stem.lower() == v.stem.lower() or f.stem.lower().startswith(v.stem.lower()):
            return f
    return candidatos[0] if len(candidatos) == 1 else None


def _fps(ruta: Path, cfg) -> float:
    exe = tools.buscar("ffprobe", cfg, obligatorio=True)
    r = tools.ejecutar([exe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "default=nw=1:nk=1", str(ruta)], capturar=True, mostrar=False, comprobar=False)
    try:
        num, den = (r.stdout or "0/1").strip().split("/")
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _compatibles(video: Path, fuente: Path, cfg) -> bool:
    """Aviso si el vídeo y la fuente de audio no casan en duración o fps: el
    audio quedaría desincronizado (corte distinto, 23,976 vs 24 fps…)."""
    mv, mf = probe.analizar(video, cfg), probe.analizar(fuente, cfg)
    fv, ff = _fps(video, cfg), _fps(fuente, cfg) if mf.video else 0.0
    problemas = []
    if mv.duracion and mf.duracion and abs(mv.duracion - mf.duracion) > 1.0:
        problemas.append(f"duración {mv.duracion:.1f}s vs {mf.duracion:.1f}s (diferencia {abs(mv.duracion - mf.duracion):.1f}s)")
    if fv and ff and abs(fv - ff) > 0.01:
        problemas.append(f"fps {fv:.3f} vs {ff:.3f}")
    if not problemas:
        ui.ok(f"Sincronía: misma duración ({mv.duracion:.1f}s)" + (f" y fps ({fv:.3f})" if fv and ff else ""))
        return True
    ui.aviso("El vídeo y la fuente de audio NO casan: " + "; ".join(problemas))
    ui.aviso("El audio quedaría desincronizado (habría que ajustar retardo o velocidad antes de juntar).")
    return ui.preguntar_sn("¿Juntar de todas formas?", False)


def flujo_juntar(cfg) -> Optional[Path]:
    """Vídeo de un contenedor (p. ej. el 4K extranjero) + audios/subtítulos de
    otro mkv/mka (p. ej. tu 1080p ya preparado). Se puede arrastrar el fichero
    o la carpeta; con carpetas se emparejan por nombre (o el único que haya).
    Al terminar ofrece seguir con PREPARAR RELEASE sobre la carpeta de salida."""
    ui.titulo("JUNTAR — la IMAGEN de un mkv extranjero + los AUDIOS/SUBTÍTULOS de tu mkv preparado")
    ui.info("Sirve en los dos sentidos: 4K extranjero + tu 1080p preparado, o 1080p extranjero + tu 4K preparado.")
    print()
    origen_video = ui.preguntar_ruta("mkv EXTRANJERO (el que pone la imagen)", tipo="any")
    origen_audio = ui.preguntar_ruta("tu mkv PREPARADO (el que pone los audios y subtítulos en castellano)", tipo="any")
    salida = ui.preguntar_ruta("Carpeta de salida para el mkv nuevo (se crea si no existe)", debe_existir=False)
    salida.mkdir(parents=True, exist_ok=True)
    print()
    ui.info("El mkv nuevo llevará SIEMPRE: la imagen del extranjero + todos los audios y subtítulos de tu preparado.")
    extra = ui.preguntar_opcion("¿Y el audio V.O. y los subtítulos que trae el extranjero?", [
        ("si", "añadirlos también (si su V.O. es mejor: Atmos, TrueHD…)"),
        ("no", "ignorarlos: solo lo de mi mkv preparado"),
    ], defecto="si")
    conservar_audio = conservar_subs = (extra == "si")

    exts = {".mkv", ".mka", ".mp4"}
    candidatos = [origen_audio] if origen_audio.is_file() else sorted(
        f for f in origen_audio.rglob("*") if f.is_file() and f.suffix.lower() in exts
        and not any(p.lower() in ("temporal", "originals", "originales") for p in f.relative_to(origen_audio).parts[:-1]))
    videos = _videos_de(origen_video, cfg)
    if not videos:
        ui.error(f"No hay ningún vídeo en {origen_video}")
        return None
    if not candidatos:
        ui.error(f"No hay ningún mkv/mka en {origen_audio}")
        return None
    hechos = 0
    for v in videos:
        pareja = _pareja(v, origen_audio, candidatos)
        if pareja is None:
            ui.aviso(f"{v.name}: no hay fichero de audio emparejable, se salta.")
            continue
        destino = salida / (v.stem + ".mkv")
        if destino.exists() and destino.samefile(v):
            ui.error("La salida coincide con el vídeo de entrada; elige otra carpeta de salida.")
            continue
        if not _compatibles(v, pareja, cfg):
            continue
        plan = construir_plan(v, destino, cfg, [pareja], conservar_audio, conservar_subs)
        for pp in plan.pistas:
            pp.origen = "EXTRANJERO" if pp.fichero == 0 else "PREPARADO"
        ui.info("Revisa el plan: si hay pistas repetidas (p. ej. dos V.O. inglés), quita con 'x' la que no quieras.")
        mostrar_plan(plan, cfg)
        if not ui.preguntar_sn("¿Correcto?", True):
            editar_plan(plan, cfg)
        ejecutar_plan(plan, cfg)
        hechos += 1

    if hechos and ui.preguntar_sn("¿Seguir con PREPARAR RELEASE sobre la carpeta de salida?", True):
        from . import release
        release.flujo(cfg, salida)
    return salida
