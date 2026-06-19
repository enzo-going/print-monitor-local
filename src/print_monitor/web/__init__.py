"""Dashboard local (Flask) — interface completa do mini app.

Alem da visualizacao do volume mensal (filtros, ranking, exportacao CSV), a
interface permite gerir a ferramenta sem usar a linha de comando: cadastrar e
remover impressoras, coletar leituras (mock ou SNMP) e descobrir impressoras na
rede.

A aplicacao e criada por um *factory* (``create_app``), o que facilita os testes
com ``app.test_client()``. Cada requisicao abre e fecha sua propria conexao
SQLite (o servidor e multithread e conexoes nao podem ser compartilhadas entre
threads).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..collector import Collector, make_backend
from ..config import load_config
from ..db import Database
from ..discovery import DEFAULT_PRINTER_PORTS, discover
from ..exports import report_to_csv
from ..printers import register_printer
from ..reports import monthly_report


def _parse_int(value: str | None, default: int | None = None) -> int | None:
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def create_app(db_path: str | Path | None = None) -> Flask:
    # template_folder explicito: resolve corretamente tanto em execucao normal
    # quanto empacotado com PyInstaller (templates incluidos via --add-data).
    template_folder = str(Path(__file__).resolve().parent / "templates")
    app = Flask(__name__, template_folder=template_folder)
    # Chave de sessao por processo (apenas para mensagens flash; app local).
    app.secret_key = secrets.token_hex(16)
    config = load_config()
    app.config["DB_PATH"] = str(db_path or config.db_path)
    app.config["DEFAULT_BACKEND"] = config.backend

    def open_db() -> Database:
        db = Database(app.config["DB_PATH"])
        db.initialize()
        return db

    def read_filters() -> dict:
        now = datetime.now(timezone.utc)
        year = _parse_int(request.args.get("year"), now.year)
        month = _parse_int(request.args.get("month"), now.month)
        if not (year and 1 <= year <= 9999):
            year = now.year
        if not (month and 1 <= month <= 12):
            month = now.month
        return {
            "year": year,
            "month": month,
            "printer_id": _parse_int(request.args.get("printer_id")),
            "ip": (request.args.get("ip") or "").strip(),
            "location": (request.args.get("location") or "").strip(),
        }

    # -- visualizacao ------------------------------------------------------

    @app.route("/")
    def index() -> str:
        f = read_filters()
        db = open_db()
        try:
            printers = db.list_printers()
            report = monthly_report(
                db,
                f["year"],
                f["month"],
                printer_id=f["printer_id"],
                ip=f["ip"] or None,
                location=f["location"] or None,
            )
        finally:
            db.close()
        total = sum(pv.volume for pv in report)
        top = [pv for pv in report if pv.volume > 0]
        return render_template(
            "index.html",
            report=report,
            ranking=top,
            total=total,
            printers=printers,
            filters=f,
            months=range(1, 13),
            query=request.query_string.decode(),
            default_backend=app.config["DEFAULT_BACKEND"],
        )

    @app.route("/printers")
    def printers_view() -> str:
        db = open_db()
        try:
            printers = db.list_printers()
        finally:
            db.close()
        return render_template("printers.html", printers=printers)

    @app.route("/export.csv")
    def export_csv() -> Response:
        f = read_filters()
        db = open_db()
        try:
            report = monthly_report(
                db,
                f["year"],
                f["month"],
                printer_id=f["printer_id"],
                ip=f["ip"] or None,
                location=f["location"] or None,
            )
        finally:
            db.close()
        csv_text = report_to_csv(report, f["year"], f["month"])
        filename = f"relatorio-{f['year']}-{f['month']:02d}.csv"
        return Response(
            csv_text,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # -- gestao (acoes) ----------------------------------------------------

    @app.route("/printers/add", methods=["POST"])
    def printers_add() -> Response:
        db = open_db()
        try:
            register_printer(
                db,
                name=request.form.get("name", ""),
                ip=request.form.get("ip", ""),
                location=request.form.get("location") or None,
                model=request.form.get("model") or None,
                serial=request.form.get("serial") or None,
            )
            flash("Impressora cadastrada com sucesso.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        finally:
            db.close()
        return redirect(url_for("printers_view"))

    @app.route("/printers/<int:printer_id>/delete", methods=["POST"])
    def printers_delete(printer_id: int) -> Response:
        db = open_db()
        try:
            removed = db.delete_printer(printer_id)
            flash(
                "Impressora removida." if removed else "Impressora nao encontrada.",
                "ok" if removed else "erro",
            )
        finally:
            db.close()
        return redirect(url_for("printers_view"))

    @app.route("/collect", methods=["POST"])
    def collect() -> Response:
        backend_name = request.form.get("backend") or app.config["DEFAULT_BACKEND"]
        db = open_db()
        try:
            backend, source = make_backend(config, override=backend_name)
            outcome = Collector(db, backend, source=source).collect_all()
        finally:
            db.close()
        if outcome.readings:
            flash(
                f"{len(outcome.readings)} leitura(s) coletada(s) via {source}.", "ok"
            )
        if outcome.failures:
            detalhes = "; ".join(f"{p.ip}: {err}" for p, err in outcome.failures[:5])
            flash(f"{len(outcome.failures)} falha(s). {detalhes}", "erro")
        if not outcome.readings and not outcome.failures:
            flash("Nenhuma impressora ativa para coletar.", "erro")
        return redirect(request.referrer or url_for("index"))

    @app.route("/discover", methods=["GET", "POST"])
    def discover_view() -> str:
        results = None
        params = {
            "network": "",
            "ports": "9100,631,515",
            "snmp": False,
            "register": False,
            "max_hosts": 1024,
        }
        if request.method == "POST":
            params["network"] = (request.form.get("network") or "").strip()
            params["ports"] = (request.form.get("ports") or "9100,631,515").strip()
            params["snmp"] = bool(request.form.get("snmp"))
            params["register"] = bool(request.form.get("register"))
            params["max_hosts"] = _parse_int(request.form.get("max_hosts"), 1024)
            try:
                ports = tuple(
                    int(p) for p in params["ports"].split(",") if p.strip()
                ) or DEFAULT_PRINTER_PORTS
                results = discover(
                    params["network"],
                    ports=ports,
                    max_hosts=params["max_hosts"],
                    snmp_confirm=params["snmp"],
                    config=config,
                )
            except ValueError as exc:
                flash(str(exc), "erro")
                results = None
            else:
                if params["register"] and results:
                    db = open_db()
                    added = 0
                    try:
                        for d in results:
                            if db.get_printer_by_ip(d.ip) is None:
                                register_printer(
                                    db, name=f"Impressora {d.ip}", ip=d.ip
                                )
                                added += 1
                    finally:
                        db.close()
                    flash(f"{added} impressora(s) cadastrada(s).", "ok")
                elif not results:
                    flash("Nenhum host com portas de impressao encontrado.", "ok")
        return render_template("discover.html", results=results, params=params)

    return app
