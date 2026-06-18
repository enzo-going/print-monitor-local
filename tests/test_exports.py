"""Testes da exportacao CSV."""

from __future__ import annotations

import csv
import io

from print_monitor.exports import CSV_HEADER, report_to_csv
from print_monitor.reports import PrinterVolume


def _pv(printer_id, name, ip, location, volume):
    return PrinterVolume(
        printer_id=printer_id, name=name, ip=ip, location=location, volume=volume
    )


def test_csv_has_header_and_rows():
    report = [
        _pv(1, "Alfa", "10.0.0.1", "Financeiro", 4500),
        _pv(2, "Beta", "10.0.0.2", None, 1000),
    ]
    text = report_to_csv(report, 2026, 6)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == CSV_HEADER
    assert rows[1] == ["1", "Alfa", "10.0.0.1", "Financeiro", "2026", "6", "4500"]
    # location None vira string vazia.
    assert rows[2] == ["2", "Beta", "10.0.0.2", "", "2026", "6", "1000"]


def test_csv_empty_report_has_only_header():
    text = report_to_csv([], 2026, 6)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows == [CSV_HEADER]
