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
from typing import List, Optional

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
    return cmd


_RE_EPISODIO = re.compile(r"S\d{1,2}E\d{1,3}|\b\d{1,2}x\d{2}\b", re.IGNORECASE)
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
    # FileBot para Windows escribe su salida de consola en cp1252. Sin indicar
    # esta codificación, las tildes de las rutas se reemplazan por � al mostrar
    # la prueba, aunque el nombre que FileBot aplica sea correcto.
    codificacion = "cp1252" if tools.ES_WINDOWS else "utf-8"
    r = tools.ejecutar(cmd, capturar=True, comprobar=False, codificacion=codificacion)
    salida = (r.stdout or "") + (r.stderr or "")
    procesados = 0
    resultados = []
    episodios = []
    for linea in salida.splitlines():
        m = _RE_RESULTADO.match(linea.strip())
        if m:
            procesados += 1
            origen, destino = Path(m.group(2)), Path(m.group(3))
            try:
                mostrado = destino.relative_to(origen.parent)   # incluye la carpeta de temporada si la crea
            except ValueError:
                mostrado = destino.name
            resultados.append((origen.name, str(mostrado)))
            ep = _RE_EPISODIO.search(destino.name)
            if ep:
                episodios.append(ep.group(0).upper())
        elif any(x in linea for x in ("License", "Failure", "Exception", "No match", "Failed", "Error")):
            ui.aviso(linea.strip())
    if tools.DETALLADO:
        print(ui.gris(salida))
    elif procesados <= 3:
        for origen, destino in resultados:
            print(f"   {origen}")
            print(f"     → {destino}")
    elif resultados:
        ui.info(f"{procesados} archivos detectados.")
        ui.info("Primer resultado:")
        print(f"     {resultados[0][0]}")
        print(f"       → {resultados[0][1]}")
        if episodios:
            ui.info(f"Rango detectado: {episodios[0]} → {episodios[-1]}")
        ui.info("Activa 'mostrar comandos técnicos' si necesitas ver el detalle completo.")
    return procesados


def _probar_y_mover(cfg, op: Opciones, entradas: List[Path], referencia: Path, formato: str) -> Optional[Opciones]:
    while True:
        n = _ejecutar_filebot(comando_filebot(cfg, op, entradas, formato, "test"))
        if n == 0:
            ui.aviso("FileBot no ha encontrado coincidencia (o ha fallado).")
        if ui.preguntar_sn("¿El resultado es correcto?", n > 0):
            break
        accion = ui.preguntar_opcion("¿Qué probamos?", [
            ("id", "indicar el id de TheTVDB/TheMovieDB"),
            ("en", "buscar en inglés" if op.idioma != "en" else "buscar en español"),
            ("db", "cambiar base de datos (TheTVDB ↔ TheMovieDB::TV)"),
            ("op", "cambiar las opciones (fuente, tipo, grupo…)"),
            ("x", "no renombrar"),
        ], defecto="id")
        if accion == "id":
            op.id_elem = ui.preguntar("Id", obligatorio=True)
        elif accion == "en":
            op.idioma = "en" if op.idioma != "en" else "es"
        elif accion == "db":
            op.db = "TheMovieDB::TV" if op.db == "TheTVDB" else "TheTVDB"
        elif accion == "op":
            op = _preguntar_opciones(cfg, referencia, op)
            formato = construir_formato(cfg, op, referencia)
        else:
            return op

    _ejecutar_filebot(comando_filebot(cfg, op, entradas, formato, "move"))
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
