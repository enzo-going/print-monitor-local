"""Testes de persistencia (impressoras e leituras)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest


def _dt(year, month, day) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


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


def test_list_readings_period_filter(db):
    pid = db.add_printer(name="HP 1", ip="192.168.0.10")
    db.add_reading(pid, 100, collected_at=_dt(2026, 5, 31))
    db.add_reading(pid, 200, collected_at=_dt(2026, 6, 15))
    db.add_reading(pid, 300, collected_at=_dt(2026, 7, 1))

    in_june = db.list_readings(
        printer_id=pid, start=_dt(2026, 6, 1), end=_dt(2026, 6, 30)
    )
    assert [r.total_counter for r in in_june] == [200]


def test_foreign_key_cascade_on_printer_delete(db):
    pid = db.add_printer(name="HP 1", ip="192.168.0.10")
    db.add_reading(pid, 100, collected_at=_dt(2026, 6, 1))
    db.conn.execute("DELETE FROM printers WHERE id = ?", (pid,))
    db.conn.commit()
    assert db.list_readings(printer_id=pid) == []
