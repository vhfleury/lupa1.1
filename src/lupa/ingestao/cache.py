"""Cache do resultado intermediário entre uploads do mesmo arquivo (Etapa 4F.8).

As páginas extraídas dependem só dos bytes do arquivo e da versão do extrator de páginas. Se
outro arquivo do MESMO gabinete, com o mesmo SHA-256, já tem todas as páginas gravadas na versão
corrente, elas são copiadas para o arquivo novo em vez de extraídas de novo (OCR incluído). A
busca filtra pelo gabinete explicitamente, além da RLS: cache nunca atravessa gabinetes. O
índice (peças) é recalculado das páginas copiadas, porque é determinístico e custa segundos;
correções manuais de peça não são herdadas por outro processo.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lupa.dominio.tabelas import ArquivoTabela, PaginaTabela
from lupa.ingestao import repositorio
from lupa.ingestao.repositorio import Lease

PAGINAS_POR_INSERT = 500
COLUNAS_COPIADAS = (
    "numero",
    "tipo",
    "texto",
    "flags",
    "sinais",
    "coordenadas",
    "extracao",
    "texto_nativo",
    "texto_ocr",
    "versao_extrator",
    "origem_arquivo",
    "pagina_origem",
    "texto_normalizado",
    "trechos_ocultos",
    "trechos_suspeitos",
)


def fonte_em_cache(
    session: Session,
    gabinete_id: UUID,
    arquivo_id: UUID,
    sha256: str,
    versao_extrator: str,
    total_paginas: int,
) -> UUID | None:
    """Outro arquivo do gabinete com o mesmo conteúdo e todas as páginas na versão corrente.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        gabinete_id: Gabinete do job.
        arquivo_id: Arquivo que vai ser extraído.
        sha256: Hash do arquivo.
        versao_extrator: Versão corrente do extrator de páginas.
        total_paginas: Páginas esperadas.

    Returns:
        Id do arquivo de origem, ou None.
    """
    if total_paginas <= 0:
        return None
    consulta = (
        select(ArquivoTabela.id)
        .join(PaginaTabela, PaginaTabela.arquivo_id == ArquivoTabela.id)
        .where(
            ArquivoTabela.gabinete_id == gabinete_id,
            ArquivoTabela.sha256 == sha256,
            ArquivoTabela.id != arquivo_id,
            PaginaTabela.versao_extrator == versao_extrator,
        )
        .group_by(ArquivoTabela.id)
        .having(func.count(PaginaTabela.id) == total_paginas)
        .limit(1)
    )
    return session.scalar(consulta)


def copiar_paginas(session: Session, lease: Lease, origem_id: UUID, destino_id: UUID) -> int:
    """Copia as páginas de um arquivo para outro, sob o lease do job de destino.

    Args:
        session: Sessão com transação aberta.
        lease: Lease do job de destino.
        origem_id: Arquivo com as páginas.
        destino_id: Arquivo que recebe a cópia.

    Returns:
        Páginas copiadas.
    """
    colunas = [getattr(PaginaTabela, c) for c in COLUNAS_COPIADAS]
    linhas: list[dict[str, Any]] = [
        dict(zip(COLUNAS_COPIADAS, linha, strict=True))
        for linha in session.execute(
            select(*colunas)
            .where(PaginaTabela.arquivo_id == origem_id)
            .order_by(PaginaTabela.numero)
        )
    ]
    return sum(
        repositorio.gravar_paginas(session, lease, destino_id, linhas[i : i + PAGINAS_POR_INSERT])
        for i in range(0, len(linhas), PAGINAS_POR_INSERT)
    )
