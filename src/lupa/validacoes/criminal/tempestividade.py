"""Validação 1: tempestividade da interposição do recurso criminal.

Base legal registrada para conferência do gabinete: prazos dos arts. 586 (RESE), 593 (apelação)
e 619 (embargos de declaração) do CPP; contagem em dias corridos, excluído o dia do começo e
prorrogado o vencimento em dia sem expediente (art. 798, caput e §§ 1º e 3º, CPP); prazo da
defesa contado da última intimação entre réu e defensor (art. 392 CPP). Os números ficam em
``dados/prazos_recursos.yaml``; feriados e suspensões em ``dados/feriados`` e
``dados/suspensoes_prazo.yaml``.
"""

from collections.abc import Mapping
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
from lupa.validacoes.calendario import Calendario, ResultadoPrazo, contar_prazo_corrido
from lupa.validacoes.dados import TabelaPrazosRecursos, calendario_padrao, prazos_recursos_padrao
from lupa.validacoes.modelo import AchadoValidacao, Fato, ModeloProcesso, ResultadoAchado

NOME = "tempestividade_recurso"
BASE_LEGAL = "arts. 392, 586, 593, 619 e 798 do CPP"
FATOS_NECESSARIOS = (
    "tipo_recurso",
    "data_interposicao_recurso",
    "data_intimacao_defesa",
    "data_intimacao_reu",
    "data_intimacao_mp",
)
INTIMACOES_POR_RECORRENTE: Mapping[str, tuple[str, ...]] = {
    "defesa": ("data_intimacao_defesa", "data_intimacao_reu"),
    "mp": ("data_intimacao_mp",),
}


@dataclass(frozen=True)
class DadosTempestividade:
    """Tabelas usadas pela validação."""

    prazos: TabelaPrazosRecursos
    calendario: Calendario
    versoes: Mapping[str, str]


def dados_padrao() -> DadosTempestividade:
    """Monta os dados a partir dos YAML empacotados.

    Returns:
        Dados da validação.
    """
    calendario, versoes = calendario_padrao()
    prazos = prazos_recursos_padrao()
    return DadosTempestividade(
        prazos, calendario, {**versoes, "prazos_recursos.yaml": prazos.versao}
    )


def _ler_tipo(fato: Fato) -> tuple[str, str]:
    valor = fato.valor if isinstance(fato.valor, dict) else {}
    return str(valor.get("tipo", "")), str(valor.get("recorrente", ""))


def _texto_prorrogacao(prazo: ResultadoPrazo) -> str:
    if not prazo.deslocamentos:
        return "sem prorrogação"
    dias = listar(f"{formatar_data(d.data)} ({d.motivo})" for d in prazo.deslocamentos)
    return f"vencimento nominal em {formatar_data(prazo.vencimento_nominal)} prorrogado por: {dias}"


def executar(
    modelo: ModeloProcesso, referencia: date, dados: DadosTempestividade | None = None
) -> AchadoValidacao:
    """Confere se o recurso foi interposto dentro do prazo.

    Args:
        modelo: Fatos do processo.
        referencia: Data de referência (registrada em ``valores``; não altera a conta).
        dados: Tabelas jurídicas; padrão são os YAML empacotados.

    Returns:
        AchadoValidacao ``conforme`` (tempestivo), ``atencao`` (intempestivo) ou ``verificar``.
    """
    dados = dados or dados_padrao()
    coleta = Coleta(modelo)
    fato_tipo = coleta.unico("tipo_recurso")
    fato_interposicao = coleta.unico("data_interposicao_recurso")
    if fato_tipo is None:
        return coleta.verificar(NOME, motivo_pendencia(coleta))
    tipo, recorrente = _ler_tipo(fato_tipo)
    regra = dados.prazos.recursos.get(tipo)
    if regra is None:
        return coleta.verificar(NOME, f"tipo de recurso desconhecido: {tipo or 'vazio'}.")
    if recorrente not in INTIMACOES_POR_RECORRENTE:
        return coleta.verificar(NOME, f"recorrente não identificado: {recorrente or 'vazio'}.")
    intimacoes = [coleta.unico(t) for t in INTIMACOES_POR_RECORRENTE[recorrente]]
    if coleta.pendente or fato_interposicao is None:
        return coleta.verificar(NOME, motivo_pendencia(coleta))
    presentes = [f for f in intimacoes if f is not None]
    fato_base = max(presentes, key=lambda f: (data_de(f), f.tipo))
    prazo = contar_prazo_corrido(
        data_de(fato_base), regra.dias, dados.calendario.feriados, dados.calendario.suspensoes
    )
    interposicao = data_de(fato_interposicao)
    diferenca = (interposicao - prazo.vencimento).days
    resultado: ResultadoAchado = "conforme" if diferenca <= 0 else "atencao"
    valores: dict[str, Any] = {
        "tipo_recurso": {"tipo": tipo, "recorrente": recorrente, "fato_id": str(fato_tipo.id)},
        "intimacoes": [rastrear(f) for f in presentes],
        "data_base": rastrear(fato_base),
        "origem_data_base": str(fato_base.tipo),
        "prazo_dias": regra.dias,
        "base_legal_prazo": regra.base_legal,
        "base_legal_contagem": dados.prazos.contagem_base_legal,
        "vencimento_nominal": prazo.vencimento_nominal.isoformat(),
        "vencimento": prazo.vencimento.isoformat(),
        "feriados_deslocamento": [
            {"data": d.data.isoformat(), "motivo": d.motivo} for d in prazo.deslocamentos
        ],
        "dias_suspensos": [
            {"data": d.data.isoformat(), "motivo": d.motivo} for d in prazo.dias_suspensos
        ],
        "interposicao": rastrear(fato_interposicao),
        "diferenca_dias": diferenca,
        "data_referencia": referencia.isoformat(),
        "versoes_dados": dict(dados.versoes),
    }
    explicacao = renderizar(
        f"{NOME}_{resultado}",
        recurso=regra.nome,
        interposicao=formatar_data(interposicao),
        prazo_dias=regra.dias,
        base_legal=regra.base_legal,
        data_base=formatar_data(prazo.data_base),
        origem_data_base=fato_base.tipo,
        vencimento=formatar_data(prazo.vencimento),
        prorrogacao=_texto_prorrogacao(prazo),
        diferenca=diferenca,
    )
    return criar_achado(NOME, resultado, coleta.usados, valores, explicacao)
