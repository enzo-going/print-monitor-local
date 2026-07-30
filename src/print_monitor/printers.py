"""Cadastro e validacao de impressoras.

Camada de servico sobre ``db.py``: valida a entrada (IP) e normaliza os dados
antes de persistir.
"""

from __future__ import annotations

import ipaddress
import sqlite3
from dataclasses import dataclass

from .db import Database
from .models import Printer

MAX_NAME_LENGTH = 120
MAX_LOCATION_LENGTH = 120
MAX_MODEL_LENGTH = 160
MAX_SERIAL_LENGTH = 120


@dataclass(frozen=True)
class _PrinterFields:
    name: str
    ip: str
    location: str | None
    model: str | None
    serial: str | None


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


def _clean_text(value: str | None, label: str, max_length: int, *, required: bool) -> str | None:
    cleaned = (value or "").strip()
    if required and not cleaned:
        raise ValueError(f"{label} nao pode ser vazio.")
    if len(cleaned) > max_length:
        raise ValueError(f"{label} deve ter no maximo {max_length} caracteres.")
    return cleaned or None


def _normalize_fields(
    *,
    name: str,
    ip: str,
    location: str | None,
    model: str | None,
    serial: str | None,
) -> _PrinterFields:
    clean_name = _clean_text(name, "Nome da impressora", MAX_NAME_LENGTH, required=True)
    assert clean_name is not None
    return _PrinterFields(
        name=clean_name,
        ip=validate_ip(ip),
        location=_clean_text(location, "Local", MAX_LOCATION_LENGTH, required=False),
        model=_clean_text(model, "Modelo", MAX_MODEL_LENGTH, required=False),
        serial=_clean_text(serial, "Numero de serie", MAX_SERIAL_LENGTH, required=False),
    )


def _duplicate_ip_error(ip: str, exc: sqlite3.IntegrityError) -> ValueError:
    if "printers.ip" not in str(exc) and getattr(exc, "sqlite_errorname", "") != (
        "SQLITE_CONSTRAINT_UNIQUE"
    ):
        raise exc
    return ValueError(f"Ja existe uma impressora cadastrada com o IP {ip}.")


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
    fields = _normalize_fields(
        name=name,
        ip=ip,
        location=location,
        model=model,
        serial=serial,
    )
    if db.get_printer_by_ip(fields.ip) is not None:
        raise ValueError(f"Ja existe uma impressora cadastrada com o IP {fields.ip}.")

    try:
        printer_id = db.add_printer(
            name=fields.name,
            ip=fields.ip,
            location=fields.location,
            model=fields.model,
            serial=fields.serial,
        )
    except sqlite3.IntegrityError as exc:
        raise _duplicate_ip_error(fields.ip, exc) from exc
    printer = db.get_printer(printer_id)
    assert printer is not None  # acabou de ser inserida
    return printer


def update_printer(
    db: Database,
    printer_id: int,
    *,
    name: str,
    ip: str,
    location: str | None = None,
    model: str | None = None,
    serial: str | None = None,
) -> Printer:
    """Atualiza o cadastro sem alterar o estado nem as leituras da impressora."""
    if db.get_printer(printer_id) is None:
        raise ValueError("Impressora nao encontrada.")

    fields = _normalize_fields(
        name=name,
        ip=ip,
        location=location,
        model=model,
        serial=serial,
    )
    printer_with_ip = db.get_printer_by_ip(fields.ip)
    if printer_with_ip is not None and printer_with_ip.id != printer_id:
        raise ValueError(f"Ja existe uma impressora cadastrada com o IP {fields.ip}.")

    try:
        changed = db.update_printer(
            printer_id,
            name=fields.name,
            ip=fields.ip,
            location=fields.location,
            model=fields.model,
            serial=fields.serial,
        )
    except sqlite3.IntegrityError as exc:
        raise _duplicate_ip_error(fields.ip, exc) from exc
    if not changed:
        raise ValueError("Impressora nao encontrada.")

    printer = db.get_printer(printer_id)
    assert printer is not None
    return printer
