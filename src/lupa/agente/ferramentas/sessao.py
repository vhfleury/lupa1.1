"""Estado de uma chamada ao agente, compartilhado pelas ferramentas por fechamento.

O par (gabinete, processo) vem do processo autorizado por `exige_processo` e fica aqui; as
ferramentas nunca o recebem do modelo. Também ficam aqui o delimitador da chamada, o
pseudonimizador do processo, o contador de páginas originais e as saídas de ferramenta (para o
hash de entrada registrado em `chamada_modelo`).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from lupa.agente.contexto import Delimitador, Pseudonimizador
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.dominio.tabelas import ArquivoTabela, PaginaTabela, PecaTabela

Registrador = Callable[[AcaoAuditoria, str, str], None]
"""Grava um evento de auditoria: `(acao, objeto_tipo, objeto_id)`."""


@dataclass
class SessaoAgente:
    """Contexto de uma chamada; criado por requisição.

    Attributes:
        session: Sessão do banco da requisição (RLS do gabinete).
        gabinete_id: Gabinete do processo.
        processo_id: Processo da conversa.
        materia: Matéria do processo (catálogo de validações).
        numero_cnj: Número do processo.
        pseudonimizador: Pseudonimizador dos réus do processo.
        delimitador: Delimitador aleatório da chamada.
        registrar: Grava evento de auditoria.
        referencia: Data de referência das validações.
        limite_paginas_originais: Máximo de `ler_pagina_original` por conversa.
        paginas_originais: Quantas já foram usadas na conversa.
        saidas: Saídas das ferramentas nesta chamada.
    """

    session: Session
    gabinete_id: UUID
    processo_id: UUID
    materia: str
    numero_cnj: str
    pseudonimizador: Pseudonimizador
    delimitador: Delimitador
    registrar: Registrador
    referencia: date
    limite_paginas_originais: int = 20
    paginas_originais: int = 0
    saidas: list[str] = field(default_factory=list)


class PaginaForaDoProcessoError(LookupError):
    """Página inexistente ou de outro processo."""


def _uuid(valor: Any) -> UUID | None:
    try:
        return UUID(str(valor))
    except ValueError:
        return None


def arquivos_do_processo(sessao: SessaoAgente) -> list[UUID]:
    """Arquivos do processo em ordem de envio.

    Args:
        sessao: Sessão do agente.

    Returns:
        Ids.
    """
    consulta = (
        select(ArquivoTabela.id)
        .where(ArquivoTabela.processo_id == sessao.processo_id)
        .order_by(ArquivoTabela.enviado_em, ArquivoTabela.id)
    )
    return list(sessao.session.scalars(consulta))


def _por_id(sessao: SessaoAgente, pagina_id: UUID) -> PaginaTabela:
    consulta = (
        select(PaginaTabela)
        .join(ArquivoTabela, ArquivoTabela.id == PaginaTabela.arquivo_id)
        .where(PaginaTabela.id == pagina_id, ArquivoTabela.processo_id == sessao.processo_id)
    )
    pagina = sessao.session.scalar(consulta)
    if pagina is None:
        raise PaginaForaDoProcessoError("página não pertence a este processo")
    return pagina


def _por_numero(sessao: SessaoAgente, numero: int, arquivo: UUID | None) -> PaginaTabela:
    arquivos = arquivos_do_processo(sessao)
    if arquivo is None:
        if len(arquivos) != 1:
            raise PaginaForaDoProcessoError("informe arquivo_id: o processo tem mais de um arquivo")
        arquivo = arquivos[0]
    if arquivo not in arquivos:
        raise PaginaForaDoProcessoError("arquivo não pertence a este processo")
    consulta = select(PaginaTabela).where(
        PaginaTabela.arquivo_id == arquivo, PaginaTabela.numero == numero
    )
    pagina = sessao.session.scalar(consulta)
    if pagina is None:
        raise PaginaForaDoProcessoError("página não encontrada neste processo")
    return pagina


def resolver_pagina(sessao: SessaoAgente, argumentos: dict[str, Any]) -> PaginaTabela:
    """Página pedida pelo modelo, sempre dentro do processo da sessão.

    Args:
        sessao: Sessão do agente.
        argumentos: `pagina_id`, ou `numero` (com `arquivo_id` se houver mais de um arquivo).

    Returns:
        A página.

    Raises:
        PaginaForaDoProcessoError: Página de outro processo, inexistente ou pedido ambíguo.
    """
    if argumentos.get("pagina_id"):
        pagina_id = _uuid(argumentos["pagina_id"])
        if pagina_id is None:
            raise PaginaForaDoProcessoError("pagina_id inválido")
        return _por_id(sessao, pagina_id)
    numero = argumentos.get("numero")
    if not isinstance(numero, int) or isinstance(numero, bool):
        raise PaginaForaDoProcessoError("informe pagina_id ou numero")
    arquivo = _uuid(argumentos["arquivo_id"]) if argumentos.get("arquivo_id") else None
    return _por_numero(sessao, numero, arquivo)


def peca_da_pagina(sessao: SessaoAgente, pagina: PaginaTabela) -> tuple[str, str]:
    """Tipo e origem da peça vigente que contém a página.

    Args:
        sessao: Sessão do agente.
        pagina: Página.

    Returns:
        `(tipo, origem)`; `("desconhecido", "desconhecida")` sem peça.
    """
    consulta = (
        select(PecaTabela.tipo, PecaTabela.origem)
        .where(
            PecaTabela.arquivo_id == pagina.arquivo_id,
            PecaTabela.vigente.is_(True),
            PecaTabela.pagina_inicial <= pagina.numero,
            PecaTabela.pagina_final >= pagina.numero,
        )
        .order_by(PecaTabela.confianca.desc(), PecaTabela.id)
        .limit(1)
    )
    linha = sessao.session.execute(consulta).first()
    return (str(linha[0]), str(linha[1])) if linha else ("desconhecido", "desconhecida")


def flags_ligadas(flags: dict[str, Any]) -> list[str]:
    """Flags de saneamento ligadas na página.

    Args:
        flags: `pagina.flags`.

    Returns:
        Nomes em ordem.
    """
    return sorted(k for k, v in (flags or {}).items() if v)
