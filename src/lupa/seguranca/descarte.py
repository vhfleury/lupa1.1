"""Exclusão criptográfica de um processo (Etapa 7.7).

Ordem: (1) `lupa_descartar_processo` apaga, na transação, páginas, evidências, fatos, achados,
peças, réus e identidades, conversas, mensagens, chamadas ao modelo, jobs e arquivos, zera a DEK
cifrada e deixa o processo como tombstone `descartado`; (2) a DEK sai do contexto de cifra;
(3) os objetos do processo (originais, entradas de ZIP e cache de PNG) são apagados do storage;
(4) o evento `processo_descartado` entra na cadeia de auditoria do gabinete com o SHA-256 da DEK
cifrada apagada. Sem a DEK cifrada, nenhuma cópia remanescente (backup, réplica) do conteúdo é
legível, nem com a chave do gabinete.
"""

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lupa.ingestao.storage import ObjectStorage
from lupa.seguranca.contexto import esquecer_processo

PREFIXO_RENDERIZACAO = "renderizacao/"


@dataclass(frozen=True)
class ResultadoDescarte:
    """Resumo do descarte, sem conteúdo.

    Attributes:
        processo_id: Processo descartado.
        hash_chave: SHA-256 da DEK cifrada apagada (ou None se já não havia).
        objetos_apagados: Objetos removidos do storage.
    """

    processo_id: UUID
    hash_chave: str | None
    objetos_apagados: int


def objetos_do_processo(storage: ObjectStorage, gabinete_id: UUID, processo_id: UUID) -> list[str]:
    """Chaves de todos os objetos do processo (originais, entradas e cache de renderização).

    Args:
        storage: Storage.
        gabinete_id: Gabinete.
        processo_id: Processo.

    Returns:
        Chaves.
    """
    base = f"gabinete/{gabinete_id}/processo/{processo_id}/"
    cache = [c for c in storage.listar(PREFIXO_RENDERIZACAO) if f"/{base}" in c]
    return storage.listar(base) + cache


def descartar(
    session: Session, storage: ObjectStorage, gabinete_id: UUID, processo_id: UUID
) -> ResultadoDescarte:
    """Descarta o processo: banco, DEK e objetos. A auditoria fica com quem chama.

    Args:
        session: Sessão com o contexto de RLS do ator (gabinete ou administrador).
        storage: Storage.
        gabinete_id: Gabinete do processo.
        processo_id: Processo.

    Returns:
        Resumo do descarte.
    """
    chave = session.execute(
        text("SELECT lupa_descartar_processo(:id)"), {"id": processo_id}
    ).scalar()
    esquecer_processo(processo_id)
    objetos = objetos_do_processo(storage, gabinete_id, processo_id)
    for objeto in objetos:
        storage.apagar(objeto)
    session.expire_all()
    hash_chave = hashlib.sha256(chave.encode()).hexdigest() if chave else None
    return ResultadoDescarte(processo_id, hash_chave, len(objetos))
