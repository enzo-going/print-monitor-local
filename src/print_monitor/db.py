"""Persistencia em SQLite.

Define o esquema e as operacoes basicas sobre impressoras e leituras. Datas sao
armazenadas em ISO 8601 (UTC). A classe ``Database`` pode ser usada como context
manager.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from .models import Printer, Reading, ReadingSummary, validate_counter

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

CREATE INDEX IF NOT EXISTS idx_readings_time_printer
    ON readings (collected_at, printer_id);

CREATE TABLE IF NOT EXISTS reading_ignores (
    reading_id  INTEGER PRIMARY KEY,
    ignored_at  TEXT NOT NULL,
    reason      TEXT,
    FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE CASCADE
);
"""

_INSERT_READING = """
INSERT INTO readings (printer_id, total_counter, collected_at, source)
VALUES (?, ?, ?, ?)
"""

_INSERT_READING_IF_ACTIVE = """
INSERT INTO readings (printer_id, total_counter, collected_at, source)
SELECT ?, ?, ?, ?
WHERE EXISTS (
    SELECT 1 FROM printers WHERE id = ? AND active = 1
)
"""


def utcnow() -> datetime:
    """Retorna o instante atual em UTC (timezone-aware)."""
    return datetime.now(UTC)


def _to_iso(value: datetime) -> str:
    """Serializa um datetime para ISO 8601, assumindo UTC quando ingenuo."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str) -> datetime:
    """Reconstroi um datetime UTC a partir de uma string ISO 8601."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class Database:
    """Camada fina de acesso ao SQLite."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.parent and str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA busy_timeout = 10000")
        if str(self.path) != ":memory:":
            # WAL permite que o dashboard leia relatorios enquanto uma coleta grava.
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")

    # -- ciclo de vida -----------------------------------------------------

    def initialize(self) -> None:
        """Cria as tabelas e indices, se ainda nao existirem."""
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
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
        row = self.conn.execute("SELECT * FROM printers WHERE id = ?", (printer_id,)).fetchone()
        return _row_to_printer(row) if row else None

    def get_printer_by_ip(self, ip: str) -> Printer | None:
        row = self.conn.execute("SELECT * FROM printers WHERE ip = ?", (ip,)).fetchone()
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

    def set_printer_active(self, printer_id: int, active: bool) -> bool:
        """Ativa ou pausa a coleta sem apagar a impressora nem seu historico."""
        cur = self.conn.execute(
            "UPDATE printers SET active = ? WHERE id = ?",
            (1 if active else 0, printer_id),
        )
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
        total_counter = validate_counter(total_counter)
        cur = self.conn.execute(
            _INSERT_READING,
            (printer_id, total_counter, _to_iso(collected_at), source),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_readings(
        self,
        readings: Iterable[tuple[int, int, datetime, str]],
    ) -> list[int]:
        """Registra varias leituras em uma unica transacao atomica."""
        ids: list[int] = []
        try:
            for printer_id, total_counter, collected_at, source in readings:
                total_counter = validate_counter(total_counter)
                cur = self.conn.execute(
                    _INSERT_READING,
                    (printer_id, total_counter, _to_iso(collected_at), source),
                )
                ids.append(int(cur.lastrowid))
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()
        return ids

    def add_readings_if_printers_active(
        self,
        readings: Iterable[tuple[int, int, datetime, str]],
    ) -> list[int | None]:
        """Grava em lote e ignora equipamentos removidos ou pausados durante a coleta.

        Cada ``None`` mantém o alinhamento com a entrada e indica que a impressora
        deixou de estar ativa antes da persistência. A verificação e a inserção
        acontecem na mesma instrução SQL, evitando a janela entre consultar e gravar.
        """
        ids: list[int | None] = []
        try:
            for printer_id, total_counter, collected_at, source in readings:
                total_counter = validate_counter(total_counter)
                cur = self.conn.execute(
                    _INSERT_READING_IF_ACTIVE,
                    (
                        printer_id,
                        total_counter,
                        _to_iso(collected_at),
                        source,
                        printer_id,
                    ),
                )
                ids.append(int(cur.lastrowid) if cur.rowcount > 0 else None)
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()
        return ids

    def list_readings(
        self,
        printer_id: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        include_ignored: bool = False,
    ) -> list[Reading]:
        """Lista leituras, opcionalmente filtrando por impressora e periodo."""
        query = """
            SELECT r.*, (i.reading_id IS NOT NULL) AS ignored, i.reason AS ignore_reason
            FROM readings AS r
            LEFT JOIN reading_ignores AS i ON i.reading_id = r.id
            WHERE 1 = 1
        """
        params: list[object] = []
        if not include_ignored:
            query += " AND i.reading_id IS NULL"
        if printer_id is not None:
            query += " AND r.printer_id = ?"
            params.append(printer_id)
        if start is not None:
            query += " AND r.collected_at >= ?"
            params.append(_to_iso(start))
        if end is not None:
            query += " AND r.collected_at <= ?"
            params.append(_to_iso(end))
        query += " ORDER BY r.printer_id, r.collected_at, r.id"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_reading(r) for r in rows]

    def list_period_readings_with_baseline(
        self,
        printer_ids: set[int],
        start: datetime,
        end: datetime,
    ) -> list[Reading]:
        """Lista o periodo e a ultima leitura valida anterior por impressora.

        A consulta e feita em lote para evitar uma consulta adicional por
        impressora. A leitura anterior funciona como linha de base do primeiro
        delta observado no periodo.
        """
        if not printer_ids:
            return []
        placeholders = ", ".join("?" for _ in printer_ids)
        ordered_ids = sorted(printer_ids)
        query = f"""
            SELECT r.*, 0 AS ignored, NULL AS ignore_reason
            FROM readings AS r
            WHERE r.printer_id IN ({placeholders})
              AND r.collected_at <= ?
              AND NOT EXISTS (
                  SELECT 1 FROM reading_ignores AS i WHERE i.reading_id = r.id
              )
              AND (
                  r.collected_at >= ?
                  OR r.id = (
                      SELECT r2.id
                      FROM readings AS r2
                      WHERE r2.printer_id = r.printer_id
                        AND r2.collected_at < ?
                        AND NOT EXISTS (
                            SELECT 1
                            FROM reading_ignores AS i2
                            WHERE i2.reading_id = r2.id
                        )
                      ORDER BY r2.collected_at DESC, r2.id DESC
                      LIMIT 1
                  )
              )
            ORDER BY r.printer_id, r.collected_at, r.id
        """
        params: list[object] = [
            *ordered_ids,
            _to_iso(end),
            _to_iso(start),
            _to_iso(start),
        ]
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_reading(row) for row in rows]

    def get_reading(self, reading_id: int) -> Reading | None:
        """Retorna uma leitura, inclusive quando estiver ignorada."""
        row = self.conn.execute(
            """
            SELECT r.*, (i.reading_id IS NOT NULL) AS ignored, i.reason AS ignore_reason
            FROM readings AS r
            LEFT JOIN reading_ignores AS i ON i.reading_id = r.id
            WHERE r.id = ?
            """,
            (reading_id,),
        ).fetchone()
        return _row_to_reading(row) if row else None

    def list_recent_readings(
        self,
        *,
        limit: int = 100,
        printer_id: int | None = None,
    ) -> list[Reading]:
        """Retorna as leituras mais recentes, inclusive as ignoradas."""
        safe_limit = max(1, min(limit, 500))
        query = """
            SELECT r.*, (i.reading_id IS NOT NULL) AS ignored, i.reason AS ignore_reason
            FROM readings AS r
            LEFT JOIN reading_ignores AS i ON i.reading_id = r.id
        """
        params: list[object] = []
        if printer_id is not None:
            query += " WHERE r.printer_id = ?"
            params.append(printer_id)
        query += " ORDER BY r.collected_at DESC, r.id DESC LIMIT ?"
        params.append(safe_limit)
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_reading(row) for row in rows]

    def reading_deltas(self, reading_ids: set[int]) -> dict[int, int | None]:
        """Calcula deltas validos para um conjunto de leituras em uma consulta."""
        if not reading_ids:
            return {}
        placeholders = ", ".join("?" for _ in reading_ids)
        query = f"""
            WITH valid_readings AS (
                SELECT
                    r.id,
                    r.total_counter,
                    LAG(r.total_counter) OVER (
                        PARTITION BY r.printer_id
                        ORDER BY r.collected_at, r.id
                    ) AS previous_counter
                FROM readings AS r
                WHERE NOT EXISTS (
                    SELECT 1 FROM reading_ignores AS i WHERE i.reading_id = r.id
                )
            )
            SELECT id, total_counter, previous_counter
            FROM valid_readings
            WHERE id IN ({placeholders})
        """
        rows = self.conn.execute(query, sorted(reading_ids)).fetchall()
        return {
            int(row["id"]): (
                int(row["total_counter"]) - int(row["previous_counter"])
                if row["previous_counter"] is not None
                else None
            )
            for row in rows
        }

    def ignore_reading(self, reading_id: int, reason: str | None = None) -> bool:
        """Desconsidera uma leitura dos calculos sem apaga-la."""
        if self.get_reading(reading_id) is None:
            return False
        clean_reason = (reason or "").strip()[:300] or None
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO reading_ignores (reading_id, ignored_at, reason)
            VALUES (?, ?, ?)
            """,
            (reading_id, _to_iso(utcnow()), clean_reason),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def restore_reading(self, reading_id: int) -> bool:
        """Volta a considerar uma leitura anteriormente ignorada."""
        cur = self.conn.execute(
            "DELETE FROM reading_ignores WHERE reading_id = ?",
            (reading_id,),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def latest_readings(self) -> list[Reading]:
        """Retorna somente a leitura mais recente de cada impressora."""
        rows = self.conn.execute(
            """
            SELECT r.*
            FROM readings AS r
            WHERE r.id = (
                SELECT r2.id
                FROM readings AS r2
                WHERE r2.printer_id = r.printer_id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM reading_ignores AS i2
                      WHERE i2.reading_id = r2.id
                  )
                ORDER BY r2.collected_at DESC, r2.id DESC
                LIMIT 1
            )
              AND NOT EXISTS (
                  SELECT 1 FROM reading_ignores AS i WHERE i.reading_id = r.id
              )
            ORDER BY r.printer_id
            """
        ).fetchall()
        return [_row_to_reading(row) for row in rows]

    def reading_summary(self) -> ReadingSummary:
        """Resume o histórico para exibir o estado real da coleta no painel."""
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total_readings,
                COUNT(DISTINCT printer_id) AS printers_with_readings,
                MAX(collected_at) AS last_collected_at
            FROM readings AS r
            WHERE NOT EXISTS (
                SELECT 1 FROM reading_ignores AS i WHERE i.reading_id = r.id
            )
            """
        ).fetchone()
        assert row is not None
        last_collected_at = row["last_collected_at"]
        return ReadingSummary(
            total_readings=int(row["total_readings"]),
            printers_with_readings=int(row["printers_with_readings"]),
            last_collected_at=_from_iso(last_collected_at) if last_collected_at else None,
        )


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
    keys = set(row.keys())
    return Reading(
        id=row["id"],
        printer_id=row["printer_id"],
        total_counter=row["total_counter"],
        collected_at=_from_iso(row["collected_at"]),
        source=row["source"],
        ignored=bool(row["ignored"]) if "ignored" in keys else False,
        ignore_reason=row["ignore_reason"] if "ignore_reason" in keys else None,
    )
