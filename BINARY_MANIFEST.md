# Manifiesto de binarios Windows x64

Este documento permite reconstruir `binaries/` al retomar el proyecto desde
GitHub. Los ejecutables no se guardan en el repositorio porque FFmpeg supera el
límite de tamaño de GitHub. El paquete ZIP de distribución sí los incluye.

La referencia es la carpeta `binaries/` de tociNoTool v2.1.5 para Windows x64.
Descarga las versiones indicadas, extrae solo los ficheros señalados y verifica
sus hashes. No sustituyas versiones por “la última” si se busca reproducir el
paquete exactamente.

## 1. FFmpeg 8.1.2 full build

Fuente: [GyanD/codexffmpeg · release 8.1.2](https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-full_build.zip).

Del archivo extraído, copia estos ejecutables desde su carpeta `bin/`:

| Destino | SHA-256 esperado |
|---|---|
| `binaries/ffmpeg.exe` | `AD8F211BC894755E0061C55AB280AE00E8D3D4F15A8CC4372B24CFA247B5942E` |
| `binaries/ffprobe.exe` | `9DF3B0B5275E830961DF6D94E1F7A71121A7ABD5FF708E9FEC8A0B6084A55015` |

## 2. MKVToolNix 101.0 x64 portable

Fuente: [MKVToolNix 101.0 portable x64](https://mkvtoolnix.download/windows/releases/101.0/mkvtoolnix-64-bit-101.0.7z).

Del archivo extraído, copia:

| Destino | SHA-256 esperado |
|---|---|
| `binaries/mkvmerge.exe` | `0DE358F33EB943AAEE1770600B8E2E6E8740DF834844C3B6C642DCF3E0E22100` |
| `binaries/mkvpropedit.exe` | `BC0E5F1763A96E416315465781842CCCBE5F6DF5EB113338A7C4F94211F198B6` |

## 3. MediaInfo 26.05 x64

Descarga y extrae ambos archivos oficiales:

- [DLL 26.05 x64](https://mediaarea.net/download/binary/libmediainfo0/26.05/MediaInfo_DLL_26.05_Windows_x64_WithoutInstaller.zip)
- [CLI 26.05 x64](https://mediaarea.net/download/binary/mediainfo/26.05/MediaInfo_CLI_26.05_Windows_x64.zip)

Combina sus ficheros en `binaries/mediainfo/` y conserva los documentos de
licencia que traen los paquetes. Los ficheros esenciales son:

| Destino | SHA-256 esperado |
|---|---|
| `binaries/mediainfo/MediaInfo.dll` | `A2612FA8BF639349AEE9747D8A555D361F5DB95B049B3AF9B0C3851A21A4308D` |
| `binaries/mediainfo/MediaInfo.exe` | `30F2828A45A1895B033C3CD7784581033327E7B393033C55F4A03BB15CAB0D89` |
| `binaries/mediainfo/LIBCURL.DLL` | `22B972F008AB8BB5BC225889A8BE60683B2BF7546B8E0D699B5B4186BDBB7CC1` |

## Verificación

Desde la raíz del proyecto en PowerShell:

```powershell
@(
  "binaries\ffmpeg.exe", "binaries\ffprobe.exe", "binaries\mkvmerge.exe",
  "binaries\mkvpropedit.exe", "binaries\mediainfo\MediaInfo.dll",
  "binaries\mediainfo\MediaInfo.exe", "binaries\mediainfo\LIBCURL.DLL"
) | Get-FileHash -Algorithm SHA256
```

Después ejecuta:

```powershell
& .\binaries\ffmpeg.exe -version
& .\binaries\mkvmerge.exe --version
& .\binaries\mediainfo\MediaInfo.exe --Version
```

El resultado debe indicar FFmpeg 8.1.2, MKVToolNix 101.0 y MediaInfo 26.05.
Con los binarios verificados, se puede regenerar el paquete Windows desde la
carpeta completa del proyecto. No se deben subir estos ejecutables a GitHub.
