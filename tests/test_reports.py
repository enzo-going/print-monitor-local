"""Testes do calculo de volume e dos relatorios."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from print_monitor.models import Reading
from print_monitor.reports import (
    month_bounds,
    monthly_report,
    monthly_volume,
    period_usage,
    period_volume,
    ranking,
)


def _reading(counter: int, year: int, month: int, day: int) -> Reading:
    return Reading(
        id=None,
        printer_id=1,
        total_counter=counter,
        collected_at=datetime(year, month, day, tzinfo=UTC),
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
        _reading(103_000, 2026, 7, 1),  # fora (julho)
    ]
    assert monthly_volume(readings, 2026, 6) == 1500


def test_volume_uses_last_reading_before_month_as_baseline():
    readings = [
        _reading(99_500, 2026, 5, 31),
        _reading(101_000, 2026, 6, 15),
    ]
    assert monthly_volume(readings, 2026, 6) == 1500


def test_single_reading_is_waiting_not_confirmed_zero():
    start, end = month_bounds(2026, 6)
    usage = period_usage([_reading(100_000, 2026, 6, 15)], start, end)
    assert usage.volume == 0
    assert usage.measurable is False
    assert usage.state == "waiting_baseline"


def test_two_equal_readings_are_a_measured_zero():
    start, end = month_bounds(2026, 6)
    usage = period_usage(
        [_reading(100_000, 2026, 6, 1), _reading(100_000, 2026, 6, 15)],
        start,
        end,
    )
    assert usage.volume == 0
    assert usage.measurable is True
    assert usage.state == "no_increase"


def test_equal_readings_at_same_timestamp_do_not_create_interval():
    start, end = month_bounds(2026, 6)
    same_moment = datetime(2026, 6, 15, 9, 30, tzinfo=UTC)
    readings = [
        Reading(id=1, printer_id=1, total_counter=100_000, collected_at=same_moment),
        Reading(id=2, printer_id=1, total_counter=100_000, collected_at=same_moment),
    ]

    usage = period_usage(readings, start, end)

    assert usage.volume == 0
    assert usage.measurable is False
    assert usage.state == "waiting_baseline"
    assert usage.coverage_start == usage.coverage_end == same_moment


def test_different_counters_at_same_timestamp_require_review():
    start, end = month_bounds(2026, 6)
    same_moment = datetime(2026, 6, 15, 9, 30, tzinfo=UTC)
    readings = [
        Reading(id=1, printer_id=1, total_counter=100_000, collected_at=same_moment),
        Reading(id=2, printer_id=1, total_counter=100_500, collected_at=same_moment),
    ]

    usage = period_usage(readings, start, end)

    assert usage.volume == 0
    assert usage.measurable is False
    assert usage.state == "conflicting_readings"
    assert usage.coverage_start == usage.coverage_end == same_moment


def test_conflicting_baseline_at_same_timestamp_requires_review():
    start, end = month_bounds(2026, 6)
    baseline_moment = datetime(2026, 5, 31, 23, 30, tzinfo=UTC)
    readings = [
        Reading(id=1, printer_id=1, total_counter=99_000, collected_at=baseline_moment),
        Reading(id=2, printer_id=1, total_counter=99_500, collected_at=baseline_moment),
        _reading(100_000, 2026, 6, 2),
    ]

    usage = period_usage(readings, start, end)

    assert usage.measurable is False
    assert usage.state == "conflicting_readings"


def test_volume_with_counter_reset_is_robust():
    # Reset do contador (troca/zeragem): a diferenca negativa e descartada.
    readings = [
        _reading(124_000, 2026, 6, 1),
        _reading(125_000, 2026, 6, 10),  # +1000
        _reading(300, 2026, 6, 20),  # reset (descartado)
        _reading(1_300, 2026, 6, 30),  # +1000
    ]
    assert monthly_volume(readings, 2026, 6) == 2000
    start, end = month_bounds(2026, 6)
    usage = period_usage(readings, start, end)
    assert usage.measurable is False
    assert usage.state == "counter_reset"


def test_volume_zero_with_few_readings():
    assert monthly_volume([], 2026, 6) == 0
    assert monthly_volume([_reading(100, 2026, 6, 15)], 2026, 6) == 0


def test_month_bounds_inclusive_end():
    start, end = month_bounds(2026, 2)  # ano nao bissexto: 28 dias
    assert start == datetime(2026, 2, 1, tzinfo=UTC)
    assert end.year == 2026 and end.month == 2 and end.day == 28
    assert end < datetime(2026, 3, 1, tzinfo=UTC)


def test_month_bounds_december():
    start, end = month_bounds(2026, 12)
    assert start == datetime(2026, 12, 1, tzinfo=UTC)
    assert end < datetime(2027, 1, 1, tzinfo=UTC)


def test_month_bounds_supports_last_representable_month():
    start, end = month_bounds(9999, 12)

    assert start == datetime(9999, 12, 1, tzinfo=UTC)
    assert end == datetime.max.replace(tzinfo=UTC)

    local_start, local_end = month_bounds(9999, 12, timezone(timedelta(hours=-3)))
    assert local_start == datetime(9999, 12, 1, 3, tzinfo=UTC)
    assert local_end == datetime.max.replace(tzinfo=UTC)


def test_month_bounds_respect_local_timezone():
    brazil_offset = timezone(timedelta(hours=-3))
    start, end = month_bounds(2026, 7, brazil_offset)
    assert start == datetime(2026, 7, 1, 3, tzinfo=UTC)
    assert end < datetime(2026, 8, 1, 3, tzinfo=UTC)


def test_month_bounds_rejects_out_of_range():
    import pytest

    with pytest.raises(ValueError):
        month_bounds(2026, 13)
    with pytest.raises(ValueError):
        month_bounds(0, 6)
    with pytest.raises(ValueError):
        month_bounds(99999, 6)


def test_monthly_report_and_ranking(db):
    a = db.add_printer(name="Alfa", ip="10.0.0.1", location="Financeiro")
    b = db.add_printer(name="Beta", ip="10.0.0.2", location="RH")
    db.add_printer(name="Gama", ip="10.0.0.3")  # sem leituras -> volume 0

    db.add_reading(a, 100_000, collected_at=datetime(2026, 6, 1, tzinfo=UTC))
    db.add_reading(a, 104_500, collected_at=datetime(2026, 6, 30, tzinfo=UTC))
    db.add_reading(b, 50_000, collected_at=datetime(2026, 6, 1, tzinfo=UTC))
    db.add_reading(b, 51_000, collected_at=datetime(2026, 6, 30, tzinfo=UTC))

    report = monthly_report(db, 2026, 6)
    # Ordenado do maior para o menor volume.
    assert [pv.name for pv in report] == ["Alfa", "Beta", "Gama"]
    assert [pv.volume for pv in report] == [4500, 1000, 0]

    top = ranking(db, 2026, 6, limit=1)
    assert len(top) == 1 and top[0].name == "Alfa"


def test_monthly_report_fetches_baseline_from_database(db):
    printer_id = db.add_printer(name="Alfa", ip="192.0.2.10")
    db.add_reading(printer_id, 120_000, collected_at=datetime(2026, 5, 31, tzinfo=UTC))
    db.add_reading(printer_id, 126_543, collected_at=datetime(2026, 6, 20, tzinfo=UTC))

    report = monthly_report(db, 2026, 6)

    assert report[0].volume == 6543
    assert report[0].measurable is True
    assert report[0].state == "partial"
    assert report[0].opening_counter == 120_000
    assert report[0].closing_counter == 126_543


def test_baseline_without_reading_in_month_has_no_false_coverage():
    start, end = month_bounds(2026, 7)
    usage = period_usage([_reading(100_000, 2026, 6, 30)], start, end)
    assert usage.state == "no_reading_in_period"
    assert usage.coverage_start is None
    assert usage.coverage_end is None
