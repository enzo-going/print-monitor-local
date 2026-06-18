"""Interface de linha de comando.

Subcomandos:
- ``init``           cria o banco de dados;
- ``add-printer``    cadastra uma impressora por IP;
- ``list-printers``  lista impressoras cadastradas;
- ``collect``        coleta leituras (Fase 1: backend simulado);
- ``report``         relatorio mensal de volume por impressora.
"""

from __future__ import annotations

import argparse
import sys

from .collector import Collector, MockBackend
from .config import load_config
from .db import Database
from .printers import register_printer
from .reports import monthly_report


def _open_db() -> Database:
    config = load_config()
    db = Database(config.db_path)
    db.initialize()
    return db


def cmd_init(args: argparse.Namespace) -> int:
    config = load_config()
    db = Database(config.db_path)
    db.initialize()
    db.close()
    print(f"Banco de dados pronto em: {config.db_path}")
    return 0


def cmd_add_printer(args: argparse.Namespace) -> int:
    db = _open_db()
    try:
        printer = register_printer(
            db,
            name=args.name,
            ip=args.ip,
            location=args.location,
            model=args.model,
            serial=args.serial,
        )
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        db.close()
        return 1
    print(f"Impressora cadastrada (id={printer.id}): {printer.name} [{printer.ip}]")
    db.close()
    return 0


def cmd_list_printers(args: argparse.Namespace) -> int:
    db = _open_db()
    printers = db.list_printers()
    db.close()
    if not printers:
        print("Nenhuma impressora cadastrada.")
        return 0
    print(f"{'ID':<4} {'NOME':<24} {'IP':<16} {'LOCAL':<18} {'MODELO'}")
    for p in printers:
        print(
            f"{p.id:<4} {p.name[:24]:<24} {p.ip:<16} "
            f"{(p.location or '-')[:18]:<18} {p.model or '-'}"
        )
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    db = _open_db()
    backend = MockBackend()
    collector = Collector(db, backend, source="mock")

    if args.all:
        readings = collector.collect_all()
        if not readings:
            print("Nenhuma impressora ativa para coletar.")
        for r in readings:
            print(f"Impressora {r.printer_id}: contador={r.total_counter}")
        db.close()
        return 0

    if args.printer_id is None:
        print("Informe --printer-id ou use --all.", file=sys.stderr)
        db.close()
        return 1

    printer = db.get_printer(args.printer_id)
    if printer is None:
        print(f"Impressora id={args.printer_id} nao encontrada.", file=sys.stderr)
        db.close()
        return 1
    reading = collector.collect(printer)
    print(f"Impressora {reading.printer_id}: contador={reading.total_counter}")
    db.close()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    db = _open_db()
    report = monthly_report(db, args.year, args.month)
    db.close()

    print(f"Relatorio mensal - {args.month:02d}/{args.year}")
    if not report:
        print("Nenhuma impressora cadastrada.")
        return 0
    print(f"{'IMPRESSORA':<24} {'IP':<16} {'LOCAL':<18} {'VOLUME':>8}")
    total = 0
    for pv in report:
        if args.printer_id is not None and pv.printer_id != args.printer_id:
            continue
        total += pv.volume
        print(
            f"{pv.name[:24]:<24} {pv.ip:<16} "
            f"{(pv.location or '-')[:18]:<18} {pv.volume:>8}"
        )
    print("-" * 68)
    print(f"{'TOTAL':<60} {total:>8}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="print-monitor",
        description="Monitor local de impressoras de rede e volume de impressao.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Cria o banco de dados.").set_defaults(func=cmd_init)

    p_add = sub.add_parser("add-printer", help="Cadastra uma impressora por IP.")
    p_add.add_argument("--name", required=True, help="Nome da impressora.")
    p_add.add_argument("--ip", required=True, help="Endereco IP da impressora.")
    p_add.add_argument("--location", help="Local/setor da impressora.")
    p_add.add_argument("--model", help="Modelo da impressora.")
    p_add.add_argument("--serial", help="Numero de serie.")
    p_add.set_defaults(func=cmd_add_printer)

    sub.add_parser("list-printers", help="Lista impressoras.").set_defaults(
        func=cmd_list_printers
    )

    p_col = sub.add_parser("collect", help="Coleta leituras (backend simulado).")
    p_col.add_argument("--printer-id", type=int, help="Id da impressora.")
    p_col.add_argument("--all", action="store_true", help="Coleta todas as ativas.")
    p_col.set_defaults(func=cmd_collect)

    p_rep = sub.add_parser("report", help="Relatorio mensal de volume.")
    p_rep.add_argument("--year", type=int, required=True, help="Ano (ex.: 2026).")
    p_rep.add_argument("--month", type=int, required=True, help="Mes (1-12).")
    p_rep.add_argument("--printer-id", type=int, help="Filtra por impressora.")
    p_rep.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
