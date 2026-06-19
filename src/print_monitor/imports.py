"""Importacao de impressoras a partir de CSV.

Permite carregar um parque inteiro de impressoras de uma planilha exportada em
CSV (ex.: o "Controle de Impressoras"). O mapeamento de colunas e flexivel e
tolera variacoes comuns de cabecalho (com/sem acento, maiusculas/minusculas) e
separador ``,`` ou ``;`` (comum no Excel em pt-BR).

Mapeamento de colunas reconhecidas:
- nome:   NOME / NAME            (se ausente, usa o SETOR)
- local:  SETOR / LOCAL / DEPARTAMENTO
- ip:     IP / ENDERECO
- modelo: MODELO / MODEL         (combinado com a MARCA, se houver)
- marca:  MARCA / FABRICANTE / BRAND
- serie:  N SERIE / NUMERO DE SERIE / SERIE / SERIAL / SN
"""

from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass, field

from .db import Database
from .printers import register_printer

_ALIASES = {
    "name": {"NOME", "NAME"},
    "location": {"SETOR", "LOCAL", "LOCATION", "DEPARTAMENTO", "DEPTO"},
    "ip": {"IP", "ENDERECO", "ENDERECO IP", "ADDRESS"},
    "model": {"MODELO", "MODEL"},
    "brand": {"MARCA", "FABRICANTE", "BRAND"},
    "serial": {
        "N SERIE",
        "NO SERIE",
        "NUMERO DE SERIE",
        "N DE SERIE",
        "SERIE",
        "SERIAL",
        "SN",
    },
}


@dataclass
class ImportResult:
    """Resultado de uma importacao de impressoras."""

    added: int = 0
    skipped: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)


def _normalize_header(text: str) -> str:
    """Remove acentos, espacos extras e caixa para casar cabecalhos."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.replace("º", "").replace("°", "").split()).upper()


def decode_bytes(data: bytes) -> str:
    """Decodifica bytes de CSV tentando UTF-8 (com BOM) e, depois, cp1252."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _detect_delimiter(sample: str) -> str:
    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    return ";" if first_line.count(";") > first_line.count(",") else ","


def _build_column_map(fieldnames: list[str]) -> dict[str, str]:
    """Mapeia cada campo conhecido para o nome de coluna real do CSV."""
    mapping: dict[str, str] = {}
    for raw in fieldnames:
        norm = _normalize_header(raw)
        for field_name, aliases in _ALIASES.items():
            if norm in aliases and field_name not in mapping:
                mapping[field_name] = raw
    return mapping


def import_printers_from_csv(db: Database, csv_text: str) -> ImportResult:
    """Importa impressoras de um texto CSV, ignorando IPs ja cadastrados.

    Cada linha vira uma impressora. Linhas com IP invalido ou faltando dados
    obrigatorios sao reportadas em ``errors`` sem interromper a importacao.
    """
    result = ImportResult()
    text = csv_text.lstrip("﻿")
    if not text.strip():
        return result

    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        return result
    cols = _build_column_map(reader.fieldnames)

    if "ip" not in cols:
        result.errors.append((1, "Coluna de IP nao encontrada no cabecalho."))
        return result

    for line_no, row in enumerate(reader, start=2):
        def value(field_name: str) -> str:
            col = cols.get(field_name)
            return (row.get(col) or "").strip() if col else ""

        ip = value("ip")
        if not ip:
            continue  # linha vazia / sem IP, ignora silenciosamente

        name = value("name") or value("location")
        location = value("location") or None
        brand, model = value("brand"), value("model")
        full_model = " ".join(part for part in (brand, model) if part) or None
        serial = value("serial") or None
        if not name:
            name = ip  # ultimo recurso para nao ficar sem nome

        try:
            register_printer(
                db,
                name=name,
                ip=ip,
                location=location,
                model=full_model,
                serial=serial,
            )
            result.added += 1
        except ValueError as exc:
            message = str(exc)
            if "Ja existe" in message:
                result.skipped += 1
            else:
                result.errors.append((line_no, message))
    return result
