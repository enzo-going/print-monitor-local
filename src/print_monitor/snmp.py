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
import time
from dataclasses import dataclass

from .config import Config
from .models import Printer

# OID padrao Printer-MIB para contador total (prtMarkerLifeCount, marcador 1).
OID_PRT_MARKER_LIFE_COUNT = "1.3.6.1.2.1.43.10.2.1.4.1.1"

# Identificacao (MIB-II e Printer-MIB), usada para nomear o equipamento.
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_SYS_LOCATION = "1.3.6.1.2.1.1.6.0"
OID_PRT_SERIAL = "1.3.6.1.2.1.43.5.1.1.17.1"
OID_HR_DEVICE_DESCR = "1.3.6.1.2.1.25.3.2.1.3.1"

# Alternativas proprietarias, tentadas SOMENTE quando o OID padrao responde que
# nao suporta. Varios equipamentos de entrada nao implementam a Printer-MIB
# completa, mas expoem o total em um ramo do proprio fabricante — sem estas
# tentativas eles ficavam permanentemente sem contador, mesmo acessiveis.
VENDOR_TOTAL_COUNTER_OIDS: tuple[tuple[str, str], ...] = (
    ("Printer-MIB (marcador 2)", "1.3.6.1.2.1.43.10.2.1.4.1.2"),
    ("HP", "1.3.6.1.4.1.11.2.3.9.4.2.1.4.1.2.5.0"),
    ("Ricoh", "1.3.6.1.4.1.367.3.2.1.2.19.5.1.9.1"),
    ("Kyocera", "1.3.6.1.4.1.1347.42.2.1.1.1.6.1.1"),
    ("Brother", "1.3.6.1.4.1.2435.2.3.9.4.2.1.5.4.5.1.0"),
    ("Samsung/HP", "1.3.6.1.4.1.236.11.5.1.1.1.1.0"),
    ("Lexmark", "1.3.6.1.4.1.641.2.1.5.1.9.1"),
    ("Xerox", "1.3.6.1.4.1.253.8.53.13.2.1.6.1.20.1"),
    ("Epson", "1.3.6.1.4.1.1248.1.2.2.27.1.1.5.1.1"),
)

# OIDs candidatos para o total, tentados em ordem: padrao primeiro.
COMMON_TOTAL_COUNTER_OIDS: tuple[str, ...] = (
    OID_PRT_MARKER_LIFE_COUNT,
    *(oid for _, oid in VENDOR_TOTAL_COUNTER_OIDS),
)

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
    try:
        parts = [int(p) for p in oid.strip().split(".") if p != ""]
    except ValueError as exc:
        raise ValueError(f"OID invalido: {oid!r}") from exc
    if len(parts) < 2:
        raise ValueError(f"OID invalido: {oid!r}")
    if parts[0] not in (0, 1, 2) or parts[1] < 0:
        raise ValueError(f"OID invalido: {oid!r}")
    if parts[0] < 2 and parts[1] > 39:
        raise ValueError(f"OID invalido: {oid!r}")
    if any(part < 0 for part in parts[2:]):
        raise ValueError(f"OID invalido: {oid!r}")
    body = bytearray([40 * parts[0] + parts[1]])
    for sub in parts[2:]:
        body += _encode_base128(sub)
    return _tlv(_TAG_OID, bytes(body))


def _version_code(version: str) -> int:
    normalized = str(version).strip().lower()
    if normalized == "1":
        return 0
    if normalized == "2c":
        return 1
    raise ValueError(f"Versao SNMP invalida: {version!r}. Use '1' ou '2c'.")


def build_get_request(community: str, oid: str, request_id: int, version: str = "2c") -> bytes:
    """Monta uma mensagem SNMP GET para um unico OID."""
    varbind = _tlv(_TAG_SEQUENCE, _encode_oid(oid) + _encode_null())
    varbind_list = _tlv(_TAG_SEQUENCE, varbind)
    pdu_body = _encode_integer(request_id) + _encode_integer(0) + _encode_integer(0) + varbind_list
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
    if idx >= len(data):
        raise SNMPError("Mensagem SNMP truncada ao ler comprimento BER.")
    first = data[idx]
    idx += 1
    if first < 0x80:
        return first, idx
    num = first & 0x7F
    if num == 0:
        raise SNMPError("Comprimento BER indefinido nao e suportado.")
    if num > 8 or idx + num > len(data):
        raise SNMPError("Comprimento BER invalido ou truncado.")
    length = int.from_bytes(data[idx : idx + num], "big")
    return length, idx + num


def _read_tlv(data: bytes, idx: int) -> tuple[int, bytes, int]:
    if idx >= len(data):
        raise SNMPError("Mensagem SNMP truncada ao ler campo BER.")
    tag = data[idx]
    length, idx = _decode_length(data, idx + 1)
    end = idx + length
    if end > len(data):
        raise SNMPError("Campo BER excede o tamanho da mensagem SNMP.")
    value = data[idx:end]
    return tag, value, end


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


def parse_response(data: bytes) -> tuple[int, int, list[tuple[str, object]]]:
    """Decodifica uma resposta SNMP em (request_id, error_status, varbinds)."""
    tag, message, _ = _read_tlv(data, 0)
    if tag != _TAG_SEQUENCE:
        raise SNMPError("Mensagem SNMP invalida (sequencia esperada).")

    idx = 0
    _, _version, idx = _read_tlv(message, idx)
    _, _community, idx = _read_tlv(message, idx)
    pdu_tag, pdu, idx = _read_tlv(message, idx)
    if pdu_tag not in (_TAG_GET_REQUEST, _TAG_GET_RESPONSE):
        raise SNMPError("Tipo de PDU SNMP inesperado.")

    pidx = 0
    _, request_id_raw, pidx = _read_tlv(pdu, pidx)
    _, error_raw, pidx = _read_tlv(pdu, pidx)
    _, _error_index, pidx = _read_tlv(pdu, pidx)
    _, varbind_list, pidx = _read_tlv(pdu, pidx)
    request_id = int.from_bytes(request_id_raw, "big", signed=True)
    error_status = int.from_bytes(error_raw, "big", signed=True)

    varbinds: list[tuple[str, object]] = []
    vidx = 0
    while vidx < len(varbind_list):
        _, varbind, vidx = _read_tlv(varbind_list, vidx)
        oidx = 0
        _, oid_raw, oidx = _read_tlv(varbind, oidx)
        value_tag, value_raw, oidx = _read_tlv(varbind, oidx)
        varbinds.append((_decode_oid(oid_raw), _decode_varbind_value(value_tag, value_raw)))
    return request_id, error_status, varbinds


def build_get_response(
    community: str,
    oid: str,
    value: int | bytes,
    request_id: int = 1,
    error_status: int = 0,
    value_tag: int = _TAG_COUNTER32,
) -> bytes:
    """Monta uma resposta SNMP GET. Usado por testes e como referencia.

    ``value`` em ``bytes`` produz um OCTET STRING, permitindo simular os OIDs
    textuais de identificacao (nome, modelo, numero de serie).
    """
    if isinstance(value, bytes):
        value_bytes = _tlv(_TAG_OCTET, value)
    else:
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


def snmp_get_value(
    host: str,
    oid: str,
    community: str = "public",
    port: int = 161,
    timeout: float = 2.0,
    retries: int = 1,
    version: str = "2c",
) -> object:
    """Executa um SNMP GET e retorna o valor bruto do OID (int ou bytes).

    Levanta ``SNMPTimeout`` se nao houver resposta e ``SNMPError`` para demais
    falhas (erro do agente, OID nao suportado).
    """
    request_id = random.randint(1, 0x7FFFFFFF)
    packet = build_get_request(community, oid, request_id, version)

    try:
        address_infos = socket.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_DGRAM,
            proto=socket.IPPROTO_UDP,
        )
    except OSError as exc:
        raise SNMPError(f"Erro de rede ao resolver {host}: {exc}") from exc
    if not address_infos:
        raise SNMPError(f"Nenhum endereco UDP encontrado para {host}:{port}.")

    network_errors: list[OSError] = []
    endpoint_timed_out = False
    for family, socktype, proto, _canonical_name, sockaddr in address_infos:
        with socket.socket(family, socktype, proto) as sock:
            try:
                # UDP conectado restringe as respostas ao mesmo IP e porta de
                # destino e funciona tanto com endpoints IPv4 quanto IPv6.
                sock.connect(sockaddr)
            except OSError as exc:
                network_errors.append(exc)
                continue

            endpoint_failed = False
            for _ in range(max(1, retries + 1)):
                try:
                    sock.send(packet)
                except OSError as exc:
                    network_errors.append(exc)
                    endpoint_failed = True
                    break

                # Aguarda a resposta CORRETA: mesmo request-id. A conexao UDP
                # ja filtra datagramas de outra origem ou porta.
                deadline = time.monotonic() + timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    sock.settimeout(remaining)
                    try:
                        data = sock.recv(65535)
                    except TimeoutError:
                        break
                    except OSError as exc:
                        network_errors.append(exc)
                        endpoint_failed = True
                        break
                    try:
                        resp_id, error_status, varbinds = parse_response(data)
                    except (SNMPError, IndexError, ValueError):
                        continue  # pacote malformado/estranho
                    if resp_id != request_id:
                        continue  # resposta de uma consulta anterior

                    if error_status != 0:
                        raise SNMPError(f"Agente retornou erro SNMP {error_status} para {oid}.")
                    if not varbinds:
                        raise SNMPError("Resposta SNMP sem varbinds.")
                    response_oid, value = varbinds[0]
                    if response_oid != oid:
                        raise SNMPError(
                            f"Resposta SNMP retornou OID inesperado: {response_oid or '<vazio>'}."
                        )
                    if value is None:
                        raise SNMPError(f"OID nao suportado pela impressora: {oid}.")
                    return value
                if endpoint_failed:
                    break
            if not endpoint_failed:
                endpoint_timed_out = True

    if endpoint_timed_out:
        raise SNMPTimeout(f"Sem resposta de {host}:{port} para {oid}.")
    if network_errors:
        error = network_errors[-1]
        raise SNMPError(f"Erro de rede ao consultar {host}: {error}") from error
    raise SNMPTimeout(f"Sem resposta de {host}:{port} para {oid}.")


def snmp_get(
    host: str,
    oid: str,
    community: str = "public",
    port: int = 161,
    timeout: float = 2.0,
    retries: int = 1,
    version: str = "2c",
) -> int:
    """SNMP GET de um OID numerico (contadores)."""
    value = snmp_get_value(
        host,
        oid,
        community=community,
        port=port,
        timeout=timeout,
        retries=retries,
        version=version,
    )
    if not isinstance(value, int):
        raise SNMPError(f"Valor nao numerico retornado para {oid}.")
    return value


def snmp_get_text(
    host: str,
    oid: str,
    community: str = "public",
    port: int = 161,
    timeout: float = 2.0,
    retries: int = 0,
    version: str = "2c",
) -> str:
    """SNMP GET de um OID textual (nome, descricao, serie), ja decodificado."""
    value = snmp_get_value(
        host,
        oid,
        community=community,
        port=port,
        timeout=timeout,
        retries=retries,
        version=version,
    )
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    # Equipamentos costumam devolver descricoes com quebras de linha e padding.
    return " ".join(text.split()).strip("\x00 ")


# --------------------------------------------------------------------------
# Identificacao do equipamento
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PrinterIdentity:
    """Dados de identificacao lidos de um equipamento na rede."""

    ip: str
    name: str | None = None  # sysName — o nome dado pelo administrador
    description: str | None = None  # sysDescr — marca/modelo/firmware
    location: str | None = None  # sysLocation — setor, quando preenchido
    model: str | None = None
    serial: str | None = None
    counter: int | None = None

    @property
    def responded(self) -> bool:
        """Se o equipamento respondeu a qualquer uma das consultas."""
        return any([self.name, self.description, self.model, self.counter is not None])

    @property
    def suggested_name(self) -> str:
        """Melhor nome disponivel para cadastrar automaticamente."""
        for candidate in (self.name, self.model, self.description):
            if candidate and candidate.strip():
                # sysDescr costuma ser uma frase inteira; corta no essencial.
                return candidate.strip()[:60]
        return f"Impressora {self.ip}"


def _quiet_text(host: str, oid: str, **kwargs) -> str | None:
    """Le um OID textual devolvendo ``None`` em vez de levantar erro."""
    try:
        return snmp_get_text(host, oid, **kwargs) or None
    except SNMPError:
        return None


def identify(
    ip: str,
    community: str = "public",
    port: int = 161,
    timeout: float = 1.0,
    version: str = "2c",
    read_counter: bool = True,
) -> PrinterIdentity:
    """Le nome, modelo, serie e contador de um equipamento, sem levantar erro.

    Cada campo ausente vira ``None``: o objetivo e enriquecer o cadastro com o
    que o equipamento oferecer, nunca falhar por causa de um OID que determinado
    modelo nao implementa. E o que permite a descoberta cadastrar
    "RICOH IM C3000 - Recepcao" em vez de "Impressora 192.168.20.31".
    """
    kwargs = {
        "community": community,
        "port": port,
        "timeout": timeout,
        "retries": 0,
        "version": version,
    }
    description = _quiet_text(ip, OID_SYS_DESCR, **kwargs)
    model = _quiet_text(ip, OID_HR_DEVICE_DESCR, **kwargs)
    counter = None
    if read_counter:
        try:
            counter = read_total_counter(
                ip,
                community=community,
                port=port,
                timeout=timeout,
                retries=0,
                version=version,
            )[0]
        except SNMPError:
            counter = None
    return PrinterIdentity(
        ip=ip,
        name=_quiet_text(ip, OID_SYS_NAME, **kwargs),
        description=description,
        location=_quiet_text(ip, OID_SYS_LOCATION, **kwargs),
        model=model or description,
        serial=_quiet_text(ip, OID_PRT_SERIAL, **kwargs),
        counter=counter,
    )


# --------------------------------------------------------------------------
# Leitura do contador
# --------------------------------------------------------------------------


def read_total_counter(
    ip: str,
    community: str = "public",
    port: int = 161,
    timeout: float = 2.0,
    retries: int = 1,
    version: str = "2c",
    oids: tuple[str, ...] = COMMON_TOTAL_COUNTER_OIDS,
) -> tuple[int, str]:
    """Le o contador total tentando os OIDs conhecidos em ordem.

    Retorna ``(contador, oid_usado)`` e levanta ``SNMPError`` com uma mensagem
    voltada ao usuario quando nenhum responde — distinguindo "o equipamento nao
    respondeu" de "respondeu, mas nao expoe o contador", porque a acao corretiva
    e diferente em cada caso.
    """
    unreachable = False
    last_error: Exception | None = None
    # Palpites de fabricante nao merecem a espera inteira: um agente real apenas
    # ignora o OID que nao conhece, entao cada tentativa custaria um timeout.
    vendor_timeout = min(timeout, 1.0)
    for index, oid in enumerate(oids):
        is_standard = index == 0
        try:
            value = snmp_get(
                ip,
                oid,
                community=community,
                port=port,
                timeout=timeout if is_standard else vendor_timeout,
                # Apenas o OID padrao merece as tentativas extras configuradas.
                retries=retries if is_standard else 0,
                version=version,
            )
        except SNMPTimeout as exc:
            last_error = exc
            if is_standard:
                # Se nem o OID padrao respondeu, o equipamento esta inacessivel
                # ou com SNMP desligado: percorrer o resto so faria esperar.
                unreachable = True
                break
            # Silencio em um OID de fabricante significa "nao implementado";
            # continuar e o proposito da lista.
        except SNMPError as exc:
            last_error = exc
        else:
            if value >= 0:
                return value, oid

    if unreachable:
        raise SNMPTimeout(
            f"{ip} nao respondeu ao SNMP. Verifique se o equipamento esta ligado, "
            "se o SNMP esta habilitado no painel dele e se a comunidade de "
            "leitura confere (normalmente “public”)."
        )
    raise SNMPError(
        f"{ip} respondeu, mas nao informou o contador de paginas em nenhum dos "
        f"OIDs conhecidos. Ultimo erro: {last_error}"
    )


class SNMPBackend:
    """Backend real: le o contador total via SNMP.

    Segue a mesma interface de ``collector.CounterBackend``, podendo substituir o
    backend mockado sem alterar o restante do codigo.
    """

    def __init__(self, config: Config, oids: tuple[str, ...] = COMMON_TOTAL_COUNTER_OIDS):
        self.config = config
        self.oids = oids

    def read_total_counter(self, printer: Printer) -> int:
        counter, _oid = read_total_counter(
            printer.ip,
            community=self.config.snmp_community,
            port=self.config.snmp_port,
            timeout=self.config.snmp_timeout,
            retries=self.config.snmp_retries,
            version=self.config.snmp_version,
            oids=self.oids,
        )
        return counter
