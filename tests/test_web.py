"""Testes do dashboard (Flask)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from print_monitor.db import Database

pytest.importorskip("flask")

from print_monitor.web import create_app  # noqa: E402


@pytest.fixture()
def app_client(tmp_path):
    db_path = tmp_path / "web.db"
    db = Database(db_path)
    db.initialize()
    pid = db.add_printer(name="Alfa", ip="192.168.10.21", location="Financeiro")
    db.add_reading(pid, 100_000, collected_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    db.add_reading(pid, 104_500, collected_at=datetime(2026, 6, 30, tzinfo=timezone.utc))
    db.close()

    app = create_app(db_path=db_path)
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_ok(app_client):
    resp = app_client.get("/?year=2026&month=6")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Alfa" in body
    assert "Dashboard" in body


def test_index_default_loads(app_client):
    # Sem parametros: usa mes/ano atuais, deve responder 200.
    assert app_client.get("/").status_code == 200


def test_index_out_of_range_params_do_not_500(app_client):
    # Ano/mes fora do intervalo (URL montada a mao) sao saneados, sem erro 500.
    assert app_client.get("/?year=0&month=99").status_code == 200
    assert app_client.get("/?year=99999&month=6").status_code == 200


def test_printers_view(app_client):
    resp = app_client.get("/printers")
    assert resp.status_code == 200
    assert "Alfa" in resp.get_data(as_text=True)


def test_export_csv(app_client):
    resp = app_client.get("/export.csv?year=2026&month=6")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"]
    body = resp.get_data(as_text=True)
    assert "printer_id,name,ip" in body
    assert "Alfa" in body
    assert "4500" in body


def test_filter_excludes_non_matching(app_client):
    resp = app_client.get("/?year=2026&month=6&location=RH")
    body = resp.get_data(as_text=True)
    # Nenhuma impressora em "RH" -> Alfa nao aparece na tabela de detalhamento.
    assert "Nenhuma impressora atende" in body
