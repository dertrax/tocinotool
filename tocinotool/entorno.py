"""Entorno aislado (venv) gestionado por la propia tool.

Al arrancar con cualquier Python (`python -m tocinotool`), si no estamos ya
dentro del venv de la tool: lo crea en `.venv/` junto a esta instalación,
instala requirements.txt y se relanza dentro. Así la instalación es autónoma:
se puede limpiar su configuración y dependencias borrando su propia carpeta.
Funciona igual en Windows, Linux y macOS. Los lanzadores launcher.bat /
tocinotool.sh solo hacen falta cuando no hay Python instalado.
"""
import os
import subprocess
import sys
from pathlib import Path

from . import ROOT

REQUISITOS = ROOT / "requirements.txt"


def ruta_venv() -> Path:
    """Venv propio, siempre dentro de la carpeta de esta instalación."""
    return ROOT / ".venv"


def python_venv(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def en_venv() -> bool:
    """True solo si se ejecuta desde el venv propio de la tool.

    Un venv de otro proyecto no debe impedir crear el aislado de tociNoTool.
    """
    esperado = python_venv(ruta_venv())
    try:
        return esperado.exists() and Path(sys.executable).resolve() == esperado.resolve()
    except OSError:
        return False


def _dependencias_al_dia(venv: Path) -> bool:
    marca = venv / "requirements.installed"
    return marca.exists() and marca.read_bytes() == REQUISITOS.read_bytes()


def asegurar() -> None:
    """Si no estamos en el venv de la tool, lo prepara y relanza el proceso dentro."""
    if os.environ.get("TOCINOTOOL_SIN_VENV") or en_venv():
        return
    if sys.version_info < (3, 9):
        raise RuntimeError(f"Hace falta Python 3.9 o superior (tienes {sys.version.split()[0]}).")

    venv = ruta_venv()
    py = python_venv(venv)
    if not py.exists():
        print(f"Creando entorno aislado en {venv} ...")
        try:
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        except subprocess.CalledProcessError as ex:
            raise RuntimeError("No se pudo crear el entorno virtual "
                               f"(código {ex.returncode}). En Debian/Ubuntu: "
                               "sudo apt-get install python3-venv") from ex

    if not _dependencias_al_dia(venv):
        print("Instalando dependencias Python ...")
        r = subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(REQUISITOS)])
        if r.returncode != 0:
            raise RuntimeError(f"Error instalando dependencias Python (código {r.returncode}).")
        (venv / "requirements.installed").write_bytes(REQUISITOS.read_bytes())

    # relanzar dentro del venv con los mismos argumentos
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run([str(py), "-m", "tocinotool", *sys.argv[1:]], cwd=str(ROOT), env=env)
    sys.exit(r.returncode)
