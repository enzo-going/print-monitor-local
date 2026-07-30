"""Testes do backend SNMP (codificacao BER e cliente GET via loopback)."""

from __future__ import annotations

import socket
import threading

import pytest

from print_monitor.config import Config
from print_monitor.models import Printer
from print_monitor.snmp import (
    OID_PRT_MARKER_LIFE_COUNT,
    SNMPBackend,
    SNMPError,
    SNMPTimeout,
    _decode_oid,
    _encode_oid,
    build_get_request,
    build_get_response,
    parse_response,
    snmp_get,
)

OID = OID_PRT_MARKER_LIFE_COUNT


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
