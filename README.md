# tociNoTool v2.1.8

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
7. Crear torrent, ficha, NFO de identificación, `info.txt` y capturas.

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
- Si un AC3 ya existe en `temporal/`, se reutiliza después de validar codec,
  bitrate, canales y duración frente a su fuente. Uno incompleto o incompatible
  se avisa y se regenera.
- El muxer aplica idioma, nombre, orden y flags default/forced.
- Todo subtítulo de texto que no sea SRT se convierte a SRT, venga suelto o
  integrado en el contenedor. En WEB-DL solo se conserva además el ASS/SSA
  original, porque aporta posiciones y estilos; WebVTT y otros formatos de
  texto quedan normalizados como SRT.
- En Encode y Blu-ray Rip/Remux se conserva también la fuente original, pero
  cada pista no-SRT debe tener su SRT equivalente. PGS/VobSub son imágenes y
  requieren OCR: si no hay un SRT real correspondiente, la tool detiene el
  mux en vez de inventar subtítulos.
- Si un WEB-DL solo tiene un ASS/SSA español completo, se revisan estilos y
  posicionamiento para extraer carteles reales como SRT y ASS forzados.
- Si no existe ninguna pista española marcada como forzada y solo hay una
  fuente SRT española completa o SDH, la tool puede detectar carteles escritos
  mayoritariamente en MAYÚSCULAS. Lo avisa y pregunta antes de crear un SRT
  forzado; el SRT completo/SDH original siempre se conserva. Si hay completo y
  SDH, prueba primero el completo; con varias fuentes iguales no propone nada.
  No se hace esta inferencia desde WebVTT ni cuando ya hay un forzado español.
- Los WebVTT de plataformas se convierten directamente a SRT: se conserva el
  texto y la cursiva, pero no las clases de color/fondo ni el posicionamiento
  básico de WebVTT. Un nombre como `.forced.vtt` mantiene el flag forzado.
- Si un MP4 trae dos subtítulos españoles sin flag `forced`, el muxer compara
  sus cues: una pista muy corta frente a otra completa se propone como
  forzada. Es una regla conservadora y el plan sigue siendo editable.
- Si una plataforma etiqueta una pista como `spa`/`es-ES` pero su texto se
  detecta como latino, el plan muestra un aviso. Antes de confirmar puedes
  responder **No**, elegir la pista y usar **i — cambiar idioma** para dejarla
  como Castellano si la detección no corresponde.
- Un título de pista explícito como `Castellano` o `Español latino` prevalece
  sobre la inferencia por texto.
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
| 6 | Generar ficha BBCode, NFO de identificación e `info.txt`. |
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
| `tracker.yaml` | Tracker, torrent, ficha BBCode y NFO de identificación. |
| `capturas.yaml` | Capturas y tonemapping. |

`tocinotool/es.csv` solo traduce etiquetas de MediaInfo para la ficha; no define
idiomas, codecs ni reglas del muxer.

### NFO de identificación

La opción **Ficha** genera NFO XML estándar además de la ficha BBCode. No es
la ficha legible del tracker: sirve para que un panel, Emby o Plex pueda saber
qué obra contiene el release. FileBot aporta los IDs de TMDb, TheTVDB e IMDb;
si no está disponible, el enlace manual solicitado deja al menos el ID de
TMDb en películas o IMDb en series.

| Contenido | NFO generados |
|---|---|
| Película | `<release>.nfo` con `<movie>` e IDs de película. |
| Capítulo | `<release>.nfo` con `<episodedetails>` y `tvshow.nfo` con los IDs de la serie. |
| Temporada completa | `tvshow.nfo`, `season.nfo` y un `<capítulo>.nfo` junto a cada MKV. |

Los IDs que FileBot entrega para una serie identifican la serie, no cada
episodio. Por eso los capítulos llevan título, temporada y número, mientras
los IDs se escriben una vez en `tvshow.nfo`; no se inventan IDs de episodios.
Si no hay ningún ID, se crea el NFO con tipo y título y la tool lo avisa.

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

## Actualizaciones de Windows

Una actualización diferencial contiene un ZIP y un archivo
`Actualizar-tociNoTool-vX.Y.Z.bat`. Copia ambos a la raíz de la instalación
(junto a `launcher.bat`) y ejecuta el BAT con la tool cerrada. Antes de copiar
nada indica versión de origen, lista los archivos que cambiarán y pide
confirmación. Conserva `config/`, `.venv/` y `logs/`; al terminar borra el ZIP
y deja solo el BAT, que ya se puede eliminar.

Para generar una actualización al publicar una versión, el mantenedor usa
`herramientas/generar_actualizacion.ps1`, comparando las dos carpetas completas
de distribución. También detecta archivos nuevos y, si algún día cambian,
binarios; nunca empaqueta la configuración particular.

Para usuarios de una versión antigua sin una base intermedia disponible, el
mantenedor puede usar `-Acumulativa -BaseVersion X.Y.Z`. Genera un paquete de
código y plantillas compatible con esa versión, sin volver a descargar los
binarios portables ni tocar datos locales.

## Documentación del proyecto

En el repositorio de GitHub se mantienen también `MEMORIA.md` (estado técnico y
decisiones a conservar) y `BITACORA.md` (historial cronológico). Esos documentos
son de desarrollo y no se incluyen en el paquete de uso.
