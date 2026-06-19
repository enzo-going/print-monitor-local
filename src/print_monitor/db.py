"""Persistencia em SQLite.

Define o esquema e as operacoes basicas sobre impressoras e leituras. Datas sao
armazenadas em ISO 8601 (UTC). A classe ``Database`` pode ser usada como context
manager.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Printer, Reading

SCHEMA = """
CREATE TABLE IF NOT EXISTS printers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    ip         TEXT    NOT NULL UNIQUE,
    location   TEXT,
    model      TEXT,
    serial     TEXT,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS readings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    printer_id    INTEGER NOT NULL,
    total_counter INTEGER NOT NULL,
    collected_at  TEXT    NOT NULL,
    source        TEXT    NOT NULL DEFAULT 'manual',
    FOREIGN KEY (printer_id) REFERENCES printers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_readings_printer_time
    ON readings (printer_id, collected_at);
"""


def utcnow() -> datetime:
    """Retorna o instante atual em UTC (timezone-aware)."""
    return datetime.now(timezone.utc)


def _to_iso(value: datetime) -> str:
    """Serializa um datetime para ISO 8601, assumindo UTC quando ingenuo."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
    """Reconstroi um datetime UTC a partir de uma string ISO 8601."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class Database:
    """Camada fina de acesso ao SQLite."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.parent and str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

    # -- ciclo de vida -----------------------------------------------------

    def initialize(self) -> None:
        """Cria as tabelas e indices, se ainda nao existirem."""
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- impressoras -------------------------------------------------------

    def add_printer(
        self,
        name: str,
        ip: str,
        location: str | None = None,
        model: str | None = None,
        serial: str | None = None,
        active: bool = True,
    ) -> int:
        """Insere uma impressora e retorna seu id. IP deve ser unico."""
        cur = self.conn.execute(
            """
            INSERT INTO printers (name, ip, location, model, serial, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, ip, location, model, serial, 1 if active else 0, _to_iso(utcnow())),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_printer(self, printer_id: int) -> Printer | None:
        row = self.conn.execute(
            "SELECT * FROM printers WHERE id = ?", (printer_id,)
        ).fetchone()
        return _row_to_printer(row) if row else None

    def get_printer_by_ip(self, ip: str) -> Printer | None:
        row = self.conn.execute(
            "SELECT * FROM printers WHERE ip = ?", (ip,)
        ).fetchone()
        return _row_to_printer(row) if row else None

    def list_printers(self, only_active: bool = False) -> list[Printer]:
        query = "SELECT * FROM printers"
        if only_active:
            query += " WHERE active = 1"
        query += " ORDER BY name"
        rows = self.conn.execute(query).fetchall()
        return [_row_to_printer(r) for r in rows]

    def delete_printer(self, printer_id: int) -> bool:
        """Remove uma impressora e suas leituras (cascade). Retorna se removeu."""
        cur = self.conn.execute("DELETE FROM printers WHERE id = ?", (printer_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # -- leituras ----------------------------------------------------------

    def add_reading(
        self,
        printer_id: int,
        total_counter: int,
        collected_at: datetime | None = None,
        source: str = "manual",
    ) -> int:
        """Registra uma leitura do contador total."""
        collected_at = collected_at or utcnow()
        cur = self.conn.execute(
            """
            INSERT INTO readings (printer_id, total_counter, collected_at, source)
            VALUES (?, ?, ?, ?)
            """,
            (printer_id, total_counter, _to_iso(collected_at), source),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_readings(
        self,
        printer_id: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Reading]:
        """Lista leituras, opcionalmente filtrando por impressora e periodo."""
        query = "SELECT * FROM readings WHERE 1 = 1"
        params: list[object] = []
        if printer_id is not None:
            query += " AND printer_id = ?"
            params.append(printer_id)
        if start is not None:
            query += " AND collected_at >= ?"
            params.append(_to_iso(start))
        if end is not None:
            query += " AND collected_at <= ?"
            params.append(_to_iso(end))
        query += " ORDER BY printer_id, collected_at"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_reading(r) for r in rows]


def _row_to_printer(row: sqlite3.Row) -> Printer:
    return Printer(
        id=row["id"],
        name=row["name"],
        ip=row["ip"],
        location=row["location"],
        model=row["model"],
        serial=row["serial"],
        active=bool(row["active"]),
    )


def _row_to_reading(row: sqlite3.Row) -> Reading:
    return Reading(
        id=row["id"],
        printer_id=row["printer_id"],
        total_counter=row["total_counter"],
        collected_at=_from_iso(row["collected_at"]),
        source=row["source"],
    )
