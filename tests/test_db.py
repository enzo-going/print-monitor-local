"""Testes de persistencia (impressoras e leituras)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from print_monitor.models import MAX_COUNTER


def _dt(year, month, day) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def test_add_and_get_printer(db):
    printer_id = db.add_printer(name="HP 1", ip="192.168.0.10", location="TI")
    printer = db.get_printer(printer_id)
    assert printer is not None
    assert printer.id == printer_id
    assert printer.name == "HP 1"
    assert printer.ip == "192.168.0.10"
    assert printer.location == "TI"
    assert printer.active is True


def test_get_printer_by_ip(db):
    db.add_printer(name="HP 1", ip="10.0.0.5")
    found = db.get_printer_by_ip("10.0.0.5")
    assert found is not None and found.name == "HP 1"
    assert db.get_printer_by_ip("10.0.0.99") is None


def test_unique_ip_constraint(db):
    db.add_printer(name="A", ip="10.0.0.1")
    with pytest.raises(sqlite3.IntegrityError):
        db.add_printer(name="B", ip="10.0.0.1")


def test_list_printers_sorted_by_name(db):
    db.add_printer(name="Zeta", ip="10.0.0.2")
    db.add_printer(name="Alfa", ip="10.0.0.3")
    names = [p.name for p in db.list_printers()]
    assert names == ["Alfa", "Zeta"]


def test_add_and_query_readings_roundtrip(db):
    pid = db.add_printer(name="HP 1", ip="192.168.0.10")
    db.add_reading(pid, 120_000, collected_at=_dt(2026, 6, 1))
    db.add_reading(pid, 124_500, collected_at=_dt(2026, 6, 30))

    readings = db.list_readings(printer_id=pid)
    assert [r.total_counter for r in readings] == [120_000, 124_500]
    # Timestamps voltam como UTC timezone-aware.
    assert readings[0].collected_at == _dt(2026, 6, 1)


def test_add_readings_batches_in_one_call(db):
    pid = db.add_printer(name="HP 1", ip="192.168.0.11")
    ids = db.add_readings(
        [
            (pid, 100, _dt(2026, 6, 1), "snmp"),
            (pid, 200, _dt(2026, 6, 2), "snmp"),
        ]
    )

    assert len(ids) == 2
    assert [r.total_counter for r in db.list_readings(pid)] == [100, 200]


def test_counter_must_fit_sqlite_integer(db):
    pid = db.add_printer(name="HP 1", ip="192.168.0.12")

    with pytest.raises(ValueError, match="Contador invalido"):
        db.add_reading(pid, MAX_COUNTER + 1)

    assert db.list_readings(pid) == []


def test_conditional_batch_skips_inactive_or_removed_printers(db):
    active = db.add_printer(name="Ativa", ip="192.168.0.13")
    paused = db.add_printer(name="Pausada", ip="192.168.0.14")
    removed = db.add_printer(name="Removida", ip="192.168.0.15")
    db.set_printer_active(paused, False)
    db.delete_printer(removed)

    ids = db.add_readings_if_printers_active(
        [
            (active, 100, _dt(2026, 6, 1), "snmp"),
            (paused, 200, _dt(2026, 6, 1), "snmp"),
            (removed, 300, _dt(2026, 6, 1), "snmp"),
        ]
    )

    assert ids[0] is not None
    assert ids[1:] == [None, None]
    assert [(reading.printer_id, reading.total_counter) for reading in db.list_readings()] == [
        (active, 100)
    ]


def test_list_readings_period_filter(db):
    pid = db.add_printer(name="HP 1", ip="192.168.0.10")
    db.add_reading(pid, 100, collected_at=_dt(2026, 5, 31))
    db.add_reading(pid, 200, collected_at=_dt(2026, 6, 15))
    db.add_reading(pid, 300, collected_at=_dt(2026, 7, 1))

    in_june = db.list_readings(printer_id=pid, start=_dt(2026, 6, 1), end=_dt(2026, 6, 30))
    assert [r.total_counter for r in in_june] == [200]


def test_reading_summary_empty(db):
    summary = db.reading_summary()
    assert summary.total_readings == 0
    assert summary.printers_with_readings == 0
    assert summary.last_collected_at is None


def test_reading_summary_and_latest_per_printer(db):
    first = db.add_printer(name="Primeira", ip="192.168.0.20")
    second = db.add_printer(name="Segunda", ip="192.168.0.21")
    db.add_reading(first, 100, collected_at=_dt(2026, 6, 1))
    db.add_reading(first, 250, collected_at=_dt(2026, 6, 2))
    db.add_reading(second, 900, collected_at=_dt(2026, 6, 3))

    summary = db.reading_summary()
    assert summary.total_readings == 3
    assert summary.printers_with_readings == 2
    assert summary.last_collected_at == _dt(2026, 6, 3)
    assert [(r.printer_id, r.total_counter) for r in db.latest_readings()] == [
        (first, 250),
        (second, 900),
    ]


def test_foreign_key_cascade_on_printer_delete(db):
    pid = db.add_printer(name="HP 1", ip="192.168.0.10")
    db.add_reading(pid, 100, collected_at=_dt(2026, 6, 1))
    db.conn.execute("DELETE FROM printers WHERE id = ?", (pid,))
    db.conn.commit()
    assert db.list_readings(printer_id=pid) == []


def test_ignore_and_restore_reading_without_deleting_it(db):
    pid = db.add_printer(name="Alfa", ip="192.0.2.20")
    reading_id = db.add_reading(pid, 100, collected_at=_dt(2026, 6, 1))

    assert db.ignore_reading(reading_id, "contador incorreto") is True
    assert db.list_readings(pid) == []
    ignored = db.get_reading(reading_id)
    assert ignored is not None
    assert ignored.ignored is True
    assert ignored.ignore_reason == "contador incorreto"

    assert db.restore_reading(reading_id) is True
    assert [reading.total_counter for reading in db.list_readings(pid)] == [100]


def test_period_query_includes_only_latest_valid_baseline(db):
    pid = db.add_printer(name="Alfa", ip="192.0.2.21")
    old_id = db.add_reading(pid, 100, collected_at=_dt(2026, 5, 1))
    baseline_id = db.add_reading(pid, 200, collected_at=_dt(2026, 5, 31))
    period_id = db.add_reading(pid, 300, collected_at=_dt(2026, 6, 15))

    rows = db.list_period_readings_with_baseline(
        {pid},
        _dt(2026, 6, 1),
        _dt(2026, 6, 30),
    )
    assert [row.id for row in rows] == [baseline_id, period_id]
    assert old_id not in {row.id for row in rows}


def test_reading_deltas_returns_only_requested_valid_rows(db):
    pid = db.add_printer(name="Alfa", ip="192.0.2.22")
    first = db.add_reading(pid, 100, collected_at=_dt(2026, 6, 1))
    second = db.add_reading(pid, 175, collected_at=_dt(2026, 6, 2))
    ignored = db.add_reading(pid, 999, collected_at=_dt(2026, 6, 3))
    db.ignore_reading(ignored)

    assert db.reading_deltas({first, second, ignored}) == {
        first: None,
        second: 75,
    }
