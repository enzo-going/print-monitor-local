"""Testes da configuracao e do parser de .env."""

from __future__ import annotations

import print_monitor.config as config


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
