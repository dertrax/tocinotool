"""Análisis y agrupación común de un espacio de trabajo de releases.

Una carpeta no equivale necesariamente a un MKV: puede contener componentes
sueltos de una película o de varios episodios. Este módulo es el único sitio
que clasifica esos componentes; el flujo completo y el Muxer lo reutilizan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from . import probe, ui

_EPISODIO = re.compile(r"(?:\b|_)(?:s(?P<s>\d{1,2})[ ._-]*e(?P<e>\d{1,3})|(?P<s2>\d{1,2})x(?P<e2>\d{1,3}))(?:\b|_)", re.I)
_RUIDO = re.compile(
    r"\b(?:video|audio|subs?|subtitles?|forced|forzados?|complete|full|sdh|cc|"
    r"spa|es(?:[-_.]?(?:es|419))?|castellano|lat(?:ino)?|eng|en|jpn|ja|"
    r"ac3|eac3|aac|dts(?:[-_. ]?hd(?:[-_. ]?(?:ma|hra))?)?|truehd|thd|flac|pcm|"
    r"h264|x264|avc|h265|x265|hevc|av1|\d{3,4}p|web[-_. ]?dl|bluray|bdrip|remux)\b",
    re.I,
)
_AUX_VOBSUB = {".sub"}
_EXCLUIR = {"temporal", "originales", "originals", "capturas", "__pycache__"}


@dataclass
class Componente:
    ruta: Path
    medio: probe.Medio
    tipo: str  # video | audio | subtitle

    @property
    def duracion(self) -> float:
        return self.medio.duracion


@dataclass
class ReleaseGroup:
    clave: str
    video: Componente
    audios: list[Componente] = field(default_factory=list)
    subtitulos: list[Componente] = field(default_factory=list)
    auxiliares: list[Path] = field(default_factory=list)  # .sub que acompaña a un .idx
    incidencias: list[str] = field(default_factory=list)

    @property
    def raiz(self) -> Path:
        return self.video.ruta.parent

    @property
    def componentes_sueltos(self) -> list[Path]:
        return [c.ruta for c in self.audios + self.subtitulos if c.ruta != self.video.ruta]

    @property
    def es_episodio(self) -> bool:
        return bool(_EPISODIO.search(self.clave) or re.fullmatch(r"(?:EP)?\d{1,3}", self.clave, re.I))


@dataclass
class Workspace:
    raiz: Path
    grupos: list[ReleaseGroup] = field(default_factory=list)
    sin_asignar: list[Path] = field(default_factory=list)
    incidencias: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return bool(self.grupos) and not self.incidencias and not any(g.incidencias for g in self.grupos)


def _ep(ruta: Path) -> Optional[str]:
    """Clave SxxExx del nombre o de sus carpetas, si la hay."""
    for texto in (ruta.stem, *(p.name for p in ruta.parents)):
        m = _EPISODIO.search(texto)
        if m:
            s, e = m.group("s") or m.group("s2"), m.group("e") or m.group("e2")
            return f"S{int(s):02d}E{int(e):02d}"
    return None


def _base(ruta: Path) -> str:
    texto = ruta.stem.lower().replace(".", " ").replace("_", " ").replace("-", " ")
    texto = _EPISODIO.sub(" ", texto)
    texto = _RUIDO.sub(" ", texto)
    return re.sub(r"\W+", "", texto)


def _es_hijo_de(ruta: Path, raiz: Path) -> bool:
    try:
        ruta.relative_to(raiz)
        return True
    except ValueError:
        return False


def _candidatos(raiz: Path, cfg) -> Iterable[Path]:
    exts = cfg["extensiones"]
    conocidas = {"." + str(e).lower() for k in ("video", "audio", "subtitulo") for e in exts[k]} | _AUX_VOBSUB
    if raiz.is_file():
        if raiz.suffix.lower() in conocidas:
            yield raiz
        return
    for ruta in sorted(raiz.rglob("*")):
        if not ruta.is_file() or ruta.suffix.lower() not in conocidas:
            continue
        if any(p.lower() in _EXCLUIR for p in ruta.relative_to(raiz).parts[:-1]):
            continue
        yield ruta


def _clasificar(ruta: Path, cfg) -> Optional[Componente]:
    if ruta.suffix.lower() in _AUX_VOBSUB:
        return None
    try:
        medio = probe.analizar(ruta, cfg)
    except (OSError, RuntimeError, ValueError):
        return None
    # Las pistas elementales normalmente no guardan un tag language. El nombre
    # solo completa ese metadato ausente (es/ac3, en/truehd…), nunca lo pisa.
    tokens = re.split(r"[. _\-\[\]()]+", ruta.stem.lower())
    idioma_nombre = next((cfg.canon_idioma(t) for t in tokens if cfg.es_idioma(t)), "und")
    if idioma_nombre != "und":
        for pista in medio.audios + medio.subtitulos:
            if pista.idioma == "und":
                pista.idioma = idioma_nombre
    tipos = {p.tipo for p in medio.pistas}
    if "video" in tipos:
        return Componente(ruta, medio, "video")
    if "audio" in tipos:
        return Componente(ruta, medio, "audio")
    if "subtitle" in tipos:
        return Componente(ruta, medio, "subtitle")
    return None


def _asignar(componente: Componente, grupos: list[ReleaseGroup]) -> tuple[Optional[ReleaseGroup], Optional[str]]:
    episodio = _ep(componente.ruta)
    if episodio:
        candidatos = [g for g in grupos if _ep(g.video.ruta) == episodio]
    else:
        # Un vídeo único en la misma carpeta es una asociación segura. Si hay
        # varios, solo se acepta un prefijo/base inequívoco.
        mismos = [g for g in grupos if g.video.ruta.parent == componente.ruta.parent]
        candidatos = mismos if len(mismos) == 1 else []
        if not candidatos:
            base = _base(componente.ruta)
            candidatos = [g for g in grupos if base and (_base(g.video.ruta) == base
                          or componente.ruta.name.lower().startswith(g.video.ruta.stem.lower())
                          or g.video.ruta.name.lower().startswith(componente.ruta.stem.lower()))]
    if len(candidatos) == 1:
        return candidatos[0], None
    if len(candidatos) > 1:
        return None, f"{componente.ruta.name}: coincide con varios vídeos; usa SxxExx o una base de nombre inequívoca"
    return None, f"{componente.ruta.name}: no se ha podido asociar con ningún vídeo"


def _clave_grupo(video: Componente) -> str:
    episodio = _ep(video.ruta)
    if episodio:
        return episodio
    # Temporadas con 01/video.hevc, 02/video.hevc…: la carpeta numérica es
    # más informativa que el nombre genérico "video" y permite tratarlas como
    # episodios sin mezclar los componentes de cada subcarpeta.
    if video.ruta.parent.name.isdigit() and video.ruta.stem.lower() in {"video", "episode", "capitulo", "capítulo"}:
        return f"EP{int(video.ruta.parent.name):02d}"
    return video.ruta.stem


def analizar(raiz: Path, cfg) -> Workspace:
    """Escanea una carpeta, o solamente el contenedor indicado, sin muxear."""
    entrada = raiz.resolve()
    # Aunque se seleccione un MKV, la raíz del workspace es su carpeta para
    # poder mostrar rutas relativas y crear los auxiliares junto al release.
    raiz = entrada.parent if entrada.is_file() else entrada
    ws = Workspace(raiz)
    componentes: list[Componente] = []
    auxiliares: list[Path] = []
    for ruta in _candidatos(entrada, cfg):
        if ruta.suffix.lower() in _AUX_VOBSUB:
            auxiliares.append(ruta)
            continue
        c = _clasificar(ruta, cfg)
        if c is None:
            ws.incidencias.append(f"No se puede identificar técnicamente: {ruta.relative_to(raiz)}")
        else:
            componentes.append(c)

    videos = [c for c in componentes if c.tipo == "video"]
    for video in videos:
        clave = _clave_grupo(video)
        ws.grupos.append(ReleaseGroup(clave=clave, video=video))
    if not ws.grupos:
        ws.incidencias.append("No se ha detectado ninguna pista de vídeo válida")
        return ws

    for c in (x for x in componentes if x.tipo != "video"):
        grupo, error = _asignar(c, ws.grupos)
        if grupo is None:
            ws.sin_asignar.append(c.ruta)
            ws.incidencias.append(error or c.ruta.name)
            continue
        (grupo.audios if c.tipo == "audio" else grupo.subtitulos).append(c)
        dur_video, dur = grupo.video.duracion, c.duracion
        if c.tipo == "audio" and dur_video and dur and abs(dur_video - dur) > 2.0:
            grupo.incidencias.append(f"{c.ruta.name}: duración {dur:.1f}s, vídeo {dur_video:.1f}s")

    for sub in auxiliares:
        idx = sub.with_suffix(".idx")
        grupo, error = _asignar(Componente(sub, probe.Medio(sub), "subtitle"), ws.grupos)
        if idx.exists() and grupo is not None:
            grupo.auxiliares.append(sub)
        else:
            ws.sin_asignar.append(sub)
            ws.incidencias.append(error or f"{sub.name}: falta su .idx asociado")
    return ws


def mostrar(ws: Workspace, cfg) -> None:
    ui.seccion("Grupos de release detectados")
    filas = []
    for g in ws.grupos:
        v = g.video.medio.video
        detalle = f"{v.codec if v else '?'} {(v.alto if v else '?')}p"
        filas.append([g.clave, str(g.video.ruta.relative_to(ws.raiz)), detalle,
                      str(len(g.audios)), str(len(g.subtitulos)), "OK" if not g.incidencias else "REVISAR"])
    ui.tabla(["grupo", "vídeo", "formato", "audios", "subs", "estado"], filas)
    for g in ws.grupos:
        for incidencia in g.incidencias:
            ui.error(f"{g.clave}: {incidencia}")
    for incidencia in ws.incidencias:
        ui.error(incidencia)
