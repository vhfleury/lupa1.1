"""Validação 3: revisão periódica da prisão preventiva.

Base legal registrada para conferência do gabinete: art. 316, parágrafo único, do CPP (revisão da
necessidade da preventiva a cada 90 dias, com decisão fundamentada). O prazo fica em
``dados/preventiva.yaml``. Regra de borda adotada, a confirmar: intervalo igual ao prazo é
conforme; só intervalo maior que o prazo gera atenção.
"""

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
from lupa.validacoes.dados import ParametrosPreventiva, preventiva_padrao
from lupa.validacoes.modelo import AchadoValidacao, ModeloProcesso, ResultadoAchado

NOME = "revisao_preventiva"
BASE_LEGAL = "art. 316, parágrafo único, do CPP"
FATOS_NECESSARIOS = ("data_decretacao_preventiva", "data_revisao_preventiva")


def _descrever(intervalo: dict[str, Any]) -> str:
    return (
        f"{formatar_data(intervalo['inicio']['data'])} a {formatar_data(intervalo['fim']['data'])}"
        f" ({intervalo['dias']} dias)"
    )


def executar(
    modelo: ModeloProcesso, referencia: date, parametros: ParametrosPreventiva | None = None
) -> AchadoValidacao:
    """Confere se cada intervalo entre decretação, revisões e a referência respeita o prazo.

    Args:
        modelo: Fatos do processo (de um réu).
        referencia: Data de referência para o último intervalo.
        parametros: Prazo e base legal; padrão é o YAML empacotado.

    Returns:
        AchadoValidacao ``conforme``, ``atencao`` (algum intervalo estourou) ou ``verificar``.
    """
    parametros = parametros or preventiva_padrao()
    coleta = Coleta(modelo)
    decretacao = coleta.unico("data_decretacao_preventiva")
    if coleta.pendente or decretacao is None:
        return coleta.verificar(NOME, motivo_pendencia(coleta))
    revisoes = sorted(modelo.fatos("data_revisao_preventiva"), key=lambda f: (data_de(f), f.id))
    coleta.usados.extend(f.id for f in revisoes)
    anteriores = [f for f in revisoes if data_de(f) < data_de(decretacao)]
    if anteriores or data_de(revisoes[-1] if revisoes else decretacao) > referencia:
        return coleta.verificar(NOME, "há revisão anterior à decretação ou posterior à referência.")
    cadeia = [rastrear(decretacao), *(rastrear(f) for f in revisoes)]
    pontos = [*cadeia, {"data": referencia.isoformat(), "tipo": "data_referencia"}]
    intervalos: list[dict[str, Any]] = []
    for inicio, fim in zip(pontos, pontos[1:], strict=False):
        dias = (date.fromisoformat(fim["data"]) - date.fromisoformat(inicio["data"])).days
        estourou = dias > parametros.prazo_revisao_dias
        intervalos.append({"inicio": inicio, "fim": fim, "dias": dias, "estourou": estourou})
    estourados = [i for i in intervalos if i["estourou"]]
    resultado: ResultadoAchado = "atencao" if estourados else "conforme"
    valores: dict[str, Any] = {
        "prazo_dias": parametros.prazo_revisao_dias,
        "base_legal": parametros.base_legal,
        "cadeia": cadeia,
        "intervalos": intervalos,
        "intervalos_estourados": [n for n, i in enumerate(intervalos) if i["estourou"]],
        "data_referencia": referencia.isoformat(),
        "versao_parametros": parametros.versao,
    }
    explicacao = renderizar(
        f"{NOME}_{resultado}",
        prazo=parametros.prazo_revisao_dias,
        base_legal=parametros.base_legal,
        cadeia=listar(formatar_data(c["data"]) for c in cadeia),
        intervalos=listar(_descrever(i) for i in intervalos),
        quantidade=len(estourados),
        estourados=listar(_descrever(i) for i in estourados),
        maior=max(i["dias"] for i in intervalos),
        referencia=formatar_data(referencia),
    )
    return criar_achado(NOME, resultado, coleta.usados, valores, explicacao)
