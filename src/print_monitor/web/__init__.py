"""Dashboard local (Flask).

Painel simples para visualizar o volume mensal de impressao, com filtros por
mes, impressora, IP e local, ranking das mais usadas e exportacao CSV.

A aplicacao e criada por um *factory* (``create_app``), o que facilita os testes
com ``app.test_client()``. Cada requisicao abre e fecha sua propria conexao
SQLite (o servidor de desenvolvimento e multithread e conexoes nao podem ser
compartilhadas entre threads).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, render_template, request

from ..config import load_config
from ..db import Database
from ..exports import report_to_csv
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
    config = load_config()
    app.config["DB_PATH"] = str(db_path or config.db_path)

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

    return app
