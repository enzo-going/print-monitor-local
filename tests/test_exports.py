"""Testes da exportacao CSV."""

from __future__ import annotations

import csv
import io

from print_monitor.exports import CSV_HEADER, report_to_csv
from print_monitor.reports import PrinterVolume


def _pv(printer_id, name, ip, location, volume):
    return PrinterVolume(printer_id=printer_id, name=name, ip=ip, location=location, volume=volume)


def test_csv_has_header_and_rows():
    report = [
        _pv(1, "Alfa", "10.0.0.1", "Financeiro", 4500),
        _pv(2, "Beta", "10.0.0.2", None, 1000),
    ]
    text = report_to_csv(report, 2026, 6)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == CSV_HEADER
    assert rows[1] == [
        "1",
        "Alfa",
        "10.0.0.1",
        "Financeiro",
        "2026",
        "6",
        "4500",
        "yes",
        "measured",
        "",
        "",
    ]
    # location None vira string vazia.
    assert rows[2] == [
        "2",
        "Beta",
        "10.0.0.2",
        "",
        "2026",
        "6",
        "1000",
        "yes",
        "measured",
        "",
        "",
    ]


def test_csv_does_not_present_unmeasurable_volume_as_zero():
    report = [
        PrinterVolume(
            printer_id=1,
            name="Alfa",
            ip="192.0.2.41",
            location=None,
            volume=0,
            measurable=False,
            state="waiting_baseline",
        )
    ]

    rows = list(csv.reader(io.StringIO(report_to_csv(report, 2026, 7))))

    assert rows[1][6] == ""
    assert rows[1][7:9] == ["no", "waiting_baseline"]


def test_csv_neutralizes_spreadsheet_formulas():
    report = [
        PrinterVolume(
            printer_id=1,
            name="=2+2",
            ip="192.0.2.42",
            location="+comando",
            volume=10,
        )
    ]

    rows = list(csv.reader(io.StringIO(report_to_csv(report, 2026, 7))))

    assert rows[1][1] == "'=2+2"
    assert rows[1][3] == "'+comando"


def test_csv_empty_report_has_only_header():
    text = report_to_csv([], 2026, 6)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows == [CSV_HEADER]


def test_excel_mode_uses_utf8_bom_and_semicolon_without_losing_accents():
    report = [_pv(1, "Recepção", "192.0.2.10", "Administração", 25)]

    text = report_to_csv(
        report,
        2026,
        7,
        delimiter=";",
        include_bom=True,
    )

    assert text.encode("utf-8").startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff")), delimiter=";"))
    assert rows[0] == CSV_HEADER
    assert rows[1][1:4] == ["Recepção", "192.0.2.10", "Administração"]
