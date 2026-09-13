"""Subtítulos: limpieza, conversión a srt y detección de idioma por el texto.

Casos que resuelve (vistos con descargas de Crunchyroll):
  * srt con etiquetas de estilo ASS dentro ({\\b1\\bord1\\an2\\fn…}): se limpian
    (la cursiva \\i1/\\i0 se conserva como <i></i>, \\N → salto de línea).
  * .ass / .ssa sueltos: se conservan, se convierten a srt limpio y, si
    contienen carteles/textos posicionados, se generan ASS y SRT forzados.
  * mp4 con dos subtítulos "spa": se distingue castellano de latino por el
    vocabulario del texto (vosotros/vale/tío vs ustedes/celular/carro…).
  * srt sin idioma en el nombre: se propone el idioma por el texto (es/en/fr/de/it/pt/ca).
"""
import html
import re
from pathlib import Path
from typing import Optional

from . import tools

_TAG_ASS = re.compile(r"\{\\[^}]*\}")
_TAG_I1 = re.compile(r"\{\\i1[^}]*\}")
_TAG_I0 = re.compile(r"\{\\i0[^}]*\}")
_ESTILO_CARTEL = re.compile(r"(?:^|[_ .-])(cart|sign|title|screen|onscreen|typeset|ts)(?:$|[_ .-])", re.IGNORECASE)
_NOMBRE_CARTEL = re.compile(r"(?:episode[ _-]*title|chapter[ _-]*title|screen[ _-]*text|sign)", re.IGNORECASE)
_TAG_POSICION = re.compile(r"\\(?:pos|move|org|i?clip|p[1-9]|fr[xyz]|fa[xy])(?:\(|\b)", re.IGNORECASE)

# palabras (en minúsculas, aisladas) típicas de cada variante del español
_ES_ES = ["vosotros", "vosotras", "vale", "tío", "tía", "coche", "móvil", "ordenador", "zumo", "patata",
          "vale,", "joder", "hostia", "gilipollas", "mola", "guay", "os", "habéis", "tenéis", "sois", "queréis"]
_ES_LAT = ["ustedes", "celular", "carro", "computadora", "jugo", "papa", "papas", "chévere", "órale", "ahorita",
           "lindo", "linda", "plata", "enojado", "enojada", "manejar", "pendejo", "boleto", "apurate", "apúrate"]

# palabras muy frecuentes por idioma para adivinar el idioma de un texto
_STOPWORDS = {
    "spa": ["que", "de", "no", "la", "el", "es", "y", "en", "un", "por", "qué", "para", "con", "una", "los", "está", "pero"],
    "eng": ["the", "you", "and", "to", "of", "it", "that", "is", "in", "what", "this", "for", "not", "have", "with", "are"],
    "fre": ["le", "la", "les", "et", "je", "vous", "que", "pas", "est", "une", "des", "nous", "dans", "pour", "qui", "c'est"],
    "ger": ["ich", "und", "die", "der", "das", "nicht", "ist", "du", "sie", "wir", "ein", "mit", "was", "ja", "auf", "zu"],
    "ita": ["che", "non", "di", "il", "la", "è", "un", "una", "per", "sono", "con", "come", "ma", "mi", "ho", "questo"],
    "por": ["que", "não", "você", "de", "um", "uma", "para", "com", "isso", "está", "ele", "ela", "mas", "eu", "o", "os"],
    "cat": ["que", "no", "és", "el", "la", "i", "amb", "per", "una", "això", "molt", "però", "aquest", "són", "hi", "ho"],
    "jpn": [],
}


def leer_texto(ruta: Path) -> str:
    datos = ruta.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return datos.decode(enc)
        except UnicodeDecodeError:
            continue
    return datos.decode("utf-8", "replace")


def tiene_etiquetas_ass(texto: str) -> bool:
    return bool(_TAG_ASS.search(texto))


def limpiar_texto_srt(texto: str) -> str:
    """Quita etiquetas {\\…} conservando cursiva, normaliza saltos de línea y
    elimina líneas vacías dentro de un bloque."""
    t = texto.replace("\r\n", "\n").replace("\r", "\n")
    t = _TAG_I1.sub("<i>", t)
    t = _TAG_I0.sub("</i>", t)
    t = _TAG_ASS.sub("", t)
    t = t.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
    # <i></i> vacíos o repetidos que dejan las etiquetas
    t = re.sub(r"<i>\s*</i>", "", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"


def preparar_suelto(ruta: Path, destino_dir: Path, cfg=None) -> Path:
    """Devuelve un srt limpio listo para muxear: convierte .ass/.ssa/.vtt con
    ffmpeg y limpia etiquetas. El llamador conserva también el ASS/SSA original
    cuando corresponda. Si el fichero ya está bien, lo devuelve tal cual."""
    ext = ruta.suffix.lower()
    if ext == ".vtt":
        destino_dir.mkdir(parents=True, exist_ok=True)
        salida = destino_dir / (ruta.stem + ".srt")
        _vtt_a_srt(ruta, salida)
        return salida
    if ext in (".ass", ".ssa"):
        destino_dir.mkdir(parents=True, exist_ok=True)
        salida = destino_dir / (ruta.stem + ".srt")
        ffmpeg = tools.buscar("ffmpeg", cfg, obligatorio=True)
        tools.ejecutar_silencioso([ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                                   "-i", str(ruta), str(salida)])
        salida.write_text(limpiar_texto_srt(leer_texto(salida)), encoding="utf-8")
        return salida
    if ext == ".srt":
        texto = leer_texto(ruta)
        if tiene_etiquetas_ass(texto) or "\r" in texto or ruta.read_bytes()[:3] == b"\xef\xbb\xbf":
            destino_dir.mkdir(parents=True, exist_ok=True)
            salida = destino_dir / ruta.name
            salida.write_text(limpiar_texto_srt(texto), encoding="utf-8")
            return salida
    return ruta


# Formatos de texto que FFmpeg puede convertir limpiamente a SubRip. Los PGS y
# VobSub son imágenes: convertirlos a SRT exige OCR y nunca debe inventarse con
# una simple conversión de contenedor.
_FORMATOS_TEXTO = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "tx3g", "text", "eia_608", "eia_708"}
_FORMATOS_IMAGEN = {"hdmv_pgs_subtitle", "pgs", "dvd_subtitle", "dvdsub", "vobsub", "sup", "idx"}


def es_subtitulo_texto(codec_o_formato: str) -> bool:
    return (codec_o_formato or "").lower() in _FORMATOS_TEXTO


def es_subtitulo_imagen(codec_o_formato: str) -> bool:
    return (codec_o_formato or "").lower() in _FORMATOS_IMAGEN


def extraer_srt_interno(video: Path, indice: int, codec: str, salida: Path, cfg=None) -> Path:
    """Extrae cualquier subtítulo *de texto* de un contenedor como SRT.

    No acepta PGS/VobSub: necesitan OCR y emitir un SRT vacío o falso sería
    peor que detener el release y pedir el SRT real.
    """
    codec = (codec or "").lower()
    if not es_subtitulo_texto(codec):
        tipo = "PGS/VobSub (imagen)" if es_subtitulo_imagen(codec) else (codec or "formato desconocido")
        raise RuntimeError(f"{video.name}: {tipo} no se puede convertir a SRT sin OCR. Añade el SRT correspondiente.")
    salida.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = tools.buscar("ffmpeg", cfg, obligatorio=True)
    if codec == "webvtt":
        vtt = salida.with_suffix(".vtt")
        tools.ejecutar_silencioso([ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                                   "-i", str(video), "-map", f"0:{indice}", "-c:s", "webvtt", str(vtt)])
        _vtt_a_srt(vtt, salida)
    else:
        tools.ejecutar_silencioso([ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                                   "-i", str(video), "-map", f"0:{indice}", "-c:s", "srt", str(salida)])
        salida.write_text(limpiar_texto_srt(leer_texto(salida)), encoding="utf-8")
    if not salida.exists() or not salida.read_text(encoding="utf-8", errors="replace").strip():
        raise RuntimeError(f"{video.name}: no se obtuvo un SRT legible de la pista {indice}.")
    return salida


def extraer_ass_interno(video: Path, indice: int, salida: Path, cfg=None) -> Path:
    """Extrae ASS/SSA de un contenedor para analizar carteles reales."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = tools.buscar("ffmpeg", cfg, obligatorio=True)
    tools.ejecutar_silencioso([ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                               "-i", str(video), "-map", f"0:{indice}", "-c:s", "ass", str(salida)])
    return salida


_VTT_TIEMPO = re.compile(
    r"^\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})[.](\d{3})\s+-->\s+"
    r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.](\d{3})(?:\s+.*)?$"
)
_VTT_CLASE = re.compile(r"</?c(?:\.[^ >]+)*>", re.I)
_VTT_ETIQUETA = re.compile(r"</?(?:v|lang|ruby|rt)(?:\s+[^>]*)?>", re.I)


def _vtt_tiempo(grupos: tuple, inicio: bool) -> str:
    """Convierte un tiempo WebVTT a la sintaxis SRT."""
    offset = 0 if inicio else 4
    horas = int(grupos[offset] or 0)
    minutos, segundos, ms = (int(grupos[offset + i]) for i in (1, 2, 3))
    return f"{horas:02d}:{minutos:02d}:{segundos:02d},{ms:03d}"


def _vtt_a_srt(origen: Path, destino: Path) -> None:
    """Conversor WebVTT de Netflix sin depender del demuxer de FFmpeg.

    Conserva texto y etiquetas SRT comunes (cursiva/negrita/subrayado), pero
    elimina posicionamiento, clases de color/fondo y notas WebVTT. Esas marcas
    no contienen el typesetting avanzado de un ASS original.
    """
    texto = leer_texto(origen).replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    bloques = []
    for bloque in re.split(r"\n[ \t]*\n", texto):
        lineas = [linea.rstrip() for linea in bloque.split("\n")]
        if not lineas:
            continue
        primero = lineas[0].strip()
        if not primero or primero.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        indice_tiempo = 0 if "-->" in lineas[0] else 1
        if indice_tiempo >= len(lineas):
            continue
        m = _VTT_TIEMPO.match(lineas[indice_tiempo])
        if not m:
            continue
        contenido = "\n".join(lineas[indice_tiempo + 1:]).strip()
        contenido = _VTT_CLASE.sub("", contenido)
        contenido = _VTT_ETIQUETA.sub("", contenido)
        contenido = html.unescape(contenido).strip()
        if contenido:
            bloques.append((_vtt_tiempo(m.groups(), True), _vtt_tiempo(m.groups(), False), contenido))
    if not bloques:
        raise RuntimeError(f"{origen.name}: WebVTT sin cues legibles; no se crea un SRT vacío.")
    destino.write_text("\n\n".join(f"{n}\n{ini} --> {fin}\n{txt}" for n, (ini, fin, txt) in enumerate(bloques, 1)) + "\n",
                       encoding="utf-8")


def cobertura_subtitulos(video: Path, cfg=None) -> dict[int, tuple[int, float, float]]:
    """Devuelve ``{índice_global: (cues, primero, último)}`` de un contenedor.

    Algunos MP4 añaden paquetes vacíos al principio y al final de una pista, de
    modo que su duración aparente no basta para distinguir los carteles. El
    número relativo de cues entre pistas del mismo idioma sí es una señal útil.
    """
    ffprobe = tools.buscar("ffprobe", cfg, obligatorio=True)
    r = tools.ejecutar([ffprobe, "-v", "error", "-show_entries", "packet=stream_index,pts_time",
                        "-select_streams", "s", "-of", "csv=p=0", str(video)],
                       capturar=True, mostrar=False, comprobar=False)
    tiempos: dict[int, list[float]] = {}
    for linea in (r.stdout or "").splitlines():
        partes = linea.split(",", 1)
        if len(partes) != 2:
            continue
        try:
            stream, tiempo = int(partes[0]), float(partes[1])
        except ValueError:
            continue
        tiempos.setdefault(stream, []).append(tiempo)
    return {stream: (len(valores), min(valores), max(valores))
            for stream, valores in tiempos.items() if valores}


def es_forzado_por_cobertura(cobertura: Optional[tuple[int, float, float]],
                             maximo_mismo_idioma: int) -> bool:
    """Detecta una pista de carteles sin flag ``forced`` de forma conservadora.

    Solo se aplica cuando hay otra pista del mismo idioma claramente completa:
    la candidata debe tener como máximo 80 cues y cinco veces menos cues que
    aquella. Así una pista de diálogo corta no se etiqueta erróneamente como
    forzada. Los metadatos explícitos del contenedor siempre tienen prioridad.
    """
    if not cobertura or maximo_mismo_idioma <= 0:
        return False
    cues, _inicio, _fin = cobertura
    return cues <= 80 and cues * 5 <= maximo_mismo_idioma


def _tiempo_srt(valor: str) -> Optional[str]:
    """H:MM:SS.cc de ASS → HH:MM:SS,mmm de SRT."""
    m = re.fullmatch(r"\s*(\d+):(\d{1,2}):(\d{1,2})(?:[.](\d+))?\s*", valor)
    if not m:
        return None
    horas, minutos, segundos = (int(m.group(i)) for i in range(1, 4))
    fraccion = (m.group(4) or "0")[:3].ljust(3, "0")
    return f"{horas:02d}:{minutos:02d}:{segundos:02d},{int(fraccion):03d}"


def _es_cartel_ass(estilo: str, nombre: str, texto: str) -> bool:
    """Heurística conservadora para textos en pantalla de un ASS de anime.

    Las llaves por sí solas no bastan: cursiva, negrita o un fundido también
    pueden pertenecer a un diálogo normal. Se consideran carteles los estilos
    nombrados como Cart/Sign/Title o eventos con posicionamiento, movimiento,
    recorte, dibujo o transformación geométrica explícitos.
    """
    return bool(_ESTILO_CARTEL.search(estilo) or _NOMBRE_CARTEL.search(nombre) or _TAG_POSICION.search(texto))


def extraer_carteles_ass(ruta: Path, destino_dir: Path) -> Optional[tuple]:
    """Extrae carteles de un ASS/SSA a ``*.forced.srt`` y ``*.forced.ass``.

    Devuelve None cuando el fichero no tiene eventos identificables como
    carteles. El ASS no posee un flag estándar de "forzado" por evento, por lo
    que se usan estilo/nombre y etiquetas de typesetting, sin confundir simples
    ``{\\i1}``, ``{\\b1}`` o ``{\\fad(...)}`` con un cartel.
    """
    texto = leer_texto(ruta).replace("\r\n", "\n").replace("\r", "\n")
    en_eventos = False
    formato = []
    bloques = []
    lineas_ass = []
    for linea in texto.splitlines():
        seccion = re.fullmatch(r"\s*\[([^]]+)\]\s*", linea)
        if seccion:
            en_eventos = seccion.group(1).strip().lower() == "events"
            lineas_ass.append(linea)
            continue
        if not en_eventos:
            lineas_ass.append(linea)
            continue
        if linea.lower().startswith("format:"):
            formato = [x.strip().lower() for x in linea.split(":", 1)[1].split(",")]
            lineas_ass.append(linea)
            continue
        if not linea.lower().startswith("dialogue:"):
            lineas_ass.append(linea)
            continue
        if not formato:
            continue
        valores = linea.split(":", 1)[1].lstrip().split(",", len(formato) - 1)
        if len(valores) != len(formato):
            continue
        evento = dict(zip(formato, valores))
        bruto = evento.get("text", "")
        if not _es_cartel_ass(evento.get("style", ""), evento.get("name", ""), bruto):
            continue
        lineas_ass.append(linea)
        inicio = _tiempo_srt(evento.get("start", ""))
        fin = _tiempo_srt(evento.get("end", ""))
        limpio = limpiar_texto_srt(bruto).strip()
        if inicio and fin and limpio:
            bloques.append((inicio, fin, limpio))
    if not bloques:
        return None
    destino_dir.mkdir(parents=True, exist_ok=True)
    salida_srt = destino_dir / f"{ruta.stem}.forced.srt"
    salida_ass = destino_dir / f"{ruta.stem}.forced{ruta.suffix.lower()}"
    contenido = "\n\n".join(f"{i}\n{inicio} --> {fin}\n{texto}" for i, (inicio, fin, texto) in enumerate(bloques, 1))
    salida_srt.write_text(contenido + "\n", encoding="utf-8")
    salida_ass.write_text("\n".join(lineas_ass) + "\n", encoding="utf-8-sig")
    return salida_srt, salida_ass


_SRT_BLOQUE = re.compile(
    r"(?:^|\n\s*\n)\s*(?:\d+\s*\n)?"
    r"(?P<inicio>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s+-->\s+"
    r"(?P<fin>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})(?:[^\n]*)\n"
    r"(?P<texto>.*?)(?=\n\s*\n|\Z)", re.DOTALL)


def carteles_srt_mayusculas(ruta: Path) -> list[tuple[str, str, str]]:
    """Devuelve posibles carteles escritos en mayúsculas en un SRT completo.

    Es una señal auxiliar, no una forma de adivinar diálogos: cada cue debe
    contener letras, estar casi enteramente en mayúsculas y ser una minoría
    clara del fichero. Así se descartan SRTs cuya convención sea escribir todo
    el diálogo en mayúsculas. El llamador solo puede usarla si no había una
    pista española ``forced`` declarada y debe pedir confirmación al usuario.
    """
    texto = leer_texto(ruta).replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cues = []
    for bloque in _SRT_BLOQUE.finditer(texto):
        limpio = limpiar_texto_srt(bloque.group("texto")).strip()
        letras = [c for c in limpio if c.isalpha()]
        # Tres letras evitan etiquetar como cartel "OK", siglas o ruidos.
        if len(letras) < 3:
            continue
        mayusculas = sum(c.isupper() for c in letras)
        if mayusculas / len(letras) >= 0.85:
            cues.append((bloque.group("inicio").replace(".", ","),
                         bloque.group("fin").replace(".", ","), limpio))
    total = len(list(_SRT_BLOQUE.finditer(texto)))
    # Si una parte apreciable del SRT es mayúscula, puede ser simplemente la
    # convención de ese proveedor o diálogo enfático; no se propone nada.
    if not cues or total < 2 or len(cues) * 3 > total:
        return []
    return cues


def escribir_forzado_srt(ruta_origen: Path, destino_dir: Path,
                         cues: list[tuple[str, str, str]]) -> Path:
    """Materializa los cues previamente confirmados como ``*.forced.srt``."""
    if not cues:
        raise RuntimeError("No hay carteles en mayúsculas para guardar.")
    destino_dir.mkdir(parents=True, exist_ok=True)
    salida = destino_dir / f"{ruta_origen.stem}.forced.srt"
    contenido = "\n\n".join(
        f"{i}\n{inicio} --> {fin}\n{texto}"
        for i, (inicio, fin, texto) in enumerate(cues, 1)
    )
    salida.write_text(contenido + "\n", encoding="utf-8")
    return salida


def texto_pista(video: Path, indice: int, cfg=None, segundos: int = 1200) -> str:
    """Texto de un subtítulo interno (los primeros `segundos`) como srt, vía ffmpeg."""
    ffmpeg = tools.buscar("ffmpeg", cfg, obligatorio=True)
    r = tools.ejecutar([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-t", str(segundos),
                        "-i", str(video), "-map", f"0:{indice}", "-f", "srt", "-"],
                       capturar=True, mostrar=False, comprobar=False)
    return r.stdout or ""


def _palabras(texto: str) -> list:
    limpio = texto.replace("\\N", " ").replace("\\n", " ").replace("\\h", " ")
    limpio = re.sub(r"<[^>]+>|\{[^}]*\}|\d+:\d+:\d+[,.]\d+ --> \d+:\d+:\d+[,.]\d+|^\d+$", " ", limpio, flags=re.MULTILINE)
    return re.findall(r"[a-záéíóúüñàèìòùçâêîôûäëïöß']+", limpio.lower())


def detectar_idioma(texto: str) -> Optional[str]:
    """Código canónico del idioma más probable del texto, o None si no está claro."""
    palabras = _palabras(texto)
    if len(palabras) < 30:
        # sin apenas texto latino: ¿japonés/coreano/chino?
        if re.search(r"[぀-ヿ]", texto):
            return "jpn"
        if re.search(r"[가-힯]", texto):
            return "kor"
        if re.search(r"[一-鿿]", texto):
            return "chi"
        return None
    puntos = {}
    for idioma, lista in _STOPWORDS.items():
        if lista:
            puntos[idioma] = sum(1 for p in palabras if p in lista)
    mejor = max(puntos, key=puntos.get)
    total = len(palabras)
    if puntos[mejor] / total < 0.05:
        return None
    if mejor == "spa":
        return detectar_variante_es(texto) or "spa"
    return mejor


def puntuacion_es(texto: str) -> int:
    """Positivo = rasgos de castellano (vosotros, vale, tío…); negativo = latino
    (ustedes, celular…); 0 = sin pruebas (español neutro)."""
    palabras = _palabras(texto)
    es = sum(1 for p in palabras if p in _ES_ES)
    lat = sum(1 for p in palabras if p in _ES_LAT)
    es += sum(1 for p in palabras if re.search(r"(áis|éis)$", p) and len(p) > 4)  # formas de vosotros
    return es - lat


def detectar_variante_es(texto: str) -> Optional[str]:
    """'spa' (castellano), 'spal' (latino) o None si el texto no da pruebas."""
    n = puntuacion_es(texto)
    return "spa" if n > 0 else "spal" if n < 0 else None


def asignar_variantes(textos: list) -> list:
    """Para varias pistas 'spa' del mismo fichero: devuelve una lista paralela
    con 'spa'/'spal'. Si ninguna da pruebas, la primera es castellano."""
    puntos = [puntuacion_es(t) for t in textos]
    if len(textos) == 1:
        return ["spal" if puntos[0] < 0 else "spa"]
    res = []
    mejor = max(range(len(textos)), key=lambda i: puntos[i])
    for i, n in enumerate(puntos):
        if n > 0:
            res.append("spa")
        elif n < 0:
            res.append("spal")
        else:
            res.append("spa" if i == mejor and puntos[mejor] >= 0 else "spal")
    if res.count("spa") == 0:
        res[mejor] = "spa"
    return res
