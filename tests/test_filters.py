"""Testes dos filtros de relatorio (impressora, IP, local)."""

from __future__ import annotations

from datetime import datetime, timezone

from print_monitor.models import Printer
from print_monitor.reports import filter_printers, monthly_report


def _p(pid, name, ip, location):
    return Printer(id=pid, name=name, ip=ip, location=location)


PRINTERS = [
    _p(1, "Alfa", "192.168.10.21", "Financeiro"),
    _p(2, "Beta", "192.168.20.30", "RH"),
    _p(3, "Gama", "10.0.0.5", "Financeiro"),
]


def test_filter_by_printer_id():
    out = filter_printers(PRINTERS, printer_id=2)
    assert [p.name for p in out] == ["Beta"]


def test_filter_by_ip_partial_case_insensitive():
    out = filter_printers(PRINTERS, ip="192.168.10")
    assert [p.name for p in out] == ["Alfa"]


def test_filter_by_location_partial():
    out = filter_printers(PRINTERS, location="financeiro")
    assert {p.name for p in out} == {"Alfa", "Gama"}


def test_filter_combined():
    out = filter_printers(PRINTERS, ip="192.168", location="RH")
    assert [p.name for p in out] == ["Beta"]


def test_no_filters_returns_all():
    assert len(filter_printers(PRINTERS)) == 3


def test_monthly_report_respects_filters(db):
    a = db.add_printer(name="Alfa", ip="192.168.10.21", location="Financeiro")
    db.add_printer(name="Beta", ip="192.168.20.30", location="RH")
    db.add_reading(a, 100_000, collected_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    db.add_reading(a, 104_500, collected_at=datetime(2026, 6, 30, tzinfo=timezone.utc))

    report = monthly_report(db, 2026, 6, location="Financeiro")
    assert [pv.name for pv in report] == ["Alfa"]
    assert report[0].volume == 4500
