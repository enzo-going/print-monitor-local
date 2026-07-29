"""Testes das protecoes do modo servidor local."""

from print_monitor.cli import _is_loopback_host


def test_dashboard_server_accepts_only_loopback_hosts():
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("127.0.0.2")
    assert _is_loopback_host("localhost")
    assert _is_loopback_host("::1")
    assert not _is_loopback_host("0.0.0.0")
    assert not _is_loopback_host("192.0.2.10")
    assert not _is_loopback_host("example.test")
