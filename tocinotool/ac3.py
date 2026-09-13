"""AUDIO → AC3: extrae las pistas de audio elegidas, las codifica a AC3 con el
bitrate de la tabla de conversión y remuxea el mkv con los nuevos audios.

Equivale a la opción 1 del tociNoTool.bat, pero sin preguntar bitrates ni
códigos de idioma: se leen del fichero y de config/audio.yaml. Se decide una vez
con el primer fichero y se aplica al resto por idioma.
"""
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

from . import probe, tools, ui

if TYPE_CHECKING:
    from .workspace import ReleaseGroup


@dataclass
class Conversion:
    idioma: str          # canónico
    kbps: int            # bitrate AC3 destino
    copiar: bool = False # la pista ya es AC3 con ese bitrate → se copia sin recodificar


@dataclass
class FuenteAC3:
    """Una pista concreta elegida para generar el AC3 de un idioma."""
    ruta: Path
    pista: probe.Pista
    idioma: str
    kbps: int
    copiar: bool


def _sugerencias(medio: probe.Medio, cfg) -> List[Conversion]:
    res = []
    for a in medio.audios:
        idioma = cfg.canon_idioma(a.idioma)
        kbps = cfg.sugerir_bitrate_ac3(a.codec, a.kbps, a.canales)
        copiar = a.codec == "ac3" and a.kbps is not None and abs(a.kbps - kbps) <= 8
        res.append(Conversion(idioma=idioma, kbps=kbps, copiar=copiar))
    return res


def _mostrar_audios(medio: probe.Medio, cfg, sugerencias: List[Conversion]) -> None:
    filas = []
    for i, (a, s) in enumerate(zip(medio.audios, sugerencias), 1):
        filas.append([str(i), a.idioma, cfg.nombre_idioma(s.idioma, preguntar=False),
                      cfg.nombre_codec_audio(a.codec, a.perfil, preguntar=False),
                      cfg.etiqueta_canales(a.canales), a.kbps or "?", a.titulo,
                      f"{s.kbps} {'(copiar)' if s.copiar else ''}"])
    ui.tabla(["#", "código", "idioma", "codec", "canales", "kbps", "título", "→ AC3"], filas)


def _elegir(medio: probe.Medio, cfg, todas: bool = False) -> List[Conversion]:
    """Muestra las pistas con el bitrate AC3 propuesto por la tabla.
    `todas` (WEB-DL): se convierten todas sin preguntar. Si no: todas / elegir / ajustar bitrates."""
    sugerencias = _sugerencias(medio, cfg)
    ui.seccion(f"Pistas de audio de {medio.ruta.name}")
    _mostrar_audios(medio, cfg, sugerencias)
    seleccion = list(range(len(sugerencias)))
    if todas:
        ui.info("WEB-DL: se convierten todas las pistas con estos bitrates.")
    else:
        while True:
            r = ui.preguntar_opcion("Pistas a convertir", [
                ("todas", "todas, con los bitrates propuestos"),
                ("elegir", "elegir cuáles (números separados por comas)"),
                ("bitrate", "cambiar algún bitrate"),
            ], defecto="todas")
            if r == "todas":
                break
            if r == "elegir":
                opciones = [(str(i), f"{cfg.nombre_idioma(s.idioma, preguntar=False)} {cfg.nombre_codec_audio(a.codec, a.perfil, preguntar=False)} "
                             f"{cfg.etiqueta_canales(a.canales)} {a.kbps or '?'} kbps → AC3 {s.kbps}")
                            for i, (a, s) in enumerate(zip(medio.audios, sugerencias))]
                seleccion = [int(k) for k in ui.preguntar_multi("Pistas a convertir", opciones, marcadas=[str(i) for i in seleccion])]
                break
            for i in seleccion:
                sugerencias[i].kbps = ui.preguntar_entero(
                    f"Bitrate AC3 pista {i + 1} ({cfg.nombre_idioma(sugerencias[i].idioma, preguntar=False)})",
                    defecto=sugerencias[i].kbps, minimo=32, maximo=int(cfg["bitrates_ac3"].get("maximo", 640)))
            _mostrar_audios(medio, cfg, sugerencias)

    elegidas: List[Conversion] = []
    for i in seleccion:
        a, c = medio.audios[i], sugerencias[i]
        cfg.nombre_idioma(c.idioma)  # pregunta y guarda el nombre si el idioma es desconocido
        if c.idioma == "und":
            c.idioma = ui.preguntar_idioma(cfg, f"Pista {i + 1} sin idioma: ¿cuál es?")
        c.copiar = a.codec == "ac3" and a.kbps is not None and abs(a.kbps - c.kbps) <= 8
        elegidas.append(c)
    return elegidas


def _pista_por_idioma(medio: probe.Medio, idioma: str, cfg) -> Optional[probe.Pista]:
    for a in medio.audios:
        if cfg.canon_idioma(a.idioma) == idioma:
            return a
    return None


def _rango_calidad(pista: probe.Pista, cfg) -> int:
    """Menor es mejor, siguiendo la tabla de calidad común del config."""
    nombre = cfg.nombre_codec_audio(pista.codec, pista.perfil, preguntar=False).lower()
    if pista.atmos:
        nombre += " atmos"
    orden = [str(x).lower() for x in cfg.get("orden_codecs_audio", [])]
    return min((i for i, valor in enumerate(orden) if valor == nombre), default=len(orden))


def fuentes_grupo(grupo: "ReleaseGroup", cfg) -> List[FuenteAC3]:
    """Elige una fuente por idioma: AC3 válido primero; si no, la mejor pista.

    Sirve igual para vídeo con pistas internas que para vídeo elemental con
    audios externos. Evita convertir la primera pista encontrada cuando hay
    un TrueHD/DTS-HD mejor del mismo idioma.
    """
    candidatas: list[tuple[Path, probe.Pista, str]] = []
    for p in grupo.video.medio.audios:
        candidatas.append((grupo.video.ruta, p, cfg.canon_idioma(p.idioma)))
    for componente in grupo.audios:
        for p in componente.medio.audios:
            candidatas.append((componente.ruta, p, cfg.canon_idioma(p.idioma)))

    por_idioma: dict[str, list[tuple[Path, probe.Pista]]] = {}
    for ruta, pista, idioma in candidatas:
        if idioma == "und":
            grupo.incidencias.append(f"{ruta.name}: audio sin idioma; asígnalo antes de convertir")
            continue
        por_idioma.setdefault(idioma, []).append((ruta, pista))

    elegidas: List[FuenteAC3] = []
    for idioma, opciones in por_idioma.items():
        def clave(item: tuple[Path, probe.Pista]):
            _, p = item
            kbps = cfg.sugerir_bitrate_ac3(p.codec, p.kbps, p.canales)
            ac3_valido = p.codec == "ac3" and p.kbps is not None and abs(p.kbps - kbps) <= 8 and (p.canales or 0) <= 6
            return (0 if ac3_valido else 1, _rango_calidad(p, cfg), -(p.canales or 0), -(p.kbps or 0))
        ruta, pista = min(opciones, key=clave)
        kbps = cfg.sugerir_bitrate_ac3(pista.codec, pista.kbps, pista.canales)
        copiar = pista.codec == "ac3" and pista.kbps is not None and abs(pista.kbps - kbps) <= 8 and (pista.canales or 0) <= 6
        elegidas.append(FuenteAC3(ruta, pista, idioma, kbps, copiar))
    return elegidas


def _validar_ac3(ruta: Path, fuente: FuenteAC3, cfg) -> None:
    medio = probe.analizar(ruta, cfg)
    pista = medio.audios[0] if medio.audios else None
    if not pista or pista.codec != "ac3":
        raise RuntimeError(f"{ruta.name}: la salida no es AC3")
    if pista.kbps is None or abs(pista.kbps - fuente.kbps) > 8:
        raise RuntimeError(f"{ruta.name}: bitrate {pista.kbps or '?'} no coincide con AC3 {fuente.kbps}")
    if (fuente.pista.canales or 0) > 2 and pista.canales != 6:
        raise RuntimeError(f"{ruta.name}: se esperaban 6 canales y se obtuvieron {pista.canales}")
    if fuente.ruta != ruta and fuente.pista and medio.duracion and fuente.ruta.exists():
        origen = probe.analizar(fuente.ruta, cfg).duracion
        if origen and abs(origen - medio.duracion) > 2.0:
            raise RuntimeError(f"{ruta.name}: duración {medio.duracion:.1f}s distinta del origen ({origen:.1f}s)")


def convertir_fuente(fuente: FuenteAC3, cfg, destino_dir: Path, prefijo: str) -> Path:
    """Genera un AC3 validado desde una pista interna o un fichero externo.

    Para 7.1 con layout conocido aplica una matriz explícita que mezcla BL/BR
    en SL/SR. Un layout 7.1 desconocido se detiene antes de hacer un downmix
    destructivo.
    """
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"{prefijo}.[{fuente.idioma}].ac3"
    if destino.exists():
        try:
            _validar_ac3(destino, fuente, cfg)
            ui.info(f"{destino.name}: AC3 temporal válido; se reutiliza.")
            return destino
        except Exception as exc:  # el temporal puede ser una conversión interrumpida
            ui.aviso(f"{destino.name}: no se puede reutilizar ({exc}); se regenera.")
    ffmpeg = tools.buscar("ffmpeg", cfg, obligatorio=True)
    cmd = [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "warning", "-stats", "-i", str(fuente.ruta),
           "-map", f"0:{fuente.pista.indice}", "-vn", "-sn", "-dn"]
    if fuente.copiar:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "ac3", "-center_mixlev", "0.707", "-b:a", f"{fuente.kbps}k"]
        if (fuente.pista.canales or 0) > 6:
            layout = (fuente.pista.layout or "").lower()
            if fuente.pista.canales != 8 or layout not in ("7.1", "7.1(side)"):
                raise RuntimeError(f"{fuente.ruta.name}: {fuente.pista.canales} canales con layout '{layout or '?'}'; no se hará downmix automático")
            # En FFmpeg el layout de salida 5.1 nombra los surrounds como
            # BL/BR; SL/SR solo existen en la entrada 7.1.
            cmd += ["-af", "pan=5.1|FL=FL|FR=FR|FC=FC|LFE=LFE|BL=0.707*BL+0.707*SL|BR=0.707*BR+0.707*SR", "-ac", "6"]
    cmd.append(str(destino))
    tools.ejecutar(cmd, mostrar=False)
    _validar_ac3(destino, fuente, cfg)
    return destino


def convertir_grupo(grupo: "ReleaseGroup", cfg, copiar_ac3_existente: bool = True) -> List[Path]:
    """Genera como máximo un AC3 por idioma para un grupo de release.

    En WEB-DL/Blu-ray un AC3 válido ya se conserva tal cual; en Encode se
    vuelve a materializar como fichero suelto porque la pista interna original
    se excluye del MKV final.
    """
    fuentes = fuentes_grupo(grupo, cfg)
    if grupo.incidencias:
        return []
    temporal = grupo.video.ruta.parent / "temporal"
    return [convertir_fuente(f, cfg, temporal, grupo.video.ruta.stem) for f in fuentes
            if copiar_ac3_existente or not f.copiar]


def procesar_grupos(cfg, grupos: list["ReleaseGroup"], perfil: str, revisar_plan: bool = True) -> List[Path]:
    """Motor común de audio+automux para el flujo completo y la utilidad AC3."""
    from . import mux
    conservar = perfil != "encode"
    planes = []
    for grupo in grupos:
        ac3s = convertir_grupo(grupo, cfg, copiar_ac3_existente=not conservar)
        if grupo.incidencias:
            raise RuntimeError(f"{grupo.clave}: " + "; ".join(grupo.incidencias))
        sueltos = [c.ruta for c in grupo.subtitulos]
        if conservar:
            sueltos.extend(c.ruta for c in grupo.audios)
        sueltos.extend(ac3s)
        plan = mux.construir_plan(grupo.video.ruta, grupo.video.ruta.parent / (grupo.video.ruta.stem + ".mkv"),
                                  cfg, sueltos, conservar_audio=conservar, conservar_subs=True,
                                  perfil_subs=perfil)
        # En Encode los audios externos originales tampoco entran al MKV; se
        # conservan junto al resto de fuentes, nunca al lado del release final.
        if not conservar:
            plan.extra_apartar.extend(c.ruta for c in grupo.audios)
        planes.append(plan)
    if revisar_plan:
        for plan in planes:
            mux.mostrar_plan(plan, cfg)
        if not ui.preguntar_sn("¿Correcto?", True):
            for plan in planes:
                mux.editar_plan(plan, cfg)
    salidas = []
    for i, plan in enumerate(planes, 1):
        salidas.append(mux.ejecutar_plan_con_originales(plan, cfg, f"[{i}/{len(planes)}] "))
    return salidas


def convertir(video: Path, conversiones: List[Conversion], cfg, salida_dir: Path) -> Dict[str, Path]:
    """Genera un .ac3 por conversión. Devuelve {idioma: ruta_ac3}."""
    medio = probe.analizar(video, cfg)
    res: Dict[str, Path] = {}
    for c in conversiones:
        pista = _pista_por_idioma(medio, c.idioma, cfg)
        if pista is None and len(medio.audios) == 1 and len(conversiones) == 1:
            pista = medio.audios[0]  # un solo audio: se usa aunque el idioma no coincida
        if pista is None:
            ui.aviso(f"{video.name}: no hay pista '{c.idioma}', se salta.")
            continue
        fuente = FuenteAC3(video, pista, c.idioma, c.kbps, c.copiar)
        res[c.idioma] = convertir_fuente(fuente, cfg, salida_dir, video.stem)
    return res


def remuxear(video: Path, ac3s: Dict[str, Path], conversiones: List[Conversion], cfg,
             salida: Path, modo: str) -> None:
    """modo: 'sustituir' (quita solo las pistas convertidas), 'todas' (mantiene todos
    los audios originales) o 'solo_ac3' (elimina todos los audios originales)."""
    from . import mux  # ids de pista de mkvmerge
    mkvmerge = tools.buscar("mkvmerge", cfg, obligatorio=True)
    pistas = mux.pistas_contenedor(video, cfg)
    audios = [(tid, p) for tid, p in pistas if p.tipo == "audio"]
    v = next((tid for tid, p in pistas if p.tipo == "video"), 0)
    cmd = [mkvmerge, "-o", str(salida)]
    if modo == "solo_ac3":
        cmd.append("--no-audio")
    elif modo == "sustituir":
        convertidos = {cfg.canon_idioma(c.idioma) for c in conversiones if c.idioma in ac3s}
        mantener = [tid for tid, a in audios if cfg.canon_idioma(a.idioma) not in convertidos]
        if len(audios) == 1 and len(conversiones) == 1:
            mantener = []  # un solo audio y se ha convertido: fuera
        cmd += ["--audio-tracks", ",".join(map(str, mantener))] if mantener else ["--no-audio"]
    cmd += ["--language", f"{v}:und", "--default-track", f"{v}:yes", str(video)]
    primero = True
    for c in conversiones:
        ruta = ac3s.get(c.idioma)
        if not ruta:
            continue
        a = probe.analizar(ruta, cfg).audios[0]
        nombre = cfg["plantillas"]["pista_audio"].format(
            lang=cfg.nombre_idioma(c.idioma), codec=cfg.nombre_codec_audio("ac3"),
            channels=cfg.etiqueta_canales(a.canales), bitrate=a.kbps or c.kbps)
        cmd += ["--language", f"0:{c.idioma}", "--track-name", f"0:{nombre}",
                "--default-track", f"0:{'yes' if primero else 'no'}", str(ruta)]
        primero = False
    tools.ejecutar_mkvmerge(cmd)


def procesar_carpeta(cfg, carpeta: Path, preguntar_borrado: bool = True, modo: Optional[str] = None,
                     todas: bool = False, solo: Optional[Path] = None, revisar_plan: bool = True) -> List[Path]:
    """Convierte los audios a AC3 y monta el mkv final con el MUXER en una sola
    pasada: el vídeo original (con sus audios según `modo`) + los .ac3 + los
    sueltos que haya. Así los subtítulos que mkvmerge no lee (mov_text de mp4)
    se extraen y no se pierden. Los originales quedan en originales/ (no se borran)."""
    from . import mux
    videos = [solo] if solo else probe.listar_videos(carpeta, cfg, recursivo=True)
    if not videos:
        ui.error("No hay vídeos en la carpeta.")
        return []
    ui.info(f"{len(videos)} vídeo(s) encontrados. Se configura con el primero y se aplica a todos por idioma.")

    primero = probe.analizar(videos[0], cfg)
    if not primero.audios:
        ui.error(f"{videos[0].name} no tiene audio.")
        return []
    conversiones = _elegir(primero, cfg, todas=todas)
    if not conversiones:
        return []
    if modo is None:
        modo = ui.preguntar_opcion("¿Mantener los audios originales junto a los AC3?", [
            ("todas", "sí: originales + AC3 (WEB-DL y rips)"),
            ("solo_ac3", "no: solo los AC3 (encodes: una pista por idioma)"),
            ("sustituir", "quitar solo las pistas convertidas y mantener las demás"),
        ], defecto="todas")

    # 1) los .ac3 de cada vídeo → temporal/ junto al fichero
    ui.seccion(f"Convirtiendo {len(videos)} fichero(s)")
    trabajos = []   # (video, [ac3...])
    for i, video in enumerate(videos, 1):
        print(f"   [{i}/{len(videos)}] {video.name}")
        temporal = video.parent / "temporal"
        temporal.mkdir(exist_ok=True)
        ac3s = convertir(video, conversiones, cfg, temporal)
        if ac3s:
            trabajos.append((video, list(ac3s.values())))

    # 2) el mkv final con el muxer: vídeo + sus sueltos + los .ac3
    planes = []
    for video, ac3s in trabajos:
        sueltos = mux.buscar_sueltos(video, video.parent, cfg) + ac3s
        excluir = [c.idioma for c in conversiones] if modo == "sustituir" else ()
        planes.append(mux.construir_plan(video, video.parent / (video.stem + ".mkv"), cfg, sueltos,
                                         conservar_audio=(modo != "solo_ac3"), conservar_subs=True,
                                         excluir_audio_idiomas=excluir))
    if not planes:
        return []
    if revisar_plan:
        mux.mostrar_plan(planes[0], cfg)
        if not ui.preguntar_sn("¿Correcto?", True):
            mux.editar_plan(planes[0], cfg)
        if len(planes) > 1 and not ui.preguntar_sn(f"Hay {len(planes)} vídeos. ¿Aplicar el mismo criterio sin revisar uno a uno?", True):
            for plan in planes[1:]:
                mux.mostrar_plan(plan, cfg)
                if not ui.preguntar_sn("¿Correcto?", True):
                    mux.editar_plan(plan, cfg)
    salidas = []
    ui.seccion(f"Muxeando {len(planes)} fichero(s)")
    for i, plan in enumerate(planes, 1):
        salidas.append(mux.ejecutar_plan_con_originales(plan, cfg, f"[{i}/{len(planes)}] "))
    ui.info("Los ficheros de origen se conservan en originales/ (bórralos tú cuando hayas comprobado el release).")
    return salidas


def flujo(cfg, carpeta: Optional[Path] = None) -> Optional[Path]:
    ui.titulo("AUDIO → AC3")
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "Qué convertir", admitir_fichero=True)
    solo = carpeta if carpeta.is_file() else None
    carpeta = carpeta.parent if carpeta.is_file() else carpeta
    from . import workspace
    perfil = ui.preguntar_opcion("Perfil de destino", [
        ("webdl", "WEB-DL: conservar originales + AC3"),
        ("encode", "Encode / MicroHD: una pista AC3 por idioma"),
        ("bluray", "Blu-ray Rip / Remux: originales + AC3 compatible"),
        ("manual", "Manual / avanzado: conservar originales + AC3"),
    ], defecto="manual")
    ws = workspace.analizar(carpeta, cfg)
    if solo:
        ws.grupos = [g for g in ws.grupos if g.video.ruta == solo]
    workspace.mostrar(ws, cfg)
    if not ws.valido:
        ui.aviso("No se convierte nada mientras haya componentes ambiguos o desincronizados.")
        return carpeta
    procesar_grupos(cfg, ws.grupos, perfil)
    return carpeta
