"""Persistência de réus, fatos e achados da ingestão (Etapas 4F.5, 4F.6 e 4F.7).

Tudo roda na transação do chamador (um lote por processo): se algo falha, nada fica pela
metade. Fatos têm id derivado da chave natural (processo, tipo, valor, evidência), então
regravar a mesma extração não duplica. Fatos automáticos de outra versão do extrator são
apagados antes de gravar a versão nova, exceto os que têm anotação ou foram substituídos por
correção humana; fatos confirmados e corrigidos nunca são tocados. Achados são imutáveis: uma
execução do catálogo só grava o achado de uma validação quando ele difere do último gravado.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session, aliased

from lupa.dominio.enums import OrigemPeca, StatusFato, TipoPeca
from lupa.dominio.esquemas import Achado, Fato
from lupa.dominio.repositorios import listar_achados, salvar_achado, salvar_fato
from lupa.dominio.tabelas import (
    AnotacaoTabela,
    ArquivoTabela,
    FatoTabela,
    PaginaTabela,
    PecaTabela,
    ReuIdentidadeTabela,
    ReuTabela,
)
from lupa.ingestao.eventos.fatos import EXTRAIDO_POR
from lupa.ingestao.eventos.modelo import PaginaTexto, PecaTexto, ReuQualificado
from lupa.seguranca.chaves import cifrar_identidade
from lupa.seguranca.contexto import obter_cofre


def pecas_do_processo(session: Session, processo_id: UUID) -> list[PecaTexto]:
    """Peças vigentes de todos os arquivos do processo, com o texto original das páginas.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        processo_id: Processo.

    Returns:
        Peças em ordem de envio do arquivo e de página.
    """
    pecas = session.execute(
        select(PecaTabela)
        .join(ArquivoTabela, ArquivoTabela.id == PecaTabela.arquivo_id)
        .where(ArquivoTabela.processo_id == processo_id, PecaTabela.vigente.is_(True))
        .order_by(ArquivoTabela.enviado_em, ArquivoTabela.id, PecaTabela.pagina_inicial)
    ).scalars()
    lista = list(pecas)
    arquivos = {p.arquivo_id for p in lista}
    paginas: dict[tuple[UUID, int], PaginaTexto] = {}
    for linha in session.execute(
        select(
            PaginaTabela.arquivo_id,
            PaginaTabela.id,
            PaginaTabela.numero,
            PaginaTabela.texto,
            PaginaTabela.origem_arquivo,
            PaginaTabela.pagina_origem,
        ).where(PaginaTabela.arquivo_id.in_(arquivos))
    ):
        paginas[(linha[0], linha[2])] = PaginaTexto(
            linha[1], linha[2], linha[3], linha[4], linha[5]
        )
    return [
        PecaTexto(
            TipoPeca(p.tipo),
            OrigemPeca(p.origem),
            tuple(
                paginas[(p.arquivo_id, n)]
                for n in range(p.pagina_inicial, p.pagina_final + 1)
                if (p.arquivo_id, n) in paginas
            ),
        )
        for p in lista
    ]


def gravar_reus(
    session: Session, gabinete_id: UUID, processo_id: UUID, reus: Sequence[ReuQualificado]
) -> dict[str, UUID]:
    """Grava os réus (pseudônimo) e a identidade separada; idempotente por pseudônimo.

    Args:
        session: Sessão com transação aberta.
        gabinete_id: Gabinete.
        processo_id: Processo.
        reus: Réus identificados.

    Returns:
        Id de cada pseudônimo.
    """
    existentes = {
        r.pseudonimo: r.id
        for r in session.scalars(select(ReuTabela).where(ReuTabela.processo_id == processo_id))
    }
    cofre = obter_cofre()
    for reu in reus:
        if reu.pseudonimo in existentes:
            continue
        linha = ReuTabela(
            id=uuid4(), gabinete_id=gabinete_id, processo_id=processo_id, pseudonimo=reu.pseudonimo
        )
        session.add(linha)
        session.flush()
        session.add(
            ReuIdentidadeTabela(
                reu_id=linha.id,
                gabinete_id=gabinete_id,
                nome=cifrar_identidade(cofre, gabinete_id, reu.nome),
                documento=cifrar_identidade(cofre, gabinete_id, reu.documento),
            )
        )
        existentes[reu.pseudonimo] = linha.id
    session.flush()
    return existentes


def remover_fatos_obsoletos(session: Session, processo_id: UUID, versao: str) -> int:
    """Apaga fatos automáticos da regra gravados por outra versão do extrator.

    Ficam os fatos com anotação, os substituídos por correção humana e os não automáticos.

    Args:
        session: Sessão com transação aberta.
        processo_id: Processo.
        versao: Versão corrente do extrator de eventos.

    Returns:
        Quantidade apagada.
    """
    corretor = aliased(FatoTabela)
    resultado = session.execute(
        delete(FatoTabela)
        .where(
            FatoTabela.processo_id == processo_id,
            FatoTabela.status == StatusFato.AUTOMATICO.value,
            FatoTabela.extraido_por == EXTRAIDO_POR,
            FatoTabela.versao_extrator != versao,
            ~exists().where(AnotacaoTabela.fato_id == FatoTabela.id),
            ~exists().where(corretor.substitui_fato_id == FatoTabela.id),
        )
        .returning(FatoTabela.id)
    )
    return len(resultado.all())


def versoes_gravadas(session: Session, processo_id: UUID) -> set[str]:
    """Versões do extrator de eventos com fatos automáticos gravados no processo.

    Args:
        session: Sessão com transação aberta.
        processo_id: Processo.

    Returns:
        Versões.
    """
    consulta = select(FatoTabela.versao_extrator).where(
        FatoTabela.processo_id == processo_id, FatoTabela.extraido_por == EXTRAIDO_POR
    )
    return set(session.scalars(consulta.distinct()))


def gravar_fatos(session: Session, fatos: Sequence[Fato]) -> int:
    """Grava os fatos que ainda não existem (idempotente pela chave natural do id).

    Args:
        session: Sessão com transação aberta.
        fatos: Fatos extraídos.

    Returns:
        Quantidade gravada nesta chamada.
    """
    if not fatos:
        return 0
    ids = [f.id for f in fatos]
    existentes = set(session.scalars(select(FatoTabela.id).where(FatoTabela.id.in_(ids))))
    novos = [f for f in fatos if f.id not in existentes]
    for fato in novos:
        salvar_fato(session, fato)
    session.flush()
    return len(novos)


def _chave(achado: Achado) -> tuple[str, str]:
    return achado.validacao, str(achado.valores.get("reu_id") or "")


def _assinatura(achado: Achado) -> tuple[str, str, str, Any]:
    return (achado.versao_catalogo, achado.resultado.value, achado.explicacao, achado.valores)


def achados_vigentes(session: Session, processo_id: UUID) -> list[Achado]:
    """Último achado gravado de cada validação do processo.

    Args:
        session: Sessão com transação aberta.
        processo_id: Processo.

    Returns:
        Achados, um por validação (e por réu, quando há mais de um), em ordem de nome.
    """
    ultimos: dict[tuple[str, str], Achado] = {}
    for achado in listar_achados(session, processo_id):
        ultimos[_chave(achado)] = achado
    return [ultimos[chave] for chave in sorted(ultimos)]


def gravar_achados(session: Session, processo_id: UUID, achados: Sequence[Achado]) -> int:
    """Grava os achados que mudaram em relação ao último de cada validação.

    Args:
        session: Sessão com transação aberta.
        processo_id: Processo.
        achados: Achados do catálogo (já vinculados ao processo).

    Returns:
        Quantidade gravada.
    """
    vigentes = {_chave(a): a for a in achados_vigentes(session, processo_id)}
    gravados = 0
    for achado in achados:
        anterior = vigentes.get(_chave(achado))
        if anterior is not None and _assinatura(anterior) == _assinatura(achado):
            continue
        salvar_achado(session, achado)
        gravados += 1
    session.flush()
    return gravados
