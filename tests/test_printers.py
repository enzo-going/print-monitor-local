"""Testes de cadastro e validacao de impressoras."""

from __future__ import annotations

import pytest

from print_monitor.printers import register_printer, validate_ip


def test_validate_ip_accepts_valid_ipv4():
    assert validate_ip(" 192.168.0.10 ") == "192.168.0.10"


def test_validate_ip_rejects_invalid():
    with pytest.raises(ValueError):
        validate_ip("999.1.1.1")
    with pytest.raises(ValueError):
        validate_ip("nao-e-ip")
    with pytest.raises(ValueError):
        validate_ip("")


def test_register_printer_persists(db):
    printer = register_printer(db, name="HP 1", ip="192.168.0.10", location="TI")
    assert printer.id is not None
    assert db.get_printer_by_ip("192.168.0.10") is not None


def test_register_printer_requires_name(db):
    with pytest.raises(ValueError):
        register_printer(db, name="   ", ip="192.168.0.10")


def test_register_printer_rejects_duplicate_ip(db):
    register_printer(db, name="HP 1", ip="192.168.0.10")
    with pytest.raises(ValueError, match="Ja existe"):
        register_printer(db, name="HP 2", ip="192.168.0.10")


def test_register_printer_normalizes_ip(db):
    printer = register_printer(db, name="HP 1", ip=" 10.0.0.1 ")
    assert printer.ip == "10.0.0.1"
