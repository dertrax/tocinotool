"""Identificadores y enlaces del release: TMDB / IMDb (de los metadatos que
FileBot deja en el fichero al renombrar) y FilmAffinity (buscador web, sin API).
Se usan en info.txt y en el .nfo."""
import html as _html
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from . import tools, ui

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
_RE_TMDB_PELICULA = re.compile(r"(?:themoviedb\.org|tmdb\.org)/movie/(\d+)", re.IGNORECASE)
_RE_IMDB_SERIE = re.compile(r"imdb\.com/title/(tt\d+)", re.IGNORECASE)


@dataclass
class Enlaces:
    titulo: str = ""
    anio: str = ""
    tmdbid: str = ""
    tvdbid: str = ""
    imdbid: str = ""
    serie: bool = False
    filmaffinity: str = ""

    @property
    def tmdb(self) -> str:
        if not self.tmdbid:
            return ""
        return f"https://www.themoviedb.org/{'tv' if self.serie else 'movie'}/{self.tmdbid}"

    @property
    def tvdb(self) -> str:
        return f"https://thetvdb.com/?tab=series&id={self.tvdbid}" if self.tvdbid else ""

    @property
    def imdb(self) -> str:
        return f"https://www.imdb.com/title/{self.imdbid}/" if self.imdbid else ""

    def lineas(self) -> list:
        res = []
        if self.tmdb:
            res.append(f"TMDB: {self.tmdb}")
        elif self.tvdb:
            res.append(f"TheTVDB: {self.tvdb}")
        if self.imdb:
            res.append(f"IMDb: {self.imdb}")
        if self.filmaffinity:
            res.append(f"FilmAffinity: {self.filmaffinity}")
        return res


def ids_filebot(cfg, mkv: Path, serie: bool) -> Enlaces:
    """Lee los metadatos que FileBot guardó (xattr) al renombrar."""
    e = Enlaces(serie=serie)
    exe = tools.buscar("filebot", cfg)
    if not exe:
        return e
    fmt = "{n}|{y}|{any{tmdbid}{''}}|{any{tvdbid}{''}}|{any{imdbid}{''}}"
    try:
        r = subprocess.run([exe, "-mediainfo", str(mkv), "--format", fmt], capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return e
    # FileBot en Windows suele escribir los metadatos en la página de códigos
    # local (cp1252), aunque la aplicación trabaje internamente con Unicode.
    # Se intenta UTF-8 primero para instalaciones que sí lo emitan, y se evita
    # reemplazar tildes por U+FFFD, pues esas cadenas se usan para buscar FA.
    salida = r.stdout or b""
    try:
        texto = salida.decode("utf-8")
    except UnicodeDecodeError:
        texto = salida.decode("cp1252", errors="replace")
    for linea in texto.splitlines():
        partes = linea.strip().split("|")
        if len(partes) == 5 and partes[0]:
            e.titulo, e.anio, e.tmdbid, e.tvdbid, e.imdbid = (p.strip() for p in partes)
            break
    return e


def buscar_filmaffinity(titulo: str, anio: str = "", serie: bool = False) -> str:
    """URL de la ficha en FilmAffinity (es) que mejor casa con título y año; '' si no hay."""
    if not titulo:
        return ""
    q = urllib.parse.urlencode({"stype": "title", "stext": titulo})
    url = "https://www.filmaffinity.com/es/search.php?" + q
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Language": "es-ES,es;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            final, pagina = r.geturl(), r.read().decode("utf-8", "replace")
    except Exception as ex:  # noqa: BLE001 — sin red o bloqueado: se sigue sin enlace
        ui.aviso(f"FilmAffinity no disponible: {ex}")
        return ""
    m = re.match(r"https://www\.filmaffinity\.com/es/film\d+\.html", final)
    if m:  # un único resultado: redirige a la ficha
        return m.group(0)

    candidatos = []
    for bloque in re.split(r'<div class="row movie-card', pagina)[1:]:
        mid = re.search(r'data-movie-id="(\d+)"', bloque)
        mt = re.search(r'class="fs-6 mc-title">\s*<a[^>]*>([^<]+)</a>', bloque)
        my = re.search(r'class="mc-year[^"]*">\s*(\d{4})', bloque) or re.search(r'>(\d{4})<', bloque)
        if not (mid and mt):
            continue
        t = _html.unescape(mt.group(1)).strip()
        es_serie = "(serie de tv)" in t.lower() or "(miniserie" in t.lower()
        t_limpio = re.sub(r"\s*\((?:serie de tv|miniserie de tv|tv)\)\s*", "", t, flags=re.IGNORECASE).strip()
        y = my.group(1) if my else ""
        puntos = 0
        if t_limpio.lower() == titulo.lower():
            puntos += 3
        elif titulo.lower() in t_limpio.lower():
            puntos += 1
        if anio and y == anio:
            puntos += 2
        elif anio and y and abs(int(y) - int(anio)) == 1:
            puntos += 1
        if es_serie == serie:
            puntos += 1
        candidatos.append((puntos, mid.group(1)))
    if not candidatos:
        return ""
    puntos, mid = max(candidatos)
    return f"https://www.filmaffinity.com/es/film{mid}.html" if puntos >= 3 else ""


def pedir_enlace_manual(e: Enlaces) -> None:
    """Salvaguarda sin FileBot: un enlace útil, opcional y validado.

    La ficha no debe quedar bloqueada porque una persona no tenga FileBot. Para
    películas necesita el enlace de TMDb; para series, el de IMDb. Se
    guarda únicamente el identificador dentro del objeto de la ficha, nunca en
    la configuración del usuario.
    """
    if e.serie:
        servicio, ejemplo, patron = "IMDb", "https://www.imdb.com/title/tt1234567/", _RE_IMDB_SERIE
        atributo = "imdbid"
    else:
        servicio, ejemplo, patron = "TMDb", "https://www.themoviedb.org/movie/12345", _RE_TMDB_PELICULA
        atributo = "tmdbid"
    ui.seccion(f"Enlace manual de {servicio}")
    ui.info("No hay metadatos de FileBot para obtener este enlace automáticamente.")
    ui.info("Pega el enlace de la ficha. ENTER permite continuar sin enlace.")
    while True:
        valor = ui.preguntar(f"Enlace de {servicio} ({ejemplo})", defecto="")
        if not valor:
            ui.aviso(f"Se genera la ficha sin enlace de {servicio}.")
            return
        m = patron.search(valor)
        if m:
            setattr(e, atributo, m.group(1))
            ui.ok(f"Enlace de {servicio} añadido a la ficha.")
            return
        ui.aviso(f"No parece un enlace válido de {servicio}. Pega la URL completa o pulsa ENTER para omitirlo.")


def enlaces_release(cfg, entrada: Path, serie: bool) -> Enlaces:
    """Enlaces de un release (mkv o carpeta de temporada) tras el renombrado."""
    mkv = entrada if entrada.is_file() else next(iter(sorted(entrada.rglob("*.mkv"))), None)
    if mkv is None:
        return Enlaces(serie=serie)
    e = ids_filebot(cfg, mkv, serie)
    if not e.titulo:  # sin metadatos de FileBot: título y año del nombre de fichero
        m = re.match(r"^(.*?)\.(\d{4})\.", entrada.name) or re.match(r"^(.*?)\.S\d{2}", entrada.name, re.IGNORECASE)
        if m:
            e.titulo = m.group(1).replace(".", " ")
            e.anio = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
    # Sin FileBot (o sin sus metadatos) se mantiene la generación de ficha.
    # La persona aporta solo el enlace que corresponde al tipo de contenido.
    if (serie and not e.imdbid) or (not serie and not e.tmdbid):
        pedir_enlace_manual(e)
    if cfg.get("enlaces", {}).get("filmaffinity", True):
        e.filmaffinity = buscar_filmaffinity(e.titulo, e.anio, serie)
    return e
