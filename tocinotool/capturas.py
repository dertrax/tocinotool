"""Capturas para el tracker.

Mejoras respecto a la v1 (minutos fijos 5:40, 14:25… que fallaban en capítulos
cortos y salían negras o lavadas en HDR):
  * posiciones en % de la duración (config capturas.porcentajes)
  * en cada posición ffmpeg elige el fotograma más representativo de los
    siguientes N (filtro `thumbnail`): evita fundidos a negro y planos vacíos
  * HDR10 / HLG → SDR con tonemapping para que no salgan grises
  * 4K → 1080p opcional (capturas.ancho_max) para que no pesen tanto
  * PNG (sin pérdida) o JPG (capturas.formato / calidad_jpg)
  * en el flujo se generan solas: una tanda por release (película o capítulo;
    para una temporada, del primer episodio) en la carpeta capturas/
"""
from pathlib import Path
from typing import List, Optional

from . import probe, tools, ui

# HDR10/HLG → SDR BT.709. Requiere ffmpeg con zscale (libzimg); las builds
# "full" de gyan.dev y los paquetes de Debian/Ubuntu lo incluyen.
_TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
            "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def capturar(video: Path, cfg, destino: Optional[Path] = None, prefijo: Optional[str] = None) -> List[Path]:
    c = cfg["capturas"]
    ffmpeg = tools.buscar("ffmpeg", cfg, obligatorio=True)
    medio = probe.analizar(video, cfg)
    if not medio.duracion:
        ui.error(f"No se puede leer la duración de {video.name}")
        return []
    v = medio.video
    destino = destino or (video.parent / str(c.get("carpeta") or "capturas"))
    destino.mkdir(parents=True, exist_ok=True)
    prefijo = prefijo or video.stem

    filtros = []
    if v is not None and v.es_hdr and c.get("tonemap_hdr", True):
        if tools.ffmpeg_tiene_filtro("zscale", cfg):
            filtros.append(_TONEMAP)
            ui.info("Vídeo HDR: tonemapping a SDR" + (" (DoVi perfil 5 puede quedar verdoso con este ffmpeg)" if v.dovi else ""))
        else:
            ui.aviso("Vídeo HDR pero este ffmpeg no tiene el filtro zscale: las capturas saldrán lavadas.")
    # el fotograma más representativo de los siguientes N: evita negros y fundidos
    filtros.append(f"thumbnail={int(c.get('candidatos', 40))}")
    ancho_max = int(c.get("ancho_max") or 0)
    if ancho_max > 0:
        filtros.append(f"scale='min(iw,{ancho_max})':-2")

    formato = str(c.get("formato", "png")).lower()
    salidas = []
    posiciones = [float(p) for p in c["porcentajes"]]
    for i, pct in enumerate(posiciones, 1):
        t = medio.duracion * pct / 100.0
        out = destino / f"{prefijo}-{i}.{formato}"
        cmd = [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video),
               "-map", "0:v:0", "-vf", ",".join(filtros), "-frames:v", "1"]
        if formato in ("jpg", "jpeg"):
            q = int(c.get("calidad_jpg", 92))
            cmd += ["-q:v", str(max(2, min(31, round(31 - (q / 100) * 29))))]
        else:
            cmd += ["-compression_level", "6"]
        cmd.append(str(out))
        tools.ejecutar_silencioso(cmd)
        salidas.append(out)
    total_kb = sum(s.stat().st_size for s in salidas) // 1024
    ui.ok(f"{len(salidas)} capturas de {video.name} ({total_kb // len(salidas)} KB/u) → {destino.name}/")
    return salidas


def capturar_releases(cfg, carpeta: Path) -> List[Path]:
    """Una tanda por release de la carpeta: mkv sueltos y, en carpetas de
    temporada, el primer episodio. Salida en carpeta/capturas/<release>-N.png"""
    from .renombrar import entradas_carpeta
    destino = carpeta / str(cfg["capturas"].get("carpeta") or "capturas")
    salidas = []
    for e in entradas_carpeta(carpeta):
        if e.is_dir():
            primero = next(iter(sorted(e.rglob("*.mkv"))), None)
            if primero is None:
                continue
            salidas += capturar(primero, cfg, destino, prefijo=e.name)
        else:
            salidas += capturar(e, cfg, destino)
    return salidas


def flujo(cfg, carpeta: Optional[Path] = None) -> Optional[Path]:
    ui.titulo("CAPTURAS")
    if carpeta is None:
        carpeta = ui.preguntar_carpeta(cfg, "De qué sacar capturas", admitir_fichero=True)
    if carpeta.is_file():
        capturar(carpeta, cfg)
        return carpeta.parent
    videos = probe.listar_videos(carpeta, cfg)
    if not videos:
        ui.error("No hay vídeos en la carpeta.")
        return None
    from .torrent import entradas_carpeta, tipo_release
    releases = entradas_carpeta(carpeta)
    if len(videos) == 1:
        capturar(videos[0], cfg)
        return carpeta
    tipos = [tipo_release(e) for e in releases]
    ui.tabla(["tipo", "release"], [[t, e.name + ("/" if e.is_dir() else "")] for e, t in zip(releases, tipos)][:12])
    r = ui.preguntar_opcion("¿De qué sacar capturas?", [
        ("release", f"una tanda por release ({len(releases)}): temporada = su primer episodio"),
        ("todos", f"de todos los vídeos ({len(videos)})"),
        ("elegir", "elegir vídeos"),
    ], defecto="release")
    if r == "release":
        capturar_releases(cfg, carpeta)
        return carpeta
    if r == "todos":
        elegidos = videos
    else:
        claves = ui.preguntar_multi("Vídeos", [(str(i), v.name) for i, v in enumerate(videos)], marcadas=["0"])
        elegidos = [videos[int(k)] for k in claves]
    for v in elegidos:
        capturar(v, cfg)
    return carpeta
