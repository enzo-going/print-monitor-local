"""Testes do backend SNMP (codificacao BER e cliente GET via loopback)."""

from __future__ import annotations

import socket
import threading

import pytest

from print_monitor.config import Config
from print_monitor.models import Printer
from print_monitor.snmp import (
    OID_PRT_MARKER_LIFE_COUNT,
    OID_SYS_NAME,
    VENDOR_TOTAL_COUNTER_OIDS,
    SNMPBackend,
    SNMPError,
    SNMPTimeout,
    _decode_oid,
    _encode_oid,
    build_get_request,
    build_get_response,
    diagnose_silence,
    host_is_reachable,
    identify,
    parse_response,
    read_total_counter,
    snmp_get,
    snmp_get_text,
)

OID = OID_PRT_MARKER_LIFE_COUNT


def _fake_agent(valores: dict[str, int | bytes], respostas: int = 1):
    """Agente SNMP de mentira: responde os OIDs de ``valores`` e ignora os demais.

    Ignorar em silencio e o comportamento de um agente real diante de um OID que
    ele nao implementa, que e justamente o caso que a busca por OIDs de
    fabricante precisa atravessar.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    def serve():
        for _ in range(respostas):
            try:
                data, addr = sock.recvfrom(65535)
            except OSError:
                return
            req_id, _, varbinds = parse_response(data)
            oid = varbinds[0][0]
            if oid not in valores:
                continue
            try:
                sock.sendto(
                    build_get_response("public", oid, valores[oid], request_id=req_id), addr
                )
            except OSError:
                return

    threading.Thread(target=serve, daemon=True).start()
    return sock, port


def test_oid_encode_decode_roundtrip():
    for oid in (OID, "1.3.6.1.2.1.1.1.0", "1.3.6.1.4.1.2435.2.3.9.4.2.1.5.5.1.1.1"):
        # _encode_oid embute tag+len; o valor BER vem apos o cabecalho de 2 bytes.
        encoded = _encode_oid(oid)
        assert _decode_oid(encoded[2:]) == oid


def test_request_packet_is_parseable():
    packet = build_get_request("public", OID, request_id=42, version="2c")
    request_id, error_status, varbinds = parse_response(packet)
    assert request_id == 42
    assert error_status == 0
    assert varbinds and varbinds[0][0] == OID


def test_response_roundtrip():
    packet = build_get_response("public", OID, 124500, request_id=7)
    request_id, error_status, varbinds = parse_response(packet)
    assert request_id == 7
    assert error_status == 0
    assert varbinds[0] == (OID, 124500)


def test_response_with_error_status():
    packet = build_get_response("public", OID, 0, error_status=2)
    _, error_status, _ = parse_response(packet)
    assert error_status == 2


@pytest.mark.parametrize(
    "packet",
    [
        b"",
        b"\x30",
        b"\x30\x82\x01",
        b"\x30\x05\x02\x01",
    ],
)
def test_parse_response_rejects_truncated_packets(packet):
    with pytest.raises(SNMPError):
        parse_response(packet)


@pytest.mark.parametrize("oid", ["", "3.1.2", "1.40.2", "1.-1.2", "abc"])
def test_build_request_rejects_invalid_oid(oid):
    with pytest.raises(ValueError):
        build_get_request("public", oid, request_id=1)


def _start_udp_responder(
    value: int,
    *,
    family: socket.AddressFamily = socket.AF_INET,
    host: str = "127.0.0.1",
    response_oid: str = OID,
):
    sock = socket.socket(family, socket.SOCK_DGRAM)
    sock.bind((host, 0))
    port = sock.getsockname()[1]

    def serve():
        data, addr = sock.recvfrom(65535)
        req_id, _, _ = parse_response(data)  # ecoa o request-id da consulta
        sock.sendto(
            build_get_response("public", response_oid, value, request_id=req_id),
            addr,
        )

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return sock, port


def test_snmp_get_loopback_success():
    sock, port = _start_udp_responder(987654)
    try:
        value = snmp_get("127.0.0.1", OID, port=port, timeout=2.0, retries=0)
        assert value == 987654
    finally:
        sock.close()


@pytest.mark.skipif(not socket.has_ipv6, reason="IPv6 indisponivel neste sistema")
def test_snmp_get_ipv6_loopback_success():
    try:
        sock, port = _start_udp_responder(
            456789,
            family=socket.AF_INET6,
            host="::1",
        )
    except OSError as exc:
        pytest.skip(f"Loopback IPv6 indisponivel: {exc}")
    try:
        value = snmp_get("::1", OID, port=port, timeout=2.0, retries=0)
        assert value == 456789
    finally:
        sock.close()


def test_snmp_get_rejects_response_for_another_oid():
    sock, port = _start_udp_responder(
        123,
        response_oid="1.3.6.1.2.1.1.3.0",
    )
    try:
        with pytest.raises(SNMPError, match="OID inesperado"):
            snmp_get("127.0.0.1", OID, port=port, timeout=2.0, retries=0)
    finally:
        sock.close()


def test_snmp_get_ignores_response_from_another_udp_port():
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    other_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    other_socket.bind(("127.0.0.1", 0))

    def serve():
        data, addr = listener.recvfrom(65535)
        req_id, _, _ = parse_response(data)
        other_socket.sendto(
            build_get_response("public", OID, 999, request_id=req_id),
            addr,
        )

    threading.Thread(target=serve, daemon=True).start()
    try:
        with pytest.raises(SNMPTimeout):
            snmp_get("127.0.0.1", OID, port=port, timeout=0.3, retries=0)
    finally:
        listener.close()
        other_socket.close()


def test_snmp_get_timeout():
    # Socket bound but never responds -> GET deve expirar (sem ICMP unreachable).
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        with pytest.raises(SNMPTimeout):
            snmp_get("127.0.0.1", OID, port=port, timeout=0.3, retries=0)
    finally:
        sock.close()


def test_snmp_get_ignores_wrong_request_id():
    # Respondedor envia request-id ERRADO -> deve ser descartado e expirar.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    def serve():
        _data, addr = sock.recvfrom(65535)
        sock.sendto(build_get_response("public", OID, 123, request_id=999_999), addr)

    threading.Thread(target=serve, daemon=True).start()
    try:
        with pytest.raises(SNMPTimeout):
            snmp_get("127.0.0.1", OID, port=port, timeout=0.6, retries=0)
    finally:
        sock.close()


def test_snmp_backend_reads_counter():
    sock, port = _start_udp_responder(555000)
    config = Config(
        db_path="data/test.db",
        backend="snmp",
        snmp_community="public",
        snmp_port=port,
        snmp_timeout=2,
        snmp_retries=0,
    )
    backend = SNMPBackend(config)
    printer = Printer(id=1, name="Teste", ip="127.0.0.1")
    try:
        assert backend.read_total_counter(printer) == 555000
    finally:
        sock.close()


def test_snmp_backend_passes_configured_v1(monkeypatch):
    received: dict[str, object] = {}

    def fake_snmp_get(host, oid, **kwargs):
        received.update(host=host, oid=oid, **kwargs)
        return 321

    monkeypatch.setattr("print_monitor.snmp.snmp_get", fake_snmp_get)
    config = Config(
        db_path="data/test.db",
        backend="snmp",
        snmp_community="public",
        snmp_port=161,
        snmp_timeout=2,
        snmp_retries=0,
        snmp_version="1",
    )
    printer = Printer(id=1, name="Teste", ip="192.0.2.10")

    assert SNMPBackend(config).read_total_counter(printer) == 321
    assert received["version"] == "1"


def test_snmp_backend_raises_on_unsupported_oid():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = Config(
        db_path="data/test.db",
        backend="snmp",
        snmp_community="public",
        snmp_port=port,
        snmp_timeout=0.3,
        snmp_retries=0,
    )
    backend = SNMPBackend(config)
    printer = Printer(id=1, name="Teste", ip="127.0.0.1")
    try:
        with pytest.raises(SNMPError):
            backend.read_total_counter(printer)
    finally:
        sock.close()


# -- OIDs de fabricante e identificacao -----------------------------------


def test_snmp_get_text_decodifica_string():
    sock, port = _fake_agent({OID_SYS_NAME: b"RICOH-RECEPCAO\x00"})
    try:
        nome = snmp_get_text("127.0.0.1", OID_SYS_NAME, port=port, timeout=2.0)
    finally:
        sock.close()
    assert nome == "RICOH-RECEPCAO"


def test_read_total_counter_usa_o_oid_padrao_primeiro():
    sock, port = _fake_agent({OID: 555000})
    try:
        resultado = read_total_counter("127.0.0.1", port=port, timeout=1.0, retries=0)
    finally:
        sock.close()
    assert resultado == (555000, OID)


def test_read_total_counter_cai_para_oid_de_fabricante():
    """Equipamento que responde, mas nao implementa a Printer-MIB completa."""
    _rotulo, oid_ricoh = VENDOR_TOTAL_COUNTER_OIDS[2]
    # O agente responde o OID padrao com um texto (valor nao numerico), que e
    # um erro e nao um silencio: o codigo deve seguir tentando os demais.
    sock, port = _fake_agent({OID: b"nao suportado", oid_ricoh: 4242}, respostas=12)
    try:
        valor, usado = read_total_counter("127.0.0.1", port=port, timeout=0.5, retries=0)
    finally:
        sock.close()
    assert (valor, usado) == (4242, oid_ricoh)


def test_read_total_counter_sem_resposta_orienta_o_usuario():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        # Nada atende TCP no loopback aqui, entao o diagnostico e "host morto".
        with pytest.raises(SNMPTimeout, match="ligado e conectado"):
            read_total_counter("127.0.0.1", port=port, timeout=0.3, retries=0)
    finally:
        sock.close()


def test_identify_le_o_que_conseguir_sem_falhar():
    sock, port = _fake_agent({OID_SYS_NAME: b"RICOH-RECEPCAO", OID: 4200}, respostas=16)
    try:
        ident = identify("127.0.0.1", port=port, timeout=0.4)
    finally:
        sock.close()
    assert ident.name == "RICOH-RECEPCAO"
    assert ident.counter == 4200
    assert ident.suggested_name == "RICOH-RECEPCAO"
    assert ident.responded is True
    assert ident.serial is None  # OID nao respondido, sem erro


def test_identity_sem_resposta_sugere_nome_pelo_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        ident = identify("127.0.0.1", port=port, timeout=0.2)
    finally:
        sock.close()
    assert ident.responded is False
    assert ident.suggested_name == "Impressora 127.0.0.1"


# -- diagnostico de silencio do SNMP --------------------------------------


def test_host_is_reachable_detecta_porta_aberta():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    porta = srv.getsockname()[1]
    try:
        assert host_is_reachable("127.0.0.1", ports=(porta,), timeout=1.0) is True
    finally:
        srv.close()


def test_host_is_reachable_falso_quando_nada_atende():
    livre = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    livre.bind(("127.0.0.1", 0))
    porta = livre.getsockname()[1]
    livre.close()
    assert host_is_reachable("127.0.0.1", ports=(porta,), timeout=0.3) is False


def test_diagnose_silence_separa_desligado_de_snmp_desabilitado(monkeypatch):
    """Dizer 'verifique se esta ligado' para um host online faz perder tempo."""
    monkeypatch.setattr("print_monitor.snmp.host_is_reachable", lambda ip, **kw: True)
    vivo = diagnose_silence("192.0.2.10")
    assert "ligado e acessivel" in vivo
    assert "Habilite o SNMP" in vivo

    monkeypatch.setattr("print_monitor.snmp.host_is_reachable", lambda ip, **kw: False)
    morto = diagnose_silence("192.0.2.11")
    assert "esta ligado e conectado" in morto
    assert "DHCP" in morto


def test_read_total_counter_usa_o_diagnostico(monkeypatch):
    """A mensagem de timeout tem de refletir o estado real do host."""
    monkeypatch.setattr("print_monitor.snmp.host_is_reachable", lambda ip, **kw: True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        with pytest.raises(SNMPTimeout, match="Habilite o SNMP"):
            read_total_counter("127.0.0.1", port=port, timeout=0.3, retries=0)
    finally:
        sock.close()
