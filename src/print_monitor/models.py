"""Estruturas de dados do dominio.

Modelos simples e imutaveis que circulam entre os modulos. A persistencia fica
em ``db.py``; aqui ficam apenas os dados.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Printer:
    """Uma impressora de rede cadastrada."""

    id: int | None
    name: str
    ip: str
    location: str | None = None
    model: str | None = None
    serial: str | None = None
    active: bool = True


@dataclass(frozen=True)
class Reading:
    """Uma leitura do contador total de uma impressora em um instante."""

    id: int | None
    printer_id: int
    total_counter: int
    collected_at: datetime
    source: str = "manual"
