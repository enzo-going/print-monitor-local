"""Ponto de entrada do mini app empacotado (PyInstaller).

Comportamento:
- com argumentos: repassa para a CLI (``init``, ``collect``, ``report`` etc.);
- sem argumentos (ex.: duplo clique no .exe): inicia o servico local e abre o
  dashboard em uma JANELA NATIVA (pywebview/WebView2). Se o pywebview nao estiver
  disponivel, abre no navegador padrao como alternativa.

Toda a operacao do app (cadastrar impressora, coletar, descobrir, relatorios,
filtros e exportacao) e feita pela interface, sem linha de comando.
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

HOST = "127.0.0.1"
WINDOW_TITLE = "print-monitor-local"


def _free_port() -> int:
    import socket

    sock = socket.socket()
    sock.bind((HOST, 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_until_up(port: int, timeout: float = 20.0) -> bool:
    import socket
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _attach_parent_console() -> None:
    """Anexa ao console do processo pai (modo CLI em executavel de janela).

    Empacotado com ``--windowed``, o executavel nao tem console proprio, entao a
    saida da CLI nao apareceria no terminal. Ao ser chamado a partir de um
    terminal, este truque (Windows) anexa ao console pai e reabre stdout/stderr.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        attach_parent_process = -1
        if ctypes.windll.kernel32.AttachConsole(attach_parent_process):
            sys.stdout = open("CONOUT$", "w", buffering=1, encoding="utf-8")
            sys.stderr = open("CONOUT$", "w", buffering=1, encoding="utf-8")
    except Exception:
        pass


def _show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, WINDOW_TITLE, 0x10)
    except Exception:
        print(message, file=sys.stderr)


def run_app() -> int:
    import threading

    from print_monitor.web import create_app

    port = _free_port()
    app = create_app()

    def serve() -> None:
        app.run(host=HOST, port=port, threaded=True, use_reloader=False)

    threading.Thread(target=serve, daemon=True).start()
    if not _wait_until_up(port):
        _show_error("Nao foi possivel iniciar o servico local.")
        return 1

    url = f"http://{HOST}:{port}/"
    try:
        import webview
    except ImportError:
        # Alternativa: navegador padrao. Mantem o processo vivo.
        import webbrowser

        webbrowser.open(url)
        threading.Event().wait()
        return 0

    webview.create_window(
        WINDOW_TITLE, url, width=1180, height=820, min_size=(900, 600)
    )
    webview.start()
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if argv:
        _attach_parent_console()
        return cli_main(argv)
    try:
        return run_app()
    except Exception as exc:  # janela sem console: erro precisa ser visivel
        import traceback

        _show_error(f"Falha ao iniciar o aplicativo:\n{exc}\n\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
