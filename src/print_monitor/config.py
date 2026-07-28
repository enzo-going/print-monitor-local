"""Configuracao da aplicacao.

Le parametros do ambiente (e de um arquivo ``.env`` ao lado da aplicacao) com
valores padrao sensatos. O ``.env`` e interpretado por um parser proprio (sem
dependencias externas), garantindo que funcione tambem no executavel empacotado.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Raiz do projeto (dois niveis acima deste arquivo: src/print_monitor/config.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def app_base_dir() -> Path:
    """Diretorio base para dados e configuracao.

    Em execucao normal, e a raiz do projeto. Empacotado com PyInstaller
    (``sys.frozen``), e a pasta do executavel, mantendo o banco SQLite e o
    ``.env`` FORA do executavel (ao lado dele, em local gravavel).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def _load_dotenv() -> None:
    """Carrega o ``.env`` do diretorio base no ambiente (parser proprio).

    Formato simples ``CHAVE=VALOR`` por linha; linhas vazias e iniciadas por
    ``#`` sao ignoradas. Variaveis ja definidas no ambiente tem precedencia.
    """
    env_file = app_base_dir() / ".env"
    if not env_file.exists():
        return
    try:
        content = env_file.read_text(encoding="utf-8")
    except OSError:
        return
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


@dataclass(frozen=True)
class Config:
    """Parametros de execucao resolvidos a partir do ambiente."""

    db_path: Path
    backend: str
    snmp_community: str
    snmp_port: int
    snmp_timeout: float
    snmp_retries: int
    collection_workers: int = 8


def _env_number(
    name: str,
    default: str,
    cast: type[int] | type[float],
    *,
    minimum: float,
    maximum: float,
) -> int | float:
    raw = os.environ.get(name, default).strip()
    try:
        value = cast(raw)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser numerico; recebido {raw!r}.") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} deve estar entre {minimum:g} e {maximum:g}; recebido {raw!r}.")
    return value


def load_config() -> Config:
    """Resolve a configuracao a partir do ambiente e dos padroes."""
    _load_dotenv()

    base = app_base_dir()
    default_db_path = base / "data" / "print_monitor.db"
    db_path = Path(os.environ.get("PRINT_MONITOR_DB", str(default_db_path)))
    if not db_path.is_absolute():
        db_path = (base / db_path).resolve()

    backend = os.environ.get("PRINT_MONITOR_BACKEND", "snmp").strip().lower()
    if backend not in {"mock", "snmp"}:
        raise ValueError(f"PRINT_MONITOR_BACKEND deve ser 'mock' ou 'snmp'; recebido {backend!r}.")

    return Config(
        db_path=db_path,
        backend=backend,
        snmp_community=os.environ.get("SNMP_COMMUNITY", "public"),
        snmp_port=int(_env_number("SNMP_PORT", "161", int, minimum=1, maximum=65535)),
        snmp_timeout=float(_env_number("SNMP_TIMEOUT", "2", float, minimum=0.1, maximum=60)),
        snmp_retries=int(_env_number("SNMP_RETRIES", "1", int, minimum=0, maximum=10)),
        collection_workers=int(
            _env_number("PRINT_MONITOR_WORKERS", "8", int, minimum=1, maximum=128)
        ),
    )
