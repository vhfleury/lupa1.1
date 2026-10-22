"""Operações de chave: carregador da DEK, chaves do gabinete, rotação e identidades dos réus.

- `carregador_sql`: lê `(gabinete_id, chave_dados_cifrada)` pela função `lupa_chave_processo`
  (SECURITY DEFINER, migração 0010) numa conexão própria; usado pelo contexto de cifra para
  abrir a DEK de um processo cujo campo foi lido sob a RLS da requisição ou do job.
- `criar_chaves_gabinete`: chave do envelope e chave das identidades no cofre.
- `rotacionar_gabinete`: versão nova da chave do gabinete e rewrap de todas as DEKs (o
  conteúdo dos autos não é tocado; a DEK não sai em claro no Vault).
- `cifrar_identidade`/`decifrar_identidade`: nome e documento do réu cifrados direto no Transit
  com a chave `lupa-gabinete-<id>-identidades` (7.6).
"""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from lupa.seguranca.cofre import Cofre, nome_chave_gabinete, nome_chave_identidades
from lupa.seguranca.contexto import Carregador, ChaveIndisponivelError

PREFIXOS_TOKEN_COFRE = ("vault:v", "mem:v")


def carregador_sql(fabrica: Callable[[], Session]) -> Carregador:
    """Cria o carregador da DEK cifrada a partir de uma fábrica de sessões.

    Args:
        fabrica: Abre uma sessão nova (conexão própria, fora da transação corrente).

    Returns:
        Função `processo_id -> (gabinete_id, chave_dados_cifrada)`.
    """

    def _carregar(processo_id: UUID) -> tuple[UUID, str | None]:
        with fabrica() as session:
            linha = session.execute(
                text("SELECT gabinete_id, chave FROM lupa_chave_processo(:id)"),
                {"id": processo_id},
            ).first()
        if linha is None:
            raise ChaveIndisponivelError(str(processo_id))
        return linha[0], linha[1]

    return _carregar


def criar_chaves_gabinete(cofre: Cofre, gabinete_id: UUID) -> None:
    """Cria (idempotente) as duas chaves Transit do gabinete.

    Args:
        cofre: Cofre.
        gabinete_id: Gabinete.
    """
    cofre.criar_chave(nome_chave_gabinete(gabinete_id))
    cofre.criar_chave(nome_chave_identidades(gabinete_id))


def rotacionar_gabinete(session: Session, cofre: Cofre, gabinete_id: UUID) -> int:
    """Rotaciona a chave do gabinete e recifra (rewrap) a DEK de cada processo dele.

    Args:
        session: Sessão com permissão de UPDATE em `processo` do gabinete.
        cofre: Cofre.
        gabinete_id: Gabinete.

    Returns:
        Quantidade de DEKs recifradas.
    """
    from lupa.dominio.tabelas import ProcessoTabela

    nome = nome_chave_gabinete(gabinete_id)
    cofre.rotacionar(nome)
    processos = session.scalars(
        select(ProcessoTabela).where(
            ProcessoTabela.gabinete_id == gabinete_id,
            ProcessoTabela.chave_dados_cifrada.is_not(None),
        )
    ).all()
    for processo in processos:
        assert processo.chave_dados_cifrada is not None  # noqa: S101 - filtrado acima
        processo.chave_dados_cifrada = cofre.recifrar(nome, processo.chave_dados_cifrada)
    session.flush()
    return len(processos)


def identidade_cifrada(valor: str | None) -> bool:
    """Diz se o valor já é token do cofre.

    Args:
        valor: Valor da coluna.

    Returns:
        Verdadeiro se começa com `vault:v` ou `mem:v`.
    """
    return valor is not None and valor.startswith(PREFIXOS_TOKEN_COFRE)


def cifrar_identidade(cofre: Cofre, gabinete_id: UUID, valor: str | None) -> str | None:
    """Cifra nome ou documento do réu com a chave de identidades do gabinete.

    Args:
        cofre: Cofre.
        gabinete_id: Gabinete.
        valor: Texto em claro (ou None).

    Returns:
        Token do cofre (ou None).
    """
    if valor is None or identidade_cifrada(valor):
        return valor
    nome = nome_chave_identidades(gabinete_id)
    cofre.criar_chave(nome)
    return cofre.cifrar(nome, valor.encode())


def decifrar_identidade(cofre: Cofre, gabinete_id: UUID, valor: str | None) -> str | None:
    """Decifra nome ou documento do réu.

    Args:
        cofre: Cofre.
        gabinete_id: Gabinete.
        valor: Token do cofre (ou None; valor legado em claro volta como está).

    Returns:
        Texto em claro (ou None).
    """
    if valor is None or not identidade_cifrada(valor):
        return valor
    return cofre.decifrar(nome_chave_identidades(gabinete_id), valor).decode()
