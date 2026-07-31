"""Testes da linha de comando."""

from __future__ import annotations

import pytest

from print_monitor.cli import _is_loopback_host, main


class _BackendParcial:
    """Responde por uns IPs e falha por outros, como um parque real."""

    def read_total_counter(self, printer) -> int:
        if printer.ip.startswith("192.0.2.9"):
            raise RuntimeError("sem resposta")
        return 1000


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PRINT_MONITOR_DB", str(tmp_path / "cli.db"))
    monkeypatch.setenv("PRINT_MONITOR_BACKEND", "mock")
    return tmp_path


def _collect(monkeypatch, *ips_com_falha: str) -> int:
    from print_monitor import cli

    monkeypatch.setattr(cli, "make_backend", lambda *a, **k: (_BackendParcial(), "test"))
    return main(["collect", "--all"])


def test_collect_all_nao_falha_por_impressora_desligada(cli_env, monkeypatch):
    """Uma maquina desligada nao pode marcar a coleta inteira como erro.

    Em um parque real sempre ha alguma offline; se a tarefa agendada do Windows
    aparecer como falha todo dia, o alarme perde a serventia.
    """
    main(["add-printer", "--name", "Liga", "--ip", "192.0.2.10"])
    main(["add-printer", "--name", "Desliga", "--ip", "192.0.2.90"])
    assert _collect(monkeypatch) == 0


def test_collect_all_falha_quando_ninguem_responde(cli_env, monkeypatch):
    main(["add-printer", "--name", "Desliga", "--ip", "192.0.2.90"])
    assert _collect(monkeypatch) == 1


def test_collect_all_sem_impressoras_nao_e_erro(cli_env, monkeypatch):
    assert _collect(monkeypatch) == 0


def test_dashboard_server_accepts_only_loopback_hosts():
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("127.0.0.2")
    assert _is_loopback_host("localhost")
    assert _is_loopback_host("::1")
    assert not _is_loopback_host("0.0.0.0")
    assert not _is_loopback_host("192.0.2.10")
    assert not _is_loopback_host("example.test")
