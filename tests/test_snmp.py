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
    error_status, varbinds = parse_response(packet)
    assert error_status == 0
    assert varbinds and varbinds[0][0] == OID


def test_response_roundtrip():
    packet = build_get_response("public", OID, 124500, request_id=7)
    error_status, varbinds = parse_response(packet)
    assert error_status == 0
    assert varbinds[0] == (OID, 124500)


def test_response_with_error_status():
    packet = build_get_response("public", OID, 0, error_status=2)
    error_status, _ = parse_response(packet)
    assert error_status == 2


def _start_udp_responder(value: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    def serve():
        data, addr = sock.recvfrom(65535)
        sock.sendto(build_get_response("public", OID, value), addr)

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
