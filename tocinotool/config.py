"""Configuración repartida por temas en config/*.yaml.

    config/tool.yaml         usuario, herramientas, instalación (local de cada PC)
    config/idiomas.yaml      idiomas, alias, orden  ← común a todos los pasos
    config/audio.yaml        codecs, canales, orden por calidad, tabla AC3
    config/muxer.yaml        nombres de pista, subtítulos, sueltos
    config/plataformas.yaml  plataformas VOD
    config/renombrado.yaml   FileBot
    config/tracker.yaml      tracker, torrent, ficha
    config/capturas.yaml     capturas

El resto del código accede por clave (`cfg["idiomas"]`, `cfg["bitrates_ac3"]`…)
sin saber en qué fichero está; `guardar()` reescribe solo el fichero al que
pertenece la clave. Los ficheros se crean la primera vez a partir de
tocinotool/config_defaults/, y las claves nuevas de una versión posterior se
añaden solas. Cuando aparece un idioma, codec o plataforma desconocidos, la
tool pregunta y lo guarda en su fichero.
"""
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from . import ROOT, ui

CONFIG_DIR = ROOT / "config"
DEFAULTS_DIR = Path(__file__).with_name("config_defaults")
FICHEROS = ["tool", "idiomas", "audio", "muxer", "release", "plataformas", "renombrado", "tracker", "capturas"]

# secciones de datos que aprende la tool (se reescriben sin comentarios);
# el resto se mezcla en profundidad para añadir claves nuevas sin pisar las del usuario
_SECCIONES_DATOS = {"idiomas", "idiomas_alias", "codecs_audio", "codecs_video", "plataformas", "canales"}


def _leer(ruta: Path) -> Dict[str, Any]:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Config:
    def __init__(self, carpeta: Path = CONFIG_DIR):
        self.carpeta = carpeta
        self.d: Dict[str, Any] = {}
        self._fichero_de: Dict[str, str] = {}   # clave de primer nivel → nombre de fichero
        self._sucios: set = set()
        carpeta.mkdir(parents=True, exist_ok=True)
        self._migrar_tracker(carpeta)
        antiguo = self._migrar_config_antiguo()
        for nombre in FICHEROS:
            defecto = _leer(DEFAULTS_DIR / f"{nombre}.yaml")
            ruta = carpeta / f"{nombre}.yaml"
            if not ruta.exists():
                shutil.copyfile(DEFAULTS_DIR / f"{nombre}.yaml", ruta)
            datos = _leer(ruta)
            # Las versiones 2.1.7/2.1.8 usaron NFO XML de identificación.
            # El panel vuelve a requerir el NFO de texto histórico; se migra
            # al formato distribuido, que no incluye un campo de uploader.
            if nombre == "tracker" and isinstance(datos.get("nfo"), dict):
                datos["nfo"] = defecto.get("nfo", "")
                self._sucios.add(nombre)
                ui.info("Configuración NFO migrada: se usará el NFO de texto del panel, sin uploader.")
            elif nombre == "tracker" and isinstance(datos.get("nfo"), str):
                # También se corrige una plantilla histórica que conservara
                # el campo personal Uploader tras actualizar desde v2.1.6.
                sin_uploader = "\n".join(
                    linea for linea in datos["nfo"].splitlines()
                    if not linea.strip().casefold().startswith("uploader:")
                )
                if sin_uploader != datos["nfo"].rstrip("\n"):
                    datos["nfo"] = sin_uploader.rstrip() + "\n"
                    self._sucios.add(nombre)
                    ui.info("Configuración NFO actualizada: se elimina el campo Uploader.")
            # valores del config.yaml antiguo (v2.0) → su fichero nuevo
            for k in defecto:
                if k in antiguo:
                    datos[k] = antiguo[k]
            if _mezclar(datos, defecto):
                self._sucios.add(nombre)
            for k in defecto:
                self._fichero_de[k] = nombre
            self.d.update(datos)
        if antiguo:
            self._sucios.update(FICHEROS)
        if self._sucios:
            self.guardar()

    @staticmethod
    def _migrar_tracker(carpeta: Path) -> None:
        """Migra una configuración monolítica anterior a tracker.yaml."""
        actual = carpeta / "tracker.yaml"
        if actual.exists():
            return
        # Las primeras versiones guardaban tracker y torrent juntos bajo un
        # nombre particular. Se reconoce por su estructura, no por la marca.
        for anterior in carpeta.glob("*.yaml"):
            if anterior == actual:
                continue
            datos = _leer(anterior)
            if isinstance(datos.get("tracker"), dict) and isinstance(datos.get("torrent"), dict):
                anterior.replace(actual)
                ui.info("Configuración de tracker anterior migrada a tracker.yaml")
                return

    # ------------------------------------------------------------------
    def _migrar_config_antiguo(self) -> Dict[str, Any]:
        """config.yaml único de la v2.0 → config/*.yaml. Deja config.yaml.bak."""
        viejo = ROOT / "config.yaml"
        if not viejo.exists():
            return {}
        datos = _leer(viejo)
        # Tracker único: antes había una lista de trackers.
        if "trackers" in datos and "tracker" not in datos:
            dt = (datos["trackers"] or {}).get("dt") or {}
            datos["tracker"] = {"nombre": "Tracker", "announce": dt.get("announce", ""),
                                "comentario": dt.get("comentario", ""), "sufijo": dt.get("sufijo", "")}
        viejo.rename(ROOT / "config.yaml.bak")
        ui.info("Configuración migrada a config/*.yaml (copia en config.yaml.bak)")
        return datos

    def guardar(self, clave: Optional[str] = None) -> None:
        """Escribe los ficheros con cambios (o el de `clave`)."""
        if clave is not None:
            self._sucios.add(self._fichero_de.get(clave, "tool"))
        for nombre in sorted(self._sucios):
            claves = [k for k, f in self._fichero_de.items() if f == nombre]
            contenido = {k: self.d[k] for k in claves if k in self.d}
            with open(self.carpeta / f"{nombre}.yaml", "w", encoding="utf-8") as f:
                yaml.safe_dump(contenido, f, allow_unicode=True, sort_keys=False, width=120)
        self._sucios.clear()

    def __getitem__(self, clave: str) -> Any:
        return self.d[clave]

    def get(self, clave: str, defecto: Any = None) -> Any:
        return self.d.get(clave, defecto)

    def fichero_de(self, clave: str) -> Path:
        return self.carpeta / f"{self._fichero_de.get(clave, 'tool')}.yaml"

    # ------------------------------------------------------------------
    # Idiomas (config/idiomas.yaml)
    # ------------------------------------------------------------------
    def canon_idioma(self, codigo: Optional[str]) -> str:
        """Código canónico (spa, eng…) para cualquier alias. 'und' si vacío."""
        if not codigo:
            return "und"
        c = codigo.strip().lower()
        if c in self.d["idiomas"]:
            return c
        alias = {str(k).lower(): v for k, v in self.d["idiomas_alias"].items()}
        return alias.get(c, c)

    def es_idioma(self, token: str) -> bool:
        t = token.lower()
        return t in self.d["idiomas"] or t in {str(k).lower() for k in self.d["idiomas_alias"]}

    def nombre_idioma(self, codigo: str, preguntar: bool = True) -> str:
        """Nombre en castellano. Si no existe y `preguntar`, lo pide y lo guarda en idiomas.yaml."""
        c = self.canon_idioma(codigo)
        if c in self.d["idiomas"]:
            return self.d["idiomas"][c]
        if not preguntar:
            return c
        ui.aviso(f"Idioma desconocido: '{codigo}'.")
        nombre = ui.preguntar(f"Nombre en castellano para el idioma '{c}' (se guarda en {self.fichero_de('idiomas').name})",
                              obligatorio=True)
        self.d["idiomas"][c] = nombre
        self.guardar("idiomas")
        ui.ok(f"Guardado: {c} = {nombre}")
        return nombre

    # ------------------------------------------------------------------
    # Codecs (config/audio.yaml, config/muxer.yaml)
    # ------------------------------------------------------------------
    def nombre_codec_audio(self, codec: str, perfil: Optional[str] = None, preguntar: bool = True) -> str:
        if perfil:
            for clave, nombre in self.d.get("codecs_audio_perfil", {}).items():
                if clave.lower() in perfil.lower():
                    return nombre
        c = (codec or "").lower()
        if c in self.d["codecs_audio"]:
            return self.d["codecs_audio"][c]
        if not preguntar:
            return c.upper()
        ui.aviso(f"Codec de audio desconocido: '{codec}' (perfil: {perfil or '-'}).")
        nombre = ui.preguntar(f"Nombre comercial para el codec '{c}' (ej. DD+, TrueHD)", defecto=c.upper())
        self.d["codecs_audio"][c] = nombre
        self.guardar("codecs_audio")
        ui.ok(f"Guardado: {c} = {nombre}")
        return nombre

    def nombre_codec_video(self, codec: str, preguntar: bool = True) -> str:
        c = (codec or "").lower()
        if c in self.d["codecs_video"]:
            return self.d["codecs_video"][c]
        if not preguntar:
            return c.upper()
        ui.aviso(f"Codec de vídeo desconocido: '{codec}'.")
        nombre = ui.preguntar(f"Nombre para el codec de vídeo '{c}' (ej. H265)", defecto=c.upper())
        self.d["codecs_video"][c] = nombre
        self.guardar("codecs_video")
        return nombre

    def etiqueta_canales(self, n: Optional[int]) -> str:
        if n is None:
            return "?"
        tabla = {int(k): v for k, v in self.d["canales"].items()}
        if n in tabla:
            return tabla[n]
        etiqueta = ui.preguntar(f"Etiqueta para {n} canales (ej. 5.1)", defecto=f"{n}.0")
        self.d["canales"][n] = etiqueta
        self.guardar("canales")
        return etiqueta

    # ------------------------------------------------------------------
    # Tabla de conversión a AC3 (config/audio.yaml)
    # ------------------------------------------------------------------
    def sugerir_bitrate_ac3(self, codec: str, kbps: Optional[int], canales: Optional[int]) -> int:
        tablas = self.d["bitrates_ac3"]
        maximo = int(tablas.get("maximo", 640))
        grupo = tablas["2.0"] if (canales or 6) <= 2 else tablas["5.1"]
        tope = 192 if (canales or 6) == 1 else maximo   # mono: no tiene sentido más de 192
        fila = grupo.get((codec or "").lower())
        if not fila or not kbps:
            return min(int(grupo.get("otros", maximo)), tope)
        for origen in sorted(int(k) for k in fila):
            if kbps <= origen:
                return min(int(fila[origen]), tope)
        ultimo = max(int(k) for k in fila)
        return min(int(fila[ultimo]), tope)

    # ------------------------------------------------------------------
    # Plataformas (config/plataformas.yaml)
    # ------------------------------------------------------------------
    def nombre_plataforma(self, tag: str) -> Optional[str]:
        for k, v in self.d["plataformas"].items():
            if str(k).lower() == tag.lower():
                return v
        return None

    def anadir_plataforma(self, tag: str, nombre: str) -> None:
        self.d["plataformas"][tag] = nombre
        self.guardar("plataformas")

    # ------------------------------------------------------------------
    def ruta_herramienta(self, nombre: str) -> str:
        return (self.d.get("herramientas") or {}).get(nombre) or ""


def _mezclar(destino: Dict[str, Any], origen: Dict[str, Any]) -> bool:
    """Añade a `destino` las claves de `origen` que falten (en profundidad, salvo
    en las secciones de datos que gestiona el usuario). Devuelve si cambió algo."""
    cambiado = False
    for k, v in origen.items():
        if k not in destino:
            destino[k] = v
            cambiado = True
        elif isinstance(v, dict) and isinstance(destino[k], dict) and k not in _SECCIONES_DATOS:
            cambiado = _mezclar(destino[k], v) or cambiado
    return cambiado
