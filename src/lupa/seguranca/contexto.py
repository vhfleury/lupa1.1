"""Contexto de cifra: as DEKs em claro do escopo corrente (requisição, job ou script).

As DEKs abertas ficam só neste objeto, em memória, e somem com ele no fim do escopo. O
middleware da API cria um contexto por requisição (`lupa.api.middleware`); o worker cria um por
job. Fora desses escopos (testes, scripts) vale um contexto padrão do processo Python.

Leitura: o campo cifrado traz o id do processo no cabeçalho; a DEK vem do cache do contexto ou
do `carregador` (que lê a DEK cifrada do banco e abre no cofre). Gravação: usa o processo
`atual`, definido por `ativar_processo` (rota com `exige_processo`, job do worker) ou pelo
último processo criado no escopo. Nunca registre DEK em log.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import UUID

from lupa.seguranca.cofre import Cofre, nome_chave_gabinete
from lupa.seguranca.envelope import gerar_dek

Carregador = Callable[[UUID], tuple[UUID, str | None]]


class ChaveIndisponivelError(LookupError):
    """Não há DEK para o processo (sem contexto, processo descartado ou sem chave)."""


@dataclass
class ContextoCifra:
    """DEKs abertas de um escopo.

    Attributes:
        deks: DEK em claro por processo.
        atual: Processo cujas gravações são cifradas.
        carregador: `processo_id -> (gabinete_id, dek_cifrada)` lido do banco (ou None).
    """

    deks: dict[UUID, bytes] = field(default_factory=dict)
    atual: UUID | None = None
    carregador: Carregador | None = None
    trava: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __repr__(self) -> str:
        """Nunca mostra as chaves.

        Returns:
            Só a quantidade de DEKs e o processo atual.
        """
        return f"ContextoCifra(deks={len(self.deks)}, atual={self.atual})"


_PADRAO = ContextoCifra()
_CONTEXTO: ContextVar[ContextoCifra | None] = ContextVar("lupa_contexto_cifra", default=None)
_COFRE: list[Cofre] = []
_CARREGADOR_PADRAO: list[Carregador] = []


def definir_cofre(cofre: Cofre) -> None:
    """Registra o cofre usado por este processo Python (API, worker, scripts, testes).

    Args:
        cofre: Cofre de chaves.
    """
    _COFRE[:] = [cofre]


def obter_cofre() -> Cofre:
    """Cofre registrado; sem registro, cria pelo `LUPA_COFRE_BACKEND` da configuração.

    Returns:
        O cofre.
    """
    if not _COFRE:
        from lupa.config import get_settings
        from lupa.seguranca.cofre import criar_cofre

        _COFRE.append(criar_cofre(get_settings()))
    return _COFRE[0]


def definir_carregador_padrao(carregador: Carregador | None) -> None:
    """Carregador do contexto padrão (fora de requisição e de job).

    Args:
        carregador: Leitor da DEK cifrada, ou None para remover.
    """
    _CARREGADOR_PADRAO[:] = [carregador] if carregador else []
    _PADRAO.carregador = carregador


def contexto_atual() -> ContextoCifra:
    """Contexto do escopo corrente (ou o padrão).

    Returns:
        O contexto.
    """
    return _CONTEXTO.get() or _PADRAO


@contextmanager
def contexto_cifra(carregador: Carregador | None = None) -> Iterator[ContextoCifra]:
    """Abre um escopo novo; ao sair, as DEKs abertas são descartadas.

    Args:
        carregador: Leitor da DEK cifrada pelo id do processo.

    Yields:
        O contexto novo.
    """
    contexto = ContextoCifra(carregador=carregador)
    token = _CONTEXTO.set(contexto)
    try:
        yield contexto
    finally:
        contexto.deks.clear()
        contexto.atual = None
        _CONTEXTO.reset(token)


def limpar_contexto_padrao() -> None:
    """Esquece as DEKs do contexto padrão (testes e fim de script)."""
    _PADRAO.deks.clear()
    _PADRAO.atual = None


def abrir_dek(cofre: Cofre, gabinete_id: UUID, dek_cifrada: str) -> bytes:
    """Abre a DEK com a chave do gabinete no cofre.

    Args:
        cofre: Cofre.
        gabinete_id: Gabinete dono do processo.
        dek_cifrada: Token de `processo.chave_dados_cifrada`.

    Returns:
        DEK em claro.
    """
    return cofre.decifrar(nome_chave_gabinete(gabinete_id), dek_cifrada)


def nova_dek(cofre: Cofre, gabinete_id: UUID) -> tuple[bytes, str]:
    """Gera a DEK de um processo novo e a cifra com a chave do gabinete (criada se faltar).

    Args:
        cofre: Cofre.
        gabinete_id: Gabinete do processo.

    Returns:
        DEK em claro e token para `processo.chave_dados_cifrada`.
    """
    nome = nome_chave_gabinete(gabinete_id)
    cofre.criar_chave(nome)
    dek = gerar_dek()
    return dek, cofre.cifrar(nome, dek)


def registrar_dek(processo_id: UUID, dek: bytes, *, atual: bool = True) -> None:
    """Guarda a DEK aberta no contexto corrente.

    Args:
        processo_id: Processo.
        dek: DEK em claro.
        atual: Se o processo passa a ser o das gravações.
    """
    contexto = contexto_atual()
    with contexto.trava:
        contexto.deks[processo_id] = dek
        if atual:
            contexto.atual = processo_id


def ativar_processo(processo_id: UUID, gabinete_id: UUID, dek_cifrada: str | None) -> None:
    """Abre a DEK do processo e o torna o processo das gravações do escopo.

    Args:
        processo_id: Processo.
        gabinete_id: Gabinete do processo.
        dek_cifrada: `processo.chave_dados_cifrada`.

    Raises:
        ChaveIndisponivelError: Processo sem chave (descartado).
    """
    contexto = contexto_atual()
    if processo_id not in contexto.deks:
        if dek_cifrada is None:
            raise ChaveIndisponivelError(str(processo_id))
        registrar_dek(processo_id, abrir_dek(obter_cofre(), gabinete_id, dek_cifrada))
    contexto.atual = processo_id


def esquecer_processo(processo_id: UUID) -> None:
    """Remove a DEK do processo do contexto corrente e do padrão (descarte).

    Args:
        processo_id: Processo.
    """
    for contexto in {id(contexto_atual()): contexto_atual(), id(_PADRAO): _PADRAO}.values():
        contexto.deks.pop(processo_id, None)
        if contexto.atual == processo_id:
            contexto.atual = None


def dek_de(processo_id: UUID) -> bytes:
    """DEK do processo: do cache do contexto ou pelo carregador.

    Args:
        processo_id: Processo (do cabeçalho do campo cifrado).

    Returns:
        DEK em claro.

    Raises:
        ChaveIndisponivelError: Sem DEK no contexto e sem carregador, ou processo sem chave.
    """
    contexto = contexto_atual()
    dek = contexto.deks.get(processo_id)
    if dek is not None:
        return dek
    carregador = contexto.carregador or (_CARREGADOR_PADRAO[0] if _CARREGADOR_PADRAO else None)
    if carregador is None:
        raise ChaveIndisponivelError(str(processo_id))
    gabinete_id, dek_cifrada = carregador(processo_id)
    if dek_cifrada is None:
        raise ChaveIndisponivelError(str(processo_id))
    dek = abrir_dek(obter_cofre(), gabinete_id, dek_cifrada)
    registrar_dek(processo_id, dek, atual=False)
    return dek


def dek_para_gravar() -> tuple[UUID, bytes]:
    """Processo e DEK das gravações do escopo.

    Returns:
        `(processo_id, dek)`.

    Raises:
        ChaveIndisponivelError: Nenhum processo ativo no escopo.
    """
    contexto = contexto_atual()
    if contexto.atual is None:
        raise ChaveIndisponivelError("nenhum processo ativo para cifrar")
    return contexto.atual, dek_de(contexto.atual)
