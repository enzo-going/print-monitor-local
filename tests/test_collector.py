"""Testes da orquestracao de coleta e selecao de backend."""

from __future__ import annotations

from print_monitor.collector import (
    Collector,
    MockBackend,
    make_backend,
)
from print_monitor.config import Config
from print_monitor.models import Printer


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
