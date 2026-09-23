"""Fixtures compartilhadas dos testes."""

from __future__ import annotations

import socket

import pytest

from print_monitor.db import Database


@pytest.fixture()
def db(tmp_path):
    """Banco SQLite temporario e isolado por teste."""
    database = Database(tmp_path / "test.db")
    database.initialize()
    yield database
    database.close()


@pytest.fixture()
def closed_tcp_port():
    """Porta TCP do loopback em que nada escuta, garantida ate o fim do teste.

    O socket fica vinculado sem ``listen()``: as conexoes sao recusadas e nenhum
    outro processo consegue escutar na porta enquanto ele estiver aberto. Liberar
    a porta antes de sonda-la deixaria uma janela para outro programa ocupa-la.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    yield sock.getsockname()[1]
    sock.close()
