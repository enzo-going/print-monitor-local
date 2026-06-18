"""Coleta via SNMP (v1/v2c) implementada em Python puro.

Implementa o minimo necessario para um SNMP GET de um unico OID inteiro
(tipicamente o contador total da impressora), com codificacao/decodificacao BER
sobre a biblioteca padrao. Isso evita dependencias nativas pesadas e simplifica o
empacotamento (PyInstaller), mantendo o codigo testavel sem rede.

Estrutura de uma mensagem SNMP v2c GET:

    SEQUENCE {
      INTEGER  version            -- 0 = v1, 1 = v2c
      OCTET    community
      [A0] GetRequest-PDU {
        INTEGER request-id
        INTEGER error-status      -- 0 no request
        INTEGER error-index       -- 0 no request
        SEQUENCE OF VarBind {
          SEQUENCE { OID, NULL }
        }
      }
    }

OIDs de referencia (ver docs/limitacoes-fabricantes.md):
- Printer-MIB prtMarkerLifeCount (RFC 3805): 1.3.6.1.2.1.43.10.2.1.4.1.1
  (contador total de impressoes para o marcador 1; o mais portavel).
"""

from __future__ import annotations

import random
import socket

from .config import Config
from .models import Printer

# OID padrao Printer-MIB para contador total (prtMarkerLifeCount, marcador 1).
OID_PRT_MARKER_LIFE_COUNT = "1.3.6.1.2.1.43.10.2.1.4.1.1"

# OIDs candidatos para o total, tentados em ordem.
COMMON_TOTAL_COUNTER_OIDS = (OID_PRT_MARKER_LIFE_COUNT,)

# Tags BER usadas.
_TAG_INTEGER = 0x02
_TAG_OCTET = 0x04
_TAG_NULL = 0x05
_TAG_OID = 0x06
_TAG_SEQUENCE = 0x30
_TAG_GET_REQUEST = 0xA0
_TAG_GET_RESPONSE = 0xA2
# Tipos de aplicacao com valor inteiro nao assinado.
_TAG_COUNTER32 = 0x41
_TAG_GAUGE32 = 0x42
_TAG_TIMETICKS = 0x43
_TAG_COUNTER64 = 0x46
_UNSIGNED_TAGS = (_TAG_COUNTER32, _TAG_GAUGE32, _TAG_TIMETICKS, _TAG_COUNTER64)
# Excecoes do SNMPv2 que aparecem como valor de um varbind.
_EXCEPTION_TAGS = (0x80, 0x81, 0x82)  # noSuchObject/Instance, endOfMibView


class SNMPError(Exception):
    """Falha ao consultar uma impressora via SNMP."""


class SNMPTimeout(SNMPError):
    """Nao houve resposta do agente dentro do tempo limite."""


# --------------------------------------------------------------------------
# Codificacao BER
# --------------------------------------------------------------------------

def _encode_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    out = bytearray()
    while n:
        out.append(n & 0xFF)
        n >>= 8
    out.reverse()
    return bytes([0x80 | len(out)]) + bytes(out)


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _encode_length(len(value)) + value


def _encode_unsigned_value(n: int) -> bytes:
    if n == 0:
        return b"\x00"
    nbytes = (n.bit_length() + 7) // 8
    return n.to_bytes(nbytes, "big")


def _encode_integer(n: int) -> bytes:
    # Apenas valores nao negativos sao usados aqui (versao, request-id, status).
    if n == 0:
        value = b"\x00"
    else:
        value = _encode_unsigned_value(n)
        if value[0] & 0x80:  # evitar interpretacao como negativo
            value = b"\x00" + value
    return _tlv(_TAG_INTEGER, value)


def _encode_octet_string(data: bytes) -> bytes:
    return _tlv(_TAG_OCTET, data)


def _encode_null() -> bytes:
    return bytes([_TAG_NULL, 0x00])


def _encode_base128(n: int) -> bytes:
    if n == 0:
        return b"\x00"
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.reverse()
    return bytes(out)


def _encode_oid(oid: str) -> bytes:
    parts = [int(p) for p in oid.strip().split(".") if p != ""]
    if len(parts) < 2:
        raise ValueError(f"OID invalido: {oid!r}")
    body = bytearray([40 * parts[0] + parts[1]])
    for sub in parts[2:]:
        body += _encode_base128(sub)
    return _tlv(_TAG_OID, bytes(body))


def _version_code(version: str) -> int:
    return 0 if str(version) in ("1", "v1") else 1


def build_get_request(
    community: str, oid: str, request_id: int, version: str = "2c"
) -> bytes:
    """Monta uma mensagem SNMP GET para um unico OID."""
    varbind = _tlv(_TAG_SEQUENCE, _encode_oid(oid) + _encode_null())
    varbind_list = _tlv(_TAG_SEQUENCE, varbind)
    pdu_body = (
        _encode_integer(request_id)
        + _encode_integer(0)
        + _encode_integer(0)
        + varbind_list
    )
    pdu = _tlv(_TAG_GET_REQUEST, pdu_body)
    message_body = (
        _encode_integer(_version_code(version))
        + _encode_octet_string(community.encode("utf-8"))
        + pdu
    )
    return _tlv(_TAG_SEQUENCE, message_body)


# --------------------------------------------------------------------------
# Decodificacao BER
# --------------------------------------------------------------------------

def _decode_length(data: bytes, idx: int) -> tuple[int, int]:
    first = data[idx]
    idx += 1
    if first < 0x80:
        return first, idx
    num = first & 0x7F
    length = int.from_bytes(data[idx : idx + num], "big")
    return length, idx + num


def _read_tlv(data: bytes, idx: int) -> tuple[int, bytes, int]:
    tag = data[idx]
    length, idx = _decode_length(data, idx + 1)
    value = data[idx : idx + length]
    return tag, value, idx + length


def _decode_oid(data: bytes) -> str:
    if not data:
        return ""
    parts = [data[0] // 40, data[0] % 40]
    acc = 0
    for byte in data[1:]:
        acc = (acc << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            parts.append(acc)
            acc = 0
    return ".".join(str(p) for p in parts)


def _decode_varbind_value(tag: int, raw: bytes):
    if tag in _EXCEPTION_TAGS:
        return None
    if tag == _TAG_INTEGER:
        return int.from_bytes(raw, "big", signed=True)
    if tag in _UNSIGNED_TAGS:
        return int.from_bytes(raw, "big", signed=False)
    if tag == _TAG_OCTET:
        return raw
    return raw


def parse_response(data: bytes) -> tuple[int, list[tuple[str, object]]]:
    """Decodifica uma resposta SNMP em (error_status, lista de varbinds)."""
    tag, message, _ = _read_tlv(data, 0)
    if tag != _TAG_SEQUENCE:
        raise SNMPError("Mensagem SNMP invalida (sequencia esperada).")

    idx = 0
    _, _version, idx = _read_tlv(message, idx)
    _, _community, idx = _read_tlv(message, idx)
    _, pdu, idx = _read_tlv(message, idx)

    pidx = 0
    _, _request_id, pidx = _read_tlv(pdu, pidx)
    _, error_raw, pidx = _read_tlv(pdu, pidx)
    _, _error_index, pidx = _read_tlv(pdu, pidx)
    _, varbind_list, pidx = _read_tlv(pdu, pidx)
    error_status = int.from_bytes(error_raw, "big", signed=True)

    varbinds: list[tuple[str, object]] = []
    vidx = 0
    while vidx < len(varbind_list):
        _, varbind, vidx = _read_tlv(varbind_list, vidx)
        oidx = 0
        _, oid_raw, oidx = _read_tlv(varbind, oidx)
        value_tag, value_raw, oidx = _read_tlv(varbind, oidx)
        varbinds.append(
            (_decode_oid(oid_raw), _decode_varbind_value(value_tag, value_raw))
        )
    return error_status, varbinds


def build_get_response(
    community: str,
    oid: str,
    value: int,
    request_id: int = 1,
    error_status: int = 0,
    value_tag: int = _TAG_COUNTER32,
) -> bytes:
    """Monta uma resposta SNMP GET. Usado por testes e como referencia."""
    value_bytes = _tlv(value_tag, _encode_unsigned_value(value))
    varbind = _tlv(_TAG_SEQUENCE, _encode_oid(oid) + value_bytes)
    varbind_list = _tlv(_TAG_SEQUENCE, varbind)
    pdu = _tlv(
        _TAG_GET_RESPONSE,
        _encode_integer(request_id)
        + _encode_integer(error_status)
        + _encode_integer(0)
        + varbind_list,
    )
    return _tlv(
        _TAG_SEQUENCE,
        _encode_integer(1) + _encode_octet_string(community.encode("utf-8")) + pdu,
    )


# --------------------------------------------------------------------------
# Cliente SNMP GET
# --------------------------------------------------------------------------

def snmp_get(
    host: str,
    oid: str,
    community: str = "public",
    port: int = 161,
    timeout: float = 2.0,
    retries: int = 1,
    version: str = "2c",
) -> int:
    """Executa um SNMP GET e retorna o valor inteiro do OID.

    Levanta ``SNMPTimeout`` se nao houver resposta e ``SNMPError`` para demais
    falhas (erro do agente, OID nao suportado, valor nao numerico).
    """
    request_id = random.randint(1, 0x7FFFFFFF)
    packet = build_get_request(community, oid, request_id, version)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        for _ in range(max(1, retries + 1)):
            try:
                sock.sendto(packet, (host, port))
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError as exc:
                raise SNMPError(f"Erro de rede ao consultar {host}: {exc}") from exc

            error_status, varbinds = parse_response(data)
            if error_status != 0:
                raise SNMPError(
                    f"Agente retornou erro SNMP {error_status} para {oid}."
                )
            if not varbinds:
                raise SNMPError("Resposta SNMP sem varbinds.")
            _, value = varbinds[0]
            if value is None:
                raise SNMPError(f"OID nao suportado pela impressora: {oid}.")
            if not isinstance(value, int):
                raise SNMPError(f"Valor nao numerico retornado para {oid}.")
            return value

    raise SNMPTimeout(f"Sem resposta de {host}:{port} para {oid}.")


class SNMPBackend:
    """Backend real: le o contador total via SNMP.

    Segue a mesma interface de ``collector.CounterBackend``, podendo substituir o
    backend mockado sem alterar o restante do codigo. Tenta os OIDs candidatos em
    ordem e levanta ``SNMPError`` se nenhum responder.
    """

    def __init__(self, config: Config, oids: tuple[str, ...] = COMMON_TOTAL_COUNTER_OIDS):
        self.config = config
        self.oids = oids

    def read_total_counter(self, printer: Printer) -> int:
        last_error: Exception | None = None
        for oid in self.oids:
            try:
                return snmp_get(
                    printer.ip,
                    oid,
                    community=self.config.snmp_community,
                    port=self.config.snmp_port,
                    timeout=self.config.snmp_timeout,
                    retries=self.config.snmp_retries,
                    version="2c",
                )
            except SNMPError as exc:
                last_error = exc
        raise SNMPError(
            f"Falha ao ler contador de {printer.ip}: {last_error}"
        )
