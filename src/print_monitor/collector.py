"""Orquestracao da coleta de contadores.

Define a interface de backend (``CounterBackend``) e um backend simulado
(``MockBackend``) usado na Fase 1 e como fallback nos testes. O ``Collector``
le o contador de uma impressora e persiste a leitura.

O backend real (SNMP) e implementado em ``snmp.py`` (Fase 3) e segue a mesma
interface, podendo substituir o mock sem alterar o restante do codigo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Protocol

from .config import Config
from .db import Database, utcnow
from .models import Printer, Reading

# Data de referencia para a simulacao de contadores (inicio da "vida util").
_SIM_EPOCH = date(2024, 1, 1)


class CounterBackend(Protocol):
    """Contrato de um backend capaz de ler o contador total de uma impressora."""

    def read_total_counter(self, printer: Printer) -> int:
        ...


def _stable_seed(ip: str) -> int:
    """Gera um numero estavel e deterministico a partir do IP."""
    digest = hashlib.sha256(ip.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def simulated_counter(ip: str, at: datetime | None = None) -> int:
    """Contador total simulado, deterministico e monotonico no tempo.

    Cada IP recebe uma base e uma taxa diaria proprias, de modo que diferentes
    impressoras tenham volumes distintos e plausiveis. Util para dados ficticios
    em demonstracoes e testes.
    """
    at = at or utcnow()
    seed = _stable_seed(ip)
    base = 100_000 + (seed % 5_000)
    daily_rate = 80 + (seed % 220)  # entre 80 e ~300 paginas/dia
    days = max(0, (at.astimezone(timezone.utc).date() - _SIM_EPOCH).days)
    return base + days * daily_rate


class MockBackend:
    """Backend simulado: nao acessa a rede, gera contadores deterministicos."""

    def __init__(self, at: datetime | None = None):
        # Permite "congelar" o instante da leitura (util para seeds e testes).
        self._at = at

    def read_total_counter(self, printer: Printer) -> int:
        return simulated_counter(printer.ip, self._at)


class Collector:
    """Le contadores via um backend e persiste as leituras."""

    def __init__(self, db: Database, backend: CounterBackend, source: str = "mock"):
        self.db = db
        self.backend = backend
        self.source = source

    def collect(self, printer: Printer, at: datetime | None = None) -> Reading:
        """Coleta o contador de uma impressora e grava a leitura."""
        if printer.id is None:
            raise ValueError("Impressora sem id; cadastre-a antes de coletar.")
        counter = self.backend.read_total_counter(printer)
        reading_id = self.db.add_reading(
            printer_id=printer.id,
            total_counter=counter,
            collected_at=at,
            source=self.source,
        )
        return Reading(
            id=reading_id,
            printer_id=printer.id,
            total_counter=counter,
            collected_at=at or utcnow(),
            source=self.source,
        )

    def collect_all(self, at: datetime | None = None) -> "CollectionOutcome":
        """Coleta o contador de todas as impressoras ativas.

        Uma falha em uma impressora (ex.: incompativel ou inacessivel via SNMP)
        nao interrompe a coleta das demais: o erro e registrado em ``failures``.
        """
        outcome = CollectionOutcome()
        for printer in self.db.list_printers(only_active=True):
            try:
                outcome.readings.append(self.collect(printer, at=at))
            except Exception as exc:  # backend pode lancar erros variados (SNMP, rede)
                outcome.failures.append((printer, str(exc)))
        return outcome


@dataclass
class CollectionOutcome:
    """Resultado de uma coleta em lote: leituras bem-sucedidas e falhas."""

    readings: list[Reading] = field(default_factory=list)
    failures: list[tuple[Printer, str]] = field(default_factory=list)


def make_backend(
    config: Config, override: str | None = None
) -> tuple[CounterBackend, str]:
    """Cria o backend de coleta conforme a configuracao.

    Retorna ``(backend, rotulo)``. Backends suportados: ``mock`` (Fase 1) e
    ``snmp`` (Fase 3). O rotulo e usado como ``source`` das leituras.
    """
    name = (override or config.backend or "mock").strip().lower()
    if name == "snmp":
        from .snmp import SNMPBackend

        return SNMPBackend(config), "snmp"
    return MockBackend(), "mock"
