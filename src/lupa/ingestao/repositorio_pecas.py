"""Persistência das peças e do índice do processo (Etapas 4E.7, 4E.8 e 4E.10).

Cada peça é uma linha de `peca` ligada ao arquivo. A reclassificação manual nunca altera a
classificação gravada: grava linha nova (`metodo = manual`, `substitui_peca_id` apontando a
anterior) e só marca a anterior como não vigente, de modo que o histórico fica inteiro e o
índice lê sempre as linhas vigentes.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from lupa.dominio.enums import MetodoClassificacao, OrigemPeca, TipoPeca
from lupa.dominio.tabelas import ArquivoTabela, EvidenciaTabela, PaginaTabela, PecaTabela
from lupa.ingestao.indice import PecaIndice, ResultadoIndice

CONFIANCA_MANUAL = 1.0


class ReclassificacaoInvalidaError(ValueError):
    """Pedido de reclassificação incoerente (fronteira fora da peça, peças não vizinhas)."""


def paginas_para_indice(session: Session, arquivo_id: UUID) -> list[dict[str, Any]]:
    """Páginas do arquivo com o que o índice precisa, em ordem.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        arquivo_id: Arquivo.

    Returns:
        `{id, numero, tipo, texto, coordenadas, flags, origem_arquivo, pagina_origem}`.
    """
    consulta = (
        select(
            PaginaTabela.id,
            PaginaTabela.numero,
            PaginaTabela.tipo,
            PaginaTabela.texto,
            PaginaTabela.coordenadas,
            PaginaTabela.flags,
            PaginaTabela.origem_arquivo,
            PaginaTabela.pagina_origem,
        )
        .where(PaginaTabela.arquivo_id == arquivo_id)
        .order_by(PaginaTabela.numero)
    )
    chaves = (
        "id", "numero", "tipo", "texto", "coordenadas", "flags", "origem_arquivo", "pagina_origem",
    )  # fmt: skip
    return [dict(zip(chaves, linha, strict=True)) for linha in session.execute(consulta)]


def tem_pecas(session: Session, arquivo_id: UUID) -> bool:
    """Se o arquivo já tem peças gravadas (automáticas ou manuais).

    Args:
        session: Sessão com transação aberta.
        arquivo_id: Arquivo.

    Returns:
        Verdadeiro se há ao menos uma linha em `peca`.
    """
    consulta = select(PecaTabela.id).where(PecaTabela.arquivo_id == arquivo_id).limit(1)
    return session.scalar(consulta) is not None


def _evidencia(
    session: Session, gabinete_id: UUID, ids_pagina: dict[int, UUID], evidencia: dict[str, Any]
) -> UUID:
    linha = EvidenciaTabela(
        id=uuid4(),
        gabinete_id=gabinete_id,
        pagina_id=ids_pagina[int(evidencia["pagina"])],
        trecho=evidencia["trecho"],
        hash_trecho=evidencia["hash_trecho"],
        inicio=int(evidencia["inicio"]),
        fim=int(evidencia["fim"]),
    )
    session.add(linha)
    session.flush()
    return linha.id


def _linha_peca(
    gabinete_id: UUID, arquivo_id: UUID, peca: PecaIndice, evidencia_id: UUID | None
) -> PecaTabela:
    return PecaTabela(
        id=uuid4(),
        gabinete_id=gabinete_id,
        arquivo_id=arquivo_id,
        tipo=peca.tipo.value,
        pagina_inicial=peca.pagina_inicial,
        pagina_final=peca.pagina_final,
        confianca=peca.confianca,
        metodo=peca.metodo.value,
        origem=peca.origem.value,
        data=peca.data,
        tipo_data=peca.tipo_data,
        data_evidencia_id=evidencia_id,
        vigente=True,
        flags=peca.flags,
        classificacao=peca.classificacao | {"ordem": peca.ordem},
    )


def gravar_indice(
    session: Session,
    gabinete_id: UUID,
    arquivo_id: UUID,
    paginas: list[dict[str, Any]],
    resultado: ResultadoIndice,
) -> int:
    """Grava os sinais de fronteira das páginas e as peças do índice.

    Idempotente: se o arquivo já tem peças (de uma execução anterior ou corrigidas pelo
    assessor), nada é regravado, para não sobrescrever correções manuais.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        gabinete_id: Gabinete.
        arquivo_id: Arquivo.
        paginas: Páginas de `paginas_para_indice` (mesma ordem de `resultado.sinais`).
        resultado: Índice montado.

    Returns:
        Quantidade de peças gravadas (0 se já havia peças).
    """
    if tem_pecas(session, arquivo_id):
        return 0
    if paginas:
        session.execute(
            update(PaginaTabela),
            [
                {"id": p["id"], "sinais_fronteira": s}
                for p, s in zip(paginas, resultado.sinais, strict=True)
            ],
        )
    ids_pagina = {int(p["numero"]): p["id"] for p in paginas}
    for peca in resultado.pecas:
        evidencia_id = (
            _evidencia(session, gabinete_id, ids_pagina, peca.evidencia_data)
            if peca.evidencia_data
            else None
        )
        session.add(_linha_peca(gabinete_id, arquivo_id, peca, evidencia_id))
    session.flush()
    return len(resultado.pecas)


def _serializar(peca: PecaTabela, evidencias: dict[UUID, EvidenciaTabela]) -> dict[str, Any]:
    evidencia = evidencias.get(peca.data_evidencia_id) if peca.data_evidencia_id else None
    return {
        "id": str(peca.id),
        "arquivo_id": str(peca.arquivo_id),
        "tipo": peca.tipo,
        "origem": peca.origem,
        "pagina_inicial": peca.pagina_inicial,
        "pagina_final": peca.pagina_final,
        "data": peca.data.isoformat() if peca.data else None,
        "tipo_data": peca.tipo_data,
        "evidencia_data": (
            {
                "id": str(evidencia.id),
                "pagina_id": str(evidencia.pagina_id),
                "trecho": evidencia.trecho,
                "inicio": evidencia.inicio,
                "fim": evidencia.fim,
                "hash_trecho": evidencia.hash_trecho,
            }
            if evidencia
            else None
        ),
        "confianca": peca.confianca,
        "metodo": peca.metodo,
        "vigente": peca.vigente,
        "substitui_peca_id": str(peca.substitui_peca_id) if peca.substitui_peca_id else None,
        "flags": peca.flags,
        "resumo_flags": resumo_flags(peca.flags),
    }


def resumo_flags(flags: dict[str, Any]) -> dict[str, Any]:
    """Resumo das flags da peça para o dossiê (4D.10): marcas da peça e páginas sinalizadas.

    Args:
        flags: `peca.flags` (`peca` e `paginas`).

    Returns:
        `{peca: [...], saneamento: {flag: páginas}, total_saneamento: n}`.
    """
    paginas = dict(flags.get("paginas") or {})
    return {
        "peca": sorted(k for k, v in dict(flags.get("peca") or {}).items() if v),
        "saneamento": paginas,
        "total_saneamento": sum(int(v) for v in paginas.values()),
    }


def _evidencias(session: Session, pecas: list[PecaTabela]) -> dict[UUID, EvidenciaTabela]:
    ids = [p.data_evidencia_id for p in pecas if p.data_evidencia_id]
    if not ids:
        return {}
    return {
        e.id: e for e in session.scalars(select(EvidenciaTabela).where(EvidenciaTabela.id.in_(ids)))
    }


def indice_processo(session: Session, processo_id: UUID) -> list[dict[str, Any]]:
    """Índice do processo: peças vigentes de todos os arquivos, em ordem.

    Ordem: arquivos pela data de envio, peças pela página inicial.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        processo_id: Processo.

    Returns:
        Peças serializadas, com `ordem` de 1 a N.
    """
    consulta = (
        select(PecaTabela)
        .join(ArquivoTabela, ArquivoTabela.id == PecaTabela.arquivo_id)
        .where(ArquivoTabela.processo_id == processo_id, PecaTabela.vigente.is_(True))
        .order_by(ArquivoTabela.enviado_em, ArquivoTabela.id, PecaTabela.pagina_inicial)
    )
    pecas = list(session.scalars(consulta))
    evidencias = _evidencias(session, pecas)
    return [
        {"ordem": ordem} | _serializar(peca, evidencias)
        for ordem, peca in enumerate(pecas, start=1)
    ]


def obter_peca(session: Session, processo_id: UUID, peca_id: UUID) -> PecaTabela | None:
    """Peça do processo (vigente ou não).

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        processo_id: Processo.
        peca_id: Peça.

    Returns:
        A peça, ou None se não existe ou é de outro processo.
    """
    consulta = (
        select(PecaTabela)
        .join(ArquivoTabela, ArquivoTabela.id == PecaTabela.arquivo_id)
        .where(PecaTabela.id == peca_id, ArquivoTabela.processo_id == processo_id)
    )
    return session.scalar(consulta)


def historico_peca(session: Session, peca: PecaTabela) -> list[dict[str, Any]]:
    """Versões anteriores da peça, da mais recente para a mais antiga.

    Args:
        session: Sessão com transação aberta.
        peca: Peça de partida.

    Returns:
        Peças substituídas, seguindo `substitui_peca_id` (e as unidas, em `classificacao`).
    """
    anteriores: list[PecaTabela] = []
    fila = [peca]
    vistos = {peca.id}
    while fila:
        atual = fila.pop(0)
        ids = [atual.substitui_peca_id] if atual.substitui_peca_id else []
        ids += [UUID(i) for i in (atual.classificacao or {}).get("substitui", [])]
        for anterior_id in ids:
            if anterior_id in vistos:
                continue
            vistos.add(anterior_id)
            anterior = session.get(PecaTabela, anterior_id)
            if anterior is not None:
                anteriores.append(anterior)
                fila.append(anterior)
    evidencias = _evidencias(session, anteriores)
    return [_serializar(p, evidencias) for p in anteriores]


def detalhar_peca(session: Session, peca: PecaTabela) -> dict[str, Any]:
    """Peça serializada com a classificação e o histórico de versões.

    Args:
        session: Sessão com transação aberta.
        peca: Peça.

    Returns:
        Peça, `classificacao` e `historico`.
    """
    base = _serializar(peca, _evidencias(session, [peca]))
    return base | {"classificacao": peca.classificacao, "historico": historico_peca(session, peca)}


@dataclass(frozen=True)
class PedidoReclassificacao:
    """O que o assessor pediu.

    Attributes:
        tipo: Novo tipo (na divisão, vale para a parte nova).
        origem: Nova origem (idem).
        dividir_em: Página (numeração do arquivo) em que começa a parte nova.
        unir_com: Peça vizinha a unir com esta.
    """

    tipo: TipoPeca | None = None
    origem: OrigemPeca | None = None
    dividir_em: int | None = None
    unir_com: UUID | None = None


def _copia(
    base: PecaTabela,
    inicial: int,
    final: int,
    substitui: list[PecaTabela],
    usuario_id: UUID | None,
    pagina_data: int | None,
    tipo: TipoPeca | None = None,
    origem: OrigemPeca | None = None,
) -> PecaTabela:
    data: date | None = base.data
    evidencia_id = base.data_evidencia_id
    if pagina_data is not None and not inicial <= pagina_data <= final:
        data, evidencia_id = None, None
    return PecaTabela(
        id=uuid4(),
        gabinete_id=base.gabinete_id,
        arquivo_id=base.arquivo_id,
        tipo=(tipo or TipoPeca(base.tipo)).value,
        pagina_inicial=inicial,
        pagina_final=final,
        confianca=CONFIANCA_MANUAL,
        metodo=MetodoClassificacao.MANUAL.value,
        origem=(origem or OrigemPeca(base.origem)).value,
        data=data,
        tipo_data=base.tipo_data if data else None,
        data_evidencia_id=evidencia_id,
        substitui_peca_id=substitui[0].id,
        vigente=True,
        flags={"peca": {}, "paginas": dict(base.flags.get("paginas") or {})},
        classificacao={
            "substitui": [str(p.id) for p in substitui],
            "corrigido_por": str(usuario_id) if usuario_id else None,
        },
    )


def _pagina_da_evidencia(session: Session, peca: PecaTabela) -> int | None:
    if peca.data_evidencia_id is None:
        return None
    consulta = (
        select(PaginaTabela.numero)
        .join(EvidenciaTabela, EvidenciaTabela.pagina_id == PaginaTabela.id)
        .where(EvidenciaTabela.id == peca.data_evidencia_id)
    )
    return session.scalar(consulta)


def reclassificar(
    session: Session,
    peca: PecaTabela,
    pedido: PedidoReclassificacao,
    usuario_id: UUID | None,
) -> list[PecaTabela]:
    """Aplica a correção do assessor gravando linhas novas e encerrando as anteriores.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        peca: Peça vigente a corrigir.
        pedido: Tipo, origem, divisão ou união.
        usuario_id: Quem corrigiu.

    Returns:
        As peças novas, em ordem de página.

    Raises:
        ReclassificacaoInvalidaError: Peça não vigente, divisão fora da peça, união com peça
            que não é vizinha, ou pedido vazio.
    """
    if not peca.vigente:
        raise ReclassificacaoInvalidaError("a peça já foi substituída")
    pagina_data = _pagina_da_evidencia(session, peca)
    if pedido.dividir_em is not None:
        novas = _dividir(peca, pedido, usuario_id, pagina_data)
        encerradas = [peca]
    elif pedido.unir_com is not None:
        outra = session.get(PecaTabela, pedido.unir_com)
        novas, encerradas = _unir(session, peca, outra, pedido, usuario_id)
    elif pedido.tipo is not None or pedido.origem is not None:
        novas = [
            _copia(peca, peca.pagina_inicial, peca.pagina_final, [peca], usuario_id,
                   pagina_data, pedido.tipo, pedido.origem)
        ]  # fmt: skip
        encerradas = [peca]
    else:
        raise ReclassificacaoInvalidaError("informe tipo, origem, dividir_em ou unir_com")
    for antiga in encerradas:
        antiga.vigente = False
    session.add_all(novas)
    session.flush()
    return novas


def _dividir(
    peca: PecaTabela,
    pedido: PedidoReclassificacao,
    usuario_id: UUID | None,
    pagina_data: int | None,
) -> list[PecaTabela]:
    corte = int(pedido.dividir_em or 0)
    if not peca.pagina_inicial < corte <= peca.pagina_final:
        raise ReclassificacaoInvalidaError("a divisão precisa cair dentro da peça")
    primeira = _copia(peca, peca.pagina_inicial, corte - 1, [peca], usuario_id, pagina_data)
    segunda = _copia(
        peca, corte, peca.pagina_final, [peca], usuario_id, pagina_data, pedido.tipo, pedido.origem
    )
    return [primeira, segunda]


def _unir(
    session: Session,
    peca: PecaTabela,
    outra: PecaTabela | None,
    pedido: PedidoReclassificacao,
    usuario_id: UUID | None,
) -> tuple[list[PecaTabela], list[PecaTabela]]:
    if outra is None or not outra.vigente or outra.arquivo_id != peca.arquivo_id:
        raise ReclassificacaoInvalidaError("a peça a unir não existe ou não está vigente")
    primeira, segunda = sorted((peca, outra), key=lambda p: p.pagina_inicial)
    if segunda.pagina_inicial != primeira.pagina_final + 1:
        raise ReclassificacaoInvalidaError("só peças vizinhas podem ser unidas")
    nova = _copia(
        primeira, primeira.pagina_inicial, segunda.pagina_final, [primeira, segunda], usuario_id,
        _pagina_da_evidencia(session, primeira), pedido.tipo, pedido.origem,
    )  # fmt: skip
    nova.flags = {
        "peca": {},
        "paginas": _somar(primeira.flags.get("paginas"), segunda.flags.get("paginas")),
    }
    return [nova], [primeira, segunda]


def _somar(a: dict[str, int] | None, b: dict[str, int] | None) -> dict[str, int]:
    total = dict(a or {})
    for chave, valor in (b or {}).items():
        total[chave] = total.get(chave, 0) + int(valor)
    return dict(sorted(total.items()))
