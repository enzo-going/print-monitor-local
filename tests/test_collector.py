"""Testes da orquestracao de coleta e selecao de backend."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

import pytest

from print_monitor.collector import (
    Collector,
    MockBackend,
    make_backend,
)
from print_monitor.config import Config
from print_monitor.db import Database
from print_monitor.models import MAX_COUNTER, Printer


def _config(backend: str) -> Config:
    return Config(
        db_path="data/test.db",
        backend=backend,
        snmp_community="public",
        snmp_port=161,
        snmp_timeout=2,
        snmp_retries=1,
    )


def test_make_backend_mock():
    backend, label = make_backend(_config("mock"))
    assert label == "mock"
    assert isinstance(backend, MockBackend)


def test_make_backend_snmp():
    from print_monitor.snmp import SNMPBackend

    backend, label = make_backend(_config("mock"), override="snmp")
    assert label == "snmp"
    assert isinstance(backend, SNMPBackend)


def test_make_backend_rejects_unknown_value():
    with pytest.raises(ValueError, match="Backend de coleta invalido"):
        make_backend(_config("desconhecido"))


class _FlakyBackend:
    """Backend de teste: falha para um IP especifico."""

    def read_total_counter(self, printer: Printer) -> int:
        if printer.ip.endswith(".99"):
            raise RuntimeError("impressora incompativel")
        return 100_000


def test_collect_all_records_failures(db):
    ok = db.add_printer(name="OK", ip="192.168.0.10")
    db.add_printer(name="Ruim", ip="192.168.0.99")

    collector = Collector(db, _FlakyBackend(), source="test")
    outcome = collector.collect_all()

    assert [r.printer_id for r in outcome.readings] == [ok]
    assert len(outcome.failures) == 1
    failed_printer, message = outcome.failures[0]
    assert failed_printer.ip == "192.168.0.99"
    assert "incompativel" in message
    # A leitura bem-sucedida foi persistida; a falha nao.
    assert len(db.list_readings()) == 1


class _ConcurrentBackend:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def read_total_counter(self, printer: Printer) -> int:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.03)
        with self.lock:
            self.active -= 1
        return 10_000


def test_collect_all_reads_in_parallel_and_writes_all(db):
    for index in range(4):
        db.add_printer(name=f"P{index}", ip=f"192.168.1.{index + 1}")
    backend = _ConcurrentBackend()

    outcome = Collector(db, backend, source="test").collect_all(workers=4)

    assert backend.max_active > 1
    assert len(outcome.readings) == 4
    assert len(db.list_readings()) == 4


def test_collect_returns_the_exact_persisted_timestamp(db):
    printer_id = db.add_printer(name="P", ip="192.168.2.1")
    printer = db.get_printer(printer_id)
    assert printer is not None

    reading = Collector(db, _FlakyBackend(), source="test").collect(printer)
    persisted = db.list_readings(printer_id=printer_id)[0]

    assert reading.collected_at == persisted.collected_at


class _InvalidCounterBackend:
    def read_total_counter(self, printer: Printer) -> int:
        return -1


def test_collect_all_rejects_invalid_counter_without_persisting(db):
    db.add_printer(name="P", ip="192.0.2.40")

    outcome = Collector(db, _InvalidCounterBackend(), source="test").collect_all()

    assert outcome.readings == []
    assert len(outcome.failures) == 1
    assert "Contador invalido" in outcome.failures[0][1]
    assert db.list_readings() == []


class _ResponseTimeBackend:
    def __init__(self):
        self.returned_at: dict[int, datetime] = {}

    def read_total_counter(self, printer: Printer) -> int:
        time.sleep(0.01 if printer.ip.endswith(".1") else 0.03)
        assert printer.id is not None
        self.returned_at[printer.id] = datetime.now(UTC)
        return 10_000 + printer.id


def test_collect_all_timestamps_each_reading_after_its_response(db):
    first = db.add_printer(name="P1", ip="192.0.2.1")
    second = db.add_printer(name="P2", ip="192.0.2.2")
    backend = _ResponseTimeBackend()

    outcome = Collector(db, backend, source="test").collect_all(workers=2)

    assert {reading.printer_id for reading in outcome.readings} == {first, second}
    for reading in outcome.readings:
        assert reading.collected_at >= backend.returned_at[reading.printer_id]


class _MixedCounterBackend:
    def read_total_counter(self, printer: Printer) -> int:
        return MAX_COUNTER + 1 if printer.ip.endswith(".2") else 123


def test_collect_all_preserves_valid_readings_when_one_counter_is_too_large(db):
    valid_id = db.add_printer(name="Valida", ip="192.0.2.1")
    db.add_printer(name="Invalida", ip="192.0.2.2")

    outcome = Collector(db, _MixedCounterBackend(), source="test").collect_all(workers=2)

    assert [(reading.printer_id, reading.total_counter) for reading in outcome.readings] == [
        (valid_id, 123)
    ]
    assert len(outcome.failures) == 1
    assert "Contador invalido" in outcome.failures[0][1]


class _PauseDuringReadBackend:
    def __init__(self, db_path, printer_to_pause: int):
        self.db_path = db_path
        self.printer_to_pause = printer_to_pause

    def read_total_counter(self, printer: Printer) -> int:
        if printer.id == self.printer_to_pause:
            with Database(self.db_path) as other_db:
                other_db.initialize()
                other_db.set_printer_active(self.printer_to_pause, False)
        return 500


def test_collect_all_keeps_other_readings_when_printer_is_paused_during_collection(tmp_path):
    db_path = tmp_path / "concurrent.db"
    with Database(db_path) as db:
        db.initialize()
        kept = db.add_printer(name="Mantida", ip="192.0.2.10")
        paused = db.add_printer(name="Pausada", ip="192.0.2.11")
        backend = _PauseDuringReadBackend(db_path, paused)

        outcome = Collector(db, backend, source="test").collect_all(workers=2)

        assert [(reading.printer_id, reading.total_counter) for reading in outcome.readings] == [
            (kept, 500)
        ]
        assert len(outcome.failures) == 1
        assert outcome.failures[0][0].id == paused
        assert "removida ou pausada" in outcome.failures[0][1]
