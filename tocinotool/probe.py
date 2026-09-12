"""Análisis de ficheros multimedia con ffprobe (JSON) → objetos Python."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import tools


@dataclass
class Pista:
    indice: int                 # índice de stream en ffprobe (== id de pista en mkvmerge para mkv)
    tipo: str                   # video | audio | subtitle | attachment | data
    codec: str                  # codec_name de ffprobe (ac3, hevc…)
    perfil: Optional[str] = None
    idioma: str = "und"         # tal cual viene en el fichero (sin canonizar)
    titulo: str = ""
    canales: Optional[int] = None
    layout: Optional[str] = None
    kbps: Optional[int] = None
    sample_rate: Optional[int] = None
    duracion: float = 0.0
    ancho: Optional[int] = None
    alto: Optional[int] = None
    bit_depth: Optional[int] = None
    fps: Optional[float] = None
    transfer: Optional[str] = None   # color_transfer (smpte2084 = HDR10/PQ, arib-std-b67 = HLG)
    dovi: bool = False
    defecto: bool = False
    forzado: bool = False
    sdh: bool = False
    atmos: bool = False

    @property
    def es_hdr(self) -> bool:
        return self.dovi or (self.transfer or "").lower() in ("smpte2084", "arib-std-b67")

    def describir(self) -> str:
        if self.tipo == "audio":
            return f"{self.codec}{'/' + self.perfil if self.perfil else ''}{' atmos' if self.atmos else ''} {self.canales}ch {self.kbps or '?'} kbps"
        if self.tipo == "video":
            return f"{self.codec} {self.ancho}x{self.alto}{' HDR' if self.es_hdr else ''}"
        return self.codec


@dataclass
class Medio:
    ruta: Path
    duracion: float = 0.0
    formato: str = ""
    pistas: List[Pista] = field(default_factory=list)

    @property
    def video(self) -> Optional[Pista]:
        return next((p for p in self.pistas if p.tipo == "video"), None)

    @property
    def audios(self) -> List[Pista]:
        return [p for p in self.pistas if p.tipo == "audio"]

    @property
    def subtitulos(self) -> List[Pista]:
        return [p for p in self.pistas if p.tipo == "subtitle"]

    @property
    def adjuntos(self) -> List[Pista]:
        return [p for p in self.pistas if p.tipo == "attachment"]


def _entero(v) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _fraccion(v) -> Optional[float]:
    try:
        n, d = str(v or "0/1").split("/", 1)
        return float(n) / float(d) if float(d) else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def analizar(ruta: Path, cfg=None) -> Medio:
    exe = tools.buscar("ffprobe", cfg, obligatorio=True)
    cmd = [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(ruta)]
    r = tools.ejecutar(cmd, capturar=True, mostrar=False)
    datos = json.loads(r.stdout or "{}")
    fmt = datos.get("format", {})
    medio = Medio(ruta=ruta, duracion=float(fmt.get("duration") or 0), formato=fmt.get("format_name", ""))

    for s in datos.get("streams", []):
        tags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
        disp = s.get("disposition") or {}
        # el bitrate real de una pista mkv suele estar en la etiqueta BPS, no en bit_rate
        bps = s.get("bit_rate") or tags.get("bps") or tags.get("bps-eng")
        kbps = _entero(bps)
        if kbps:
            kbps = int(round(kbps / 1000))
        titulo = tags.get("title", "") or ""
        pista = Pista(
            indice=int(s.get("index", 0)),
            tipo=s.get("codec_type", "data"),
            codec=s.get("codec_name", "?"),
            perfil=s.get("profile"),
            idioma=(tags.get("language") or "und").lower(),
            titulo=titulo,
            canales=_entero(s.get("channels")),
            layout=s.get("channel_layout"),
            kbps=kbps,
            sample_rate=_entero(s.get("sample_rate")),
            duracion=float(s.get("duration") or 0),
            ancho=_entero(s.get("width")),
            alto=_entero(s.get("height")),
            bit_depth=_entero(s.get("bits_per_raw_sample") or s.get("bits_per_sample")),
            fps=_fraccion(s.get("avg_frame_rate") or s.get("r_frame_rate")),
            transfer=s.get("color_transfer"),
            dovi=any("dovi" in str(sd.get("side_data_type", "")).lower().replace(" ", "")
                     or "dolby vision" in str(sd.get("side_data_type", "")).lower()
                     for sd in (s.get("side_data_list") or [])),
            defecto=bool(disp.get("default")),
            forzado=bool(disp.get("forced")),
            sdh=bool(disp.get("hearing_impaired")) or "sordos" in titulo.lower() or "sdh" in titulo.lower(),
        )
        medio.pistas.append(pista)

    # sin etiqueta BPS (mkv creados con ffmpeg, mp4 con AAC…): estimamos leyendo paquetes
    for p in medio.pistas:
        if p.tipo == "audio" and not p.kbps:
            p.kbps = estimar_kbps(ruta, p.indice, cfg)
    _marcar_atmos(ruta, medio)
    return medio


def _marcar_atmos(ruta: Path, medio: "Medio") -> None:
    """Atmos no lo expone ffprobe; MediaInfo sí (commercial_name). Sin libmediainfo, nada."""
    audios = medio.audios
    if not any(a.codec in ("eac3", "truehd") for a in audios):
        return
    try:
        from pymediainfo import MediaInfo
        pistas_mi = MediaInfo.parse(str(ruta), library_file=tools.biblioteca_mediainfo()).audio_tracks
    except Exception:  # noqa: BLE001
        return
    if len(pistas_mi) != len(audios):
        return
    for a, mi in zip(audios, pistas_mi):
        a.atmos = "atmos" in ((mi.commercial_name or "") + " " + (mi.format_additionalfeatures or "")).lower()


def estimar_kbps(ruta: Path, indice: int, cfg=None, segundos: int = 60) -> Optional[int]:
    """Bitrate medio de los primeros `segundos` de la pista, sumando tamaños de paquete."""
    exe = tools.buscar("ffprobe", cfg, obligatorio=True)
    cmd = [exe, "-v", "error", "-select_streams", str(indice), "-read_intervals", f"%+{segundos}",
           "-show_entries", "packet=size,pts_time,duration_time", "-print_format", "json", str(ruta)]
    r = tools.ejecutar(cmd, capturar=True, mostrar=False, comprobar=False)
    try:
        paquetes = json.loads(r.stdout or "{}").get("packets", [])
    except ValueError:
        return None
    if len(paquetes) < 2:
        return None
    total = sum(int(pk.get("size", 0)) for pk in paquetes)
    inicio = float(paquetes[0].get("pts_time") or 0)
    fin = float(paquetes[-1].get("pts_time") or 0) + float(paquetes[-1].get("duration_time") or 0)
    if fin <= inicio:
        return None
    return int(round(total * 8 / (fin - inicio) / 1000))


def id_video_mkvmerge(ruta: Path, cfg=None) -> int:
    """Id de la pista de vídeo según mkvmerge (para --language N:und etc.)."""
    exe = tools.buscar("mkvmerge", cfg, obligatorio=True)
    r = tools.ejecutar([exe, "-J", str(ruta)], capturar=True, mostrar=False, comprobar=False)
    try:
        datos = json.loads(r.stdout or "{}")
        for t in datos.get("tracks", []):
            if t.get("type") == "video":
                return int(t["id"])
    except (ValueError, KeyError):
        pass
    return 0


def listar_videos(carpeta: Path, cfg, recursivo: bool = True, excluir=("temporal", "originals", "originales")) -> List[Path]:
    """Devuelve candidatos que contienen realmente una pista de vídeo.

    La extensión solo reduce los ficheros que hay que inspeccionar. Es
    importante para encodes y rips con pistas elementales (.264/.hevc/.ivf…):
    el códec y el tipo se confirman con ffprobe, no se infieren del nombre.
    """
    exts = {"." + e.lower() for e in cfg["extensiones"]["video"]}
    patron = carpeta.rglob("*") if recursivo else carpeta.glob("*")
    res = []
    for p in patron:
        if p.is_file() and p.suffix.lower() in exts:
            if any(parte.lower() in excluir for parte in p.relative_to(carpeta).parts[:-1]):
                continue
            try:
                if analizar(p, cfg).video:
                    res.append(p)
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
                # Un candidato corrupto o una extensión engañosa no es vídeo.
                # Los validadores del workspace podrán mostrarlo después.
                continue
    return sorted(res)
