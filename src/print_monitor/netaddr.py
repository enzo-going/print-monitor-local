"""Normalizacao tolerante de enderecos IP e faixas de rede.

Quem cadastra impressoras costuma copiar o IP de uma etiqueta, de um e-mail ou
do painel do equipamento. No caminho aparecem erros previsiveis: espacos
sobrando, virgula no lugar do ponto, a letra ``O`` no lugar do zero, ``http://``
colado na frente, a porta ``:9100`` no fim, zeros a esquerda.

Este modulo concentra a limpeza dessas entradas para que a interface aceite o
que o usuario quis dizer, e recuse com uma mensagem clara (em portugues, dizendo
o que corrigir) apenas o que realmente nao da para interpretar.

Nada aqui toca a rede nem o banco: sao funcoes puras, faceis de testar.
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata

# Espacos e marcas invisiveis que vem junto ao colar de PDFs, Word e paginas
# web. Declarados por codigo porque, escritos literalmente, sao indistinguiveis
# de um espaco comum no editor - que e exatamente o problema que causam.
_INVISIBLE = dict.fromkeys(
    (
        0x00A0,  # NO-BREAK SPACE
        0x2007,  # FIGURE SPACE
        0x200B,  # ZERO WIDTH SPACE
        0x200C,  # ZERO WIDTH NON-JOINER
        0x200D,  # ZERO WIDTH JOINER
        0x202F,  # NARROW NO-BREAK SPACE
        0x2060,  # WORD JOINER
        0xFEFF,  # ZERO WIDTH NO-BREAK SPACE (BOM)
    ),
    " ",
)

# Trocas usadas apenas quando o trecho ja parece um numero: sao os erros
# classicos de leitura de etiqueta (letra O/zero, letra l ou I/um).
_LOOKALIKE = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1"})

_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


class IPError(ValueError):
    """Endereco IP que nao pode ser interpretado, com mensagem para o usuario."""


def _pre_clean(text: str, drop_path: bool = True) -> str:
    """Remove ruido comum de copiar e colar, sem ainda interpretar o valor.

    ``drop_path=False`` preserva o que vem depois da barra — usado por
    :func:`normalize_network`, onde a barra e o prefixo CIDR, nao um caminho.
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_INVISIBLE).strip()
    text = _SCHEME.sub("", text)  # http://192.168.0.50 -> 192.168.0.50
    text = text.strip().strip("<>[]()\"'")
    if drop_path:
        text = text.split("/")[0]  # 192.168.0.50/ipp -> 192.168.0.50
    return text.strip()


def _strip_port(text: str) -> str:
    """Remove a porta de ``192.168.0.50:9100``.

    So e chamada depois de os separadores ja terem virado pontos, para que
    ``192,168,0,50:9100`` tambem seja reconhecido.
    """
    if text.count(":") == 1 and "." in text:
        host, _, port = text.partition(":")
        if port.isdigit():
            return host
    return text


def normalize_ip(value: str) -> str:
    """Interpreta o que o usuario digitou e devolve um IP valido normalizado.

    Corrige separadores trocados, letras parecidas com digitos e zeros a
    esquerda. Levanta ``IPError`` com uma mensagem explicativa quando a entrada
    nao permite adivinhar o endereco pretendido.

    >>> normalize_ip(" 192,168,O20,05 ")
    '192.168.20.5'
    >>> normalize_ip("http://192.168.0.50:9100")
    '192.168.0.50'
    """
    original = (value or "").strip()
    text = _pre_clean(value)

    if not text:
        raise IPError("Informe o endereço IP da impressora (exemplo: 192.168.0.50).")

    # IPv6 passa direto: nao sofre dos erros de digitacao tratados aqui. Dois ou
    # mais ":" so aparecem em IPv6 — um IPv4 com porta tem exatamente um.
    if text.count(":") >= 2:
        try:
            return str(ipaddress.ip_address(text))
        except ValueError:
            raise IPError(f"Endereço IPv6 inválido: “{original}”.") from None

    # Separadores alternativos que aparecem no lugar do ponto. Acontece antes de
    # remover a porta para que "192,168,0,50:9100" tambem seja reconhecido.
    text = re.sub(r"[,;\s_\-]+", ".", text)
    text = _strip_port(text)
    text = re.sub(r"\.{2,}", ".", text).strip(".")

    parts = text.split(".")
    if len(parts) != 4:
        if len(parts) < 4:
            faltam = 4 - len(parts)
            raise IPError(
                f"O endereço “{original}” está incompleto: falta{'m' if faltam > 1 else ''} "
                f"{faltam} número{'s' if faltam > 1 else ''}. "
                "Um IP tem quatro números separados por ponto, como 192.168.0.50."
            )
        raise IPError(
            f"O endereço “{original}” tem números demais. "
            "Um IP tem quatro números separados por ponto, como 192.168.0.50."
        )

    octets: list[int] = []
    for part in parts:
        cleaned = part.translate(_LOOKALIKE) if not part.isdigit() else part
        if not cleaned.isdigit():
            raise IPError(
                f"O trecho “{part}” do endereço “{original}” não é um número. "
                "Um IP só tem números e pontos, como 192.168.0.50."
            )
        number = int(cleaned)  # int() ja descarta zeros a esquerda
        if number > 255:
            raise IPError(
                f"O número {number} no endereço “{original}” é maior que 255. "
                "Cada parte de um IP vai de 0 a 255."
            )
        octets.append(number)

    return ".".join(str(o) for o in octets)


def is_valid_ip(value: str) -> bool:
    """Versao booleana de :func:`normalize_ip`, para validacoes rapidas."""
    try:
        normalize_ip(value)
    except IPError:
        return False
    return True


# ---------------------------------------------------------------------------
# Faixas de rede
# ---------------------------------------------------------------------------

_RANGE_DASH = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})\s*-\s*(\d{1,3}(?:\.\d{1,3}){0,3})$")


def normalize_network(value: str) -> str:
    """Converte uma faixa escrita de forma livre para CIDR.

    Aceita, alem do CIDR classico, as formas que as pessoas realmente digitam:

    - ``192.168.20``          -> ``192.168.20.0/24``
    - ``192.168.20.*``        -> ``192.168.20.0/24``
    - ``192.168.20.0``        -> ``192.168.20.0/24``
    - ``192.168.20.1-254``    -> ``192.168.20.0/24``
    - ``192.168.20.35``       -> ``192.168.20.0/24`` (rede do host informado)

    Levanta ``IPError`` com mensagem explicativa quando nao da para interpretar.
    """
    original = (value or "").strip()
    # A barra aqui e o prefixo CIDR, nao um caminho: precisa ser preservada.
    text = _pre_clean(value, drop_path=False).replace(",", ".")
    text = re.sub(r"\s+", "", text)

    if not text:
        raise IPError(
            "Informe a faixa de rede a procurar (exemplo: 192.168.0.0/24)."
        )

    # Faixa com hifen: usa a rede /24 que contem o endereco inicial.
    match = _RANGE_DASH.match(text)
    if match:
        text = match.group(1)

    # Curinga: 192.168.20.* / 192.168.20.x
    text = re.sub(r"\.[*xX]+$", "", text)

    if "/" in text:
        addr, _, prefix = text.partition("/")
        if not prefix.isdigit():
            raise IPError(
                f"A faixa “{original}” tem um prefixo inválido. "
                "Use algo como 192.168.0.0/24."
            )
        try:
            addr = normalize_ip(addr)
        except IPError as exc:
            raise IPError(str(exc)) from None
        try:
            return str(ipaddress.ip_network(f"{addr}/{prefix}", strict=False))
        except ValueError:
            raise IPError(
                f"A faixa “{original}” não é válida. Use algo como 192.168.0.0/24."
            ) from None

    dots = text.count(".")
    if dots == 2:  # 192.168.20 -> completa o ultimo octeto
        text = f"{text}.0"
    elif dots == 1:  # 192.168 -> faixa /16 e grande demais para varrer as cegas
        raise IPError(
            f"A faixa “{original}” é ampla demais. Informe também o terceiro "
            "número, como 192.168.0 ou 192.168.0.0/24."
        )
    elif dots != 3:
        raise IPError(
            f"Não entendi a faixa “{original}”. Use algo como 192.168.0.0/24 "
            "ou apenas 192.168.0."
        )

    addr = normalize_ip(text)
    return str(ipaddress.ip_network(f"{addr}/24", strict=False))


def network_label(cidr: str) -> str:
    """Descricao curta de uma faixa: ``192.168.0.0/24 (254 endereços)``."""
    net = ipaddress.ip_network(cidr, strict=False)
    total = net.num_addresses - 2 if net.prefixlen < net.max_prefixlen - 1 else net.num_addresses
    return f"{net} ({total} endereços)"


def local_networks() -> list[str]:
    """Descobre as faixas /24 das interfaces de rede ativas da maquina.

    Serve para pre-preencher a tela de descoberta: na esmagadora maioria das
    instalacoes a impressora esta na mesma rede do computador, e pedir um CIDR
    para quem nunca ouviu falar em CIDR e o principal obstaculo dessa tela.

    Nao depende de bibliotecas externas: usa a rota padrao (UDP sem envio) e,
    como complemento, os enderecos resolvidos pelo hostname.
    """
    import socket

    candidates: list[str] = []

    def add(ip: str) -> None:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return
        if addr.version != 4 or addr.is_loopback or addr.is_link_local:
            return
        cidr = str(ipaddress.ip_network(f"{ip}/24", strict=False))
        if cidr not in candidates:
            candidates.append(cidr)

    # IP usado para sair pela rota padrao (nao envia pacote algum).
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.2)
            sock.connect(("10.255.255.255", 1))
            add(sock.getsockname()[0])
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except OSError:
        pass

    return candidates
