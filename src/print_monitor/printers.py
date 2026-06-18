"""Cadastro e validacao de impressoras.

Camada de servico sobre ``db.py``: valida a entrada (IP) e normaliza os dados
antes de persistir.
"""

from __future__ import annotations

import ipaddress

from .db import Database
from .models import Printer


def validate_ip(ip: str) -> str:
    """Valida e normaliza um endereco IP (v4 ou v6).

    Levanta ``ValueError`` se o IP for invalido.
    """
    ip = (ip or "").strip()
    if not ip:
        raise ValueError("IP nao pode ser vazio.")
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError as exc:
        raise ValueError(f"IP invalido: {ip!r}") from exc


def register_printer(
    db: Database,
    name: str,
    ip: str,
    location: str | None = None,
    model: str | None = None,
    serial: str | None = None,
) -> Printer:
    """Cadastra uma impressora validando o IP e impedindo duplicidade.

    Levanta ``ValueError`` em caso de nome vazio, IP invalido ou IP ja cadastrado.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Nome da impressora nao pode ser vazio.")

    ip = validate_ip(ip)
    if db.get_printer_by_ip(ip) is not None:
        raise ValueError(f"Ja existe uma impressora cadastrada com o IP {ip}.")

    location = location.strip() if location else None
    model = model.strip() if model else None
    serial = serial.strip() if serial else None

    printer_id = db.add_printer(
        name=name, ip=ip, location=location, model=model, serial=serial
    )
    printer = db.get_printer(printer_id)
    assert printer is not None  # acabou de ser inserida
    return printer
