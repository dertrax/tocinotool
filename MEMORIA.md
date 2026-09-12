# Memoria del proyecto — tociNoTool v2.1.4

Estado técnico para retomar el desarrollo. Complementa al manual público
([README.md](README.md)) y al historial ([BITACORA.md](BITACORA.md)).

## Alcance

tociNoTool prepara releases para la comunidad scene en español: AC3, mux, verificación, renombrado,
torrent, ficha, `.nfo`, `info.txt` y capturas. No incluye contenido, cookies,
credenciales ni licencias en código, logs o paquetes.

El parser local de `series.py` no depende de FileBot: detecta la correlación
`SxxExx`/`1x02`, huecos y fallback manual. Las URLs de referencia son opcionales
y no activan scraping. FileBot se reserva para el renombrado final.

Las fuentes de Encode/Rip se archivan mediante `mux.ejecutar_plan_con_originales()`
solo después de que mkvmerge y la validación de pistas hayan terminado bien. Si
la reorganización falla, el MKV válido se conserva y se genera informe en `logs/`.

Autor y contacto de mejoras: **jascott**, Telegram **@jascott**. Una auditoría
asistida por IA debe documentar la propuesta y presentarla al autor; nunca debe
enviar mensajes ni publicar cambios automáticamente.

## Distribución Windows

- Entrada: `launcher.bat`.
- Paquete: `publicar/tociNoTool-v2.1.4-windows.zip`.
- Incluye código, launcher, manual, requisitos, valores por defecto y binarios
  portables de FFmpeg, MKVToolNix y MediaInfo.
- Excluye `config/`, `.venv/`, `logs/`, `_legacy/`, `binaries/_legacy/`, datos
  personales y licencias.
- Recalcular SHA-256 tras cada modificación. Los ZIP `NO_COMPARTIR-*` no se
  distribuyen.

## Arranque y diagnóstico

1. El launcher busca Python 3.9+ y deriva al asistente en una instalación nueva.
2. `entorno.py` crea `.venv/` dentro de la raíz, instala requisitos y relanza.
3. `asistente.py` comprueba dependencias, herramientas, usuario y FileBot.

MediaInfo se distribuye como DLL portable oficial en `binaries/mediainfo/` y
`tools.biblioteca_mediainfo()` la entrega explícitamente a `pymediainfo`. No se
debe volver a depender de `C:\Program Files\MediaInfo` ni ejecutar la interfaz
gráfica para comprobar versiones.

`winget` es opcional. Si falta, falla, no hay red o PATH no se actualiza, el
asistente permite reintentar, descargar, indicar ruta o posponer.

- `diagnostico.py` genera `logs/error_*.log` con sistema, Python, herramienta,
  módulo, paso y traceback.
- El launcher crea `logs/launcher_error_*.log` antes de Python.
- Se anonimizan rutas de usuario; no se guardan licencias, cookies, variables
  de entorno ni contenido de releases.
- Límite inevitable: no puede crearse un log si Windows no inicia `cmd` o el
  disco no permite escribir.

## Arquitectura

| Módulo | Responsabilidad |
|---|---|
| `__main__.py` | Menú, arranque y captura de errores. |
| `entorno.py` | Venv local y dependencias. |
| `asistente.py` | Instalación, rutas y licencia FileBot. |
| `config.py` | Carga, mezcla y guardado de `config/*.yaml`. |
| `tools.py` | Localización y ejecución de herramientas. |
| `probe.py` / `workspace.py` | Análisis y agrupación de entradas. |
| `ac3.py` / `mux.py` / `subs.py` | Conversión, mux y subtítulos. |
| `verificar.py` | Directrices del MKV final. |
| `renombrar.py` | FileBot y nombres. |
| `torrent.py` / `ficha.py` / `metadatos.py` | Entregables del tracker. |

## Invariantes funcionales

- Perfiles: WEB-DL conserva originales más AC3; Encode usa una pista por idioma;
  Blu-ray conserva compatible más original según perfil.
- Se detectan AVC, HEVC y AV1. SVT-AV1/rav1e/libaom sugieren Encode; AV1 sin
  marca se propone como WEB-DL.
- La plataforma WEB-DL se confirma desde `plataformas.yaml`.
- El muxer elimina título global y adjuntos, conserva capítulos y ordena pistas
  por idioma y calidad.
- Subtítulos: SRT forzado, SRT completo, ASS forzado, ASS completo y después
  otros formatos. ASS/SSA se conserva y genera SRT; carteles posicionados
  producen variante forzada.
- WebVTT se convierte con el lector propio de `subs.py`, no con FFmpeg: retiene
  texto y etiquetas SRT comunes, no colores/fondo/posición. Evita los SRT
  vacíos que FFmpeg podía generar con perfiles WebVTT de Netflix.
- Para dos pistas españolas internas sin flag `forced`, `subs.cobertura_subtitulos`
  compara los cues de ambas; solo marca forzada una candidata de hasta 80 cues
  y al menos cinco veces menor que otra española completa. El usuario puede
  modificar el plan antes del mux.
- Si una pista inicialmente `spa`/`es-ES` se clasifica por texto como `spal`,
  `PistaPlan.aviso_taggeo` muestra una advertencia al presentar el plan. No
  bloquea el flujo: el usuario puede corregirla con `i · cambiar idioma`.
- Un MKV suelto limita el análisis a ese contenedor.
- `originales/` nunca se elimina automáticamente.

## FileBot y alternativa manual

Estados: `NOT_INSTALLED`, `INSTALLED_UNREGISTERED`, `INSTALLED_LICENSED` y
`ERROR`. FileBot no es esencial: sin licencia, PREPARAR RELEASE convierte,
multiplexa y verifica, y se detiene antes del renombrado automático.

Alternativa: renombrar manualmente y usar la opción 6. Si faltan metadatos,
`metadatos.pedir_enlace_manual()` solicita TMDb para película o IMDb para serie,
valida el enlace y lo añade a ficha, `.nfo` e `info.txt`. Es opcional.

La licencia es personal, válida para varios equipos del mismo usuario; nunca se
presenta como compartible entre personas.

## Configuración y datos

- `config/` es local; `tocinotool/config_defaults/` es distribuible. `Config`
  mezcla nuevas claves sin pisar valores locales.
- Los datos del tracker (nombre, announce y comentario) son exclusivamente locales en
  `config/tracker.yaml`. Las plantillas públicas los dejan vacíos y Git ignora `config/`.
  `torrent.crear()` no genera un torrent sin announce.
- Si un tracker modifica el diccionario `info` del torrent, sus campos se declaran como
  `torrent.campos_info` antes de generar el hash. Es una configuración local del
  tracker; no debe trasladarse a la plantilla pública.
- `plataformas.yaml` sigue el formato `TAG: nombre`. Tags confirmados: `HMAX`,
  `Disney` y `CRUNCHY`.
- `es.csv` solo traduce MediaInfo para la ficha; no afecta codecs, idiomas ni
  mux.

## Antes de publicar

1. `python -m compileall -q tocinotool` dentro de `.venv`.
2. Probar launcher sin configuración y asistente con FileBot presente, ausente y
   sin licencia.
3. Probar ficha sin metadatos: TMDb para película e IMDb para serie.
4. Verificar que el paquete no contiene `config/`, `.venv/`, `logs/` ni legacy.
5. Calcular SHA-256 y compartir solo el ZIP sin prefijo `NO_COMPARTIR-`.

## Repositorio y binarios

GitHub guarda únicamente el código, las plantillas y la documentación. `.gitignore`
excluye `binaries/`: FFmpeg supera el límite de 100 MB por archivo. El ZIP de
Windows sí incluye FFmpeg, MKVToolNix y MediaInfo. Si alguien clona el repositorio,
el asistente ofrece winget o enlaces oficiales para instalar las herramientas que
falte; nunca se deben añadir binarios manualmente al repositorio.

`BINARY_MANIFEST.md` fija la reconstrucción exacta del conjunto Windows x64:
versiones, fuentes, destinos y SHA-256. Debe actualizarse cada vez que se cambie
un binario antes de generar un nuevo ZIP.
