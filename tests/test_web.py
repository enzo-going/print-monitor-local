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


# -- acoes de gestao na interface -----------------------------------------


@pytest.fixture()
def client_and_db(tmp_path):
    db_path = tmp_path / "web.db"
    db = Database(db_path)
    db.initialize()
    db.close()
    app = create_app(db_path=db_path)
    app.config.update(TESTING=True)
    return app.test_client(), db_path


def test_add_printer_via_post(client_and_db):
    client, db_path = client_and_db
    resp = client.post(
        "/printers/add",
        data={"name": "Nova", "ip": "192.168.5.5", "location": "TI"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Nova" in resp.get_data(as_text=True)
    db = Database(db_path)
    assert db.get_printer_by_ip("192.168.5.5") is not None
    db.close()


def test_add_printer_invalid_ip_flashes_error(client_and_db):
    client, db_path = client_and_db
    resp = client.post(
        "/printers/add",
        data={"name": "Ruim", "ip": "999.1.1.1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "IP invalido" in resp.get_data(as_text=True)
    db = Database(db_path)
    assert db.list_printers() == []
    db.close()


def test_delete_printer_via_post(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="ApagarMe", ip="192.168.5.9")
    db.close()
    resp = client.post(f"/printers/{pid}/delete", follow_redirects=True)
    assert resp.status_code == 200
    db = Database(db_path)
    assert db.get_printer(pid) is None
    db.close()


def test_collect_mock_via_post(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    db.add_printer(name="Coletar", ip="192.168.5.10")
    db.close()
    resp = client.post("/collect", data={"backend": "mock"}, follow_redirects=True)
    assert resp.status_code == 200
    db = Database(db_path)
    assert len(db.list_readings()) == 1
    db.close()


def test_discover_page_get(client_and_db):
    client, _ = client_and_db
    resp = client.get("/discover")
    assert resp.status_code == 200
    assert "Descobrir impressoras" in resp.get_data(as_text=True)


def test_discover_post_empty(client_and_db):
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    free_port = s.getsockname()[1]
    s.close()

    client, _ = client_and_db
    resp = client.post(
        "/discover",
        data={"network": "127.0.0.1/32", "ports": str(free_port)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Nenhum host" in resp.get_data(as_text=True)


def test_import_printers_via_upload(client_and_db):
    import io

    client, db_path = client_and_db
    csv_bytes = (
        "SETOR;MARCA;MODELO;IP;N° SÉRIE\n"
        "FINANCEIRO;SAMSUNG;M4080FX;192.168.60.80;088WB07JC10PBTV\n"
    ).encode("utf-8")
    resp = client.post(
        "/printers/import",
        data={"file": (io.BytesIO(csv_bytes), "impressoras.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Importadas: 1" in resp.get_data(as_text=True)
    db = Database(db_path)
    assert db.get_printer_by_ip("192.168.60.80") is not None
    db.close()


def test_discover_post_rejects_large_range(client_and_db):
    client, _ = client_and_db
    resp = client.post(
        "/discover",
        data={"network": "10.0.0.0/16", "max_hosts": "1024"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Faixa muito grande" in resp.get_data(as_text=True)
