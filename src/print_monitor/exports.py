"""Exportacao de relatorios para CSV.

Funcoes puras que transformam um relatorio (lista de ``PrinterVolume``) em texto
CSV, sem dependencia de I/O — faceis de testar e reutilizar pela CLI e pelo
dashboard.
"""

from __future__ import annotations

import csv
import io

from .reports import PrinterVolume

CSV_HEADER = ["printer_id", "name", "ip", "location", "year", "month", "volume"]


def report_to_csv(report: list[PrinterVolume], year: int, month: int) -> str:
    """Serializa um relatorio mensal para CSV (com cabecalho).

    Usa ``\\r\\n`` como terminador de linha (padrao CSV), seguro para abrir em
    planilhas no Windows.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    for pv in report:
        writer.writerow(
            [
                pv.printer_id,
                pv.name,
                pv.ip,
                pv.location or "",
                year,
                month,
                pv.volume,
            ]
        )
    return buffer.getvalue()
