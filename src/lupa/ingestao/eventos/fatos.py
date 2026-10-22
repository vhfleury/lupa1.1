"""Dos candidatos aos fatos: evidência obrigatória, reconferência e conflitos (4F.3, 4F.4, 4F.5).

Para cada peça roda o extrator do seu tipo (um módulo por tipo; peça ``outros`` só passa pelas
regras do YAML que a admitem). Cada candidato vira ``Fato`` só se:

1. tiver trecho de evidência não vazio no texto ORIGINAL da página, depois de recortado o nome e
   o documento do réu (``reus.sem_nomes``); sem trecho, o valor é descartado (4F.3);
2. sendo data, a data existir literalmente no trecho, conferida por ``datas.reconferir``, que não
   reaproveita as expressões de busca (4F.4). Data rejeitada vai para o log só com tipo, regra e
   id da página.

Candidatos com o mesmo tipo, valor e réu viram um único fato com várias evidências. Tipos que
devem ser únicos (todos menos ``data_revisao_preventiva``) com valores distintos geram todos os
fatos com a confiança reduzida (``FATOR_CONFLITO``); o motor de validações já devolve
``verificar`` para conflito. Os ids de fato e de evidência são derivados da chave natural
(processo, tipo, valor, evidência), o que torna a gravação idempotente.
"""

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID, uuid5

from lupa.dominio.enums import StatusFato, TipoFato, TipoPeca
from lupa.dominio.esquemas import Evidencia, Fato
from lupa.ingestao.datas import reconferir
from lupa.ingestao.eventos import (
    base,
    certidao,
    decisao_prisao,
    denuncia,
    recebimento,
    recurso,
    reus,
    sentenca,
)
from lupa.ingestao.eventos.modelo import Candidato, PecaTexto, ReuQualificado
from lupa.ingestao.eventos.padroes import Padroes, padroes_padrao
from lupa.logging import get_logger

EXTRAIDO_POR = "regra"
FATOR_CONFLITO = 0.5
TIPOS_MULTIPLOS = frozenset({TipoFato.DATA_REVISAO_PREVENTIVA})
NAMESPACE = UUID("5f0c2a52-6e0d-4c55-9a4a-4f46c6a1f4e1")
Extrator = Callable[[PecaTexto, Padroes], list[Candidato]]
EXTRATORES: dict[TipoPeca, Extrator] = {
    TipoPeca.DENUNCIA: denuncia.extrair,
    TipoPeca.RECEBIMENTO: recebimento.extrair,
    TipoPeca.DECISAO_PRISAO: decisao_prisao.extrair,
    TipoPeca.SENTENCA: sentenca.extrair,
    TipoPeca.CERTIDAO: certidao.extrair,
    TipoPeca.RECURSO: recurso.extrair,
}

log = get_logger(__name__)


@dataclass
class ResultadoExtracao:
    """Fatos extraídos e as contagens do que ficou de fora (sem conteúdo).

    Attributes:
        fatos: Fatos prontos para gravar.
        candidatos: Quantos candidatos os extratores produziram.
        sem_trecho: Candidatos descartados por falta de trecho de evidência.
        datas_rejeitadas: Datas que não existem literalmente no trecho, por tipo.
        conflitos: Tipos com valores divergentes.
    """

    fatos: list[Fato] = field(default_factory=list)
    candidatos: int = 0
    sem_trecho: int = 0
    datas_rejeitadas: Counter[str] = field(default_factory=Counter)
    conflitos: list[str] = field(default_factory=list)

    def resumo(self) -> dict[str, Any]:
        """Contagens para o relatório do job (sem texto).

        Returns:
            Resumo serializável.
        """
        return {
            "fatos": len(self.fatos),
            "por_tipo": dict(Counter(str(f.tipo) for f in self.fatos)),
            "candidatos": self.candidatos,
            "sem_trecho": self.sem_trecho,
            "datas_rejeitadas": dict(self.datas_rejeitadas),
            "conflitos": sorted(set(self.conflitos)),
        }


def candidatos_da_peca(peca: PecaTexto, padroes: Padroes) -> list[Candidato]:
    """Roda o extrator do tipo da peça.

    Args:
        peca: Peça.
        padroes: Padrões.

    Returns:
        Candidatos.
    """
    extrator = EXTRATORES.get(peca.tipo)
    return extrator(peca, padroes) if extrator else base.regras_da_peca(peca, padroes)


def _sem_reserva_desnecessaria(candidatos: list[Candidato]) -> list[Candidato]:
    principal = any(
        c.tipo is TipoFato.PENA_MAXIMA_ABSTRATA and c.regra != sentenca.REGRA_PENA_SENTENCA
        for c in candidatos
    )
    if not principal:
        return candidatos
    return [c for c in candidatos if c.regra != sentenca.REGRA_PENA_SENTENCA]


def _chave_valor(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, default=str)


def evidencia_de(candidato: Candidato, inicio: int) -> Evidencia | None:
    """Evidência do candidato sobre o texto original, ou None se não há trecho.

    Args:
        candidato: Candidato.
        inicio: Início (já recortado) no texto original.

    Returns:
        Evidência com hash calculado pelo esquema.
    """
    trecho = candidato.pagina.texto[inicio : candidato.fim]
    if not trecho.strip() or candidato.fim <= inicio:
        return None
    chave = f"{candidato.pagina.id}|{inicio}|{candidato.fim}"
    return Evidencia(
        id=uuid5(NAMESPACE, chave),
        pagina_id=candidato.pagina.id,
        trecho=trecho,
        inicio=inicio,
        fim=candidato.fim,
    )


def _valor_final(candidato: Candidato, ids_reu: Mapping[str, UUID]) -> Any:
    if candidato.por_reu and candidato.reu is not None and candidato.reu in ids_reu:
        return {"valor": candidato.valor, "reu_id": str(ids_reu[candidato.reu])}
    return candidato.valor


def _aceitar(
    candidato: Candidato, termos: Sequence[str], resultado: ResultadoExtracao
) -> Evidencia | None:
    inicio = reus.sem_nomes(candidato.pagina.texto, candidato.inicio, candidato.fim, termos)
    evidencia = evidencia_de(candidato, inicio)
    if evidencia is None:
        resultado.sem_trecho += 1
        log.info("fato_sem_trecho", tipo=candidato.tipo.value, regra=candidato.regra)
        return None
    if candidato.data is not None and not reconferir(evidencia.trecho, candidato.data):
        resultado.datas_rejeitadas[candidato.tipo.value] += 1
        log.warning(
            "data_rejeitada",
            tipo=candidato.tipo.value,
            regra=candidato.regra,
            pagina_id=str(candidato.pagina.id),
        )
        return None
    return evidencia


def montar_fato(
    processo_id: UUID,
    tipo: TipoFato,
    valor: Any,
    evidencias: Sequence[Evidencia],
    confianca: float,
    versao: str,
) -> Fato:
    """Fato com id derivado da chave natural (processo, tipo, valor, evidências).

    Args:
        processo_id: Processo.
        tipo: Tipo de fato.
        valor: Valor final (com ``reu_id`` quando por réu).
        evidencias: Ao menos uma evidência.
        confianca: Confiança.
        versao: Versão do extrator.

    Returns:
        Fato com status ``automatico`` e ``extraido_por = "regra"``.
    """
    ordenadas = sorted(evidencias, key=lambda e: (str(e.pagina_id), e.inicio))
    chave = "|".join(
        [str(processo_id), tipo.value, _chave_valor(valor), *(str(e.id) for e in ordenadas)]
    )
    return Fato(
        id=uuid5(NAMESPACE, chave),
        processo_id=processo_id,
        tipo=tipo,
        valor=valor,
        evidencias=tuple(ordenadas),
        extraido_por=EXTRAIDO_POR,
        versao_extrator=versao,
        confianca=confianca,
        status=StatusFato.AUTOMATICO,
    )


def _agrupar(
    aceitos: list[tuple[Candidato, Evidencia]], ids_reu: Mapping[str, UUID]
) -> dict[tuple[TipoFato, str], tuple[Any, list[Evidencia], float, str | None]]:
    grupos: dict[tuple[TipoFato, str], tuple[Any, list[Evidencia], float, str | None]] = {}
    for candidato, evidencia in aceitos:
        valor = _valor_final(candidato, ids_reu)
        chave = (candidato.tipo, _chave_valor(valor))
        _, lista, confianca, reu = grupos.get(chave, (valor, [], 0.0, candidato.reu))
        if all(e.id != evidencia.id for e in lista):
            lista.append(evidencia)
        grupos[chave] = (valor, lista, max(confianca, candidato.confianca), reu)
    return grupos


def _marcar_conflitos(
    grupos: dict[tuple[TipoFato, str], tuple[Any, list[Evidencia], float, str | None]],
    resultado: ResultadoExtracao,
) -> dict[tuple[TipoFato, str], float]:
    por_tipo = Counter((tipo, reu) for (tipo, _), (_, _, _, reu) in grupos.items())
    ajustes: dict[tuple[TipoFato, str], float] = {}
    for chave, (_, _, confianca, reu) in grupos.items():
        tipo = chave[0]
        if tipo not in TIPOS_MULTIPLOS and por_tipo[(tipo, reu)] > 1:
            ajustes[chave] = round(confianca * FATOR_CONFLITO, 3)
            resultado.conflitos.append(tipo.value)
    return ajustes


def extrair_fatos(
    processo_id: UUID,
    pecas: Sequence[PecaTexto],
    reus_qualificados: Sequence[ReuQualificado] = (),
    ids_reu: Mapping[str, UUID] | None = None,
    padroes: Padroes | None = None,
) -> ResultadoExtracao:
    """Extrai os fatos de um processo a partir das peças com texto.

    Args:
        processo_id: Processo.
        pecas: Peças vigentes com as páginas.
        reus_qualificados: Réus identificados (para pseudônimo e recorte de nome).
        ids_reu: Id gravado de cada pseudônimo (fatos por réu levam ``reu_id``).
        padroes: Padrões (padrão: os YAML empacotados).

    Returns:
        Fatos e contagens.
    """
    padroes = padroes or padroes_padrao()
    ids = ids_reu or {}
    termos = reus.sensiveis(reus_qualificados)
    resultado = ResultadoExtracao()
    candidatos = _sem_reserva_desnecessaria(
        [c for peca in pecas for c in candidatos_da_peca(peca, padroes)]
    )
    resultado.candidatos = len(candidatos)
    aceitos: list[tuple[Candidato, Evidencia]] = []
    for candidato in candidatos:
        if candidato.por_reu:
            candidato = replace(candidato, reu=reus.reu_do_candidato(candidato, reus_qualificados))
        evidencia = _aceitar(candidato, termos, resultado)
        if evidencia is not None:
            aceitos.append((candidato, evidencia))
    grupos = _agrupar(aceitos, ids)
    ajustes = _marcar_conflitos(grupos, resultado)
    for chave, (valor, evidencias, confianca, _) in grupos.items():
        resultado.fatos.append(
            montar_fato(
                processo_id,
                chave[0],
                valor,
                evidencias,
                ajustes.get(chave, confianca),
                padroes.versao_extrator,
            )
        )
    return resultado
