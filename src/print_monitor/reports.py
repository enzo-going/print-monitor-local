"""Calculo de volume de impressao e relatorios.

O volume de um periodo e a soma das diferencas *positivas* entre leituras
consecutivas dentro do intervalo. Diferencas negativas (reset/troca de contador)
sao descartadas, evitando valores incorretos por *rollover*.

As funcoes de calculo sao puras (operam sobre listas de ``Reading``), o que as
torna faceis de testar isoladamente da persistencia.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from itertools import pairwise

from .db import Database
from .models import Printer, Reading


def system_timezone() -> tzinfo:
    """Retorna o fuso local configurado no sistema operacional."""
    return datetime.now().astimezone().tzinfo or UTC


def month_bounds(
    year: int,
    month: int,
    timezone: tzinfo = UTC,
) -> tuple[datetime, datetime]:
    """Retorna (inicio, fim) UTC de um mes no fuso informado.

    O fim e o ultimo microssegundo do mes, para que a comparacao ``<=`` capture
    qualquer leitura feita dentro do mes.
    """
    if not 1 <= month <= 12:
        raise ValueError("Mes deve estar entre 1 e 12.")
    if not 1 <= year <= 9999:
        raise ValueError("Ano fora do intervalo suportado (1-9999).")
    start_local = datetime(year, month, 1, tzinfo=timezone)
    last_day = calendar.monthrange(year, month)[1]
    next_month_local = datetime(year, month, last_day, tzinfo=timezone) + timedelta(days=1)
    start = start_local.astimezone(UTC)
    end = next_month_local.astimezone(UTC) - timedelta(microseconds=1)
    return start, end


@dataclass(frozen=True)
class PeriodUsage:
    """Resultado mensuravel de um intervalo de contadores acumulados."""

    volume: int
    measurable: bool
    state: str
    readings_in_period: int
    opening_counter: int | None
    closing_counter: int | None
    coverage_start: datetime | None
    coverage_end: datetime | None
    reset_detected: bool = False


def period_usage(readings: list[Reading], start: datetime, end: datetime) -> PeriodUsage:
    """Calcula volume e cobertura no intervalo [start, end].

    Usa a ultima leitura anterior ao inicio como linha de base. Sem ela, duas
    leituras dentro do periodo ainda produzem um resultado parcial. Uma leitura
    isolada nao e apresentada como zero: o estado fica ``waiting_baseline``.
    """
    ordered = sorted(
        (r for r in readings if r.collected_at <= end and not r.ignored),
        key=lambda r: (r.collected_at, r.id if r.id is not None else -1),
    )
    previous = [r for r in ordered if r.collected_at < start]
    in_period = [r for r in ordered if start <= r.collected_at <= end]
    baseline = previous[-1] if previous else None
    # Uma leitura exatamente na abertura do mes e uma linha de base melhor do
    # que qualquer ponto anterior: nao atribua ao mes o delta antes da fronteira.
    if in_period and in_period[0].collected_at == start:
        baseline = None
    points = ([baseline] if baseline else []) + in_period
    if len(points) < 2:
        only = in_period[-1] if in_period else None
        return PeriodUsage(
            volume=0,
            measurable=False,
            state="waiting_baseline" if in_period else "no_reading_in_period",
            readings_in_period=len(in_period),
            opening_counter=only.total_counter if only else None,
            closing_counter=only.total_counter if only else None,
            coverage_start=only.collected_at if only else None,
            coverage_end=only.collected_at if only else None,
        )

    total = 0
    reset_detected = False
    for first, second in pairwise(points):
        delta = second.total_counter - first.total_counter
        if delta > 0:
            total += delta
        elif delta < 0:
            reset_detected = True

    if reset_detected:
        state = "counter_reset"
    elif total == 0:
        state = "no_increase"
    elif points[0].collected_at == start:
        state = "measured"
    else:
        state = "partial"
    return PeriodUsage(
        volume=total,
        measurable=not reset_detected,
        state=state,
        readings_in_period=len(in_period),
        opening_counter=points[0].total_counter,
        closing_counter=points[-1].total_counter,
        coverage_start=points[0].collected_at,
        coverage_end=points[-1].collected_at,
        reset_detected=reset_detected,
    )


def period_volume(readings: list[Reading], start: datetime, end: datetime) -> int:
    """Mantem a API simples, retornando somente o volume observado."""
    return period_usage(readings, start, end).volume


def monthly_volume(
    readings: list[Reading],
    year: int,
    month: int,
    timezone: tzinfo = UTC,
) -> int:
    """Volume de impressao de um mes especifico."""
    start, end = month_bounds(year, month, timezone)
    return period_volume(readings, start, end)


@dataclass(frozen=True)
class PrinterVolume:
    """Volume calculado para uma impressora em um periodo."""

    printer_id: int
    name: str
    ip: str
    location: str | None
    volume: int
    measurable: bool = True
    state: str = "measured"
    readings_in_period: int = 0
    opening_counter: int | None = None
    closing_counter: int | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    reset_detected: bool = False


def filter_printers(
    printers: list[Printer],
    printer_id: int | None = None,
    ip: str | None = None,
    location: str | None = None,
) -> list[Printer]:
    """Aplica filtros opcionais a uma lista de impressoras.

    - ``printer_id``: correspondencia exata;
    - ``ip``: correspondencia parcial, sem diferenciar maiusculas;
    - ``location``: correspondencia parcial, sem diferenciar maiusculas.
    """
    ip_term = (ip or "").strip().lower()
    loc_term = (location or "").strip().lower()
    result = []
    for p in printers:
        if printer_id is not None and p.id != printer_id:
            continue
        if ip_term and ip_term not in p.ip.lower():
            continue
        if loc_term and loc_term not in (p.location or "").lower():
            continue
        result.append(p)
    return result


def monthly_report(
    db: Database,
    year: int,
    month: int,
    printer_id: int | None = None,
    ip: str | None = None,
    location: str | None = None,
    timezone: tzinfo = UTC,
) -> list[PrinterVolume]:
    """Relatorio mensal: volume por impressora, ordenado do maior para o menor.

    Inclui todas as impressoras que atendem aos filtros (volume 0 quando nao
    houver leituras suficientes no mes). Sem filtros, considera todas.
    """
    start, end = month_bounds(year, month, timezone)
    printers = filter_printers(db.list_printers(), printer_id=printer_id, ip=ip, location=location)
    printer_ids = {printer.id for printer in printers if printer.id is not None}
    readings_by_printer: dict[int, list[Reading]] = defaultdict(list)
    if printer_ids:
        # Uma unica consulta substitui o antigo padrao N+1 (uma por impressora).
        for reading in db.list_period_readings_with_baseline(printer_ids, start, end):
            if reading.printer_id in printer_ids:
                readings_by_printer[reading.printer_id].append(reading)

    result: list[PrinterVolume] = []
    for printer in printers:
        assert printer.id is not None
        readings = readings_by_printer[printer.id]
        usage = period_usage(readings, start, end)
        result.append(
            PrinterVolume(
                printer_id=printer.id,
                name=printer.name,
                ip=printer.ip,
                location=printer.location,
                volume=usage.volume,
                measurable=usage.measurable,
                state=usage.state,
                readings_in_period=usage.readings_in_period,
                opening_counter=usage.opening_counter,
                closing_counter=usage.closing_counter,
                coverage_start=usage.coverage_start,
                coverage_end=usage.coverage_end,
                reset_detected=usage.reset_detected,
            )
        )
    result.sort(key=lambda pv: pv.volume, reverse=True)
    return result


def ranking(
    db: Database,
    year: int,
    month: int,
    limit: int | None = None,
    printer_id: int | None = None,
    ip: str | None = None,
    location: str | None = None,
) -> list[PrinterVolume]:
    """Ranking das impressoras mais usadas no mes (atalho sobre o relatorio)."""
    report = [
        pv
        for pv in monthly_report(db, year, month, printer_id=printer_id, ip=ip, location=location)
        if pv.measurable and pv.volume > 0
    ]
    return report[:limit] if limit else report
