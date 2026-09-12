# tociNoTool v2.1.3

Herramienta de preparación de releases para la comunidad scene en español.
Convierte audio a AC3,
multiplexa pistas, verifica MKV, renombra con FileBot cuando está disponible,
crea torrents, genera fichas BBCode y capturas.

> Este archivo se renderiza como Markdown al abrirlo en GitHub. En Windows,
> un `.md` se abrirá con la aplicación que el usuario tenga asociada; para verlo
> renderizado localmente se necesita un visor de Markdown.

## Inicio rápido en Windows

1. Extrae el paquete en una carpeta propia, por ejemplo `C:\tociNoTool`.
2. Ejecuta `launcher.bat`.
3. En el primer inicio elige **Ejecutar tociNoTool**.
4. Completa el asistente de instalación.
5. En el menú principal selecciona **1 — PREPARAR RELEASE**.

La instalación es autocontenida: `.venv/` y `config/` se crean junto a la
tool. Para reiniciarla se pueden borrar ambas carpetas; no se modifican entornos
Python de otros proyectos.

## Binarios: paquete o repositorio

El **ZIP de distribución para Windows** incluye las versiones portables de
FFmpeg, MKVToolNix y MediaInfo dentro de `binaries/`, por lo que no hay que
instalarlas por separado.

El **repositorio de GitHub** contiene solo código y plantillas: los binarios no
se suben porque FFmpeg supera el límite de tamaño de GitHub. Si se clona el
repositorio en lugar de usar el ZIP, ejecuta `launcher.bat` y el asistente
localizará o instalará las herramientas necesarias.

Para reconstruir exactamente los binarios incluidos en esta versión, consulta
[BINARY_MANIFEST.md](BINARY_MANIFEST.md): fija versiones, fuentes, estructura y
hashes SHA-256.

## Asistente de instalación

El asistente revisa Python, FFmpeg, MKVToolNix, MediaInfo y FileBot. En el ZIP
de Windows, FFmpeg, MKVToolNix y MediaInfo ya están incluidos. Por tanto, allí
la única dependencia externa imprescindible es Python; FileBot es opcional para
el renombrado automático.

Cuando muestra **instalar automáticamente con winget**, `winget` es el gestor
de paquetes de Windows: descarga e instala una herramienta desde su catálogo.
No es obligatorio. Si falta, no hay conexión o la instalación falla, el
asistente permite reintentar, abrir la descarga oficial cuando exista, indicar
la ruta del ejecutable o posponerla.

Si se ha clonado el repositorio y no hay `binaries/`, el asistente ofrece
instalación automática con `winget` para FFmpeg y MKVToolNix, o abre las páginas
oficiales de [FFmpeg](https://ffmpeg.org/download.html),
[MKVToolNix](https://mkvtoolnix.download/downloads.html),
[MediaInfo](https://mediaarea.net/MediaInfo/Download/Windows) y FileBot. Tras
una instalación o extracción manual, vuelve al asistente e indica la ruta del
ejecutable si Windows todavía no lo detecta automáticamente.

Los fallos se guardan en `logs/`; la opción `l` del menú abre esa carpeta.
También se registra un informe básico si falla el launcher antes de iniciar
Python. Los informes no incluyen licencias, cookies ni credenciales.

## FileBot: opcional

FileBot solo se utiliza para el renombrado automático. Si no está instalado o
no tiene licencia, la tool sigue pudiendo convertir, multiplexar y verificar.
El asistente lo marca como **pendiente** y se puede repetir más adelante.

La licencia es personal: puede usarse en varios equipos del mismo usuario, pero
no compartirse entre personas.

Sin FileBot, renombra el resultado manualmente y usa **6 — Ficha**:

- Película: pedirá el enlace de TMDb.
- Serie: pedirá el enlace de IMDb.

Los enlaces son opcionales; ENTER genera la ficha sin ellos. Si FileBot ya
aportó el identificador adecuado, no se pregunta nada.

## Preparar un release

La opción **1 — PREPARAR RELEASE** acepta una carpeta de trabajo o un MKV
suelto. Con un MKV procesa exclusivamente ese contenedor.

1. Elegir perfil: WEB-DL, Encode/MicroHD o Blu-ray Rip/Remux.
2. Indicar película, capítulo o temporada y, en WEB-DL, la plataforma.
3. Convertir los audios necesarios a AC3.
4. Ejecutar el muxer: ordena, nombra y marca las pistas.
5. Verificar el MKV final.
6. Renombrar con FileBot, si tiene una licencia válida. Anime con numeración
   continua (por ejemplo, `S02E25…S02E48`): si FileBot reparte los capítulos
   en otras temporadas, la tool repite la prueba limitada a la temporada del
   nombre (`S02E25 → S02E01`).
7. Crear torrent, ficha, `.nfo`, `info.txt` y capturas.

Los originales quedan en `originales/` después de validar el MKV final. Los derivados van a `temporal/` y solo
se limpian tras una verificación correcta.

### Series sin FileBot

La opción **8 — Parser de series** funciona sin FileBot: detecta `SxxExx` y
`1x02`, muestra un resumen de correlación (primer archivo, último y rango) y
avisa de episodios faltantes sin renumerarlos. Si los nombres no aportan datos
suficientes, permite indicar nombre de serie, temporada y primer episodio.
Una URL de IMDb, TMDb, TheTVDB u otro sitio puede guardarse como referencia,
pero no se usa scraping ni una API externa obligatoria.

### Audio y subtítulos

- Se reconocen AVC/H.264, HEVC/H.265 y AV1.
- El audio se convierte a AC3 según `config/audio.yaml`.
- El muxer aplica idioma, nombre, orden y flags default/forced.
- ASS/SSA se conserva y se convierte también a SRT. Los carteles posicionados
  producen variantes forzadas ASS y SRT.
- Los WebVTT de plataformas se convierten directamente a SRT: se conserva el
  texto y la cursiva, pero no las clases de color/fondo ni el posicionamiento
  básico de WebVTT. Un nombre como `.forced.vtt` mantiene el flag forzado.
- Si un MP4 trae dos subtítulos españoles sin flag `forced`, el muxer compara
  sus cues: una pista muy corta frente a otra completa se propone como
  forzada. Es una regla conservadora y el plan sigue siendo editable.
- El orden de subtítulos es: SRT forzado, SRT completo, ASS forzado, ASS
  completo y después otros formatos compatibles.

## Menú

| Opción | Función |
|---|---|
| 1 | PREPARAR RELEASE: flujo completo. |
| 2 | Convertir audios a AC3. |
| 3 | Muxer: ordenar, nombrar y marcar pistas. |
| 4 | Renombrar con FileBot. |
| 5 | Crear `.torrent`. |
| 6 | Generar ficha BBCode, `.nfo` e `info.txt`. |
| 8 | Parser de series y correlación sin FileBot. |
| v | Verificar pistas, flags, duración, título y adjuntos. |
| 7 | Limpieza de archivos. |
| 9 | Juntar vídeo de un MKV con audios/subtítulos de otro. |
| 0 | Capturas, con tonemapping HDR si hace falta. |
| c | Configuración. |
| l | Abrir informes de error. |
| q | Salir. |

Las carpetas y MKV se pueden arrastrar a la consola. Los selectores se manejan
con flechas y ENTER; `Ctrl+C` o `q` cancela de forma segura.

## Configuración

`config/` se crea a partir de `tocinotool/config_defaults/`. La primera carpeta
es local de cada equipo; la segunda contiene las plantillas distribuidas.
La URL announce y el comentario del tracker se rellenan únicamente en
`config/tracker.yaml`: no están en el código ni se suben al repositorio.

| Archivo | Propósito |
|---|---|
| `tool.yaml` | Usuario, rutas manuales y estado local de instalación. |
| `idiomas.yaml` | Idiomas, alias y orden. |
| `audio.yaml` | Codecs, canales, calidad y bitrates AC3. |
| `muxer.yaml` | Nombres de pista, subtítulos y componentes sueltos. |
| `release.yaml` | Perfiles WEB-DL, Encode y Blu-ray. |
| `plataformas.yaml` | Tags de plataforma y sus nombres. |
| `renombrado.yaml` | Plantillas y grupos de FileBot. |
| `tracker.yaml` | Tracker, torrent y plantillas de ficha. |
| `capturas.yaml` | Capturas y tonemapping. |

`tocinotool/es.csv` solo traduce etiquetas de MediaInfo para la ficha; no define
idiomas, codecs ni reglas del muxer.

### Configurar `tracker.yaml`

En el primer arranque se crea `config/tracker.yaml`. Ábrelo con un editor de
texto y completa únicamente los datos que use tu tracker:

```yaml
tracker:
  nombre: "Nombre del tracker"
  announce: "https://ejemplo/announce"
  comentario: ""     # opcional; admite {infohash}
  sufijo: ""         # opcional; se añade al nombre del .torrent
```

La URL `announce` es necesaria para crear torrents. Este archivo es privado de
cada equipo: no lo compartas, no lo adjuntes a informes y no lo subas a GitHub.
Si vienes de una versión anterior, la tool mueve automáticamente el archivo de
configuración anterior a `config/tracker.yaml` sin perder tus ajustes.

Si un tracker añade campos dentro de `info` al aceptar un torrent, decláralos
en `torrent.campos_info`. Es importante hacerlo antes de crear el torrent,
porque esos campos cambian su `infohash`. Usa únicamente los campos que el
tracker documente; por ejemplo:

```yaml
torrent:
  campos_info: {origen: "https://tracker.ejemplo"}
```

## Compartir mejoras

El proyecto se comparte para la comunidad. Documenta mejoras o errores y
propónlos a **jascott** por Telegram: **@jascott**. No incluyas credenciales,
licencias, cookies, rutas personales ni contenido de releases en los informes.

## Documentación del proyecto

En el repositorio de GitHub se mantienen también `MEMORIA.md` (estado técnico y
decisiones a conservar) y `BITACORA.md` (historial cronológico). Esos documentos
son de desarrollo y no se incluyen en el paquete de uso.
