"""Padrões de data (4F.1): formatos, normalização ISO, offsets no original e reconferência."""

from datetime import date

import pytest

from lupa.ingestao.datas import (
    construir_data,
    encontrar_datas,
    escrever_por_extenso,
    numero_por_extenso,
    reconferir,
)

FORMATOS = [
    ("em 15/05/2014.", "15/05/2014", "2014-05-15", "numerico"),
    ("em 5/5/2014", "5/5/2014", "2014-05-05", "numerico"),
    ("em 15.05.2014", "15.05.2014", "2014-05-15", "numerico"),
    ("em 15-05-2014", "15-05-2014", "2014-05-15", "numerico"),
    ("em 29/ 10/2018, que", "29/ 10/2018", "2018-10-29", "numerico"),
    ("em 15/05/14", "15/05/14", "2014-05-15", "numerico"),
    ("nascido em 02/04/85", "02/04/85", "1985-04-02", "numerico"),
    ("Vila Esperança, 15 de maio de 2014.", "15 de maio de 2014", "2014-05-15", "extenso"),
    ("em 1º de março de 2016", "1º de março de 2016", "2016-03-01", "extenso"),
    ("em 1o de março de 2016", "1o de março de 2016", "2016-03-01", "extenso"),
    ("em 17 DE MARÇO DE 2016", "17 DE MARÇO DE 2016", "2016-03-17", "extenso"),
    (
        "aos quinze de maio de dois mil e catorze",
        "quinze de maio de dois mil e catorze",
        "2014-05-15",
        "extenso",
    ),
    (
        "em primeiro de janeiro de dois mil",
        "primeiro de janeiro de dois mil",
        "2000-01-01",
        "extenso",
    ),
    (
        "vinte e cinco de dezembro de mil novecentos e oitenta e cinco",
        "vinte e cinco de dezembro de mil novecentos e oitenta e cinco",
        "1985-12-25",
        "extenso",
    ),
    (
        "em 15 de maio de dois mil e quatorze",
        "15 de maio de dois mil e quatorze",
        "2014-05-15",
        "extenso",
    ),
    ("em 15/mai/2014", "15/mai/2014", "2014-05-15", "abreviado"),
    ("em 15-mai-2014", "15-mai-2014", "2014-05-15", "abreviado"),
    ("em 15 mai. 2014", "15 mai. 2014", "2014-05-15", "abreviado"),
    ("em 15 mai 2014", "15 mai 2014", "2014-05-15", "abreviado"),
    ("em 15 de mai. de 2014", "15 de mai. de 2014", "2014-05-15", "abreviado"),
    ("em 3/dez/2019", "3/dez/2019", "2019-12-03", "abreviado"),
    ("quinta-feira, 15 de maio de 2014", "15 de maio de 2014", "2014-05-15", "extenso"),
    ("segunda-feira, 12/05/2014", "12/05/2014", "2014-05-12", "numerico"),
    ("sábado, 17 mai. 2014", "17 mai. 2014", "2014-05-17", "abreviado"),
]


@pytest.mark.parametrize(("texto", "literal", "iso", "formato"), FORMATOS)
def test_reconhece_formato_e_normaliza_para_iso_com_offsets(
    texto: str, literal: str, iso: str, formato: str
) -> None:
    """Cada formato da suíte é reconhecido, com literal e offsets exatos no original."""
    ocorrencias = encontrar_datas(texto)
    assert len(ocorrencias) == 1
    unica = ocorrencias[0]
    assert (unica.iso, unica.literal, unica.formato) == (iso, literal, formato)
    assert texto[unica.inicio : unica.fim] == literal
    assert reconferir(literal, unica.data)


def test_suite_de_formatos_tem_cem_por_cento_de_acerto() -> None:
    """Todos os casos da suíte acertam data, literal e formato."""
    acertos = 0
    for texto, literal, iso, formato in FORMATOS:
        achadas = encontrar_datas(texto)
        if [(o.iso, o.literal, o.formato) for o in achadas] == [(iso, literal, formato)]:
            acertos += 1
    assert acertos == len(FORMATOS)


@pytest.mark.parametrize(
    "texto",
    [
        "em 31/02/2014",
        "em 30/02/2020",
        "em 29/02/2015",
        "em 32/01/2014",
        "em 15/13/2014",
        "em 00/05/2014",
        "em 31 de abril de 2014",
        "em 31/abr/2014",
        "em 15/05/1850",
        "trinta e um de fevereiro de dois mil e catorze",
    ],
)
def test_rejeita_data_impossivel(texto: str) -> None:
    """31/02, 29/02 fora de ano bissexto, mês 13 e anos fora da faixa não viram data."""
    assert encontrar_datas(texto) == []


def test_aceita_29_de_fevereiro_em_ano_bissexto() -> None:
    """29/02/2016 existe."""
    assert [o.iso for o in encontrar_datas("em 29/02/2016")] == ["2016-02-29"]


def test_ano_de_dois_digitos_usa_pivo_e_fica_marcado() -> None:
    """Abaixo do pivô vira 20xx; acima, 19xx; as duas ocorrências saem marcadas."""
    recentes, antigas = encontrar_datas("em 15/05/14 e em 15/05/85")
    assert (recentes.iso, recentes.ano_dois_digitos) == ("2014-05-15", True)
    assert (antigas.iso, antigas.ano_dois_digitos) == ("1985-05-15", True)
    assert not encontrar_datas("em 15/05/2014")[0].ano_dois_digitos


def test_offsets_apontam_para_o_texto_original_mesmo_com_normalizacao() -> None:
    """Com dígitos de largura total e invisíveis, literal e offsets são os do original."""
    largura_total = "\N{FULLWIDTH DIGIT ONE}\N{FULLWIDTH DIGIT FIVE}/05/2014"
    texto = f"Data:\N{ZERO WIDTH SPACE} {largura_total} e de\N{SOFT HYPHEN}pois 16/05/2014"
    primeira, segunda = encontrar_datas(texto)
    assert primeira.iso == "2014-05-15"
    assert texto[primeira.inicio : primeira.fim] == largura_total
    assert texto[segunda.inicio : segunda.fim] == "16/05/2014"


def test_ignora_numero_de_processo_cpf_e_hora() -> None:
    """Número CNJ, CPF e horário não são datas."""
    texto = "Processo 9923884-34.2014.8.99.0008, CPF 123.456.789-00, às 10.30 horas"
    assert encontrar_datas(texto) == []


def test_varias_datas_em_ordem_sem_sobreposicao() -> None:
    """Datas em formatos diferentes no mesmo texto saem em ordem de posição."""
    texto = "Fato em 28/04/2014; denúncia em 8 de julho de 2014; recebida em 08.08.2014."
    assert [o.iso for o in encontrar_datas(texto)] == ["2014-04-28", "2014-07-08", "2014-08-08"]


def test_reconferir_exige_a_data_literal_no_trecho() -> None:
    """A reconferência escreve a data em todas as formas e procura no trecho."""
    assert reconferir("mantenho a prisão preventiva em 07/10/2014", date(2014, 10, 7))
    assert reconferir("em 7 de outubro de 2014", date(2014, 10, 7))
    assert reconferir("aos sete de outubro de dois mil e quatorze", date(2014, 10, 7))
    assert reconferir("em 07.10.14", date(2014, 10, 7))
    assert not reconferir("mantenho a prisão preventiva em 07/10/2014", date(2014, 10, 8))
    assert not reconferir("em 17/10/2014", date(2014, 10, 7))
    assert not reconferir("protocolo 107/10/20145", date(2014, 10, 7))


def test_numeros_por_extenso_ida_e_volta() -> None:
    """Escrita e leitura por extenso concordam de 1 a 2100."""
    for numero in range(1, 2101):
        assert numero_por_extenso(escrever_por_extenso(numero)) == numero
    assert escrever_por_extenso(2014) == "dois mil e catorze"
    assert escrever_por_extenso(1985) == "mil novecentos e oitenta e cinco"
    assert numero_por_extenso("dois mil e banana") is None


def test_construir_data_recusa_fora_da_faixa() -> None:
    """Anos antes de 1900 ou depois de 2100 não são aceitos."""
    assert construir_data(1899, 1, 1) is None
    assert construir_data(2101, 1, 1) is None
    assert construir_data(2000, 2, 29) == date(2000, 2, 29)
