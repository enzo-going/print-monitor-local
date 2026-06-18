"""Calculo de volume de impressao e relatorios.

O volume de um periodo e a soma das diferencas *positivas* entre leituras
consecutivas dentro do intervalo. Diferencas negativas (reset/troca de contador)
sao descartadas, evitando valores incorretos por *rollover*.

As funcoes de calculo sao puras (operam sobre listas de ``Reading``), o que as
torna faceis de testar isoladamente da persistencia.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .db import Database
from .models import Reading


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """Retorna (inicio, fim) de um mes em UTC, ambos inclusivos.

    O fim e o ultimo microssegundo do mes, para que a comparacao ``<=`` capture
    qualquer leitura feita dentro do mes.
    """
    if not 1 <= month <= 12:
        raise ValueError("Mes deve estar entre 1 e 12.")
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime(year, month, last_day, tzinfo=timezone.utc) + timedelta(
        days=1
    ) - timedelta(microseconds=1)
    return start, end


def period_volume(
    readings: list[Reading], start: datetime, end: datetime
) -> int:
    """Volume de impressao no intervalo [start, end] (inclusivo).

    Soma as diferencas positivas entre leituras consecutivas ordenadas por
    tempo. Com 0 ou 1 leitura no intervalo, o volume e 0.
    """
    points = sorted(
        (r.collected_at, r.total_counter)
        for r in readings
        if start <= r.collected_at <= end
    )
    total = 0
    for (_, c0), (_, c1) in zip(points, points[1:]):
        delta = c1 - c0
        if delta > 0:
            total += delta
    return total


def monthly_volume(readings: list[Reading], year: int, month: int) -> int:
    """Volume de impressao de um mes especifico."""
    start, end = month_bounds(year, month)
    return period_volume(readings, start, end)


@dataclass(frozen=True)
class PrinterVolume:
    """Volume calculado para uma impressora em um periodo."""

    printer_id: int
    name: str
    ip: str
    location: str | None
    volume: int


def monthly_report(db: Database, year: int, month: int) -> list[PrinterVolume]:
    """Relatorio mensal: volume por impressora, ordenado do maior para o menor.

    Inclui todas as impressoras cadastradas (volume 0 quando nao houver leituras
    suficientes no mes).
    """
    start, end = month_bounds(year, month)
    result: list[PrinterVolume] = []
    for printer in db.list_printers():
        assert printer.id is not None
        readings = db.list_readings(printer_id=printer.id, start=start, end=end)
        result.append(
            PrinterVolume(
                printer_id=printer.id,
                name=printer.name,
                ip=printer.ip,
                location=printer.location,
                volume=period_volume(readings, start, end),
            )
        )
    result.sort(key=lambda pv: pv.volume, reverse=True)
    return result


def ranking(db: Database, year: int, month: int, limit: int | None = None) -> list[PrinterVolume]:
    """Ranking das impressoras mais usadas no mes (atalho sobre o relatorio)."""
    report = [pv for pv in monthly_report(db, year, month) if pv.volume > 0]
    return report[:limit] if limit else report
