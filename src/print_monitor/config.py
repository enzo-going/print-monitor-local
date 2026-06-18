"""Configuracao da aplicacao.

Le parametros do ambiente (opcionalmente de um arquivo ``.env``) com valores
padrao sensatos. O carregamento de ``.env`` e opcional: se ``python-dotenv`` nao
estiver instalado, a aplicacao continua funcionando com variaveis de ambiente e
padroes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Raiz do projeto (dois niveis acima deste arquivo: src/print_monitor/config.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "print_monitor.db"


def _load_dotenv_if_available() -> None:
    """Carrega ``.env`` da raiz do projeto, se python-dotenv estiver presente."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)


@dataclass(frozen=True)
class Config:
    """Parametros de execucao resolvidos a partir do ambiente."""

    db_path: Path
    backend: str
    snmp_community: str
    snmp_port: int
    snmp_timeout: int
    snmp_retries: int


def load_config() -> Config:
    """Resolve a configuracao a partir do ambiente e dos padroes."""
    _load_dotenv_if_available()

    db_path = Path(os.environ.get("PRINT_MONITOR_DB", str(DEFAULT_DB_PATH)))
    if not db_path.is_absolute():
        db_path = (PROJECT_ROOT / db_path).resolve()

    return Config(
        db_path=db_path,
        backend=os.environ.get("PRINT_MONITOR_BACKEND", "mock").strip().lower(),
        snmp_community=os.environ.get("SNMP_COMMUNITY", "public"),
        snmp_port=int(os.environ.get("SNMP_PORT", "161")),
        snmp_timeout=int(os.environ.get("SNMP_TIMEOUT", "2")),
        snmp_retries=int(os.environ.get("SNMP_RETRIES", "1")),
    )
