"""Testes da importacao de impressoras por CSV."""

from __future__ import annotations

from print_monitor.imports import decode_bytes, import_printers_from_csv

CSV_PONTO_VIRGULA = (
    "SETOR;MARCA;MODELO;IP;N° SÉRIE\n"
    "FINANCEIRO;SAMSUNG;M4080FX;192.168.60.80;088WB07JC10PBTV\n"
    "COMPRAS;HP;HP E52645;192.168.70.210;BRBSP740K9\n"
)

CSV_VIRGULA = (
    "NOME,IP,LOCAL\n"
    "Recepcao,10.0.0.5,Entrada\n"
)


def test_import_semicolon_with_accented_headers(db):
    result = import_printers_from_csv(db, CSV_PONTO_VIRGULA)
    assert result.added == 2
    assert result.skipped == 0
    assert result.errors == []

    fin = db.get_printer_by_ip("192.168.60.80")
    assert fin is not None
    assert fin.name == "FINANCEIRO"
    assert fin.location == "FINANCEIRO"
    assert fin.model == "SAMSUNG M4080FX"  # marca + modelo combinados
    assert fin.serial == "088WB07JC10PBTV"


def test_import_comma_with_name_column(db):
    result = import_printers_from_csv(db, CSV_VIRGULA)
    assert result.added == 1
    p = db.get_printer_by_ip("10.0.0.5")
    assert p.name == "Recepcao"
    assert p.location == "Entrada"


def test_import_skips_existing_ip(db):
    import_printers_from_csv(db, CSV_PONTO_VIRGULA)
    result = import_printers_from_csv(db, CSV_PONTO_VIRGULA)
    assert result.added == 0
    assert result.skipped == 2


def test_import_reports_invalid_ip(db):
    csv_text = "SETOR;IP\nTI;999.1.1.1\nRH;10.0.0.9\n"
    result = import_printers_from_csv(db, csv_text)
    assert result.added == 1
    assert len(result.errors) == 1
    assert result.errors[0][0] == 2  # linha do IP invalido


def test_import_without_ip_column(db):
    result = import_printers_from_csv(db, "SETOR;MODELO\nTI;X\n")
    assert result.added == 0
    assert result.errors and "IP" in result.errors[0][1]


def test_import_ignores_blank_lines(db):
    csv_text = "SETOR;IP\nTI;10.0.0.1\n;\nRH;10.0.0.2\n"
    result = import_printers_from_csv(db, csv_text)
    assert result.added == 2


def test_decode_bytes_handles_bom_and_cp1252():
    assert decode_bytes("SETOR\nTI".encode("utf-8-sig")).startswith("SETOR")
    assert "Á" in decode_bytes("Á".encode("cp1252"))
