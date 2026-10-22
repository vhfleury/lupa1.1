"""Testes da validação de tempestividade do recurso (datas e feriados sintéticos)."""

from datetime import date

from lupa.validacoes.calendario import Periodo
from lupa.validacoes.criminal import tempestividade
from lupa.validacoes.modelo import AchadoValidacao
from tests.validacoes.conftest import criar_fato, dados_tempestividade, modelo_de

REFERENCIA = date(2030, 4, 1)
QUINTA = "2030-03-07"
SEGUNDA = "2030-03-04"


def _apelacao_defesa(
    intimacao_defesa: str, intimacao_reu: str, interposicao: str, **dados: object
) -> AchadoValidacao:
    modelo = modelo_de(
        criar_fato("tipo_recurso", {"tipo": "apelacao", "recorrente": "defesa"}),
        criar_fato("data_intimacao_defesa", intimacao_defesa),
        criar_fato("data_intimacao_reu", intimacao_reu),
        criar_fato("data_interposicao_recurso", interposicao),
    )
    return tempestividade.executar(modelo, REFERENCIA, dados_tempestividade(**dados))  # type: ignore[arg-type]


def test_datas_sinteticas_tem_os_dias_da_semana_esperados() -> None:
    """Datas sinteticas tem os dias da semana esperados."""
    assert date.fromisoformat(QUINTA).weekday() == 3
    assert date.fromisoformat(SEGUNDA).weekday() == 0


def test_apelacao_interposta_no_ultimo_dia_e_tempestiva() -> None:
    """Apelacao interposta no ultimo dia e tempestiva."""
    achado = _apelacao_defesa(QUINTA, QUINTA, "2030-03-12")
    assert achado.resultado == "conforme"
    assert achado.valores["vencimento"] == "2030-03-12"
    assert achado.valores["diferenca_dias"] == 0


def test_apelacao_interposta_no_sexto_dia_e_intempestiva() -> None:
    """Apelacao interposta no sexto dia e intempestiva."""
    achado = _apelacao_defesa(QUINTA, QUINTA, "2030-03-13")
    assert achado.resultado == "atencao"
    assert achado.valores["diferenca_dias"] == 1


def test_vencimento_no_sabado_prorroga_para_segunda() -> None:
    """Vencimento no sabado prorroga para segunda."""
    achado = _apelacao_defesa(SEGUNDA, SEGUNDA, "2030-03-11")
    assert achado.resultado == "conforme"
    assert achado.valores["vencimento_nominal"] == "2030-03-09"
    assert achado.valores["vencimento"] == "2030-03-11"
    motivos = [d["motivo"] for d in achado.valores["feriados_deslocamento"]]
    assert motivos == ["sábado", "domingo"]


def test_vencimento_em_feriado_do_tribunal_prorroga() -> None:
    """Vencimento em feriado do tribunal prorroga."""
    feriados = {date(2030, 3, 12): "feriado sintético do TJGO"}
    achado = _apelacao_defesa(QUINTA, QUINTA, "2030-03-13", feriados=feriados)
    assert achado.resultado == "conforme"
    assert achado.valores["feriados_deslocamento"] == [
        {"data": "2030-03-12", "motivo": "feriado: feriado sintético do TJGO"}
    ]


def test_dias_em_suspensao_nao_sao_contados() -> None:
    """Dias em suspensao nao sao contados."""
    suspensao = (Periodo(date(2030, 3, 8), date(2030, 3, 10), "suspensão sintética"),)
    achado = _apelacao_defesa(QUINTA, QUINTA, "2030-03-15", suspensoes=suspensao)
    assert achado.valores["vencimento"] == "2030-03-15"
    assert len(achado.valores["dias_suspensos"]) == 3


def test_defesa_recorre_e_reu_intimado_depois_conta_da_intimacao_do_reu() -> None:
    """Defesa recorre e reu intimado depois conta da intimacao do reu."""
    achado = _apelacao_defesa("2030-03-01", QUINTA, "2030-03-12")
    assert achado.resultado == "conforme"
    assert achado.valores["origem_data_base"] == "data_intimacao_reu"
    assert achado.valores["data_base"]["data"] == QUINTA


def test_recurso_do_mp_conta_da_intimacao_do_mp() -> None:
    """Recurso do mp conta da intimacao do mp."""
    modelo = modelo_de(
        criar_fato("tipo_recurso", {"tipo": "embargos_declaracao", "recorrente": "mp"}),
        criar_fato("data_intimacao_mp", QUINTA),
        criar_fato("data_interposicao_recurso", "2030-03-11"),
    )
    achado = tempestividade.executar(modelo, REFERENCIA, dados_tempestividade())
    assert achado.resultado == "conforme"
    assert achado.valores["vencimento"] == "2030-03-11"


def test_falta_data_de_intimacao_gera_verificar_com_faltantes() -> None:
    """Falta data de intimacao gera verificar com faltantes."""
    modelo = modelo_de(
        criar_fato("tipo_recurso", {"tipo": "apelacao", "recorrente": "defesa"}),
        criar_fato("data_intimacao_defesa", QUINTA),
        criar_fato("data_interposicao_recurso", "2030-03-12"),
    )
    achado = tempestividade.executar(modelo, REFERENCIA, dados_tempestividade())
    assert achado.resultado == "verificar"
    assert achado.valores["faltantes"] == ["data_intimacao_reu"]


def test_sem_tipo_de_recurso_gera_verificar() -> None:
    """Sem tipo de recurso gera verificar."""
    achado = tempestividade.executar(modelo_de(), REFERENCIA, dados_tempestividade())
    assert achado.valores["faltantes"] == ["tipo_recurso", "data_interposicao_recurso"]


def test_tipo_de_recurso_desconhecido_gera_verificar() -> None:
    """Tipo de recurso desconhecido gera verificar."""
    modelo = modelo_de(
        criar_fato("tipo_recurso", {"tipo": "agravo_inexistente", "recorrente": "defesa"}),
        criar_fato("data_interposicao_recurso", "2030-03-12"),
    )
    achado = tempestividade.executar(modelo, REFERENCIA, dados_tempestividade())
    assert achado.resultado == "verificar"
    assert "agravo_inexistente" in achado.valores["motivo"]


def test_recorrente_nao_identificado_gera_verificar() -> None:
    """Recorrente nao identificado gera verificar."""
    modelo = modelo_de(criar_fato("tipo_recurso", "apelacao"))
    achado = tempestividade.executar(modelo, REFERENCIA, dados_tempestividade())
    assert achado.resultado == "verificar"


def test_recorrente_desconhecido_gera_verificar() -> None:
    """Recorrente desconhecido gera verificar."""
    modelo = modelo_de(
        criar_fato("tipo_recurso", {"tipo": "apelacao", "recorrente": "assistente"}),
        criar_fato("data_interposicao_recurso", "2030-03-12"),
    )
    achado = tempestividade.executar(modelo, REFERENCIA, dados_tempestividade())
    assert achado.valores["motivo"] == "recorrente não identificado: assistente."


def test_explicacao_conforme_com_frase_inteira() -> None:
    """Explicacao conforme com frase inteira."""
    achado = _apelacao_defesa(SEGUNDA, SEGUNDA, "2030-03-11")
    assert achado.explicacao == (
        "Recurso tempestivo. Apelação interposto em 11/03/2030; prazo de 5 dias "
        "(art. 593 CPP) contado a partir de 04/03/2030 (data_intimacao_reu), com vencimento "
        "em 11/03/2030 (vencimento nominal em 09/03/2030 prorrogado por: 09/03/2030 (sábado); "
        "10/03/2030 (domingo))."
    )


def test_explicacao_atencao_com_frase_inteira() -> None:
    """Explicacao atencao com frase inteira."""
    achado = _apelacao_defesa(QUINTA, QUINTA, "2030-03-14")
    assert achado.explicacao == (
        "Recurso possivelmente intempestivo. Apelação interposto em 14/03/2030, 2 dia(s) após o "
        "vencimento em 12/03/2030 (sem prorrogação); prazo de 5 dias (art. 593 CPP) contado a "
        "partir de 07/03/2030 (data_intimacao_reu). Confira as intimações e o calendário do "
        "tribunal."
    )


def test_explicacao_verificar_com_frase_inteira() -> None:
    """Explicacao verificar com frase inteira."""
    achado = tempestividade.executar(modelo_de(), REFERENCIA, dados_tempestividade())
    assert achado.explicacao == (
        "Tempestividade do recurso não conferida automaticamente: faltam fatos necessários. "
        "Fatos faltantes: tipo_recurso; data_interposicao_recurso. Fatos em conflito: nenhum. "
        "Confira nos autos."
    )


def test_usa_dados_empacotados_quando_nao_informados() -> None:
    """Usa dados empacotados quando nao informados."""
    modelo = modelo_de(
        criar_fato("tipo_recurso", {"tipo": "rese", "recorrente": "mp"}),
        criar_fato("data_intimacao_mp", "2026-03-09"),
        criar_fato("data_interposicao_recurso", "2026-03-13"),
    )
    achado = tempestividade.executar(modelo, REFERENCIA)
    assert achado.resultado == "conforme"
    assert "prazos_recursos.yaml" in achado.valores["versoes_dados"]
