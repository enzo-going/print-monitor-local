"""Exportacao de relatorios para CSV.

Funcoes puras que transformam um relatorio (lista de ``PrinterVolume``) em texto
CSV, sem dependencia de I/O — faceis de testar e reutilizar pela CLI e pelo
dashboard.
"""

from __future__ import annotations

import csv
import io

from .reports import PrinterVolume

CSV_HEADER = [
    "printer_id",
    "name",
    "ip",
    "location",
    "year",
    "month",
    "volume",
    "measurable",
    "state",
    "coverage_start",
    "coverage_end",
]


def _safe_spreadsheet_text(value: str) -> str:
    """Impede que texto controlado pelo usuario seja interpretado como formula."""
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{value}"
    return value


def report_to_csv(
    report: list[PrinterVolume],
    year: int,
    month: int,
    *,
    delimiter: str = ",",
    include_bom: bool = False,
) -> str:
    """Serializa um relatorio mensal para CSV (com cabecalho).

    Usa ``\\r\\n`` como terminador de linha (padrao CSV), seguro para abrir em
    planilhas no Windows. A interface web ativa BOM UTF-8 e ``;`` para facilitar
    a abertura direta no Excel em ambientes pt-BR; a API padrao continua usando
    virgula para preservar compatibilidade com integracoes existentes.
    """
    buffer = io.StringIO()
    if include_bom:
        buffer.write("\ufeff")
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(CSV_HEADER)
    for pv in report:
        writer.writerow(
            [
                pv.printer_id,
                _safe_spreadsheet_text(pv.name),
                _safe_spreadsheet_text(pv.ip),
                _safe_spreadsheet_text(pv.location or ""),
                year,
                month,
                pv.volume if pv.measurable else "",
                "yes" if pv.measurable else "no",
                pv.state,
                pv.coverage_start.isoformat() if pv.coverage_start else "",
                pv.coverage_end.isoformat() if pv.coverage_end else "",
            ]
        )
    return buffer.getvalue()
