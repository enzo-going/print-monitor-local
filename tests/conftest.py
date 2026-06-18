"""Fixtures compartilhadas dos testes."""

from __future__ import annotations

import pytest

from print_monitor.db import Database


@pytest.fixture()
def db(tmp_path):
    """Banco SQLite temporario e isolado por teste."""
    database = Database(tmp_path / "test.db")
    database.initialize()
    yield database
    database.close()
