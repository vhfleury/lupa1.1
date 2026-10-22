"""Validação 2: prescrição da pretensão punitiva pela pena máxima em abstrato.

Base legal registrada para conferência do gabinete: tabela do art. 109 CP (em
``dados/prescricao_art109.yaml``); redução pela metade do art. 115 CP (menor de 21 anos na data
do fato ou maior de 70 na data da sentença); marcos interruptivos do art. 117, I (recebimento da
denúncia) e IV (publicação da sentença condenatória recorrível). Pronúncia, acórdão e causas
suspensivas (art. 116 CP, art. 366 CPP) não são considerados nesta versão.

Regra de borda adotada, a confirmar: o intervalo supera o prazo só quando a data final é
posterior à data inicial somada do prazo em meses de calendário; intervalo exatamente igual ao
prazo é tratado como não prescrito.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from lupa.validacoes.apoio import (
    Coleta,
    criar_achado,
    data_de,
    formatar_data,
    listar,
    motivo_pendencia,
    rastrear,
    renderizar,
)
from lupa.validacoes.calendario import idade_em, somar_meses
from lupa.validacoes.dados import ReducaoArt115, TabelaPrescricao, prescricao_padrao
from lupa.validacoes.modelo import AchadoValidacao, Fato, ModeloProcesso, ResultadoAchado, valor_de

NOME = "prescricao_abstrata"
BASE_LEGAL = "arts. 109, 115 e 117, I e IV, do CP"
FATOS_NECESSARIOS = (
    "pena_maxima_abstrata",
    "data_fato",
    "data_recebimento_denuncia",
    "data_publicacao_sentenca",
    "data_nascimento_reu",
)
_MESES_NO_ANO = 12


@dataclass(frozen=True)
class Reducao:
    """Resultado da análise do art. 115 CP."""

    aplicada: bool
    motivo: str
    idade_no_fato: int | None
    idade_na_sentenca: int | None


def _pena_meses(fato: Fato) -> int:
    valor = valor_de(fato)
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError(f"fato {fato.id}: pena máxima deve ser inteiro positivo em meses")
    return int(valor)


def _avaliar_reducao(
    regra: ReducaoArt115, nascimento: date | None, fato: date, sentenca: date | None
) -> Reducao:
    if nascimento is None:
        return Reducao(False, "data de nascimento do réu não informada", None, None)
    idade_fato = idade_em(nascimento, fato)
    idade_sentenca = idade_em(nascimento, sentenca) if sentenca else None
    if idade_fato < regra.idade_no_fato_abaixo_de:
        motivo = f"réu com {idade_fato} anos na data do fato ({regra.base_legal})"
        return Reducao(True, motivo, idade_fato, idade_sentenca)
    if idade_sentenca is not None and idade_sentenca >= regra.idade_na_sentenca_a_partir_de:
        motivo = f"réu com {idade_sentenca} anos na data da sentença ({regra.base_legal})"
        return Reducao(True, motivo, idade_fato, idade_sentenca)
    return Reducao(False, "idade do réu fora das hipóteses do art. 115", idade_fato, idade_sentenca)


def _texto_prazo(meses: int) -> str:
    anos, resto = divmod(meses, _MESES_NO_ANO)
    return f"{anos} anos e {resto} meses" if resto else f"{anos} anos"


def _intervalo(inicio: dict[str, Any], fim: dict[str, Any], prazo_meses: int) -> dict[str, Any]:
    data_inicio = date.fromisoformat(inicio["data"])
    data_fim = date.fromisoformat(fim["data"])
    limite = somar_meses(data_inicio, prazo_meses)
    return {
        "inicio": inicio,
        "fim": fim,
        "dias": (data_fim - data_inicio).days,
        "limite": limite.isoformat(),
        "superou_prazo": data_fim > limite,
    }


def _descrever(intervalo: dict[str, Any]) -> str:
    return (
        f"{formatar_data(intervalo['inicio']['data'])} a {formatar_data(intervalo['fim']['data'])}"
        f" ({intervalo['dias']} dias, limite {formatar_data(intervalo['limite'])})"
    )


def executar(
    modelo: ModeloProcesso, referencia: date, tabela: TabelaPrescricao | None = None
) -> AchadoValidacao:
    """Confere a prescrição pela pena máxima em abstrato entre os marcos disponíveis.

    Args:
        modelo: Fatos do processo (de um réu).
        referencia: Data de referência ("hoje") para o último intervalo.
        tabela: Tabela do art. 109; padrão é o YAML empacotado.

    Returns:
        AchadoValidacao ``conforme``, ``atencao`` (algum intervalo supera o prazo) ou ``verificar``.
    """
    tabela = tabela or prescricao_padrao()
    coleta = Coleta(modelo)
    fato_pena = coleta.unico("pena_maxima_abstrata")
    fato_crime = coleta.unico("data_fato")
    fato_recebimento = coleta.unico("data_recebimento_denuncia")
    fato_sentenca = coleta.unico("data_publicacao_sentenca", obrigatorio=False)
    fato_nascimento = coleta.unico("data_nascimento_reu", obrigatorio=False)
    if coleta.pendente or fato_pena is None or fato_crime is None or fato_recebimento is None:
        return coleta.verificar(NOME, motivo_pendencia(coleta))
    marcos = [rastrear(f) for f in (fato_crime, fato_recebimento, fato_sentenca) if f]
    datas = [m["data"] for m in marcos]
    if datas != sorted(datas) or datas[-1] > referencia.isoformat():
        return coleta.verificar(NOME, "as datas dos marcos estão fora de ordem.")
    pena = _pena_meses(fato_pena)
    faixa = tabela.faixa_para(pena)
    reducao = _avaliar_reducao(
        tabela.reducao,
        data_de(fato_nascimento) if fato_nascimento else None,
        data_de(fato_crime),
        data_de(fato_sentenca) if fato_sentenca else None,
    )
    prazo_meses = faixa.prazo_anos * _MESES_NO_ANO
    if reducao.aplicada:
        prazo_meses //= tabela.reducao.divisor
    ponto_final = {"data": referencia.isoformat(), "tipo": "data_referencia"}
    pontos = [*marcos, ponto_final]
    intervalos = [_intervalo(a, b, prazo_meses) for a, b in zip(pontos, pontos[1:], strict=False)]
    superados = [i for i in intervalos if i["superou_prazo"]]
    resultado: ResultadoAchado = "atencao" if superados else "conforme"
    valores: dict[str, Any] = {
        "pena_maxima_meses": {
            "valor": pena,
            "fato_id": str(fato_pena.id),
            "evidencia_id": str(fato_pena.evidencias[0].id),
        },
        "faixa_art109": {"inciso": faixa.inciso, "prazo_anos": faixa.prazo_anos},
        "base_legal": tabela.base_legal,
        "prazo_meses": prazo_meses,
        "prazo_texto": _texto_prazo(prazo_meses),
        "reducao_art115": {
            "aplicada": reducao.aplicada,
            "motivo": reducao.motivo,
            "idade_no_fato": reducao.idade_no_fato,
            "idade_na_sentenca": reducao.idade_na_sentenca,
            "nascimento": rastrear(fato_nascimento) if fato_nascimento else None,
        },
        "marcos": marcos,
        "intervalos": intervalos,
        "data_referencia": referencia.isoformat(),
        "limitacoes": ["pronúncia", "acórdão", "causas suspensivas"],
        "versao_tabela": tabela.versao,
    }
    explicacao = renderizar(
        f"{NOME}_{resultado}",
        pena=pena,
        inciso=faixa.inciso,
        prazo=_texto_prazo(prazo_meses),
        reducao=reducao.motivo if reducao.aplicada else f"sem redução: {reducao.motivo}",
        intervalos=listar(_descrever(i) for i in intervalos),
        superados=listar(_descrever(i) for i in superados),
        referencia=formatar_data(referencia),
    )
    return criar_achado(NOME, resultado, coleta.usados, valores, explicacao)
