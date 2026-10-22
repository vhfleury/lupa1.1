"""Testes da validação de revisão da prisão preventiva (datas sintéticas)."""

from datetime import date, timedelta

from lupa.validacoes.criminal import preventiva
from lupa.validacoes.modelo import AchadoValidacao
from tests.validacoes.conftest import criar_fato, modelo_de

REFERENCIA = date(2030, 12, 31)


def _executar(decretacao: date | None, *revisoes: date) -> AchadoValidacao:
    fatos = [criar_fato("data_revisao_preventiva", r.isoformat()) for r in revisoes]
    if decretacao is not None:
        fatos.append(criar_fato("data_decretacao_preventiva", decretacao.isoformat()))
    return preventiva.executar(modelo_de(*fatos), REFERENCIA)


def test_decretacao_ha_89_dias_sem_revisao_e_conforme() -> None:
    """Decretacao ha 89 dias sem revisao e conforme."""
    achado = _executar(REFERENCIA - timedelta(days=89))
    assert achado.resultado == "conforme"


def test_decretacao_ha_91_dias_sem_revisao_e_atencao() -> None:
    """Decretacao ha 91 dias sem revisao e atencao."""
    achado = _executar(REFERENCIA - timedelta(days=91))
    assert achado.resultado == "atencao"
    assert achado.valores["intervalos_estourados"] == [0]


def test_revisoes_a_cada_80_dias_sao_conformes() -> None:
    """Revisoes a cada 80 dias sao conformes."""
    inicio = date(2030, 1, 1)
    revisoes = [inicio + timedelta(days=80 * n) for n in range(1, 5)]
    achado = _executar(inicio, *revisoes)
    assert achado.resultado == "conforme"
    assert [i["dias"] for i in achado.valores["intervalos"][:-1]] == [80, 80, 80, 80]


def test_revisao_com_100_dias_no_meio_aponta_o_intervalo() -> None:
    """Revisao com 100 dias no meio aponta o intervalo."""
    inicio = date(2030, 6, 1)
    primeira = inicio + timedelta(days=80)
    segunda = primeira + timedelta(days=100)
    achado = _executar(inicio, primeira, segunda)
    assert achado.resultado == "atencao"
    assert achado.valores["intervalos_estourados"] == [1]
    assert achado.valores["intervalos"][1]["dias"] == 100


def test_revisoes_fora_de_ordem_sao_ordenadas_antes_do_calculo() -> None:
    """Revisoes fora de ordem sao ordenadas antes do calculo."""
    inicio = date(2030, 9, 1)
    primeira = inicio + timedelta(days=40)
    segunda = primeira + timedelta(days=40)
    achado = _executar(inicio, segunda, primeira)
    datas = [c["data"] for c in achado.valores["cadeia"]]
    assert datas == sorted(datas)
    assert achado.resultado == "conforme"


def test_sem_decretacao_gera_verificar() -> None:
    """Sem decretacao gera verificar."""
    achado = _executar(None, date(2030, 12, 1))
    assert achado.resultado == "verificar"
    assert achado.valores["faltantes"] == ["data_decretacao_preventiva"]


def test_revisao_anterior_a_decretacao_gera_verificar() -> None:
    """Revisao anterior a decretacao gera verificar."""
    achado = _executar(date(2030, 12, 1), date(2030, 11, 1))
    assert achado.resultado == "verificar"


def test_explicacao_conforme_com_frase_inteira() -> None:
    """Explicacao conforme com frase inteira."""
    achado = _executar(date(2030, 10, 2))
    assert achado.explicacao == (
        "Revisões da prisão preventiva dentro do prazo de 90 dias (art. 316, parágrafo único, "
        "CPP). Cadeia: 02/10/2030. Maior intervalo: 90 dias. Data de referência: 31/12/2030."
    )


def test_explicacao_atencao_com_frase_inteira() -> None:
    """Explicacao atencao com frase inteira."""
    achado = _executar(date(2030, 9, 1))
    assert achado.explicacao == (
        "Prazo de revisão da prisão preventiva de 90 dias (art. 316, parágrafo único, CPP) "
        "superado em 1 intervalo(s): 01/09/2030 a 31/12/2030 (121 dias). Cadeia: 01/09/2030. "
        "Data de referência: 31/12/2030."
    )


def test_explicacao_verificar_com_frase_inteira() -> None:
    """Explicacao verificar com frase inteira."""
    achado = _executar(None)
    assert achado.explicacao == (
        "Revisão da prisão preventiva não conferida automaticamente: faltam fatos necessários. "
        "Fatos faltantes: data_decretacao_preventiva. Fatos em conflito: nenhum. "
        "Confira nos autos."
    )
