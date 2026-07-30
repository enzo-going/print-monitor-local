"""Testes do dashboard (Flask)."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from print_monitor.db import Database
from print_monitor.models import MAX_COUNTER

pytest.importorskip("flask")

from print_monitor.web import create_app


@pytest.fixture()
def app_client(tmp_path):
    db_path = tmp_path / "web.db"
    db = Database(db_path)
    db.initialize()
    pid = db.add_printer(name="Alfa", ip="192.168.10.21", location="Financeiro")
    db.add_reading(pid, 100_000, collected_at=datetime(2026, 6, 1, tzinfo=UTC))
    db.add_reading(pid, 104_500, collected_at=datetime(2026, 6, 30, tzinfo=UTC))
    db.close()

    app = create_app(db_path=db_path, local_timezone=UTC)
    app.config.update(TESTING=True, CSRF_ENABLED=False)
    return app.test_client()


def test_index_ok(app_client):
    resp = app_client.get("/?year=2026&month=6")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Alfa" in body
    assert "Visão mensal" in body
    assert "104.500" in body
    assert "30/06/2026 às 00:00" in body
    assert "4.500" in body
    assert "acumulado da vida útil" in body


def test_index_default_loads(app_client):
    # Sem parametros: usa mes/ano atuais, deve responder 200.
    assert app_client.get("/").status_code == 200


def test_index_out_of_range_params_do_not_500(app_client):
    # Ano/mes fora do intervalo (URL montada a mao) sao saneados, sem erro 500.
    assert app_client.get("/?year=0&month=99").status_code == 200
    assert app_client.get("/?year=99999&month=6").status_code == 200


def test_index_supports_december_of_year_9999(app_client):
    response = app_client.get("/?year=9999&month=12")

    assert response.status_code == 200
    assert "Dezembro de 9999" in response.get_data(as_text=True)


def test_printers_view(app_client):
    resp = app_client.get("/printers")
    assert resp.status_code == 200
    assert "Alfa" in resp.get_data(as_text=True)


def test_static_assets_are_served(app_client):
    css = app_client.get("/static/app.css")
    javascript = app_client.get("/static/app.js")
    assert css.status_code == 200
    assert css.mimetype == "text/css"
    assert javascript.status_code == 200


def test_export_csv(app_client):
    resp = app_client.get("/export.csv?year=2026&month=6")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert resp.data.startswith(b"\xef\xbb\xbf")
    body = resp.data.decode("utf-8-sig")
    assert "printer_id;name;ip" in body
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
    app = create_app(db_path=db_path, local_timezone=UTC)
    app.config.update(TESTING=True, CSRF_ENABLED=False)
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


def test_edit_printer_preserves_history_and_collection_state(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="Antiga", ip="192.168.5.5", location="TI")
    reading_id = db.add_reading(pid, 123_456)
    db.set_printer_active(pid, False)
    db.close()

    response = client.post(
        f"/printers/{pid}/edit",
        data={
            "name": " Nova ",
            "ip": " 2001:0db8::5 ",
            "location": " Financeiro ",
            "model": " Modelo X ",
            "serial": " SERIE-01 ",
        },
        follow_redirects=True,
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Cadastro atualizado" in body
    assert "histórico e o estado de coleta foram preservados" in body
    assert "SERIE-01" in body
    assert "Editar cadastro de Nova" in body

    db = Database(db_path)
    updated = db.get_printer(pid)
    assert updated is not None
    assert updated.name == "Nova"
    assert updated.ip == "2001:db8::5"
    assert updated.location == "Financeiro"
    assert updated.model == "Modelo X"
    assert updated.serial == "SERIE-01"
    assert updated.active is False
    assert db.get_reading(reading_id) is not None
    db.close()


def test_edit_printer_rejects_duplicate_ip(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    first_id = db.add_printer(name="Primeira", ip="192.168.5.5")
    db.add_printer(name="Segunda", ip="192.168.5.6")
    db.close()

    response = client.post(
        f"/printers/{first_id}/edit",
        data={"name": "Primeira", "ip": "192.168.5.6"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Ja existe uma impressora cadastrada" in response.get_data(as_text=True)
    db = Database(db_path)
    unchanged = db.get_printer(first_id)
    assert unchanged is not None
    assert unchanged.ip == "192.168.5.5"
    db.close()


def test_delete_printer_requires_explicit_confirmation(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="ApagarMe", ip="192.168.5.9")
    reading_id = db.add_reading(pid, 100)
    db.close()
    resp = client.post(f"/printers/{pid}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert "Confirme que todo o histórico será apagado" in resp.get_data(as_text=True)
    db = Database(db_path)
    assert db.get_printer(pid) is not None
    assert db.get_reading(reading_id) is not None
    db.close()


def test_delete_printer_with_valid_confirmation_removes_history(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="ApagarMe", ip="192.168.5.9")
    reading_id = db.add_reading(pid, 100)
    db.close()

    resp = client.post(
        f"/printers/{pid}/delete",
        data={"delete_confirmation": str(pid)},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    db = Database(db_path)
    assert db.get_printer(pid) is None
    assert db.get_reading(reading_id) is None
    db.close()


def test_delete_printer_rejects_confirmation_for_another_id(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="Preservar", ip="192.168.5.9")
    other_id = db.add_printer(name="Outra", ip="192.168.5.10")
    reading_id = db.add_reading(pid, 100)
    db.close()

    resp = client.post(
        f"/printers/{pid}/delete",
        data={"delete_confirmation": str(other_id)},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert "Confirme que todo o histórico será apagado" in resp.get_data(as_text=True)
    db = Database(db_path)
    assert db.get_printer(pid) is not None
    assert db.get_reading(reading_id) is not None
    db.close()


def test_pause_printer_preserves_history(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="Pausar", ip="192.0.2.33")
    db.add_reading(pid, 100, collected_at=datetime(2026, 7, 1, tzinfo=UTC))
    db.close()

    response = client.post(
        f"/printers/{pid}/toggle",
        data={"active": "0"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    db = Database(db_path)
    printer = db.get_printer(pid)
    assert printer is not None and printer.active is False
    assert len(db.list_readings(pid)) == 1
    db.close()


def test_collect_mock_via_post(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    db.add_printer(name="Coletar", ip="192.168.5.10")
    db.close()
    resp = client.post("/collect", data={"backend": "mock"}, follow_redirects=True)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Coleta concluída em Coletar" in body
    assert "Linha de base criada" in body
    db = Database(db_path)
    assert len(db.list_readings()) == 1
    counter = db.list_readings()[0].total_counter
    db.close()
    assert f"{counter:,}".replace(",", ".") in body


def test_empty_dashboard_guides_registration(client_and_db):
    client, _ = client_and_db
    body = client.get("/").get_data(as_text=True)
    assert "Nenhuma impressora ativa" in body
    assert "Cadastrar impressora" in body
    assert "Descobrir na rede" in body
    assert "Atualizar contadores" not in body


def test_single_reading_is_shown_as_waiting_not_monthly_zero(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="Alfa", ip="192.0.2.31")
    db.add_reading(pid, 129_999, collected_at=datetime(2026, 7, 15, tzinfo=UTC))
    db.close()

    body = client.get("/?year=2026&month=7").get_data(as_text=True)

    assert "129.999" in body
    assert "Aguardando comparação" in body
    assert "O contador acumulado não é o total do mês" in body


def test_reset_is_shown_as_review_instead_of_missing_baseline(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="Reset", ip="192.0.2.34")
    db.add_reading(pid, 10_000, collected_at=datetime(2026, 7, 1, tzinfo=UTC))
    db.add_reading(pid, 100, collected_at=datetime(2026, 7, 2, tzinfo=UTC))
    db.close()

    body = client.get("/?year=2026&month=7").get_data(as_text=True)

    assert "Revisão necessária" in body
    assert "pode indicar reset, troca ou leitura incorreta" in body
    assert "Esses resultados não entram no total consolidado" in body
    assert "É preciso ter ao menos dois contadores" not in body


def test_conflicting_readings_are_excluded_and_explained(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="Conflito", ip="192.0.2.35")
    same_moment = datetime(2026, 7, 15, 9, 30, tzinfo=UTC)
    db.add_reading(pid, 10_000, collected_at=same_moment)
    db.add_reading(pid, 10_500, collected_at=same_moment)
    db.close()

    body = client.get("/?year=2026&month=7").get_data(as_text=True)

    assert "Revisão necessária" in body
    assert "contadores diferentes registrados" in body
    assert "Leituras conflitantes" in body
    assert "Esses resultados não entram no total consolidado" in body


def test_manual_reading_and_ignore_restore_flow(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="Alfa", ip="192.0.2.32")
    db.close()

    response = client.post(
        "/readings/add",
        data={
            "printer_id": str(pid),
            "total_counter": "740000",
            "collected_at": "2026-07-01T00:00",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Leitura histórica salva" in response.get_data(as_text=True)

    db = Database(db_path)
    reading = db.list_readings(pid)[0]
    db.close()

    response = client.post(
        f"/readings/{reading.id}/ignore",
        data={"reason": "correcao"},
        follow_redirects=True,
    )
    assert "Leitura retirada dos cálculos" in response.get_data(as_text=True)

    response = client.post(
        f"/readings/{reading.id}/restore",
        follow_redirects=True,
    )
    assert "Leitura restaurada" in response.get_data(as_text=True)


def test_manual_reading_rejects_counter_larger_than_sqlite_limit(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="Limite", ip="192.0.2.37")
    db.close()

    response = client.post(
        "/readings/add",
        data={
            "printer_id": str(pid),
            "total_counter": str(MAX_COUNTER + 1),
            "collected_at": "2026-07-01T00:00",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Contador invalido" in response.get_data(as_text=True)
    db = Database(db_path)
    assert db.list_readings(pid) == []
    db.close()


def test_month_navigation_preserves_active_filters(app_client):
    body = app_client.get("/?year=2026&month=6&printer_id=1&location=Financeiro").get_data(
        as_text=True
    )
    assert "/?year=2026&amp;month=5&amp;printer_id=1&amp;location=Financeiro" in body


def test_dashboard_uses_configured_backend(app_client):
    app_client.application.config["DEFAULT_BACKEND"] = "mock"
    body = app_client.get("/?year=2026&month=6").get_data(as_text=True)
    assert 'name="backend" value="mock"' in body


def test_collect_redirect_preserves_all_dashboard_filters(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    pid = db.add_printer(name="Contexto", ip="192.0.2.36", location="Arquivo")
    db.close()

    response = client.post(
        "/collect",
        data={
            "backend": "mock",
            "year": "2026",
            "month": "7",
            "printer_id": str(pid),
            "ip": "192.0.2",
            "location": "Arquivo",
        },
    )

    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["Location"]).query)
    assert query == {
        "year": ["2026"],
        "month": ["7"],
        "printer_id": [str(pid)],
        "ip": ["192.0.2"],
        "location": ["Arquivo"],
    }


def test_ignore_redirect_preserves_dashboard_context(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    db.initialize()
    pid = db.add_printer(name="Contexto", ip="192.0.2.40", location="Arquivo")
    reading_id = db.add_reading(
        pid,
        123_000,
        collected_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    db.close()

    response = client.post(
        f"/readings/{reading_id}/ignore",
        data={
            "return_to": "dashboard",
            "year": "2026",
            "month": "7",
            "printer_id": str(pid),
            "location": "Arquivo",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/?year=2026&month=7&printer_id={pid}&location=Arquivo"
    )


def test_restore_redirect_preserves_history_filter(client_and_db):
    client, db_path = client_and_db
    db = Database(db_path)
    db.initialize()
    pid = db.add_printer(name="Contexto", ip="192.0.2.41")
    reading_id = db.add_reading(
        pid,
        123_000,
        collected_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    db.ignore_reading(reading_id, "teste")
    db.close()

    response = client.post(
        f"/readings/{reading_id}/restore",
        data={"history_printer_id": str(pid)},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/readings?printer_id={pid}")


def test_collect_without_printers_redirects_to_registration(client_and_db):
    client, _ = client_and_db
    resp = client.post("/collect", data={"backend": "snmp"}, follow_redirects=True)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Cadastre ou descubra ao menos uma impressora ativa" in body
    assert "Cadastrar impressora" in body


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
        "SETOR;MARCA;MODELO;IP;N° SÉRIE\nFINANCEIRO;EXEMPLO;MODELO-X;192.0.2.80;TEST-SERIAL-001\n"
    ).encode()
    resp = client.post(
        "/printers/import",
        data={"file": (io.BytesIO(csv_bytes), "impressoras.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Importadas: 1" in resp.get_data(as_text=True)
    db = Database(db_path)
    assert db.get_printer_by_ip("192.0.2.80") is not None
    db.close()


def test_import_upload_shows_line_details_for_missing_ip(client_and_db):
    import io

    client, db_path = client_and_db
    csv_bytes = b"SETOR;MODELO;IP\nFinanceiro;Modelo X;\n"

    response = client.post(
        "/printers/import",
        data={"file": (io.BytesIO(csv_bytes), "impressoras.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "com erro: 1" in body
    assert "Linha 2: IP não informado" in body
    db = Database(db_path)
    assert db.list_printers() == []
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


def test_post_requires_valid_csrf_token(tmp_path):
    app = create_app(db_path=tmp_path / "csrf.db")
    app.config.update(TESTING=True)
    client = app.test_client()

    assert client.post("/collect", data={"backend": "mock"}).status_code == 400

    client.get("/printers")
    with client.session_transaction() as sess:
        token = sess["_csrf_token"]
    response = client.post(
        "/collect",
        data={"backend": "mock", "_csrf_token": token},
    )
    assert response.status_code == 302


def test_security_headers_are_present(app_client):
    response = app_client.get("/")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_non_local_host_header_is_rejected_without_session(app_client):
    response = app_client.get("/printers", headers={"Host": "attacker.example:5000"})

    assert response.status_code == 400
    assert "_csrf_token" not in response.get_data(as_text=True)
    assert "Set-Cookie" not in response.headers
