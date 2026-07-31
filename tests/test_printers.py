"""Testes de cadastro e validacao de impressoras."""

from __future__ import annotations

import pytest

from print_monitor.printers import register_printer, update_printer, validate_ip


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


def test_update_printer_normalizes_fields_and_preserves_history_and_active(db):
    printer = register_printer(db, name="Antiga", ip="192.168.0.10", location="TI")
    assert printer.id is not None
    reading_id = db.add_reading(printer.id, 123_456)
    db.set_printer_active(printer.id, False)

    updated = update_printer(
        db,
        printer.id,
        name="  Nova  ",
        ip=" 2001:0db8::1 ",
        location="  Financeiro  ",
        model="  Modelo X  ",
        serial="  SERIE-01  ",
    )

    assert updated.id == printer.id
    assert updated.name == "Nova"
    assert updated.ip == "2001:db8::1"
    assert updated.location == "Financeiro"
    assert updated.model == "Modelo X"
    assert updated.serial == "SERIE-01"
    assert updated.active is False
    assert db.get_reading(reading_id) is not None


def test_update_printer_rejects_ip_used_by_another_printer(db):
    first = register_printer(db, name="Primeira", ip="192.168.0.10")
    register_printer(db, name="Segunda", ip="192.168.0.11")
    assert first.id is not None

    with pytest.raises(ValueError, match="Ja existe"):
        update_printer(db, first.id, name="Primeira", ip="192.168.0.11")

    unchanged = db.get_printer(first.id)
    assert unchanged is not None
    assert unchanged.ip == "192.168.0.10"


def test_update_printer_converts_unique_race_to_value_error(db, monkeypatch):
    first = register_printer(db, name="Primeira", ip="192.168.0.10")
    register_printer(db, name="Segunda", ip="192.168.0.11")
    assert first.id is not None
    monkeypatch.setattr(db, "get_printer_by_ip", lambda _ip: None)

    with pytest.raises(ValueError, match="Ja existe"):
        update_printer(db, first.id, name="Primeira", ip="192.168.0.11")


def test_printer_fields_have_reasonable_length_limits(db):
    with pytest.raises(ValueError, match="no maximo 120"):
        register_printer(db, name="X" * 121, ip="192.168.0.10")


# -- tolerancia a erro de digitacao no IP ---------------------------------


def test_register_printer_corrige_erros_de_digitacao(db):
    """O endereco copiado de uma etiqueta chega torto; o programa endireita."""
    printer = register_printer(db, name="HP 1", ip=" 192,168,O,5O:9100 ")
    assert printer.ip == "192.168.0.50"


def test_register_printer_corrige_zeros_a_esquerda(db):
    assert register_printer(db, name="HP 2", ip="192.168.020.005").ip == "192.168.20.5"


def test_validate_ip_explica_o_que_corrigir(db):
    """A mensagem tem de dizer o que fazer, nao apenas que esta errado."""
    with pytest.raises(ValueError, match="maior que 255"):
        validate_ip("192.168.0.300")
    with pytest.raises(ValueError, match="incompleto"):
        validate_ip("192.168.0")
    with pytest.raises(ValueError, match="Informe o endereço"):
        validate_ip("")


def test_update_printer_aceita_ip_torto(db):
    printer = register_printer(db, name="Alfa", ip="10.0.0.1")
    atualizada = update_printer(db, printer.id, name="Alfa", ip="10,0,0,9")
    assert atualizada.ip == "10.0.0.9"
