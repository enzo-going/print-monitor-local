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
from ipaddress import ip_address

from .collector import Collector, make_backend
from .config import load_config
from .db import Database
from .discovery import DEFAULT_PRINTER_PORTS, discover
from .exports import report_to_csv
from .imports import decode_bytes, import_printers_from_csv
from .printers import register_printer
from .reports import monthly_report, system_timezone


def _open_db() -> Database:
    config = load_config()
    db = Database(config.db_path)
    db.initialize()
    return db


def _is_loopback_host(host: str) -> bool:
    """Aceita somente enderecos locais para o painel sem autenticacao."""
    normalized = host.strip().lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


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
    config = load_config()
    db = Database(config.db_path)
    db.initialize()
    backend, source = make_backend(config, override=args.backend)
    collector = Collector(db, backend, source=source)
    print(f"Backend de coleta: {source}")

    if args.all:
        outcome = collector.collect_all(workers=args.workers or config.collection_workers)
        if not outcome.readings and not outcome.failures:
            print("Nenhuma impressora ativa para coletar.")
        for r in outcome.readings:
            print(f"Impressora {r.printer_id}: contador={r.total_counter}")
        for printer, error in outcome.failures:
            print(f"Falha na impressora {printer.id} [{printer.ip}]: {error}", file=sys.stderr)
        if outcome.readings and outcome.failures:
            print(
                f"{len(outcome.readings)} lida(s) com sucesso, "
                f"{len(outcome.failures)} sem resposta."
            )
        db.close()
        # Codigo de erro somente quando NENHUMA impressora respondeu. Em um
        # parque real sempre ha alguma desligada; marcar a tarefa agendada do
        # Windows como falha todo dia ensina o usuario a ignora-la, justamente
        # o alarme que deveria avisar quando a coleta parar de vez.
        return 0 if (outcome.readings or not outcome.failures) else 1

    if args.printer_id is None:
        print("Informe --printer-id ou use --all.", file=sys.stderr)
        db.close()
        return 1

    printer = db.get_printer(args.printer_id)
    if printer is None:
        print(f"Impressora id={args.printer_id} nao encontrada.", file=sys.stderr)
        db.close()
        return 1
    try:
        reading = collector.collect(printer)
    except Exception as exc:  # falha de backend (SNMP, rede)
        print(f"Falha ao coletar de {printer.ip}: {exc}", file=sys.stderr)
        db.close()
        return 1
    print(f"Impressora {reading.printer_id}: contador={reading.total_counter}")
    db.close()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    db = _open_db()
    report = monthly_report(
        db,
        args.year,
        args.month,
        printer_id=args.printer_id,
        timezone=system_timezone(),
    )
    db.close()

    print(f"Relatorio mensal - {args.month:02d}/{args.year}")
    if not report:
        print("Nenhuma impressora para os filtros informados.")
        return 0
    print(f"{'IMPRESSORA':<24} {'IP':<16} {'LOCAL':<18} {'VOLUME':>12}")
    total = 0
    for pv in report:
        if pv.measurable:
            total += pv.volume
            volume = str(pv.volume)
        else:
            volume = "aguardando"
        print(f"{pv.name[:24]:<24} {pv.ip:<16} {(pv.location or '-')[:18]:<18} {volume:>12}")
    print("-" * 72)
    print(f"{'TOTAL MEDIDO':<60} {total:>12}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    db = _open_db()
    report = monthly_report(
        db,
        args.year,
        args.month,
        printer_id=args.printer_id,
        ip=args.ip,
        location=args.location,
        timezone=system_timezone(),
    )
    db.close()
    csv_text = report_to_csv(report, args.year, args.month)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as fh:
            fh.write(csv_text)
        print(f"CSV gravado em: {args.output}")
    else:
        # Escreve os bytes diretamente para preservar os terminadores CRLF do CSV
        # (evita que o modo texto do stdout no Windows os transforme em CR CR LF).
        try:
            sys.stdout.buffer.write(csv_text.encode("utf-8"))
        except AttributeError:  # stdout sem buffer (ex.: capturado em teste)
            sys.stdout.write(csv_text)
    return 0


def cmd_import_printers(args: argparse.Namespace) -> int:
    try:
        with open(args.file, "rb") as fh:
            text = decode_bytes(fh.read())
    except OSError as exc:
        print(f"Nao foi possivel ler o arquivo: {exc}", file=sys.stderr)
        return 1
    db = _open_db()
    result = import_printers_from_csv(db, text)
    db.close()
    print(
        f"Importadas: {result.added}; ja existentes: {result.skipped}; "
        f"com erro: {len(result.errors)}"
    )
    for line_no, message in result.errors:
        print(f"  linha {line_no}: {message}", file=sys.stderr)
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Consulta um IP e mostra o que o equipamento respondeu.

    Serve para separar "impressora desligada" de "IP errado" e de "SNMP
    desabilitado" sem precisar cadastrar nada antes.
    """
    from .netaddr import IPError, normalize_ip
    from .snmp import SNMPError, diagnose_silence, identify

    config = load_config()
    try:
        ip = normalize_ip(args.ip)
    except IPError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    if ip != args.ip.strip():
        print(f"IP interpretado como: {ip}")

    try:
        ident = identify(
            ip,
            community=config.snmp_community,
            port=config.snmp_port,
            timeout=max(1.0, config.snmp_timeout),
            version=config.snmp_version,
        )
    except SNMPError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    if not ident.responded:
        print(f"Erro: {diagnose_silence(ip)}", file=sys.stderr)
        return 1

    print(f"Endereco:  {ip}")
    print(f"Nome:      {ident.name or '-'}")
    print(f"Modelo:    {ident.model or '-'}")
    print(f"Serie:     {ident.serial or '-'}")
    print(f"Local:     {ident.location or '-'}")
    print(f"Contador:  {ident.counter if ident.counter is not None else '- (nao publicado)'}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    config = load_config()
    try:
        ports = tuple(int(p) for p in args.ports.split(",") if p.strip())
    except ValueError:
        print("Lista de portas invalida.", file=sys.stderr)
        return 1
    if not ports:
        ports = DEFAULT_PRINTER_PORTS

    try:
        found = discover(
            args.network,
            ports=ports,
            timeout=args.timeout,
            workers=args.workers,
            max_hosts=args.max_hosts,
            snmp_confirm=args.snmp,
            config=config,
        )
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    if not found:
        print("Nenhum host com portas de impressao encontrado.")
        return 0

    print(f"{'IP':<18} {'CONTADOR':>10}  {'CONFIANCA':<15} NOME")
    for d in found:
        counter = str(d.snmp_counter) if d.snmp_counter is not None else "-"
        print(f"{d.ip:<18} {counter:>10}  {d.confidence:<15} {d.suggested_name}")

    if args.register:
        db = _open_db()
        added = 0
        for d in found:
            if db.get_printer_by_ip(d.ip) is None:
                # Nome, modelo e serie vem do proprio equipamento quando ele os
                # publica; sem isso a lista virava dezenas de "Impressora <IP>".
                register_printer(
                    db,
                    name=d.suggested_name,
                    ip=d.ip,
                    location=d.location,
                    model=d.model,
                    serial=d.serial,
                )
                added += 1
        db.close()
        print(f"{added} impressora(s) cadastrada(s).")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    if not _is_loopback_host(args.host):
        print(
            "Por seguranca, o painel sem senha so pode escutar em localhost (127.0.0.1 ou ::1).",
            file=sys.stderr,
        )
        return 2
    try:
        from .web import create_app
    except ImportError:
        print(
            'Flask nao esta instalado. Instale com: pip install -e ".[dashboard]"',
            file=sys.stderr,
        )
        return 1
    app = create_app()
    print(f"Dashboard em http://{args.host}:{args.port}  (Ctrl+C para encerrar)")
    app.run(host=args.host, port=args.port, debug=args.debug)
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

    sub.add_parser("list-printers", help="Lista impressoras.").set_defaults(func=cmd_list_printers)

    p_col = sub.add_parser("collect", help="Coleta leituras (backend mock ou snmp).")
    p_col.add_argument("--printer-id", type=int, help="Id da impressora.")
    p_col.add_argument("--all", action="store_true", help="Coleta todas as ativas.")
    p_col.add_argument(
        "--backend",
        choices=["mock", "snmp"],
        help="Sobrescreve o backend de coleta (padrao: do ambiente).",
    )
    p_col.add_argument(
        "--workers",
        type=int,
        choices=range(1, 129),
        metavar="1-128",
        help="Consultas simultaneas (padrao: PRINT_MONITOR_WORKERS ou 8).",
    )
    p_col.set_defaults(func=cmd_collect)

    p_rep = sub.add_parser("report", help="Relatorio mensal de volume.")
    p_rep.add_argument("--year", type=int, required=True, help="Ano (ex.: 2026).")
    p_rep.add_argument("--month", type=int, required=True, help="Mes (1-12).")
    p_rep.add_argument("--printer-id", type=int, help="Filtra por impressora.")
    p_rep.set_defaults(func=cmd_report)

    p_exp = sub.add_parser("export", help="Exporta o relatorio mensal em CSV.")
    p_exp.add_argument("--year", type=int, required=True, help="Ano (ex.: 2026).")
    p_exp.add_argument("--month", type=int, required=True, help="Mes (1-12).")
    p_exp.add_argument("--printer-id", type=int, help="Filtra por impressora.")
    p_exp.add_argument("--ip", help="Filtra por IP (parcial).")
    p_exp.add_argument("--location", help="Filtra por local (parcial).")
    p_exp.add_argument("--output", help="Arquivo de saida (padrao: stdout).")
    p_exp.set_defaults(func=cmd_export)

    p_imp = sub.add_parser("import-printers", help="Importa impressoras de um arquivo CSV.")
    p_imp.add_argument("--file", required=True, help="Caminho do CSV.")
    p_imp.set_defaults(func=cmd_import_printers)

    p_test = sub.add_parser("test", help="Testa um IP e mostra o que ele responde.")
    p_test.add_argument("ip", help="Endereco IP a testar.")
    p_test.set_defaults(func=cmd_test)

    p_disc = sub.add_parser("discover", help="Descobre impressoras na rede (abordagem segura).")
    p_disc.add_argument(
        "--network",
        required=True,
        help="Faixa (ex.: 192.168.0.0/24, 192.168.0 ou 192.168.0.1-254).",
    )
    p_disc.add_argument("--ports", default="9100,631,515", help="Portas TCP a verificar (CSV).")
    p_disc.add_argument("--timeout", type=float, default=0.3, help="Timeout por porta (s).")
    p_disc.add_argument("--workers", type=int, default=32, help="Conexoes simultaneas.")
    p_disc.add_argument("--max-hosts", type=int, default=1024, help="Limite de hosts (seguranca).")
    p_disc.add_argument("--snmp", action="store_true", help="Confirma via SNMP e le o contador.")
    p_disc.add_argument("--register", action="store_true", help="Cadastra os hosts encontrados.")
    p_disc.set_defaults(func=cmd_discover)

    p_srv = sub.add_parser("serve", help="Inicia o dashboard local (Flask).")
    p_srv.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host local (127.0.0.1, localhost ou ::1).",
    )
    p_srv.add_argument("--port", type=int, default=5000, help="Porta (padrao 5000).")
    p_srv.add_argument("--debug", action="store_true", help="Modo debug do Flask.")
    p_srv.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(f"Erro de configuracao: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
