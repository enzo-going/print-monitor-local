"""Popula o banco com dados ficticios para demonstracao.

Cria algumas impressoras de exemplo e gera leituras historicas mensais usando o
backend simulado, de modo que os relatorios mensais tenham conteudo logo apos a
primeira execucao.

NAO usa dados reais. Execute com:

    python scripts/seed.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Garante que "src/" esteja no path quando executado diretamente.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from print_monitor.collector import MockBackend  # noqa: E402
from print_monitor.config import load_config  # noqa: E402
from print_monitor.db import Database  # noqa: E402
from print_monitor.printers import register_printer  # noqa: E402

# Impressoras ficticias (IPs de redes privadas, sem qualquer dado real).
SAMPLE_PRINTERS = [
    {"name": "HP LaserJet - Recepcao", "ip": "192.168.10.21", "location": "Recepcao", "model": "HP M404"},
    {"name": "Brother - Financeiro", "ip": "192.168.10.22", "location": "Financeiro", "model": "Brother L2540"},
    {"name": "Xerox - TI", "ip": "192.168.10.23", "location": "TI", "model": "Xerox B210"},
    {"name": "Epson - RH", "ip": "192.168.10.24", "location": "RH", "model": "Epson L3250"},
]

# Meses (ano, mes) para os quais geramos leituras de inicio e fim.
SAMPLE_MONTHS = [(2026, 4), (2026, 5), (2026, 6)]


def _month_edges(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    # Dia 28 existe em todos os meses; suficiente para uma leitura de "fim".
    end = datetime(year, month, 28, tzinfo=timezone.utc)
    return start, end


def main() -> int:
    config = load_config()
    db = Database(config.db_path)
    db.initialize()

    created = 0
    for spec in SAMPLE_PRINTERS:
        if db.get_printer_by_ip(spec["ip"]) is not None:
            continue
        register_printer(
            db,
            name=spec["name"],
            ip=spec["ip"],
            location=spec["location"],
            model=spec["model"],
        )
        created += 1

    readings = 0
    for printer in db.list_printers():
        for year, month in SAMPLE_MONTHS:
            for moment in _month_edges(year, month):
                counter = MockBackend(at=moment).read_total_counter(printer)
                db.add_reading(
                    printer.id, counter, collected_at=moment, source="seed"
                )
                readings += 1

    db.close()
    print(
        f"Seed concluido: {created} impressora(s) nova(s), "
        f"{readings} leitura(s) gerada(s) em {config.db_path}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
