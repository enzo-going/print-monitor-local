"""Testes da configuracao e do parser de .env."""

from __future__ import annotations

import pytest

import print_monitor.config as config


def test_load_config_defaults_to_real_snmp(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "app_base_dir", lambda: tmp_path)
    monkeypatch.delenv("PRINT_MONITOR_BACKEND", raising=False)

    assert config.load_config().backend == "snmp"


def test_load_config_reads_env_file(tmp_path, monkeypatch):
    # Aponta o diretorio base para um tmp com um .env e limpa o ambiente.
    (tmp_path / ".env").write_text(
        "# comentario\nPRINT_MONITOR_BACKEND=snmp\nSNMP_COMMUNITY=privada\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "app_base_dir", lambda: tmp_path)
    for var in ("PRINT_MONITOR_BACKEND", "SNMP_COMMUNITY", "PRINT_MONITOR_DB"):
        monkeypatch.delenv(var, raising=False)

    cfg = config.load_config()
    assert cfg.backend == "snmp"
    assert cfg.snmp_community == "privada"


def test_environment_takes_precedence_over_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("PRINT_MONITOR_BACKEND=snmp\n", encoding="utf-8")
    monkeypatch.setattr(config, "app_base_dir", lambda: tmp_path)
    monkeypatch.setenv("PRINT_MONITOR_BACKEND", "mock")

    cfg = config.load_config()
    assert cfg.backend == "mock"  # variavel de ambiente vence o .env


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PRINT_MONITOR_BACKEND", "outro"),
        ("SNMP_PORT", "70000"),
        ("SNMP_TIMEOUT", "zero"),
        ("PRINT_MONITOR_WORKERS", "0"),
    ],
)
def test_invalid_environment_values_have_clear_errors(tmp_path, monkeypatch, name, value):
    monkeypatch.setattr(config, "app_base_dir", lambda: tmp_path)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        config.load_config()
