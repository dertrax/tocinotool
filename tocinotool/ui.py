"""Interfaz de consola: preguntas, tablas y colores.

Regla heredada de la v1: escribir `q` en cualquier pregunta sale de la tool.
"""
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


class Salir(Exception):
    """El usuario ha escrito 'q' en una pregunta."""


class Cancelar(Exception):
    """El usuario ha cancelado la operación actual (vuelve al menú)."""


def _habilitar_ansi() -> bool:
    if os.name == "nt":
        os.system("")  # activa el procesamiento de secuencias VT en la consola de Windows
    return sys.stdout.isatty()


_ANSI = _habilitar_ansi()

def _c(codigo: str, texto: str) -> str:
    return f"\033[{codigo}m{texto}\033[0m" if _ANSI else texto


def negrita(t: str) -> str:
    return _c("1", t)


def gris(t: str) -> str:
    return _c("90", t)


def titulo(texto: str) -> None:
    linea = "-" * 78
    print()
    print(_c("36", linea))
    print(_c("36;1", f"  {texto}"))
    print(_c("36", linea))


def cabecera_principal(version: str, usuario: str = "") -> None:
    """Cabecera estable del menú, también legible en terminales sin ANSI."""
    linea = "=" * 78
    print(_c("36", linea))
    print(_c("36;1", "                 T O C I ( N O ) T O O L"))
    print(_c("36", "                Release Suite · Scene ES"))
    print(_c("90", f"     Comunidad scene en español  |  Autor: jascott  |  v{version}"))
    if usuario:
        print(_c("90", f"                              Usuario: @{usuario}"))
    print(_c("36", linea))


def seccion(texto: str) -> None:
    print()
    print(_c("1", f"== {texto}"))


def info(texto: str) -> None:
    print(f"   {texto}")


def ok(texto: str) -> None:
    print(_c("32", f" ✔ {texto}"))


def aviso(texto: str) -> None:
    print(_c("33", f" ! {texto}"))


def error(texto: str) -> None:
    print(_c("31", f" ✖ {texto}"))


def limpiar() -> None:
    os.system("cls" if os.name == "nt" else "clear")


class Barra:
    """Barra de progreso que solo AÑADE caracteres en la misma línea (sin retorno
    de carro), así se ve continua en cualquier terminal:
       [1/3] Peli.mkv  |=========25%=========50%=========75%=========100%| ✔
    Llamar a avanzar(pct) con el porcentaje actual y a terminar() al final."""

    def __init__(self, etiqueta: str = "", segmentos: int = 40):
        self.segmentos = segmentos
        self.pintados = 0
        self.hitos = {25, 50, 75}
        self.hitos_pintados = set()
        sys.stdout.write(f"   {etiqueta}|")
        sys.stdout.flush()

    def avanzar(self, pct: float) -> None:
        pct = max(0.0, min(100.0, float(pct)))
        objetivo = int(pct * self.segmentos / 100)
        while self.pintados < objetivo:
            self.pintados += 1
            sys.stdout.write("=")
            umbral = int(self.pintados * 100 / self.segmentos)
            for h in sorted(self.hitos):
                if umbral >= h and h not in self.hitos_pintados:
                    self.hitos_pintados.add(h)
                    sys.stdout.write(f"{h}%")
        sys.stdout.flush()

    def terminar(self, ok_: bool = True) -> None:
        self.avanzar(100)
        sys.stdout.write("100%| " + ("✔" if ok_ else "✖") + chr(10))
        sys.stdout.flush()


def pausa(texto: str = "Pulsa ENTER para continuar...") -> None:
    try:
        input(gris(texto))
    except EOFError:
        pass


# ---------------------------------------------------------------------------
# Preguntas
# ---------------------------------------------------------------------------

def _leer(prompt: str) -> str:
    try:
        respuesta = input(prompt)
    except (EOFError, KeyboardInterrupt):
        raise Salir()
    if respuesta.strip().lower() == "q":
        raise Salir()
    return respuesta


def preguntar(texto: str, defecto: Optional[str] = None, obligatorio: bool = False) -> str:
    """Pregunta de texto libre. ENTER devuelve el valor por defecto."""
    sufijo = f" [{defecto}]" if defecto not in (None, "") else ""
    while True:
        r = _leer(f" > {texto}{sufijo}: ").strip()
        if r == "" and defecto is not None:
            return defecto
        if r == "" and obligatorio:
            aviso("Este campo es obligatorio.")
            continue
        return r


def preguntar_sn(texto: str, defecto: Optional[bool] = None) -> bool:
    """Sí/No. Con terminal interactiva, selector de dos opciones con la propuesta
    marcada (ENTER = aceptar); si no, s/n por teclado."""
    if _selector_disponible():
        r = preguntar_opcion(texto, [("s", "Sí"), ("n", "No")],
                             defecto=None if defecto is None else ("s" if defecto else "n"))
        return r == "s"
    ayuda = "s/n" if defecto is None else ("S/n" if defecto else "s/N")
    while True:
        r = _leer(f" > {texto} ({ayuda}): ").strip().lower()
        if r == "" and defecto is not None:
            return defecto
        if r in ("s", "si", "sí", "y", "yes"):
            return True
        if r in ("n", "no"):
            return False
        aviso("Responde 's' o 'n' (o 'q' para salir).")


def preguntar_entero(texto: str, defecto: Optional[int] = None, minimo: Optional[int] = None,
                     maximo: Optional[int] = None) -> int:
    while True:
        r = preguntar(texto, str(defecto) if defecto is not None else None)
        try:
            v = int(r)
        except ValueError:
            aviso("Escribe un número entero.")
            continue
        if minimo is not None and v < minimo:
            aviso(f"Mínimo {minimo}.")
            continue
        if maximo is not None and v > maximo:
            aviso(f"Máximo {maximo}.")
            continue
        return v


try:
    import questionary as _q
    # Solo el cursor activo cambia de color: no hay una opción con resaltado
    # permanente, incluida PREPARAR RELEASE.
    _ESTILO_SELECTOR = _q.Style([("highlighted", "bold fg:cyan"), ("pointer", "bold fg:cyan"),
                                 # `default=` marca la elección inicial como selected. Al mover
                                 # el cursor debe perder todo fondo/inversión; solo la flecha
                                 # y la fila highlighted señalan la opción activa.
                                 ("selected", "noreverse nobold"), ("question", "bold"), ("instruction", "italic")])
except ImportError:
    _ESTILO_SELECTOR = None


def _recortar(texto: str, ancho: int) -> str:
    return texto if len(texto) <= ancho else texto[:ancho - 1] + "…"


def _selector_disponible() -> bool:
    if os.environ.get("TOCINOTOOL_SIN_SELECTOR"):
        return False
    try:
        import questionary  # noqa: F401
    except ImportError:
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def preguntar_opcion(texto: str, opciones: Sequence[Tuple[str, str]], defecto: Optional[str] = None) -> str:
    """Selector con cursor (flechas + ENTER) con la opción propuesta ya marcada.
    Si la terminal no lo permite, lista numerada. Devuelve la clave elegida."""
    claves = [str(k) for k, _ in opciones if str(k) != ""]
    if _selector_disponible():
        import questionary
        from questionary import Choice
        from questionary import Separator
        ancho = max(40, shutil.get_terminal_size((100, 24)).columns - 8)
        etiquetas = [Separator(" ") if str(k) == "" else Choice(title=_recortar(str(desc), ancho), value=str(k))
                     for k, desc in opciones]
        try:
            pregunta = questionary.select(
                texto, choices=etiquetas, default=defecto if defecto in claves else None,
                qmark=">", pointer="»", instruction="(flechas + ENTER · Ctrl+C sale)",
                style=_ESTILO_SELECTOR,
            )
            # Questionary interpreta `default` como elección ya seleccionada,
            # además de posición inicial. Conservamos la posición inicial pero
            # vaciamos esa selección: el único resaltado debe ser el cursor.
            for control in pregunta.application.layout.find_all_controls():
                if hasattr(control, "selected_options"):
                    control.selected_options = []
            r = pregunta.unsafe_ask()
        except KeyboardInterrupt:
            raise Salir()
        print()
        return r

    print()
    numeradas = not all(k.isdigit() for k in claves)   # si las claves ya son números, no se renumera
    i = 0
    for clave, desc in opciones:
        if str(clave) == "":
            print()
            continue
        i += 1
        marca = "*" if str(clave) == defecto else " "
        etiqueta = str(i) if numeradas else str(clave)
        print(f"   {marca} {negrita(f'{etiqueta:<4}')} {desc}")
    d = str(claves.index(defecto) + 1) if (numeradas and defecto in claves) else defecto
    while True:
        r = preguntar(texto, d)
        if numeradas and r.isdigit() and 1 <= int(r) <= len(claves):
            return claves[int(r) - 1]
        if r in claves:
            return r
        aviso(f"Opción no válida: '{r}'. Escribe el número.")


def preguntar_multi(texto: str, opciones: Sequence[Tuple[str, str]], marcadas: Sequence[str] = ()) -> List[str]:
    """Elección múltiple: flechas, ESPACIO marca/desmarca, ENTER confirma.
    `marcadas` = claves que salen marcadas. Sin selector: números separados por comas."""
    claves = [str(k) for k, _ in opciones]
    if _selector_disponible():
        import questionary
        from questionary import Choice
        try:
            r = questionary.checkbox(
                texto, choices=[Choice(title=_recortar(str(d), max(40, shutil.get_terminal_size((100, 24)).columns - 10)),
                                       value=str(k), checked=str(k) in marcadas) for k, d in opciones],
                qmark=">", pointer="»", instruction="(flechas · ESPACIO marca · ENTER confirma)",
                style=_ESTILO_SELECTOR,
            ).unsafe_ask()
        except KeyboardInterrupt:
            raise Salir()
        print()
        return list(r or [])
    print()
    for i, (clave, desc) in enumerate(opciones, 1):
        print(f"   {'*' if str(clave) in marcadas else ' '} {negrita(f'{i:<4}')} {desc}")
    d = [str(claves.index(k) + 1) for k in marcadas if k in claves]
    lista = preguntar_lista(texto + " (números separados por comas)", defecto=d or None)
    return [claves[int(x) - 1] for x in lista if x.isdigit() and 1 <= int(x) <= len(claves)]


def preguntar_idioma(cfg, texto: str = "Idioma", defecto: str = "spa") -> str:
    """Selector con los idiomas del config (código + nombre), primero los de
    orden_idiomas; 'otro' permite escribir un código nuevo (se guardará)."""
    orden = [str(x) for x in cfg["orden_idiomas"]]
    resto = sorted(k for k in cfg["idiomas"] if k not in orden and k != "und")
    opciones = [(k, f"{k:<5} {cfg['idiomas'][k]}") for k in orden + resto if k in cfg["idiomas"]]
    opciones.append(("otro", "otro código (escribir)"))
    r = preguntar_opcion(texto, opciones, defecto=defecto if defecto in cfg["idiomas"] else "spa")
    if r == "otro":
        return cfg.canon_idioma(preguntar("Código de idioma (ISO 639-2, ej. tel)", obligatorio=True))
    return r


def preguntar_ruta(texto: str, debe_existir: bool = True, tipo: str = "dir",
                   defecto: Optional[str] = None) -> Path:
    """Pide una ruta. Admite arrastrar la carpeta a la terminal (quita comillas)."""
    while True:
        r = preguntar(texto, defecto, obligatorio=True)
        r = r.strip().strip('"').strip("'").strip()
        # PowerShell añade '& ' al arrastrar en algunos casos
        if r.startswith("& "):
            r = r[2:].strip().strip('"').strip("'")
        if r == "-" and defecto == "-":
            return Path("-")
        ruta = Path(os.path.expanduser(r))
        if not ruta.exists():
            # texto colado antes de la ruta (teclas en el búfer): nos quedamos con la ruta
            m = re.search(r'"([A-Za-z]:[\\/][^"]*)"|"(/[^"]*)"|([A-Za-z]:[\\/].*)$|(/.*)$', r)
            if m:
                candidato = next(g for g in m.groups() if g)
                if Path(candidato).exists():
                    ruta = Path(candidato)
        if not debe_existir:
            return ruta
        if tipo == "dir" and ruta.is_dir():
            return ruta
        if tipo == "file" and ruta.is_file():
            return ruta
        if tipo == "any" and ruta.exists():
            return ruta
        aviso(f"No existe o no es {'una carpeta' if tipo == 'dir' else 'un fichero'}: {ruta}")


def preguntar_carpeta(cfg, texto: str = "Carpeta de trabajo", admitir_fichero: bool = False) -> Path:
    """Pide la carpeta de trabajo (arrastrarla; no se propone ninguna). Con
    `admitir_fichero` también vale arrastrar un mkv suelto."""
    if admitir_fichero:
        return preguntar_ruta(texto + " (carpeta o mkv)", tipo="any")
    return preguntar_ruta(texto)


def preguntar_lista(texto: str, defecto: Optional[Iterable[str]] = None) -> List[str]:
    """Lista separada por comas. Devuelve [] si se deja vacío sin defecto."""
    d = ",".join(defecto) if defecto else None
    r = preguntar(texto, d)
    return [x.strip() for x in r.split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------

def tabla(cabeceras: Sequence[str], filas: Iterable[Sequence[object]], sangria: str = "   ") -> None:
    filas = [[("" if c is None else str(c)) for c in f] for f in filas]
    anchos = [len(h) for h in cabeceras]
    for f in filas:
        for i, c in enumerate(f):
            anchos[i] = max(anchos[i], len(c))
    fmt = "  ".join("{:<" + str(a) + "}" for a in anchos)
    print(sangria + negrita(fmt.format(*cabeceras)))
    print(sangria + gris("  ".join("-" * a for a in anchos)))
    for f in filas:
        print(sangria + fmt.format(*f))
