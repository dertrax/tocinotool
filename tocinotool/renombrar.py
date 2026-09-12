"""Renombrado con FileBot a nomenclatura de release.

Por cada entrada de la carpeta de trabajo (un .mkv suelto o una carpeta de
temporada) pregunta fuente (web/bluray), plataforma, serie/película y tipo,
construye el formato de FileBot con las plantillas de config/renombrado.yaml, lo prueba
en modo `test` y, cuando confirmas, mueve/renombra de verdad.

Diferencias con dogtool: sin opción "internacional" (DxV); el grupo sale de
config (serie → TSeD, película → TMd, 4K → T4Kd) y se puede cambiar a mano.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import tools, ui


@dataclass
class Opciones:
    serie: bool
    web: bool
    vod: str = ""              # tag de plataforma (NF, AMZN…) si web
    tipo: str = "web"          # clave de renombrado.tipos.*
    temporada_completa: bool = False
    grupo: str = ""
    db: str = ""
    idioma: str = "es"
    id_elem: str = ""          # id de TheTVDB/TMDB si hay ambigüedad
    temporada: int = 0         # limitar la búsqueda a esta temporada (anime con numeración continua)


def _preguntar_opciones(cfg, entrada: Path, previas: Optional[Opciones]) -> Opciones:
    """Las mismas tres decisiones que en PREPARAR RELEASE, con selectores y la
    propuesta (detectada por el nombre) ya marcada: origen, contenido y plataforma."""
    origen = ui.preguntar_opcion("Origen del vídeo", [
        ("webdl", "WEB-DL"),
        ("bluray", "Blu-ray Rip / Remux"),
        ("encode", "encode (mHD, x264/x265…)"),
    ], defecto="webdl" if (previas.web if previas else True) else "bluray")
    web = origen == "webdl"
    if previas and previas.temporada_completa:
        d = "temporada"
    elif previas and previas.serie:
        d = "capitulo"
    else:
        d = "pelicula"
    contenido = ui.preguntar_opcion("Contenido", [
        ("pelicula", "película"),
        ("capitulo", "capítulo(s) suelto(s) de serie"),
        ("temporada", "temporada(s) completa(s): una carpeta por temporada"),
    ], defecto=d)
    vod = preguntar_plataforma(cfg, previas.vod if previas else "") if web else ""
    r = cfg["renombrado"]
    op = Opciones(serie=contenido != "pelicula", web=web, vod=vod, temporada_completa=contenido == "temporada",
                  db=r["db_serie"] if contenido != "pelicula" else r["db_pelicula"], idioma=str(r.get("idioma", "es")))
    return _completar_opciones(cfg, op, [entrada])


def preguntar_plataforma(cfg, defecto: str = "") -> str:
    """Listado numerado de plataformas del config; siempre se pregunta, nunca se deduce."""
    tags = [str(t) for t in cfg["plataformas"]]
    opciones = [(str(i), f"{t:<8} {cfg['plataformas'][t]}") for i, t in enumerate(tags, 1)] + [("+", "otra (se añade al config)")]
    d = str(tags.index(defecto) + 1) if defecto in tags else None
    r = ui.preguntar_opcion("Plataforma (número)", opciones, defecto=d)
    if r == "+":
        tag = ui.preguntar("Tag para el nombre del fichero (ej. NF)", obligatorio=True)
        nombre = ui.preguntar("Nombre completo (ej. Netflix)", obligatorio=True)
        cfg.anadir_plataforma(tag, nombre)
        ui.ok(f"Añadida: {tag} = {nombre}")
        return tag
    return tags[int(r) - 1]


def construir_formato(cfg, op: Opciones, entrada: Path) -> str:
    r = cfg["renombrado"]
    clave = ("serie" if op.serie else "pelicula") + ("_web" if op.web else "_bluray")
    fuente = str(r["tipos"][clave][op.tipo])
    marcadores = {
        "@bits@": r["expr_bits"], "@hdr@": r["expr_hdr"],
        "@audio@": r["expr_audio"], "@video@": r["expr_video"],
        "@vod@": op.vod, "@grupo@": op.grupo,
    }

    def rellenar(plantilla: str) -> str:
        plantilla = plantilla.replace("@fuente@", fuente)
        for k, v in marcadores.items():
            plantilla = plantilla.replace(k, str(v))
        return plantilla

    formato = rellenar(str(r["plantilla_" + clave]))
    if op.serie and op.temporada_completa:
        # la carpeta de temporada se crea junto a la entrada; si la carpeta de
        # trabajo ya es una "Sxx", un nivel más arriba (comportamiento de dogtool)
        base = entrada.parent
        if re.search(r"\.S\d{2}\.", base.name):  # la carpeta de trabajo ya es una temporada renombrada
            base = base.parent
        carpeta = rellenar(str(r["carpeta_temporada_" + ("web" if op.web else "bluray")]))
        formato = str(base).replace("\\", "/") + "/" + carpeta + "/" + formato
    return formato


def comando_filebot(cfg, op: Opciones, entradas: List[Path], formato: str, accion: str) -> List[str]:
    exe = tools.buscar("filebot", cfg, obligatorio=True)
    cmd = [exe, "-rename", "-r", *[str(e) for e in entradas], "--db", op.db, "--format", formato,
           "-non-strict", "--lang", op.idioma, "--action", accion]
    if op.id_elem:
        cmd += ["--q", op.id_elem]
    if op.serie and op.temporada:
        # Anime (Crunchyroll…): los ficheros van S02E25…S02E48 (numeración continua)
        # y FileBot los reparte por temporadas que no son. Limitando la búsqueda a
        # la temporada, FileBot casa por número absoluto: S02E25 → S02E01.
        cmd += ["--filter", f"s == {op.temporada}"]
    return cmd


_RE_EPISODIO = re.compile(r"S\d{1,2}E\d{1,3}|\b\d{1,2}x\d{2}\b", re.IGNORECASE)
_RE_TEMPORADA_NOMBRE = re.compile(r"S(\d{1,2})E\d{1,3}|\b(\d{1,2})x\d{2}\b", re.IGNORECASE)


def _temporada_nombre(nombre: str) -> int:
    m = _RE_TEMPORADA_NOMBRE.search(nombre)
    return int(m.group(1) or m.group(2)) if m else 0


def _mkvs(entradas: List[Path]) -> List[Path]:
    return [f for e in entradas for f in ([e] if e.is_file() else sorted(e.rglob("*.mkv")))]


def temporadas_de_nombres(entradas: List[Path]) -> Dict[int, List[Path]]:
    """{temporada: [mkv]} según el SxxExx de cada nombre (S02E25 → 2).
    Los mkv sin temporada en el nombre no entran."""
    grupos: Dict[int, List[Path]] = {}
    for f in _mkvs(entradas):
        t = _temporada_nombre(f.name)
        if t:
            grupos.setdefault(t, []).append(f)
    return grupos


def temporada_de_nombres(entradas: List[Path]) -> int:
    """Temporada única que dicen los nombres; 0 si no hay o si hay varias."""
    grupos = temporadas_de_nombres(entradas)
    return next(iter(grupos)) if len(grupos) == 1 else 0


def _desajustes_temporada(resultados: List[tuple]) -> List[tuple]:
    """Ficheros cuyo nombre dice una temporada y FileBot los ha puesto en otra:
    numeración continua de anime (Crunchyroll S02E25 → FileBot S01E01)."""
    malos = []
    for origen, destino in resultados:
        t_origen, t_destino = _temporada_nombre(origen), _temporada_nombre(Path(destino).name)
        if t_origen and t_destino and t_origen != t_destino:
            malos.append((origen, destino))
    return malos


_RE_TEMPORADA_DIR = re.compile(r"\bS\d{1,2}\b|temporada|season", re.IGNORECASE)
_RE_WEB = re.compile(r"WEB-?DL|WEB-?Rip|\bWEB\b", re.IGNORECASE)
_RE_DISCO = re.compile(r"BluRay|Blu-Ray|BDRip|BDRemux|Remux|UHDRip|\bBD\b", re.IGNORECASE)


def detectar(cfg, entradas: List[Path]) -> Opciones:
    """Propuesta automática a partir de los nombres de fichero: WEB/BluRay,
    plataforma, serie (capítulo suelto o temporada) o película."""
    nombres = []
    for e in entradas:
        nombres.append(e.name)
        if e.is_dir():
            nombres += [f.name for f in e.rglob("*.mkv")]
    texto = " ".join(nombres)
    episodios = sum(1 for n in nombres if _RE_EPISODIO.search(n) and n.lower().endswith(".mkv"))
    dirs_temporada = [e for e in entradas if e.is_dir() and (_RE_TEMPORADA_DIR.search(e.name) or any(e.rglob("*.mkv")))]
    serie = episodios > 0 or bool(dirs_temporada)
    temporada = serie and (episodios > 1 or bool(dirs_temporada))
    web = True if _RE_WEB.search(texto) else False if _RE_DISCO.search(texto) else True
    r = cfg["renombrado"]
    return Opciones(serie=serie, web=web, vod="", tipo="web" if web else "", temporada_completa=temporada,
                    db=r["db_serie"] if serie else r["db_pelicula"], idioma=str(r.get("idioma", "es")))


def entradas_carpeta(carpeta: Path) -> List[Path]:
    """mkv sueltos y carpetas (de temporada) de la carpeta de trabajo, sin las auxiliares."""
    return sorted(p for p in carpeta.iterdir()
                  if (p.is_dir() and p.name.lower() not in ("temporal", "originals", "originales", "capturas"))
                  or p.suffix.lower() == ".mkv")


def _completar_opciones(cfg, op: Opciones, entradas: List[Path]) -> Opciones:
    """Con las decisiones ya tomadas al principio del flujo (WEB/Blu-ray/Encode,
    serie/película, plataforma) solo falta el tipo de contenido y el grupo."""
    from . import probe
    r = cfg["renombrado"]
    clave = ("serie" if op.serie else "pelicula") + ("_web" if op.web else "_bluray")
    tipos = r["tipos"][clave]
    if op.web:
        # WEB-DL: web o web4k según la resolución del primer vídeo
        primero = next((f for e in entradas for f in ([e] if e.is_file() else sorted(e.rglob("*.mkv")))), None)
        alto = 0
        if primero is not None and primero.exists():
            v = probe.analizar(primero, cfg).video
            alto = (v.alto if v else 0) or 0
        op.tipo = "web4k" if alto >= 1600 and "web4k" in tipos else "web"
    else:
        op.tipo = ui.preguntar_opcion("Tipo de contenido", [(k, v) for k, v in tipos.items()],
                                      defecto=op.tipo if op.tipo in tipos else list(tipos)[0])
    # el grupo sale de la regla (config/renombrado.yaml → grupos), no se pregunta
    if op.serie:
        op.grupo, motivo = r["grupos"]["serie"], "serie"
    elif op.tipo in [str(x) for x in r["tipos_4k"]]:
        op.grupo, motivo = r["grupos"]["pelicula_4k"], "película 4K"
    else:
        op.grupo, motivo = r["grupos"]["pelicula"], "película"
    fuente_txt = str(tipos[op.tipo]).replace("@bits@", "").replace("@hdr@", "").replace("{vf}.", "")
    ui.info(f"Tipo: {fuente_txt} · grupo: {op.grupo} ({motivo}) · base de datos: {r['db_serie'] if op.serie else r['db_pelicula']}")
    op.db = r["db_serie"] if op.serie else r["db_pelicula"]
    op.idioma = op.idioma or str(r.get("idioma", "es"))
    return op


def renombrar_carpeta(cfg, carpeta: Path, previas: Optional[Opciones] = None,
                      fijas: Optional[Opciones] = None) -> Optional[Opciones]:
    """`carpeta` puede ser una carpeta (se renombra todo su contenido) o un mkv suelto."""
    """Una sola pasada de FileBot sobre todo el contenido de la carpeta: las
    opciones se preguntan una vez, se prueba (test) y, al confirmar, se mueve.
    Para temporadas completas FileBot crea la carpeta Serie.S01.… dentro de la
    carpeta de trabajo y mete ahí los episodios."""
    entradas = [carpeta] if carpeta.is_file() else entradas_carpeta(carpeta)
    if not entradas:
        ui.error("Nada que renombrar.")
        return previas
    ui.info(f"{sum(1 for e in entradas if e.is_dir())} carpeta(s) y {sum(1 for e in entradas if e.is_file())} mkv a renombrar")
    referencia = entradas[0]
    if fijas is not None:
        op = _completar_opciones(cfg, fijas, entradas)
        formato = construir_formato(cfg, op, referencia)
        if tools.DETALLADO:
            print(ui.gris("   formato: " + formato))
        return _probar_y_mover(cfg, op, entradas, referencia, formato)
    if previas is None:
        previas = detectar(cfg, entradas)
        ui.info("Detectado por el nombre: " + ("WEB" if previas.web else "BluRay") + " · " + ("temporada completa" if previas.temporada_completa else "serie (capítulo)" if previas.serie else "película")
                + "  (confirma o corrige)")
    op = _preguntar_opciones(cfg, referencia, previas)
    formato = construir_formato(cfg, op, referencia)
    if tools.DETALLADO:
        print(ui.gris("   formato: " + formato))
    return _probar_y_mover(cfg, op, entradas, referencia, formato)


_RE_RESULTADO = re.compile(r"^\[(TEST|MOVE|RENAME|COPY)\] from \[(.*)\] to \[(.*)\]\s*$", re.IGNORECASE)


def _ejecutar_filebot(cmd: List[str]) -> int:
    """Ejecuta FileBot mostrando solo lo útil: cada 'origen → destino' y los
    errores. Devuelve cuántos ficheros ha procesado (0 = no ha encontrado nada)."""
    n, resultados = _ejecutar_filebot_detalle(cmd)
    _mostrar_resultados(resultados)
    return n


def _ejecutar_filebot_detalle(cmd: List[str]) -> tuple:
    """(nº procesados, [(nombre origen, destino relativo)]) sin mostrar nada salvo errores."""
    # FileBot para Windows escribe su salida de consola en cp1252. Sin indicar
    # esta codificación, las tildes de las rutas se reemplazan por � al mostrar
    # la prueba, aunque el nombre que FileBot aplica sea correcto.
    codificacion = "cp1252" if tools.ES_WINDOWS else "utf-8"
    r = tools.ejecutar(cmd, capturar=True, comprobar=False, codificacion=codificacion)
    salida = (r.stdout or "") + (r.stderr or "")
    resultados = []
    for linea in salida.splitlines():
        m = _RE_RESULTADO.match(linea.strip())
        if m:
            origen, destino = Path(m.group(2)), Path(m.group(3))
            try:
                mostrado = destino.relative_to(origen.parent)   # incluye la carpeta de temporada si la crea
            except ValueError:
                mostrado = destino.name
            resultados.append((origen.name, str(mostrado)))
        elif any(x in linea for x in ("License", "Failure", "Exception", "No match", "Failed", "Error")):
            ui.aviso(linea.strip())
    if tools.DETALLADO:
        print(ui.gris(salida))
    return len(resultados), resultados


def _mostrar_resultados(resultados: List[tuple]) -> None:
    """Hasta tres: todos. Más: cantidad, primero y rango de episodios (por temporada)."""
    if tools.DETALLADO:
        return
    if len(resultados) <= 3:
        for origen, destino in resultados:
            print(f"   {origen}")
            print(f"     → {destino}")
        return
    ui.info(f"{len(resultados)} archivos detectados.")
    ui.info("Primer resultado:")
    print(f"     {resultados[0][0]}")
    print(f"       → {resultados[0][1]}")
    episodios = [m.group(0).upper() for m in (_RE_EPISODIO.search(Path(d).name) for _, d in resultados) if m]
    if episodios:
        por_temporada: Dict[int, List[str]] = {}
        for e in episodios:
            por_temporada.setdefault(_temporada_nombre(e), []).append(e)
        rangos = [f"{v[0]} → {v[-1]}" for _, v in sorted(por_temporada.items())]
        ui.info("Rango detectado: " + " · ".join(rangos))
    ui.info("Activa 'mostrar comandos técnicos' si necesitas ver el detalle completo.")


def _probar(cfg, op: Opciones, trabajos: List[tuple], formato: str, accion: str) -> tuple:
    """Ejecuta FileBot una vez por trabajo (entradas, temporada) y junta los resultados."""
    total, resultados = 0, []
    for entradas, temporada in trabajos:
        op.temporada = temporada
        n, r = _ejecutar_filebot_detalle(comando_filebot(cfg, op, entradas, formato, accion))
        total += n
        resultados += r
    return total, resultados


def _probar_y_mover(cfg, op: Opciones, entradas: List[Path], referencia: Path, formato: str) -> Optional[Opciones]:
    # Cada trabajo es (entradas, temporada a la que se limita FileBot). Lo normal
    # es uno solo sin límite; el anime con numeración continua los separa por temporada.
    trabajos: List[tuple] = [(entradas, op.temporada)]
    corregido = False
    while True:
        n, resultados = _probar(cfg, op, trabajos, formato, "test")
        # Anime con numeración continua (Crunchyroll: S02E25…S02E48): el nombre dice
        # una temporada y FileBot lo pone en otra. Se detecta por fichero, se separan
        # las temporadas y se repite la prueba limitando cada una; el usuario solo confirma.
        if op.serie and not corregido and _desajustes_temporada(resultados):
            grupos = temporadas_de_nombres(entradas)
            if grupos:
                corregido = True
                trabajos = [(ficheros, t) for t, ficheros in sorted(grupos.items())]
                temporadas = ", ".join(f"S{t:02d}" for t in sorted(grupos))
                ui.aviso(f"FileBot ha cambiado de temporada capítulos que por nombre son de {temporadas}: "
                         "numeración continua (típica de anime). Se repite limitando a esa(s) temporada(s).")
                continue
        _mostrar_resultados(resultados)
        if n == 0:
            ui.aviso("FileBot no ha encontrado coincidencia (o ha fallado).")
        if ui.preguntar_sn("¿El resultado es correcto?", n > 0):
            break
        accion = ui.preguntar_opcion("¿Qué probamos?", [
            ("id", "indicar el id de TheTVDB/TheMovieDB"),
            ("temp", "limitar a una temporada (anime con numeración continua: S02E25 → S02E01)"),
            ("en", "buscar en inglés" if op.idioma != "en" else "buscar en español"),
            ("db", "cambiar base de datos (TheTVDB ↔ TheMovieDB::TV)"),
            ("op", "cambiar las opciones (fuente, tipo, grupo…)"),
            ("x", "no renombrar"),
        ], defecto="id")
        if accion == "id":
            op.id_elem = ui.preguntar("Id", obligatorio=True)
        elif accion == "temp":
            t = ui.preguntar_entero("Temporada real de estos capítulos",
                                    defecto=temporada_de_nombres(entradas) or None, minimo=0, maximo=99)
            trabajos, corregido = [(entradas, t)], True
        elif accion == "en":
            op.idioma = "en" if op.idioma != "en" else "es"
        elif accion == "db":
            op.db = "TheMovieDB::TV" if op.db == "TheTVDB" else "TheTVDB"
        elif accion == "op":
            id_elem = op.id_elem
            op = _preguntar_opciones(cfg, referencia, op)
            op.id_elem = id_elem
            formato = construir_formato(cfg, op, referencia)
        else:
            return op

    _, hechos = _probar(cfg, op, trabajos, formato, "move")
    _mostrar_resultados(hechos)
    for e in entradas:
        if e.is_dir() and e.exists() and not any(e.iterdir()):
            e.rmdir()
    ui.ok("Renombrado.")
    return op


def flujo(cfg, carpeta: Optional[Path] = None) -> Optional[Path]:
    ui.titulo("RENOMBRAR con FileBot")
    from . import asistente
    if not tools.buscar("filebot", cfg):
        ui.error("FileBot no está instalado. Ejecuta el Asistente de instalación del launcher.")
        ui.info("Puedes configurarlo más adelante cuando tengas licencia.")
        ui.info(asistente.nota_licencia_filebot())
        return None
    estado, detalle = asistente.estado_filebot(cfg)
    if estado != asistente.FILEBOT_CON_LICENCIA:
        ui.error(detalle + ". El renombrado automático requiere una licencia válida.")
        ui.info("Vuelve a ejecutar el Asistente de instalación para activar o completar FileBot.")
        ui.info(asistente.nota_licencia_filebot())
        return None
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "Qué renombrar", admitir_fichero=True)
    renombrar_carpeta(cfg, carpeta)
    return carpeta.parent if carpeta.is_file() else carpeta
