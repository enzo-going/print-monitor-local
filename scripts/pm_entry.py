"""Ponto de entrada do executavel empacotado (PyInstaller).

Comportamento:
- com argumentos: repassa para a CLI (``init``, ``collect``, ``report`` etc.);
- sem argumentos (ex.: duplo clique no .exe): inicia o dashboard local e abre o
  navegador, oferecendo uma experiencia pronta para uso.

A importacao explicita de ``print_monitor.web`` garante que o dashboard seja
incluido no empacotamento.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Em execucao a partir do codigo-fonte, garante que "src/" esteja no path.
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import print_monitor.web  # noqa: F401  (garante inclusao do dashboard no build)
from print_monitor.cli import main as cli_main  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    if argv:
        return cli_main(argv)

    # Sem argumentos: sobe o dashboard e abre o navegador.
    import threading
    import webbrowser

    host, port = "127.0.0.1", 5000
    threading.Timer(1.5, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    return cli_main(["serve", "--host", host, "--port", str(port)])


if __name__ == "__main__":
    raise SystemExit(main())
