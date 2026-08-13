"""Dashboard local para coleta, relatorios e correcao de leituras."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta, tzinfo
from hmac import compare_digest
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..collector import Collector, make_backend
from ..config import load_config
from ..db import Database
from ..discovery import DEFAULT_PRINTER_PORTS, discover, suggested_networks
from ..exports import report_to_csv
from ..imports import decode_bytes, import_printers_from_csv
from ..netaddr import IPError, normalize_ip
from ..printers import register_printer, update_printer
from ..reports import monthly_report, system_timezone

MONTH_NAMES = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)

SOURCE_LABELS = {
    "snmp": "Coleta automática",
    "manual": "Informada manualmente",
    "mock": "Simulação",
    "seed": "Demonstração",
}


def _parse_int(value: str | None, default: int | None = None) -> int | None:
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + month - 1 + offset
    shifted_year, zero_based_month = divmod(absolute, 12)
    return shifted_year, zero_based_month + 1


def _number_pt(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", ".")


def _is_local_request_host(host_header: str) -> bool:
    """Aceita somente localhost ou IPs de loopback no cabecalho Host."""
    try:
        hostname = urlsplit(f"//{host_header}").hostname
    except ValueError:
        return False
    if hostname is None:
        return False
    normalized = hostname.lower().rstrip(".")
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def create_app(
    db_path: str | Path | None = None,
    *,
    local_timezone: tzinfo | None = None,
) -> Flask:
    """Cria o app Flask.

    ``local_timezone`` e injetavel para testes. Na instalacao, o fuso configurado
    no Windows e usado para definir o mes e exibir horarios locais.
    """
    web_dir = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(web_dir / "templates"),
        static_folder=str(web_dir / "static"),
        static_url_path="/static",
    )
    app.secret_key = secrets.token_hex(16)
    app.config.update(
        CSRF_ENABLED=True,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
    )
    config = load_config()
    app.config["DB_PATH"] = str(db_path or config.db_path)
    app.config["DEFAULT_BACKEND"] = config.backend
    display_timezone = local_timezone or system_timezone()

    def csrf_token() -> str:
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    def local_datetime(value: datetime | None) -> str:
        if value is None:
            return "—"
        return value.astimezone(display_timezone).strftime("%d/%m/%Y às %H:%M")

    app.jinja_env.globals.update(
        csrf_token=csrf_token,
        month_names=MONTH_NAMES,
        source_labels=SOURCE_LABELS,
    )
    app.jinja_env.filters["number_pt"] = _number_pt
    app.jinja_env.filters["local_datetime"] = local_datetime

    @app.before_request
    def protect_local_requests() -> None:
        if not _is_local_request_host(request.host):
            abort(400, description="Host local invalido.")
        if request.method != "POST" or not app.config["CSRF_ENABLED"]:
            return
        expected = session.get("_csrf_token", "")
        supplied = request.form.get("_csrf_token", "")
        if not expected or not supplied or not compare_digest(expected, supplied):
            abort(400, description="Token CSRF ausente ou inválido.")

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; "
            "base-uri 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    def open_db() -> Database:
        db = Database(app.config["DB_PATH"])
        db.initialize()
        return db

    def read_filters() -> dict:
        now = datetime.now(display_timezone)
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

    # -- visao mensal ----------------------------------------------------

    @app.route("/")
    def index() -> str:
        filters = read_filters()
        db = open_db()
        try:
            printers = db.list_printers()
            active_printer_count = sum(printer.active for printer in printers)
            reading_summary = db.reading_summary()
            latest_by_printer = {reading.printer_id: reading for reading in db.latest_readings()}
            recent_readings = db.list_recent_readings(limit=5)
            report = monthly_report(
                db,
                filters["year"],
                filters["month"],
                printer_id=filters["printer_id"],
                ip=filters["ip"] or None,
                location=filters["location"] or None,
                timezone=display_timezone,
            )
        finally:
            db.close()

        measured = [item for item in report if item.measurable]
        ranking = [item for item in measured if item.volume > 0]
        total = sum(item.volume for item in measured)
        partial_count = sum(item.state == "partial" for item in measured)
        reset_count = sum(item.state == "counter_reset" for item in report)
        conflict_count = sum(item.state == "conflicting_readings" for item in report)
        review_count = reset_count + conflict_count
        waiting_baseline_count = sum(item.state == "waiting_baseline" for item in report)
        previous_year, previous_month = _shift_month(filters["year"], filters["month"], -1)
        next_year, next_month = _shift_month(filters["year"], filters["month"], 1)
        now_local = datetime.now(display_timezone)

        export_params: dict[str, object] = {
            "year": filters["year"],
            "month": filters["month"],
        }
        for key in ("printer_id", "ip", "location"):
            if filters[key] not in (None, ""):
                export_params[key] = filters[key]

        def period_url(year: int, month: int) -> str:
            return url_for(
                "index",
                **{**export_params, "year": year, "month": month},
            )

        return render_template(
            "index.html",
            report=report,
            ranking=ranking,
            total=total,
            has_measured_data=bool(measured),
            measurable_count=len(measured),
            partial_count=partial_count,
            reset_count=reset_count,
            conflict_count=conflict_count,
            review_count=review_count,
            waiting_baseline_count=waiting_baseline_count,
            printers=printers,
            printer_by_id={printer.id: printer for printer in printers},
            filters=filters,
            months=enumerate(MONTH_NAMES, start=1),
            period_label=f"{MONTH_NAMES[filters['month'] - 1]} de {filters['year']}",
            previous_period_url=period_url(previous_year, previous_month),
            next_period_url=period_url(next_year, next_month),
            current_period_url=period_url(now_local.year, now_local.month),
            export_url=url_for("export_csv", **export_params),
            default_backend=app.config["DEFAULT_BACKEND"],
            active_printer_count=active_printer_count,
            reading_summary=reading_summary,
            latest_by_printer=latest_by_printer,
            recent_readings=recent_readings,
        )

    @app.route("/export.csv")
    def export_csv() -> Response:
        filters = read_filters()
        db = open_db()
        try:
            report = monthly_report(
                db,
                filters["year"],
                filters["month"],
                printer_id=filters["printer_id"],
                ip=filters["ip"] or None,
                location=filters["location"] or None,
                timezone=display_timezone,
            )
        finally:
            db.close()
        csv_text = report_to_csv(
            report,
            filters["year"],
            filters["month"],
            delimiter=";",
            include_bom=True,
        )
        filename = f"relatorio-{filters['year']}-{filters['month']:02d}.csv"
        return Response(
            csv_text,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # -- historico e correcoes ------------------------------------------

    @app.route("/readings")
    def readings_view() -> str:
        selected_printer_id = _parse_int(request.args.get("printer_id"))
        db = open_db()
        try:
            printers = db.list_printers()
            history = db.list_recent_readings(
                limit=100,
                printer_id=selected_printer_id,
            )
            delta_by_id = db.reading_deltas(
                {
                    reading.id
                    for reading in history
                    if reading.id is not None and not reading.ignored
                }
            )
        finally:
            db.close()

        return render_template(
            "readings.html",
            printers=printers,
            printer_by_id={printer.id: printer for printer in printers},
            readings=history,
            delta_by_id=delta_by_id,
            selected_printer_id=selected_printer_id,
            default_datetime=datetime.now(display_timezone).strftime("%Y-%m-%dT%H:%M"),
        )

    @app.route("/readings/add", methods=["POST"])
    def readings_add() -> Response:
        printer_id = _parse_int(request.form.get("printer_id"))
        total_counter = _parse_int(request.form.get("total_counter"))
        collected_at_raw = (request.form.get("collected_at") or "").strip()
        db = open_db()
        try:
            printer = db.get_printer(printer_id) if printer_id is not None else None
            if printer is None:
                raise ValueError("Selecione uma impressora cadastrada.")
            if total_counter is None or total_counter < 0:
                raise ValueError("Informe um contador inteiro igual ou maior que zero.")
            try:
                local_moment = datetime.fromisoformat(collected_at_raw)
            except ValueError as exc:
                raise ValueError("Informe uma data e hora validas.") from exc
            if local_moment.tzinfo is None:
                local_moment = local_moment.replace(tzinfo=display_timezone)
            collected_at = local_moment.astimezone(UTC)
            if collected_at > datetime.now(UTC) + timedelta(minutes=5):
                raise ValueError("A leitura não pode estar no futuro.")
            db.add_reading(
                printer.id,
                total_counter,
                collected_at=collected_at,
                source="manual",
            )
        except ValueError as exc:
            flash(str(exc), "erro")
        else:
            flash(
                "Leitura histórica salva. O relatório mensal foi recalculado.",
                "ok",
            )
        finally:
            db.close()
        return redirect(url_for("readings_view"))

    @app.route("/readings/<int:reading_id>/ignore", methods=["POST"])
    def readings_ignore(reading_id: int) -> Response:
        reason = request.form.get("reason")
        db = open_db()
        try:
            changed = db.ignore_reading(reading_id, reason)
        finally:
            db.close()
        flash(
            "Leitura retirada dos cálculos. Você pode restaurá-la no histórico."
            if changed
            else "Leitura não encontrada ou já estava ignorada.",
            "ok" if changed else "erro",
        )
        if request.form.get("return_to") == "dashboard":
            params: dict[str, object] = {}
            year = _parse_int(request.form.get("year"))
            month = _parse_int(request.form.get("month"))
            printer_id = _parse_int(request.form.get("printer_id"))
            if year and 1 <= year <= 9999:
                params["year"] = year
            if month and 1 <= month <= 12:
                params["month"] = month
            if printer_id is not None:
                params["printer_id"] = printer_id
            for key in ("ip", "location"):
                value = (request.form.get(key) or "").strip()
                if value:
                    params[key] = value
            return redirect(url_for("index", **params))
        history_printer_id = _parse_int(request.form.get("history_printer_id"))
        return redirect(
            url_for(
                "readings_view",
                **({"printer_id": history_printer_id} if history_printer_id is not None else {}),
            )
        )

    @app.route("/readings/<int:reading_id>/restore", methods=["POST"])
    def readings_restore(reading_id: int) -> Response:
        db = open_db()
        try:
            changed = db.restore_reading(reading_id)
        finally:
            db.close()
        flash(
            "Leitura restaurada e incluída novamente nos cálculos."
            if changed
            else "A leitura não estava ignorada.",
            "ok" if changed else "erro",
        )
        history_printer_id = _parse_int(request.form.get("history_printer_id"))
        return redirect(
            url_for(
                "readings_view",
                **({"printer_id": history_printer_id} if history_printer_id is not None else {}),
            )
        )

    # -- impressoras -----------------------------------------------------

    @app.route("/printers")
    def printers_view() -> str:
        db = open_db()
        try:
            printers = db.list_printers()
        finally:
            db.close()
        return render_template("printers.html", printers=printers)

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

    @app.route("/printers/<int:printer_id>/edit", methods=["POST"])
    def printers_edit(printer_id: int) -> Response:
        db = open_db()
        try:
            update_printer(
                db,
                printer_id,
                name=request.form.get("name", ""),
                ip=request.form.get("ip", ""),
                location=request.form.get("location") or None,
                model=request.form.get("model") or None,
                serial=request.form.get("serial") or None,
            )
            flash(
                "Cadastro atualizado. O histórico e o estado de coleta foram preservados.",
                "ok",
            )
        except ValueError as exc:
            flash(str(exc), "erro")
        finally:
            db.close()
        return redirect(url_for("printers_view"))

    @app.route("/printers/import", methods=["POST"])
    def printers_import() -> Response:
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Selecione um arquivo CSV.", "erro")
            return redirect(url_for("printers_view"))
        text = decode_bytes(file.read())
        db = open_db()
        try:
            result = import_printers_from_csv(db, text)
        finally:
            db.close()
        import_message = (
            f"Importadas: {result.added}; já cadastradas: {result.skipped}; "
            f"com erro: {len(result.errors)}."
        )
        if result.errors:
            details = " ".join(
                f"Linha {line_no}: {message}" for line_no, message in result.errors[:5]
            )
            import_message += f" {details}"
            if len(result.errors) > 5:
                import_message += f" Mais {len(result.errors) - 5} erro(s) não exibido(s)."
        flash(import_message, "ok" if not result.errors else "erro")
        return redirect(url_for("printers_view"))

    @app.route("/printers/<int:printer_id>/toggle", methods=["POST"])
    def printers_toggle(printer_id: int) -> Response:
        active = request.form.get("active") == "1"
        db = open_db()
        try:
            changed = db.set_printer_active(printer_id, active)
        finally:
            db.close()
        if changed:
            flash(
                "Coleta reativada." if active else "Coleta pausada; o histórico foi preservado.",
                "ok",
            )
        else:
            flash("Impressora não encontrada.", "erro")
        return redirect(url_for("printers_view"))

    @app.route("/printers/<int:printer_id>/delete", methods=["POST"])
    def printers_delete(printer_id: int) -> Response:
        if request.form.get("delete_confirmation") != str(printer_id):
            flash(
                "Confirme que todo o histórico será apagado antes de excluir.",
                "erro",
            )
            return redirect(url_for("printers_view"))
        db = open_db()
        try:
            removed = db.delete_printer(printer_id)
            flash(
                "Impressora e histórico removidos." if removed else "Impressora não encontrada.",
                "ok" if removed else "erro",
            )
        finally:
            db.close()
        return redirect(url_for("printers_view"))

    # -- coleta ----------------------------------------------------------

    @app.route("/collect", methods=["POST"])
    def collect() -> Response:
        backend_name = (
            "mock"
            if request.form.get("use_mock") == "1"
            else request.form.get("backend") or app.config["DEFAULT_BACKEND"]
        )
        try:
            backend, source = make_backend(config, override=backend_name)
        except ValueError as exc:
            flash(str(exc), "erro")
            return redirect(url_for("index"))

        db = open_db()
        try:
            active_printers = db.list_printers(only_active=True)
            if not active_printers:
                flash(
                    "Cadastre ou descubra ao menos uma impressora ativa antes de coletar.",
                    "erro",
                )
                return redirect(url_for("printers_view"))
            printer_by_id = {printer.id: printer for printer in active_printers}
            previous_by_printer = {reading.printer_id: reading for reading in db.latest_readings()}
            outcome = Collector(db, backend, source=source).collect_all(
                workers=config.collection_workers
            )
        finally:
            db.close()

        if outcome.readings:
            deltas: list[int] = []
            for reading in outcome.readings:
                previous = previous_by_printer.get(reading.printer_id)
                if previous is not None:
                    delta = reading.total_counter - previous.total_counter
                    if delta >= 0:
                        deltas.append(delta)
            if len(outcome.readings) == 1:
                reading = outcome.readings[0]
                printer = printer_by_id.get(reading.printer_id)
                previous = previous_by_printer.get(reading.printer_id)
                if previous is None:
                    detail = (
                        f"Linha de base criada: contador acumulado "
                        f"{_number_pt(reading.total_counter)}."
                    )
                else:
                    delta = reading.total_counter - previous.total_counter
                    if delta > 0:
                        page_word = "página" if delta == 1 else "páginas"
                        detail = (
                            f"Contador atual {_number_pt(reading.total_counter)}; "
                            f"{_number_pt(delta)} {page_word} desde a leitura anterior."
                        )
                    elif delta == 0:
                        detail = (
                            f"Contador {_number_pt(reading.total_counter)}, sem alteração "
                            "desde a leitura anterior."
                        )
                    else:
                        detail = (
                            f"Contador atual {_number_pt(reading.total_counter)}. "
                            "Ele diminuiu; verifique se houve reset ou troca do equipamento."
                        )
                flash(
                    f"Coleta concluída em {printer.name if printer else '1 impressora'}. {detail}",
                    "ok",
                )
            else:
                flash(
                    f"Coleta concluída: {len(outcome.readings)} leitura(s) salva(s). "
                    f"Variação positiva desde a coleta anterior: {_number_pt(sum(deltas))}.",
                    "ok",
                )
        if outcome.failures:
            details = "; ".join(f"{printer.ip}: {error}" for printer, error in outcome.failures[:5])
            flash(f"{len(outcome.failures)} falha(s). {details}", "erro")

        year = _parse_int(request.form.get("year"))
        month = _parse_int(request.form.get("month"))
        redirect_params = {}
        if year and 1 <= year <= 9999:
            redirect_params["year"] = year
        if month and 1 <= month <= 12:
            redirect_params["month"] = month
        printer_id = _parse_int(request.form.get("printer_id"))
        if printer_id is not None:
            redirect_params["printer_id"] = printer_id
        for key in ("ip", "location"):
            value = (request.form.get(key) or "").strip()
            if value:
                redirect_params[key] = value
        return redirect(url_for("index", **redirect_params))

    # -- descoberta ------------------------------------------------------

    # -- apoio ao preenchimento (consultado pela propria pagina) ----------

    @app.route("/api/normalizar-ip", methods=["POST"])
    def api_normalize_ip() -> Response:
        """Corrige o IP digitado, para o aviso ao vivo no formulario.

        A pagina consulta a mesma funcao usada no cadastro em vez de repetir a
        regra em JavaScript: assim o aviso nunca discorda do que sera salvo.
        """
        try:
            return jsonify({"ok": True, "ip": normalize_ip(request.form.get("ip", ""))})
        except IPError as exc:
            return jsonify({"ok": False, "erro": str(exc)})

    @app.route("/api/testar", methods=["POST"])
    def api_test() -> Response:
        """Consulta um IP na hora e devolve o que o equipamento respondeu.

        Descobrir na hora do cadastro que o IP esta errado evita um mes inteiro
        de coletas vazias percebido so no fechamento.
        """
        from ..snmp import SNMPError, diagnose_silence, identify

        try:
            ip = normalize_ip(request.form.get("ip", ""))
        except IPError as exc:
            return jsonify({"ok": False, "erro": str(exc)})

        try:
            ident = identify(
                ip,
                community=config.snmp_community,
                port=config.snmp_port,
                timeout=max(1.0, config.snmp_timeout),
                version=config.snmp_version,
            )
        except SNMPError as exc:
            return jsonify({"ok": False, "ip": ip, "erro": str(exc)})

        return jsonify(
            {
                "ok": ident.responded,
                "ip": ip,
                "nome": ident.suggested_name if ident.responded else None,
                "modelo": ident.model,
                "serie": ident.serial,
                "local": ident.location,
                "contador": ident.counter,
                "erro": None if ident.responded else diagnose_silence(ip),
            }
        )

    # -- descoberta ------------------------------------------------------

    @app.route("/discover", methods=["GET", "POST"])
    def discover_view() -> str:
        db = open_db()
        try:
            known_ips = {printer.ip for printer in db.list_printers()}
        finally:
            db.close()
        # A impressora quase sempre esta na mesma rede do computador; sugerir a
        # faixa poupa o usuario de precisar saber o que e um CIDR.
        suggestions = suggested_networks()
        results = None
        params = {
            "network": suggestions[0] if suggestions else "",
            "ports": "9100,631,515",
            "snmp": True,
            "max_hosts": 1024,
        }
        if request.method == "POST":
            params["network"] = (request.form.get("network") or "").strip()
            params["ports"] = (request.form.get("ports") or "9100,631,515").strip()
            params["snmp"] = bool(request.form.get("snmp"))
            params["max_hosts"] = _parse_int(request.form.get("max_hosts"), 1024)
            try:
                ports = (
                    tuple(int(port) for port in params["ports"].split(",") if port.strip())
                    or DEFAULT_PRINTER_PORTS
                )
                results = discover(
                    params["network"],
                    ports=ports,
                    max_hosts=params["max_hosts"],
                    snmp_confirm=params["snmp"],
                    config=config,
                    known_ips=known_ips,
                )
            except ValueError as exc:
                flash(str(exc), "erro")
                results = None
            else:
                novos = [item for item in results if not item.already_registered]
                if not results:
                    flash("Nenhum host com portas de impressão encontrado.", "ok")
                elif not novos:
                    flash(
                        f"{len(results)} equipamento(s) encontrado(s) — todos já "
                        "estão cadastrados.",
                        "ok",
                    )
                else:
                    flash(
                        f"{len(novos)} equipamento(s) novo(s). Marque os que quiser "
                        "cadastrar e confirme abaixo.",
                        "ok",
                    )
        return render_template(
            "discover.html", results=results, params=params, suggestions=suggestions
        )

    @app.route("/discover/register", methods=["POST"])
    def discover_register() -> Response:
        """Cadastra apenas os equipamentos marcados na lista de resultados.

        Cadastrar tudo em bloco enchia a lista de aparelhos que apenas abrem as
        mesmas portas — porteiros eletronicos, servidores de impressao antigos.
        """
        selecionados = request.form.getlist("selecionado")
        if not selecionados:
            flash("Marque ao menos um equipamento para cadastrar.", "erro")
            return redirect(url_for("discover_view"))

        db = open_db()
        adicionadas, erros = 0, []
        try:
            for ip in selecionados:
                try:
                    register_printer(
                        db,
                        name=(request.form.get(f"nome_{ip}") or "").strip(),
                        ip=ip,
                        location=(request.form.get(f"local_{ip}") or "").strip() or None,
                        model=(request.form.get(f"modelo_{ip}") or "").strip() or None,
                        serial=(request.form.get(f"serie_{ip}") or "").strip() or None,
                    )
                    adicionadas += 1
                except ValueError as exc:
                    erros.append(str(exc))
        finally:
            db.close()
        if adicionadas:
            flash(f"{adicionadas} impressora(s) cadastrada(s).", "ok")
        for erro in erros[:5]:
            flash(erro, "erro")
        return redirect(url_for("printers_view"))

    @app.route("/ajuda")
    def help_view() -> str:
        return render_template("help.html")

    return app
