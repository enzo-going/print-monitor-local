"""Descoberta de impressoras na rede (abordagem segura e controlada).

A descoberta procura hosts que aceitam conexao TCP em portas tipicas de
impressao (RAW/JetDirect 9100, IPP 631, LPD 515). Para evitar varredura
agressiva, a abordagem e deliberadamente conservadora:

- exige uma faixa CIDR explicita (sem varrer redes inteiras por padrao);
- recusa faixas maiores que ``max_hosts`` (guarda contra /16, /8 etc.);
- usa timeouts curtos e concorrencia limitada;
- verifica apenas um pequeno conjunto de portas;
- opcionalmente confirma via SNMP lendo o contador total.

Execute apenas em redes que voce esta autorizado a inspecionar. Ver riscos em
``docs/descoberta-rede.md``.
"""

from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .config import Config

# Portas TCP tipicas de impressao.
DEFAULT_PRINTER_PORTS = (9100, 631, 515)


@dataclass
class DiscoveredHost:
    """Host candidato a impressora encontrado na rede."""

    ip: str
    open_ports: list[int] = field(default_factory=list)
    snmp_counter: int | None = None


def host_count(cidr: str) -> int:
    """Numero de hosts utilizaveis em uma faixa, sem materializar a lista."""
    net = ipaddress.ip_network(cidr, strict=False)
    if net.prefixlen >= net.max_prefixlen - 1:  # /31, /32 (e equivalentes IPv6)
        return net.num_addresses
    return net.num_addresses - 2


def iter_hosts(cidr: str):
    """Itera os enderecos de host utilizaveis de uma faixa CIDR."""
    net = ipaddress.ip_network(cidr, strict=False)
    yield from (str(h) for h in net.hosts())


def tcp_port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    """Retorna True se for possivel abrir conexao TCP no host/porta."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _try_snmp_counter(ip: str, config: Config | None) -> int | None:
    from .snmp import OID_PRT_MARKER_LIFE_COUNT, SNMPError, snmp_get

    community = config.snmp_community if config else "public"
    port = config.snmp_port if config else 161
    timeout = config.snmp_timeout if config else 2
    try:
        return snmp_get(
            ip,
            OID_PRT_MARKER_LIFE_COUNT,
            community=community,
            port=port,
            timeout=timeout,
            retries=0,
        )
    except SNMPError:
        return None


def discover(
    cidr: str,
    ports: tuple[int, ...] = DEFAULT_PRINTER_PORTS,
    timeout: float = 0.3,
    workers: int = 32,
    max_hosts: int = 1024,
    snmp_confirm: bool = False,
    config: Config | None = None,
) -> list[DiscoveredHost]:
    """Descobre hosts com portas de impressao abertas em uma faixa CIDR.

    Levanta ``ValueError`` se a faixa exceder ``max_hosts`` (protecao contra
    varredura ampla demais). A ordem do resultado e crescente por endereco.
    """
    count = host_count(cidr)
    if count > max_hosts:
        raise ValueError(
            f"Faixa muito grande ({count} hosts > limite {max_hosts}). "
            "Reduza a faixa ou aumente max_hosts de forma consciente."
        )

    hosts = list(iter_hosts(cidr))

    def probe(ip: str) -> DiscoveredHost | None:
        open_ports = [p for p in ports if tcp_port_open(ip, p, timeout)]
        if not open_ports:
            return None
        counter = _try_snmp_counter(ip, config) if snmp_confirm else None
        return DiscoveredHost(ip=ip, open_ports=open_ports, snmp_counter=counter)

    results: list[DiscoveredHost] = []
    if hosts:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            for found in executor.map(probe, hosts):
                if found is not None:
                    results.append(found)

    results.sort(key=lambda d: ipaddress.ip_address(d.ip))
    return results
