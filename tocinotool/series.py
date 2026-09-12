"""Parser local de series, independiente de FileBot.

No consulta ni modifica archivos: reconoce los episodios disponibles, detecta
huecos y construye una correlación que el usuario puede confirmar antes de
pasar al renombrado. Una URL se conserva como referencia; no se scrapea ni se
convierte en dependencia de red.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import ui

_EP = re.compile(r"S(?P<s>\d{1,2})E(?P<e>\d{1,3})|(?P<s2>\d{1,2})x(?P<e2>\d{1,3})", re.I)
_RUIDO = re.compile(r"[._ -]+")


@dataclass(frozen=True)
class Episodio:
    archivo: Path
    temporada: int
    numero: int


@dataclass
class PlanSerie:
    titulo: str = ""
    url: str = ""
    episodios: List[Episodio] = None
    manual: bool = False

    def __post_init__(self) -> None:
        if self.episodios is None:
            self.episodios = []

    @property
    def temporadas(self) -> List[int]:
        return sorted({e.temporada for e in self.episodios})

    @property
    def faltantes(self) -> List[str]:
        res = []
        for temporada in self.temporadas:
            nums = sorted(e.numero for e in self.episodios if e.temporada == temporada)
            for n in range(nums[0], nums[-1] + 1):
                if n not in nums:
                    res.append(f"S{temporada:02d}E{n:02d}")
        return res


def _mkvs(raiz: Path) -> List[Path]:
    base = raiz.parent if raiz.is_file() else raiz
    return sorted(p for p in ( [raiz] if raiz.is_file() else base.rglob("*.mkv") )
                  if not any(x.lower() in {"originales", "originals", "temporal", "capturas"} for x in p.parts))


def _titulo_propuesto(archivo: Path) -> str:
    texto = _EP.sub(" ", archivo.stem)
    texto = re.split(r"\b(?:1080p|2160p|web[ .-]?dl|bluray|h[ .-]?264|h[ .-]?265|x264|x265)\b", texto, flags=re.I)[0]
    return _RUIDO.sub(" ", texto).strip()


def analizar(raiz: Path, url: str = "") -> PlanSerie:
    episodios = []
    for archivo in _mkvs(raiz):
        m = _EP.search(archivo.name)
        if m:
            episodios.append(Episodio(archivo, int(m.group("s") or m.group("s2")), int(m.group("e") or m.group("e2"))))
    titulo = _titulo_propuesto(episodios[0].archivo) if episodios else ""
    return PlanSerie(titulo=titulo, url=url, episodios=episodios)


def _mostrar(plan: PlanSerie) -> None:
    if not plan.episodios:
        ui.aviso("No se han detectado episodios por nombre.")
        return
    ui.seccion("Parser propio de series")
    ui.info(f"Serie: {plan.titulo or 'sin identificar'}")
    ui.info(f"Archivos detectados: {len(plan.episodios)}")
    primero, ultimo = plan.episodios[0], plan.episodios[-1]
    ui.info(f"Primer archivo: {primero.archivo.name} → S{primero.temporada:02d}E{primero.numero:02d}")
    ui.info(f"Último archivo: {ultimo.archivo.name} → S{ultimo.temporada:02d}E{ultimo.numero:02d}")
    rangos = []
    for temporada in plan.temporadas:
        nums = sorted(e.numero for e in plan.episodios if e.temporada == temporada)
        rangos.append(f"S{temporada:02d}E{nums[0]:02d} → S{temporada:02d}E{nums[-1]:02d}")
    ui.info("Rango: " + " · ".join(rangos))
    if plan.faltantes:
        ui.aviso("Episodios faltantes: " + ", ".join(plan.faltantes[:12]) + ("…" if len(plan.faltantes) > 12 else ""))


def resolver_manual(raiz: Path, url: str = "") -> PlanSerie:
    archivos = _mkvs(raiz)
    titulo = ui.preguntar("Nombre de la serie", obligatorio=True)
    temporada = ui.preguntar_entero("Temporada", defecto=1, minimo=0, maximo=99)
    inicio = ui.preguntar_entero("Primer episodio", defecto=1, minimo=0, maximo=999)
    return PlanSerie(titulo=titulo, url=url,
                     episodios=[Episodio(a, temporada, inicio + i) for i, a in enumerate(archivos)], manual=True)


def flujo(cfg, carpeta: Optional[Path] = None, pedir_fallback: bool = True) -> Optional[PlanSerie]:
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "Carpeta de serie", admitir_fichero=True)
    url = ui.preguntar("URL de referencia (opcional; IMDb/TMDb/TheTVDB u otra)")
    if url and not re.match(r"https?://", url, re.I):
        ui.aviso("La URL no parece válida; se ignora y se mantiene el análisis local.")
        url = ""
    plan = analizar(carpeta, url)
    _mostrar(plan)
    if not plan.episodios and pedir_fallback and ui.preguntar_sn("¿Asignar la correlación manualmente?", True):
        plan = resolver_manual(carpeta, url)
        _mostrar(plan)
    return plan
