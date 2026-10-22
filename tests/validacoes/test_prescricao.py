"""Testes da validação de prescrição pela pena em abstrato (datas sintéticas)."""

from datetime import date

import pytest

from lupa.dominio.esquemas import Fato
from lupa.validacoes.criminal import prescricao
from lupa.validacoes.dados import prescricao_padrao
from lupa.validacoes.modelo import AchadoValidacao
from tests.validacoes.conftest import criar_fato, modelo_de

REFERENCIA = date(2035, 1, 10)


def _executar(pena: int, *fatos: Fato, referencia: date = REFERENCIA) -> AchadoValidacao:
    modelo = modelo_de(criar_fato("pena_maxima_abstrata", pena), *fatos)
    return prescricao.executar(modelo, referencia)


@pytest.mark.parametrize(
    ("pena", "inciso", "anos"),
    [
        (145, "I", 20),
        (144, "II", 16),
        (97, "II", 16),
        (96, "III", 12),
        (49, "III", 12),
        (48, "IV", 8),
        (25, "IV", 8),
        (24, "V", 4),
        (12, "V", 4),
        (11, "VI", 3),
        (1, "VI", 3),
    ],
)
def test_cada_faixa_do_art_109_nas_bordas(pena: int, inciso: str, anos: int) -> None:
    """Cada faixa do art 109 nas bordas."""
    faixa = prescricao_padrao().faixa_para(pena)
    assert (faixa.inciso, faixa.prazo_anos) == (inciso, anos)


def test_intervalo_exatamente_igual_ao_prazo_nao_e_prescricao() -> None:
    """Intervalo exatamente igual ao prazo nao e prescricao."""
    achado = _executar(
        11,
        criar_fato("data_fato", "2030-01-10"),
        criar_fato("data_recebimento_denuncia", "2033-01-10"),
        referencia=date(2033, 2, 1),
    )
    assert achado.resultado == "conforme"
    assert achado.valores["intervalos"][0]["limite"] == "2033-01-10"


def test_intervalo_um_dia_acima_do_prazo_gera_atencao() -> None:
    """Intervalo um dia acima do prazo gera atencao."""
    achado = _executar(
        11,
        criar_fato("data_fato", "2030-01-10"),
        criar_fato("data_recebimento_denuncia", "2033-01-11"),
        referencia=date(2033, 2, 1),
    )
    assert achado.resultado == "atencao"
    assert achado.valores["intervalos"][0]["superou_prazo"] is True


def test_reu_com_20_anos_no_fato_tem_prazo_pela_metade() -> None:
    """Reu com 20 anos no fato tem prazo pela metade."""
    achado = _executar(
        49,
        criar_fato("data_nascimento_reu", "2009-06-02"),
        criar_fato("data_fato", "2030-06-01"),
        criar_fato("data_recebimento_denuncia", "2031-01-10"),
    )
    assert achado.valores["reducao_art115"]["aplicada"] is True
    assert achado.valores["reducao_art115"]["idade_no_fato"] == 20
    assert achado.valores["prazo_meses"] == 72


def test_reu_com_71_anos_na_sentenca_tem_prazo_pela_metade() -> None:
    """Reu com 71 anos na sentenca tem prazo pela metade."""
    achado = _executar(
        11,
        criar_fato("data_nascimento_reu", "1960-01-01"),
        criar_fato("data_fato", "2030-01-10"),
        criar_fato("data_recebimento_denuncia", "2030-06-10"),
        criar_fato("data_publicacao_sentenca", "2031-03-10"),
    )
    assert achado.valores["reducao_art115"]["idade_na_sentenca"] == 71
    assert achado.valores["prazo_texto"] == "1 anos e 6 meses"
    assert achado.resultado == "atencao"


def test_reu_adulto_sem_reducao_registra_o_motivo() -> None:
    """Reu adulto sem reducao registra o motivo."""
    achado = _executar(
        49,
        criar_fato("data_nascimento_reu", "1990-01-01"),
        criar_fato("data_fato", "2030-01-10"),
        criar_fato("data_recebimento_denuncia", "2030-06-10"),
    )
    assert achado.valores["reducao_art115"]["aplicada"] is False


def test_sem_sentenca_calcula_fato_recebimento_e_recebimento_hoje() -> None:
    """Sem sentenca calcula fato recebimento e recebimento hoje."""
    achado = _executar(
        49,
        criar_fato("data_fato", "2030-01-10"),
        criar_fato("data_recebimento_denuncia", "2030-06-10"),
    )
    pares = [(i["inicio"]["tipo"], i["fim"]["tipo"]) for i in achado.valores["intervalos"]]
    assert pares == [
        ("data_fato", "data_recebimento_denuncia"),
        ("data_recebimento_denuncia", "data_referencia"),
    ]
    assert achado.resultado == "conforme"


def test_duas_datas_de_sentenca_geram_verificar_por_conflito() -> None:
    """Duas datas de sentenca geram verificar por conflito."""
    achado = _executar(
        49,
        criar_fato("data_fato", "2030-01-10"),
        criar_fato("data_recebimento_denuncia", "2030-06-10"),
        criar_fato("data_publicacao_sentenca", "2031-01-10"),
        criar_fato("data_publicacao_sentenca", "2031-02-10"),
    )
    assert achado.resultado == "verificar"
    assert achado.valores["conflitos"][0]["tipo"] == "data_publicacao_sentenca"


def test_falta_recebimento_gera_verificar_com_faltantes() -> None:
    """Falta recebimento gera verificar com faltantes."""
    achado = _executar(49, criar_fato("data_fato", "2030-01-10"))
    assert achado.valores["faltantes"] == ["data_recebimento_denuncia"]


def test_marcos_fora_de_ordem_geram_verificar() -> None:
    """Marcos fora de ordem geram verificar."""
    achado = _executar(
        49,
        criar_fato("data_fato", "2031-01-10"),
        criar_fato("data_recebimento_denuncia", "2030-06-10"),
    )
    assert achado.resultado == "verificar"


def test_pena_invalida_lanca_erro() -> None:
    """Pena invalida lanca erro."""
    with pytest.raises(ValueError, match="inteiro positivo"):
        _executar(
            0,
            criar_fato("data_fato", "2030-01-10"),
            criar_fato("data_recebimento_denuncia", "2030-06-10"),
        )


def test_explicacao_conforme_com_frase_inteira() -> None:
    """Explicacao conforme com frase inteira."""
    achado = _executar(
        49,
        criar_fato("data_fato", "2030-01-10"),
        criar_fato("data_recebimento_denuncia", "2030-06-10"),
    )
    assert achado.explicacao == (
        "Sem prescrição pela pena em abstrato nos intervalos calculados. Pena máxima de 49 "
        "meses, art. 109, III, do CP: prazo de 12 anos (sem redução: data de nascimento do réu "
        "não informada). Intervalos: 10/01/2030 a 10/06/2030 (151 dias, limite 10/01/2042); "
        "10/06/2030 a 10/01/2035 (1675 dias, limite 10/06/2042). Data de referência: 10/01/2035. "
        "Limitação: esta versão considera só o recebimento da denúncia e a publicação da "
        "sentença condenatória recorrível como marcos (art. 117, I e IV, do CP); pronúncia, "
        "acórdão e causas suspensivas não foram considerados."
    )


def test_explicacao_atencao_com_frase_inteira() -> None:
    """Explicacao atencao com frase inteira."""
    achado = _executar(
        11,
        criar_fato("data_fato", "2030-01-10"),
        criar_fato("data_recebimento_denuncia", "2033-01-11"),
        referencia=date(2033, 2, 1),
    )
    assert achado.explicacao == (
        "Possível prescrição pela pena em abstrato. Pena máxima de 11 meses, art. 109, VI, do "
        "CP: prazo de 3 anos (sem redução: data de nascimento do réu não informada). "
        "Intervalo(s) acima do prazo: 10/01/2030 a 11/01/2033 (1097 dias, limite 10/01/2033). "
        "Todos os intervalos: 10/01/2030 a 11/01/2033 (1097 dias, limite 10/01/2033); "
        "11/01/2033 a 01/02/2033 (21 dias, limite 11/01/2036). Data de referência: 01/02/2033. "
        "Limitação: esta versão considera só o recebimento da denúncia e a publicação da "
        "sentença condenatória recorrível como marcos (art. 117, I e IV, do CP); pronúncia, "
        "acórdão e causas suspensivas não foram considerados."
    )


def test_explicacao_verificar_com_frase_inteira() -> None:
    """Explicacao verificar com frase inteira."""
    achado = prescricao.executar(modelo_de(), REFERENCIA)
    assert achado.explicacao == (
        "Prescrição pela pena em abstrato não conferida automaticamente: faltam fatos "
        "necessários. Fatos faltantes: pena_maxima_abstrata; data_fato; "
        "data_recebimento_denuncia. Fatos em conflito: nenhum. Confira nos autos."
    )
