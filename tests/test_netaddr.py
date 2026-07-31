"""Testes da normalizacao tolerante de IPs e faixas de rede.

Cada caso aqui corresponde a um erro de digitacao que aparece de verdade quando
alguem copia o IP de uma etiqueta, de um e-mail ou do painel do equipamento.
"""

from __future__ import annotations

import pytest

from print_monitor.netaddr import (
    IPError,
    is_valid_ip,
    normalize_ip,
    normalize_network,
)


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("192.168.0.10", "192.168.0.10"),
        ("  192.168.0.10  ", "192.168.0.10"),          # espacos ao colar
        ("192,168,0,10", "192.168.0.10"),              # virgula no lugar do ponto
        ("192.168.0.010", "192.168.0.10"),             # zero a esquerda
        ("192.168.020.005", "192.168.20.5"),
        ("http://192.168.0.10", "192.168.0.10"),       # copiado do navegador
        ("https://192.168.0.10/ipp/print", "192.168.0.10"),
        ("192.168.0.10:9100", "192.168.0.10"),         # porta colada no fim
        ("192.168.O.1O", "192.168.0.10"),              # letra O no lugar do zero
        ("l92.l68.0.10", "192.168.0.10"),              # letra l no lugar do um
        ("192 168 0 10", "192.168.0.10"),              # espaco como separador
        ("192.168..0.10", "192.168.0.10"),             # ponto duplicado
        ("<192.168.0.10>", "192.168.0.10"),            # colado de um e-mail
    ],
)
def test_normaliza_erros_comuns(entrada, esperado):
    assert normalize_ip(entrada) == esperado


def test_ipv6_passa_intacto():
    assert normalize_ip("2001:db8::1") == "2001:db8::1"


@pytest.mark.parametrize("entrada", ["", "   ", None])
def test_vazio_pede_o_endereco(entrada):
    with pytest.raises(IPError, match="Informe o endereço"):
        normalize_ip(entrada)


def test_incompleto_diz_quantos_numeros_faltam():
    with pytest.raises(IPError, match="falta 1 número"):
        normalize_ip("192.168.0")


def test_numeros_demais():
    with pytest.raises(IPError, match="números demais"):
        normalize_ip("192.168.0.10.5")


def test_octeto_acima_de_255_explica_o_limite():
    with pytest.raises(IPError, match="maior que 255"):
        normalize_ip("192.168.0.300")


def test_texto_nao_numerico_aponta_o_trecho():
    with pytest.raises(IPError, match="impressora"):
        normalize_ip("192.168.impressora.1")


def test_is_valid_ip():
    assert is_valid_ip("10.0.0.1")
    assert not is_valid_ip("10.0.0.999")


# -- faixas de rede -------------------------------------------------------


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("192.168.0.0/24", "192.168.0.0/24"),
        ("192.168.0", "192.168.0.0/24"),          # sem o ultimo numero
        ("192.168.0.*", "192.168.0.0/24"),        # curinga
        ("192.168.0.x", "192.168.0.0/24"),
        ("192.168.0.1-254", "192.168.0.0/24"),    # faixa com hifen
        ("192.168.0.35", "192.168.0.0/24"),       # um host: usa a rede dele
        ("10.0.0.0/16", "10.0.0.0/16"),
        ("  192.168.0.0 / 24  ", "192.168.0.0/24"),
    ],
)
def test_normaliza_faixas_escritas_de_forma_livre(entrada, esperado):
    assert normalize_network(entrada) == esperado


def test_faixa_vazia_pede_valor():
    with pytest.raises(IPError, match="Informe a faixa"):
        normalize_network("")


def test_faixa_ampla_demais_orienta_o_usuario():
    with pytest.raises(IPError, match="ampla demais"):
        normalize_network("192.168")
