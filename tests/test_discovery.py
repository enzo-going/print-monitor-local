"""Testes da descoberta de rede (sem varredura real; usa loopback)."""

from __future__ import annotations

import socket

import pytest

from print_monitor.discovery import (
    discover,
    host_count,
    iter_hosts,
    tcp_port_open,
)


def test_host_count():
    assert host_count("192.168.0.0/30") == 2
    assert host_count("192.168.0.0/24") == 254
    assert host_count("192.168.0.0/31") == 2
    assert host_count("192.168.0.1/32") == 1


def test_iter_hosts_slash30():
    hosts = list(iter_hosts("192.168.0.0/30"))
    assert hosts == ["192.168.0.1", "192.168.0.2"]


def _listening_tcp_port():
    """Abre um socket TCP em escuta no loopback e retorna (socket, porta)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)  # handshake conclui no SO mesmo sem accept()
    return srv, srv.getsockname()[1]


def _free_tcp_port() -> int:
    """Reserva e libera uma porta para obter um numero quase certamente fechado."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_tcp_port_open_true_and_false():
    srv, port = _listening_tcp_port()
    try:
        assert tcp_port_open("127.0.0.1", port, timeout=1.0) is True
    finally:
        srv.close()
    assert tcp_port_open("127.0.0.1", _free_tcp_port(), timeout=0.3) is False


def test_discover_finds_local_listener():
    srv, port = _listening_tcp_port()
    try:
        found = discover("127.0.0.1/32", ports=(port,), timeout=1.0)
    finally:
        srv.close()
    assert len(found) == 1
    assert found[0].ip == "127.0.0.1"
    assert found[0].open_ports == [port]
    assert found[0].snmp_counter is None


def test_discover_empty_when_no_ports_open():
    found = discover("127.0.0.1/32", ports=(_free_tcp_port(),), timeout=0.3)
    assert found == []


def test_discover_rejects_large_range():
    with pytest.raises(ValueError, match="Faixa muito grande"):
        discover("10.0.0.0/16", max_hosts=1024)
