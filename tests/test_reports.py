"""Testes do calculo de volume e dos relatorios."""

from __future__ import annotations

from datetime import datetime, timezone

from print_monitor.models import Reading
from print_monitor.reports import (
    month_bounds,
    monthly_report,
    monthly_volume,
    period_volume,
    ranking,
)


def _reading(counter: int, year: int, month: int, day: int) -> Reading:
    return Reading(
        id=None,
        printer_id=1,
        total_counter=counter,
        collected_at=datetime(year, month, day, tzinfo=timezone.utc),
    )


def test_period_volume_basic_example():
    # Exemplo do projeto: 120000 -> 124500 em junho => 4500.
    readings = [_reading(120_000, 2026, 6, 1), _reading(124_500, 2026, 6, 30)]
    start, end = month_bounds(2026, 6)
    assert period_volume(readings, start, end) == 4500


def test_monthly_volume_multiple_readings():
    readings = [
        _reading(100_000, 2026, 6, 1),
        _reading(101_000, 2026, 6, 10),
        _reading(101_750, 2026, 6, 20),
        _reading(102_000, 2026, 6, 30),
    ]
    assert monthly_volume(readings, 2026, 6) == 2000


def test_volume_ignores_other_months():
    readings = [
        _reading(100_000, 2026, 5, 31),  # fora (maio)
        _reading(100_500, 2026, 6, 1),
        _reading(102_000, 2026, 6, 30),
        _reading(103_000, 2026, 7, 1),   # fora (julho)
    ]
    assert monthly_volume(readings, 2026, 6) == 1500


def test_volume_with_counter_reset_is_robust():
    # Reset do contador (troca/zeragem): a diferenca negativa e descartada.
    readings = [
        _reading(124_000, 2026, 6, 1),
        _reading(125_000, 2026, 6, 10),  # +1000
        _reading(300, 2026, 6, 20),      # reset (descartado)
        _reading(1_300, 2026, 6, 30),    # +1000
    ]
    assert monthly_volume(readings, 2026, 6) == 2000


def test_volume_zero_with_few_readings():
    assert monthly_volume([], 2026, 6) == 0
    assert monthly_volume([_reading(100, 2026, 6, 15)], 2026, 6) == 0


def test_month_bounds_inclusive_end():
    start, end = month_bounds(2026, 2)  # ano nao bissexto: 28 dias
    assert start == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert end.year == 2026 and end.month == 2 and end.day == 28
    assert end < datetime(2026, 3, 1, tzinfo=timezone.utc)


def test_month_bounds_december():
    start, end = month_bounds(2026, 12)
    assert start == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert end < datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_monthly_report_and_ranking(db):
    a = db.add_printer(name="Alfa", ip="10.0.0.1", location="Financeiro")
    b = db.add_printer(name="Beta", ip="10.0.0.2", location="RH")
    db.add_printer(name="Gama", ip="10.0.0.3")  # sem leituras -> volume 0

    db.add_reading(a, 100_000, collected_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    db.add_reading(a, 104_500, collected_at=datetime(2026, 6, 30, tzinfo=timezone.utc))
    db.add_reading(b, 50_000, collected_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    db.add_reading(b, 51_000, collected_at=datetime(2026, 6, 30, tzinfo=timezone.utc))

    report = monthly_report(db, 2026, 6)
    # Ordenado do maior para o menor volume.
    assert [pv.name for pv in report] == ["Alfa", "Beta", "Gama"]
    assert [pv.volume for pv in report] == [4500, 1000, 0]

    top = ranking(db, 2026, 6, limit=1)
    assert len(top) == 1 and top[0].name == "Alfa"
