# Bitácora — tociNoTool v2

Historial cronológico de cambios. Para el manual público consultar
[README.md](README.md); para el estado técnico vigente, [MEMORIA.md](MEMORIA.md).
Última actualización: 2026-09-12.

## 2026-09-12 — Publicación 2.1.1

- Se publica la corrección para trackers que añaden metadatos al diccionario
  `info`; estabiliza el `infohash` y el enlace del comentario.
- Se actualiza el paquete de Windows a `tociNoTool-v2.1.1-windows.zip`.

## 2026-09-12 — Hash estable en trackers con metadatos

- Se incorpora `torrent.campos_info`: campos opcionales del diccionario
  `info` que un tracker añade al aceptar el torrent. Se escriben antes de
  calcular `{infohash}` en el comentario.
- La configuración local puede declarar los metadatos que el tracker inserta
  al subir. Al formar parte de `info`, cambiarían el hash y dejarían roto el
  enlace generado previamente si no se anticipan.

## 1. Contexto

- Herramienta para preparar releases de la comunidad scene en español: mkv con
  audio castellano en AC3, pistas ordenadas y nombradas según plantilla,
  nombre scene con FileBot, `.torrent`, ficha BBCode para el foro, `.nfo`,
  `info.txt` con enlaces y capturas.
- Usuario y grupos: configuración local de cada instalación.
- Historia: `AutoMuxerCli.exe` (2021, .NET, sin código fuente) → `dogtool`
  (Python: FileBot + torf + fill_dt) → `tociNoTool-1.7.5.bat` (menú batch que
  encadenaba todo, "un apaño"). Todo eso está en `_legacy/` y
  `binaries/_legacy/` solo como referencia; **no se usa**.
- v2 (2026-09-11): reescritura completa en Python (`tocinotool/`), Windows y
  Linux, configuración por ficheros, flujo continuo con decisiones al principio.

## 2. El flujo de trabajo (lo que hay que entender primero)

Entrada: una carpeta de trabajo con uno o varios mkv "más o menos limpios"
(vídeo, audio castellano normalmente DD+, catalán opcional, V.O. y V.O.2
opcional —nunca más de 3 audios—, subtítulos V.O. y castellano normal/SDH,
catalán opcional), con los **idiomas tageados** pero desordenados. Los sueltos
(`Peli.es.forced.srt`, `Peli.[spa].ac3`…) con el mismo nombre también valen.

Opción 1 del menú, **PREPARAR RELEASE** (`release.py`):

1. Decisiones **al principio**, con selector (flechas + ENTER) y la propuesta ya marcada:
   - **origen**: `webdl` (originales + AC3) · `rip` (pista de calidad DTS/TrueHD + AC3)
     · `encode` (una pista por idioma, solo AC3). Propuesta: nombre con WEB-DL →
     webdl; si no, settings x264/x265 en el vídeo → encode; DTS/TrueHD/PCM o
     BluRay en el nombre → rip.
   - **contenido**: película · capítulo(s) · temporada(s) completa(s). Propuesta
     por `SxxExx` / `1x01` / carpetas `S01`/`Temporada`. Varias temporadas a la
     vez valen (FileBot crea una carpeta por temporada).
   - **plataforma** (solo WEB-DL): **siempre se pregunta** con el listado de
     `config/plataformas.yaml`; nunca se deduce (decisión del usuario).
2. **Estado de las pistas**: si cada idioma ya tiene AC3 y la verificación pasa
   (mkv que viene de "Juntar" o de una pasada anterior) → se saltan convertir y
   muxer. Si hay AC3 pero orden/nombres no cumplen → solo muxer.
3. **Convertir** (`ac3.py`): todos los audios a AC3 con el bitrate de la tabla
   (`config/audio.yaml → bitrates_ac3`). WEB-DL: sin preguntar. rip/encode:
   todas / elegir (multi-selector) / ajustar bitrate. 7.1 → 5.1 (`-ac 6`), mono
   máx. 192. Si ya es AC3 al bitrate correcto se copia. Los .ac3 van a `temporal/`
   y **el mkv lo monta el muxer** (paso 4) en la misma pasada: no hay remux
   intermedio que pueda perder pistas.
4. **Muxer** (`mux.py`, sustituye a AutoMuxerCli y CUSTOMcode): un plan con las
   pistas internas + sueltos + (opcionalmente) otro contenedor. Orden: idioma
   (`orden_idiomas`) → calidad de códec (`orden_codecs_audio`: DD+ Atmos, DD+,
   DD…) → orden original. Default = primer audio; subs forzados en castellano
   default+forced. Nombres `Castellano DD+ 7.1 @ 640 kbps`, `Inglés DD+ Atmos
   5.1 @ 768 kbps`, `Inglés [Para Sordos]`. Vídeo `und` sin nombre, sin título
   global, sin adjuntos, capítulos conservados. Se enseña el plan una vez
   (editable con selector) y se aplica a todos. Barra de progreso de mkvmerge.
   Los subtítulos que mkvmerge no lee (mov_text de mp4) se extraen con ffmpeg;
   los sueltos se limpian/convierten (`subs.py`). Guardia: nº de pistas del mkv
   == plan. Ficheros de origen → `originales/` (nunca se borran).
5. **Verificación** (`verificar.py`): 13 comprobaciones (contenedor legible,
   sin título/adjuntos, vídeo `und`, idiomas en todas las pistas, un solo
   audio default y primero, subs default solo forzados, orden, nombres según
   plantilla, duración audios ≈ vídeo…). "Sin castellano" es aviso, no error.
   Si falla, el flujo para y conserva `temporal/` y `originals/`.
6. **Renombrar** (`renombrar.py`): una sola llamada a FileBot con toda la
   carpeta (o un mkv suelto). No pregunta nada más: tipo `web`/`web4k` por
   resolución (rip/encode: selector de tipo), grupo por regla configurable.
   Muestra solo `origen → destino` del `test`;
   confirmar → `move`. Si no acierta: id, inglés, otra base de datos.
   Temporadas: crea una carpeta de temporada con la nomenclatura configurada.
   OJO: FileBot devuelve código ≠ 0 aunque el test vaya bien; se juzga por las
   líneas `[TEST] from … to …`.
7. **Torrent, ficha, .nfo, info.txt y capturas: automáticos, sin preguntas**
   (`torrent.py`, `ficha.py`, `metadatos.py`, `capturas.py`). `info.txt` lleva
   el título tal como va en la ficha del tracker + enlaces TMDB/IMDb (de los
   metadatos xattr que FileBot deja al renombrar) + FilmAffinity (buscador web,
   por título+año). Una tanda de capturas por release (temporada: primer
   episodio) en `capturas/`.
8. `temporal/` (derivados) se borra si la verificación fue correcta. `originales/`
   **nunca** se borra: se avisa al final para que el usuario lo quite a mano.

Resultado para una película WEB-DL: 5 entradas del usuario (origen ENTER,
contenido ENTER, plataforma, plan ENTER, nombre FileBot ENTER).

**Juntar** (opción 9): la IMAGEN de un mkv extranjero + los AUDIOS/SUBTÍTULOS
de tu mkv preparado, en los dos sentidos (4K extranjero + 1080p preparado, o
1080p extranjero + 4K preparado). Acepta fichero o carpeta (busca en
subcarpetas), comprueba duración y fps antes de juntar, plan con columna
EXTRANJERO/PREPARADO para quitar duplicados, y ofrece seguir con PREPARAR
RELEASE (que detecta las pistas ya preparadas y salta al renombrado).

Las opciones sueltas (convertir, muxer, renombrar, torrent, info, verificar,
capturas) aceptan arrastrar **un mkv o una carpeta**. El submenú **Limpieza de
archivos** limpia mkv extranjeros (solo V.O. con multi-selector de los idiomas
presentes; o adjuntos/título/datos de vídeo). Nota: el muxer y Juntar ya hacen
esta limpieza, así que la segunda opción solo tiene sentido fuera del flujo.
Ojo con la GUI de MKVToolNix: rellena "Título del archivo" con el nombre del
fichero aunque el contenedor no tenga título; para comprobarlo de verdad, usar
la opción Verificar o `mkvmerge -J`.

## 3. Arquitectura

```
tocinotool/
  __main__.py     menú (selector); arranca entorno.asegurar() antes de importar nada más
  entorno.py      crea el venv fuera del repo (%LOCALAPPDATA%/tocinotool/venv o
                  ~/.local/share/tocinotool/venv), instala requirements.txt y
                  relanza dentro. tocinotool.bat/.sh solo garantizan que exista Python.
  asistente.py    primer arranque: deps, herramientas (winget/apt/brew o ruta a
                  mano), usuario, licencia FileBot (.psm → filebot --license)
  config.py       carga config/*.yaml en un dict; cada clave sabe su fichero;
                  guardar(clave) reescribe solo ese fichero. Aprende idiomas,
                  codecs, canales y plataformas desconocidos preguntando.
  config_defaults/  defaults con comentarios; se copian a config/ la 1ª vez;
                  las claves nuevas se mezclan (secciones de datos no se tocan)
  tools.py        localizar ejecutables (config → PATH → binaries/ en Windows →
                  rutas conocidas); ejecutar / ejecutar_silencioso /
                  ejecutar_mkvmerge (barra de progreso ui.Barra); DETALLADO = mostrar comandos
  probe.py        ffprobe JSON → Medio/Pista; bitrate estimado por paquetes si no
                  hay tag BPS; Atmos vía pymediainfo; id de vídeo de mkvmerge
  ui.py           preguntas: selectores (questionary) — preguntar_opcion,
                  preguntar_multi, preguntar_sn (también selector), preguntar_idioma,
                  preguntar_ruta (arrastrar; tolera texto colado), preguntar_carpeta
                  (carpeta o mkv); respaldo numérico sin TTY; Ctrl+C/q sale
  release.py      flujo continuo (Contexto: origen/contenido/vod; detección de estado)
  ac3.py mux.py verificar.py renombrar.py torrent.py ficha.py capturas.py limpiar.py
  metadatos.py    ids TMDB/IMDb (xattr de FileBot) y ficha de FilmAffinity (buscador web)
  subs.py         limpieza/conversión de subtítulos, idioma y variante es/latino por texto
  es.csv          idioma de MediaInfo para la ficha (vía pymediainfo)
config/           tool, idiomas, audio, muxer, plataformas, renombrado, tracker, capturas
binaries/         ffmpeg (2021), ffprobe, mkvmerge 51, mkvpropedit — reserva Windows
_legacy/, binaries/_legacy/   v1 (bat, AutoMuxerCli, dogtool…), solo referencia
```

Puntos técnicos que conviene saber:

- **Ids de pista**: mkvmerge y ffprobe numeran igual salvo con adjuntos;
  `mux.pistas_contenedor` empareja `mkvmerge -J` con ffprobe por posición.
- **Bitrate**: ffprobe no lo da en mkv sin tag `BPS` (ficheros hechos con
  ffmpeg); `probe.estimar_kbps` lee 60 s de paquetes.
- **Atmos**: ffprobe no lo expone; `probe._marcar_atmos` usa pymediainfo
  (`commercial_name`). Afecta al nombre (`DD+ Atmos`) y al orden por calidad.
- **mp4 de Crunchyroll**: mkvmerge 51 no ve los subtítulos mov_text ni distingue es-ES de
  es-419; el muxer los extrae con ffmpeg y decide la variante por el texto (`subs.py`).
- **Subtipo de subtítulo interno**: flag forced / hearing_impaired / palabras
  del título (`forz`, `sdh`, `sordos`, `cc`). Sueltos: tokens del nombre
  (`config/muxer.yaml → subtitulos.palabras`; `stripped_sdh` = completos).
- **Salida compacta**: una línea por fichero; comandos ocultos salvo
  `mostrar_comandos: true` en `config/tool.yaml`; con un solo fichero la
  verificación se muestra completa, con varios solo los fallos.
- **Capturas**: `-ss` + filtro `thumbnail=40` (fotograma representativo, evita
  negros), tonemap HDR10/HLG con zscale, `scale` a 1920 opcional. DoVi perfil 5
  necesita un ffmpeg más nuevo que el de `binaries/`.
- **ffmpeg con `-nostdin`**: si no, se come las teclas pulsadas durante la conversión.
- **FileBot** exige licencia válida incluso en `--action test`, y devuelve
  código ≠ 0 en test aunque vaya bien.
- **Encoding**: `PYTHONUTF8=1` + `reconfigure(utf-8)` en `__main__`.
- **Rutas**: todo va por listas de argumentos (sin shell): espacios, acentos,
  `&`, `#`, corchetes y paréntesis probados. Excepción teórica: `{ }` en la
  carpeta de trabajo rompería el formato Groovy de FileBot.
- **Al editar el código con scripts**: escribir los ficheros con una
  herramienta que preserve `\\` (los heredocs de bash convirtieron `\\b` en
  retroceso y `[\\/]` en `[\/]` dos veces; se detectó y corrigió).

## 4. Verificado en real (2026-09-11)

- **Película WEB-DL 1080p** (dos audios DD+ y tres subtítulos): flujo completo
  con FileBot real, conversión AC3, muxer, verificación 13/13, renombrado,
  torrent, ficha, `.nfo`, `info.txt` y capturas.
- **Juntar 4K + flujo completo**: fuente 4K HEVC DV/HDR10 y vídeo 1080p
  preparado, con verificación 13/13, torrent, ficha, NFO y capturas HDR con
  tonemapping correcto.
- Releases finales y fuentes de prueba: solo en rutas locales, no publicadas.
- Flujo completo (sin FileBot) con 2-3 capítulos sintéticos, mkv solo V.O.,
  nombres con símbolos, carpetas mixtas (release/temporada/mkv): correcto.

## 5. Pendiente / siguientes pasos

1. **Temporada completa con FileBot real**: que la carpeta `Serie.S01.…` se cree
   donde toca y que torrent/ficha/capturas la cojan.
3. **Linux**: nada probado aún. Debería funcionar con `apt install ffmpeg
   mkvtoolnix mediainfo libmediainfo0v5 python3-venv` + FileBot instalado;
   `tocinotool.sh` o `python3 -m tocinotool`.
4. **Actualizar `binaries/`** al cerrar la tool (ffmpeg 2021 → actual, para DoVi;
   mkvmerge 51 → actual). Con `winget install Gyan.FFmpeg
   MoritzBunkus.MKVToolNix` el PATH tiene prioridad sobre `binaries/`.
5. Dudas de negocio sin cerrar: tag para iTunes (`iT`?) en plataformas; a qué
   grupo van las películas BluRay 1080p (antes `TBd`, ahora `TMd`); formato de
   nombre para pelis (`DD+7.1` sale porque audio[0] es el DD+ original, como en
   dogtool) — se decide en `config/renombrado.yaml` sin tocar código.
6. Mejoras posibles: preservar comentarios en `config/*.yaml` al guardar
   (el fichero que aprende un dato se reescribe sin comentarios); ajuste de
   retardo/velocidad de audio cuando "Juntar" detecta desincronía; `.nfo` con
   el formato que pida el panel nuevo cuando exista.

## 6. Reglas de interacción (auditadas sobre las 62 preguntas del código)

- Nada de escribir cuando hay opciones: selector (flechas + ENTER) con la propuesta
  marcada; multi-selector (ESPACIO) para elegir varios; sí/no también es selector.
- Todo lo detectable se detecta y solo se confirma: origen, contenido, grupo, tipo web/web4k,
  estructura de carpetas de la ficha, idiomas presentes en un fichero, estado de las pistas.
- Texto libre solo para datos nuevos: rutas (arrastrar; tolera texto colado delante),
  nombre de un idioma/plataforma nuevo, id de TMDB, bitrate si se elige ajustarlo.
- Idiomas siempre por selector del config (`ui.preguntar_idioma`), nunca escribir códigos.
- Con muchos ficheros: cantidad y resumen del primero; una línea por fichero; sin comandos.
- **Nunca borrar originales automáticamente**: van a `originales/` y los quita el usuario.
- Vocabulario para el usuario: "mkv extranjero" (pone la imagen) / "mkv preparado" (pone
  audios y subtítulos); no usar "pilar" ni jerga interna en pantalla.
- Al añadir una pregunta nueva: pasar por esta lista antes, no heredar el estilo del bat.
- Método: revisar de forma sistemática todas las interacciones con estos criterios antes
  de entregar, no corregir una a una según se quejen.

## 7. Historial de cambios

Regla: **cada cambio o mejora se anota aquí en el momento** (y en la memoria del
asistente), no al final. Formato: fecha · qué · por qué / efecto.

- 2026-09-11 · Reescritura v2 en Python: menú, flujo continuo, config por ficheros,
  venv automático, asistente de instalación, verificación, torrent, ficha, capturas.
- 2026-09-11 · AC3: en WEB-DL se conservan los originales y se añaden los AC3 (antes
  sustituía); todos los idiomas se convierten sin preguntar. Corregido tras ver la tool
  antigua en la terminal del usuario.
- 2026-09-11 · Muxer: orden por idioma → calidad de códec (igual que AutoMuxerCli),
  nombres `kbps`, Atmos detectado por pymediainfo; sustituye también a CUSTOMcode y a
  "Juntar vídeo y audio".
- 2026-09-11 · Flujo: decisiones al principio (origen/contenido/plataforma); grupo por
  regla; torrent, ficha, .nfo, info.txt (enlaces TMDB/IMDb/FilmAffinity) y capturas
  automáticos; residuos borrados solo si la verificación pasa; detección de "pistas ya
  preparadas" para saltar convertir/muxer.
- 2026-09-11 · UI: selectores con cursor para toda pregunta con opciones (incl. sí/no y
  multi-selección), idiomas por selector, rutas tolerantes a texto colado, salida
  compacta con muchos ficheros, barra de progreso de mkvmerge, `-nostdin` en ffmpeg.
- 2026-09-11 · Opciones sueltas aceptan mkv o carpeta; "Juntar" en ambos sentidos con
  comprobación de duración/fps y vocabulario extranjero/preparado; ficha detecta la
  estructura de carpetas; limpiar V.O. con multi-selector de idiomas presentes.
- 2026-09-11 · Config repartida en `config/*.yaml`; un único tracker configurable; v1 movida a
  `_legacy/`.
- 2026-09-11 · Auditoría de las 62 interacciones contra las reglas de §6 (8 corregidas).
- 2026-09-11 · Primer release real completo (1080p y 2160p) verificado:
  cerrado el pendiente de capturas HDR reales.
- 2026-09-11 · Barra de progreso (mkvmerge y torrent) sin retorno de carro: solo añade
  caracteres en la misma línea (`ui.Barra`), porque el panel de terminal de la app no
  respeta `
` ni el repintado con cursor (también afecta al selector, que se ve duplicado ahí).
- 2026-09-11 · Crear .torrent suelto: clasifica cada entrada (temporada / capítulo /
  película), lo muestra y crea todos en lote con una sola confirmación; "elegir cuáles"
  solo a petición. Antes el multi-selector parecía confirmar uno a uno.
- 2026-09-11 · Opciones sueltas en lote sobre carpetas mixtas: Convertir y Muxer procesan
  también los mkv de las subcarpetas de temporada, cada uno en su sitio (temporal/ y
  originals/ junto al fichero); Capturas suelto trabaja por release (temporada = primer
  episodio) con opción de todos/elegir. Regla: temporada = 1 release → 1 torrent, 1 ficha,
  1 tanda de capturas (del primer capítulo); convertir/muxer/verificar = todos los capítulos.
- 2026-09-11 · Subtítulos (`subs.py`): limpieza de etiquetas ASS dentro de srt, ass/ssa/vtt → srt,
  detección de idioma por texto y de variante castellano/latino (relativa entre pistas), tag
  `es-419` para latino (`codigos_mkv` en idiomas.yaml). Muxer: empareja pistas ffprobe↔mkvmerge
  por tipo (portadas png y mov_text de mp4 rompían los ids) y extrae con ffmpeg los subtítulos
  que mkvmerge no lee. Probado con la estructura de Crunchyroll (mp4 + srt sueltos / mov_text).
- 2026-09-11 · **Incidente Frieren**: el paso Convertir remuxeaba con mkvmerge, que no ve los
  mov_text del mp4 → subtítulos perdidos; la verificación no lo detectó y el flujo borró el
  original (no recuperable). Cambios: (1) los originales van SIEMPRE a `originales/` y no se
  borran nunca (solo `temporal/`, derivados, si la verificación pasa); (2) Convertir solo genera
  los .ac3 y el mkv lo monta el muxer en una sola pasada (extrae mov_text, limpia sueltos);
  (3) guardia tras cada mux: nº de pistas del mkv == pistas del plan, si no, error;
  (4) origen: contenedor mp4 → WEB-DL; (5) mono → AC3 máx. 192 kbps.
- 2026-09-11 · Subtítulos ASS/SSA sueltos: se conservan como pista ASS, se añade una pista SRT
  completa limpia y los carteles/textos en pantalla se extraen tanto a SRT como a ASS forzados.
  La extracción usa estilos Cart/Sign/Title y tags de posicionamiento/typesetting (`\\pos`,
  `\\move`, etc.); no toma cualquier llave como forzado para no confundir cursivas/negritas.
  Si el nombre del ASS ya dice `forced`, ambas versiones son forzadas y no se duplica la extracción.
  Orden global configurable (`subtitulos.orden_formatos`): dentro de cada idioma van primero todos
  los SRT (forzado/completo/SDH), después ASS/SSA y luego PGS/VTT. Se aplica al flujo completo y al
  Muxer suelto porque ambos construyen el mismo plan. Si hay varios forzados del mismo idioma, solo
  el primero (normalmente el SRT) es default; los demás conservan únicamente el flag forced.
- 2026-09-11 · Menú: las dos operaciones de limpieza pasan al submenú **Limpieza de archivos**.
  Auditoría y adaptación: admiten carpeta o MKV, seleccionan pistas mediante ids reales de mkvmerge
  (antes pasaban códigos de idioma a una opción que exige ids), vacían también el nombre de vídeo,
  protegen en lote contra sobrescribir un original previo y verifican el resultado con reglas
  específicas de limpieza. Se mantienen los selectores y la conservación obligatoria de originales/.
- 2026-09-11 · Preparación para publicar en Windows: `tocinotool.bat` pasa a ser el punto de
  entrada con **Ejecutar** y **Asistente de instalación**. Si falta Python 3.9+ ofrece Python 3.12
  mediante winget; el venv propio se crea en `%LOCALAPPDATA%\\tocinotool\\venv` y ya no se confunde
  con un venv de otro proyecto. La tool conserva solo `c` = Configuración (usuario, rutas y salida).
  El asistente revisa también mkvpropedit, puede instalar/posponer FileBot y limita a 10 s la consulta
  informativa de versión para que una instalación GUI de MediaInfo no lo bloquee.
- 2026-09-11 · Binaries Windows actualizados y comprobados: FFmpeg 8.1.2 full build y MKVToolNix
  101.0; los ejecutables previos están en `binaries/_legacy/2026-09-11`. Creado paquete limpio
  `publicar/tociNoTool-v2.0.0-windows/`: sin `config/`, datos de usuario ni binarios legacy. Prueba
  real en copia limpia: venv, dependencias, configuración vacía y asistente completado correctamente.
- 2026-09-11 · Auditoría contra `bitacora_releases_mkv_encode_bluray.md`: el flujo ya permite elegir
  WEB-DL / rip-remux / encode y aplica la política básica correcta (encode = solo AC3; WEB/rip =
  original + AC3); flujo completo y utilidades comparten conversor y muxer. El Muxer acepta una pista
  elemental H.264 junto a audio externo (probado: `.264` → MKV válido). Se amplían las extensiones
  candidatas a `.264`, `.265`, `.av1`, `.ivf` y `.obu`; `listar_videos()` confirma ahora que contienen
  una pista de vídeo real mediante ffprobe, sin decidir por extensión.
  Esta auditoría fijó la fase de arquitectura que se implementa en las entradas siguientes. Siguen
  pendientes exclusivamente muestras reales de Blu-ray (DTS-HD/TrueHD, PGS y VobSub) y regresiones
  completas WEB-DL/Encode/Blu-ray antes de volver a publicar.
- 2026-09-11 · Implementada la primera fase de esa bitácora en el core común: `workspace.py` analiza
  por ffprobe cada candidato y crea `ReleaseGroup` por película/episodio (SxxExx, carpeta o base de
  nombre), detectando componentes no asociados o audios con otra duración antes del mux. PREPARAR
  RELEASE, AUDIO→AC3 y MUXER consumen esos grupos; por tanto admiten vídeo elemental AVC/H.264,
  HEVC/H.265 y AV1 (`.264`, `.265`, `.av1`, `.ivf`, `.obu`) además de contenedores. Se añadió VobSub
  por `.idx` + `.sub`, conservando juntos ambos ficheros al apartar originales.
- 2026-09-11 · Perfiles compartidos `release.yaml`: WEB-DL, Encode/MicroHD, Blu-ray Rip/Remux y Manual.
  Encode valida una única pista de audio por idioma; Blu-ray/Web preservan originales más AC3. El
  convertidor elige una fuente por idioma (AC3 válido o la de mayor calidad), valida codec/canales/
  duración de salida y hace 7.1→5.1 solo con layout 7.1 conocido mediante matriz explícita BL/BR→5.1;
  ante layout incierto se detiene. Probados dos episodios sueltos mezclados (`.264` + AC3) → dos MKV
  Encode válidos, y PCM 7.1 → AC3 5.1 a 48 kHz. AV1 sin marca de encoder se reconoce como WEB-DL;
  SVT-AV1/rav1e/libaom se propone como Encode.
- 2026-09-11 · Presentación Windows: nuevo `launcher.bat` (Python/venv/asistente) y `tocinotool.bat`
  compatible. Launcher y menú muestran Scene ES Release Suite, orientada a la comunidad scene en
  español por jascott. No se recrea `publicar/` hasta completar la cobertura solicitada.
- 2026-09-11 · Corrección de enlaces FilmAffinity: FileBot para Windows devolvía los metadatos en
  cp1252, pero `metadatos.py` los interpretaba siempre como UTF-8; títulos con tildes llegaban con
  `�` y la búsqueda de FilmAffinity no encontraba coincidencia. Ahora se decodifica primero como
  UTF-8 y, si no es válido, como cp1252. Probado con *La Patrulla Canina: La dino película* (2026):
  obtiene `https://www.filmaffinity.com/es/film694776.html`.
- 2026-09-11 · PREPARAR RELEASE ya admite arrastrar un MKV, como anunciaba su texto de entrada.
  El analizador limita el workspace a ese contenedor (no recoge otros vídeos de la carpeta); tras
  convertir/muxear, renombra, torrent, ficha y capturas se aplican únicamente a ese release.
  Probado el análisis directo del MKV de *La Patrulla Canina* con un solo grupo válido.
- 2026-09-12 · Renombrar: también se corrige la salida visible de FileBot en Windows. El comando
  de prueba emitía rutas cp1252 y `tools.ejecutar()` las leía como UTF-8, mostrando `pel�cula`.
  `renombrar.py` solicita cp1252 únicamente para FileBot en Windows; el nombre aplicado y el resto
  de herramientas conservan su tratamiento habitual.
- 2026-09-12 · Plan de mux: la columna `de` (fichero de procedencia de cada pista) se oculta en la
  vista normal, pues es diagnóstico y alargaba innecesariamente la tabla. Se conserva al activar
  el modo técnico `mostrar_comandos`.
- 2026-09-12 · Entorno Python: el venv deja de crearse en `%LOCALAPPDATA%` y pasa a `.venv/` dentro
  de la carpeta de tociNoTool. La instalación queda autocontenida y el usuario puede limpiarla por
  completo eliminando `.venv/` y `config/`; no se incluirá el venv al publicar.
- 2026-09-12 · Exportación Windows: paquete limpio `tociNoTool-v2.0.0-windows` con `launcher.bat`,
  código, valores por defecto, binarios actuales y documentación. Se excluyen `config/`, `.venv/`,
  caches y cualquier contenido legacy o personalizado; el primer arranque crea lo necesario.
- 2026-09-12 · Fase de robustez iniciada: nuevo `diagnostico.py` genera informes únicos en `logs/`
  con sistema, Python, versiones de herramientas y traceback, anonimizando la carpeta de usuario y
  sin guardar licencias; opción `l` abre dicha carpeta. El launcher bloquea la primera ejecución hasta
  completar el asistente. FileBot diferencia `NOT_INSTALLED`, `INSTALLED_UNREGISTERED`,
  `INSTALLED_LICENSED` y `ERROR`; PREPARAR RELEASE puede llegar a convertir/muxear sin licencia, pero
  se detiene antes de renombrar/torrent/ficha para conservar el trabajo sin fallar.
- 2026-09-12 · Plataformas auditadas sin cambiar su formato simple: `plataformas.yaml` sigue siendo
  `TAG: nombre`. Se actualizan únicamente los tags confirmados por la convención de la tool:
  `HMAX` para HBO Max y `Disney` para Disney+. Crunchyroll conserva `CRUNCHY` hasta confirmación
  explícita del tracker. También se añadió fallback de presentación para `es.csv` y la etiqueta
  `es-419` = Español latinoamericano.
- 2026-09-12 · UX: lotes de FileBot con más de tres elementos muestran cantidad, primer resultado y
  rango de episodios; el detalle completo queda tras `mostrar_comandos`. Launcher y menú incorporan
  un intento de cerdito se ha descartado para mantener el menú sobrio; el selector ya no usa fondo
  inverso permanente y solo debe resaltar la opción bajo el cursor.
- 2026-09-12 · Primer arranque y FileBot: si se elige «Ejecutar» sin Python, el launcher muestra el
  paso 1 del asistente y, tras detectarlo, deriva al asistente en vez de abrir el menú. FileBot no es
  requisito de instalación: queda registrado como `pendiente`, el usuario puede comprar/activar o
  posponer y volver después al asistente. Se unifica el aviso de licencia: es personal, válida en
  varios equipos del mismo usuario (por ejemplo, 2–3), nunca para compartir entre personas.
- 2026-09-12 · Publicación 2.1.0: la nota para auditorías asistidas por IA queda integrada en el
  docstring de `tocinotool/__init__.py`: documentar mejoras y proponerlas a jascott por Telegram
  (@jascott), sin comunicaciones ni publicaciones automáticas y sin exponer datos locales,
  credenciales o licencias.
- 2026-09-12 · MediaInfo en Windows: el asistente y los diagnósticos dejan de ejecutar
  `MediaInfo.exe --Version`, porque algunos instaladores registran el ejecutable gráfico y abrían
  su interfaz, bloqueando el flujo hasta cerrarla. La detección conserva la ruta y `pymediainfo`
  verifica la librería nativa que usa realmente la ficha.
- 2026-09-12 · Instalación robusta: `winget` se explica como opción automática, no como requisito.
  Si no está disponible, no hay red, el instalador falla o no actualiza PATH, el asistente mantiene
  un selector recuperable: reintentar, descarga oficial (MediaInfo/FileBot), ruta manual o posponer.
  El fallo de instalación de Python en el launcher también deriva a la descarga oficial, sin afirmar
  que se haya instalado correctamente.
- 2026-09-12 · Diagnóstico del asistente: las excepciones inesperadas del asistente de instalación
  generan un informe en `logs/` identificado como módulo `asistente`, con traceback y versiones de
  herramientas. Se mantiene la anonimización de rutas y la exclusión de licencias y credenciales.
- 2026-09-12 · Cobertura de errores iniciales: `launcher.bat` escribe informes de respaldo en
  `logs/` incluso antes de disponer de Python (fallo de winget o detección posterior). La creación
  de `.venv`, instalación por pip y lectura de configuración pasan al manejador de diagnóstico de
  Python. Los errores de módulos de trabajo ya se registran desde el menú. Así los distintos puntos
  de fallo conservan un informe útil sin registrar licencias, cookies ni credenciales.
- 2026-09-12 · Salvaguarda sin FileBot: la ficha deja de depender de sus metadatos. Si faltan,
  solicita opcionalmente TMDb para películas o IMDb para series, valida el enlace y lo incorpora a
  `.txt`, `.nfo` e `info.txt`. El asistente y la parada controlada de PREPARAR RELEASE explican el
  camino alternativo: renombrar manualmente y usar Ficha.
- 2026-09-12 · Documentación para continuidad: `README.md` pasa a ser el manual público de uso y
  funcionamiento, organizado para el renderizado Markdown de GitHub. Se crea `MEMORIA.md` con el
  estado técnico, invariantes, arquitectura, distribución, diagnóstico y verificación de publicación.
- 2026-09-12 · MediaInfo portable: se integra la distribución oficial DLL/CLI x64 en
  `binaries/mediainfo/`. `pymediainfo` recibe explícitamente esa DLL, eliminando la dependencia de
  una instalación global de MediaInfo y evitando abrir su interfaz gráfica. En Windows solo quedan
  como dependencias externas Python y, opcionalmente, FileBot.
- 2026-09-12 · Preparación para GitHub: se añade `.gitignore` para excluir `config/`, `.venv/`,
  `logs/`, `binaries/`, paquetes publicados y material legado. Las plantillas públicas ya no
  incluyen URL announce ni comentario del tracker; esos datos se completan solo en
  `config/tracker.yaml`. La creación de torrent se detiene con un aviso claro si falta el announce.
- 2026-09-12 · Configuración neutral: un fichero de tracker anterior pasa a llamarse
  `tracker.yaml` en las instalaciones existentes, sin perder valores. Las
  plantillas, el código y el manual no nombran un tracker concreto.
- 2026-09-12 · Repositorio sin binarios: GitHub distribuye código y plantillas, no `binaries/`,
  porque FFmpeg supera su límite de tamaño. El ZIP de Windows conserva los portables. Para un clon
  del repositorio, el asistente instala FFmpeg y MKVToolNix con winget o abre sus páginas oficiales
  junto con las de MediaInfo y FileBot; el README diferencia ambos caminos.
- 2026-09-12 · Apertura a la comunidad: la presentación, documentación y valores por defecto pasan
  a ser genéricos para la comunidad scene en español. Se conserva `jascott` como autor.
- 2026-09-12 · Reconstrucción portable: se añade `BINARY_MANIFEST.md` con las versiones, enlaces,
  estructura y hashes SHA-256 de FFmpeg 8.1.2, MKVToolNix 101.0 y MediaInfo 26.05. Permite
  regenerar `binaries/` de forma verificable sin subir ejecutables al repositorio.

## 8. Cómo continuar

```bash
python -m tocinotool          # menú; opción c = configuración; Ctrl+C o q sale en cualquier pregunta
```

Para tocar comportamiento: primero `config/*.yaml` (casi todo es dato); el
código solo si cambia el flujo. Probar con ficheros sintéticos:
`ffmpeg -f lavfi -i testsrc2 -f lavfi -i sine … -c:a eac3 -metadata:s:a:0 language=spa`.
Tras cambiar código, **salir y relanzar la tool** (Python no recarga en caliente).
