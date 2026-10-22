"""Rotas de achados, fatos e anotações do processo (Etapas 4F.7 e 6.7).

`GET /processos/{id}/achados` devolve o último achado de cada validação (com valores,
explicação e fatos usados) e o status do processo; `GET .../achados/historico` devolve todos os
achados já gravados (imutáveis), marcando os vigentes. `GET .../fatos` lista os fatos com as
evidências (arquivo, página, trecho) e a cadeia de correção. Leituras de conteúdo: auditadas
como `processo_aberto` (com `admin_acesso_conteudo` para o administrador).

`POST .../fatos/{fato_id}/corrigir` grava um fato NOVO (`corrigido` ou `confirmado`) ligado ao
original por `substitui_fato_id`, registra `fato_corrigido`, reexecuta o catálogo sobre os fatos
vigentes e grava só os achados que mudaram (os antigos ficam como histórico), registrando
`validacao_executada`. `POST .../anotacoes` grava uma nota sobre achado ou fato (`anotacao`).
Processo de outro gabinete responde 404 (`exige_processo`).
"""

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select

from lupa.acesso.autorizacao import AtorAutenticado, ContextoReq, SessaoBanco, exige_processo
from lupa.acesso.erros import (
    ConflitoError,
    DadosInvalidosError,
    NaoEncontradoError,
    PermissaoNegadaError,
)
from lupa.acesso.papeis import Permissao, pode
from lupa.acesso.servico import Ator, Contexto, auditar
from lupa.api.middleware import auditar_rota
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.dominio import correcoes
from lupa.dominio.enums import StatusFato
from lupa.dominio.repositorios import listar_achados, listar_fatos_por_processo
from lupa.dominio.tabelas import (
    AchadoTabela,
    AnotacaoTabela,
    FatoTabela,
    PaginaTabela,
    ProcessoTabela,
    UsuarioTabela,
)
from lupa.ingestao import repositorio_eventos
from lupa.ingestao.eventos.etapa import achados_do_processo

router = APIRouter()

Processo = Annotated[ProcessoTabela, Depends(exige_processo)]


class CorpoCorrecao(BaseModel):
    """Correção (`corrigido`, com valor novo) ou confirmação (`confirmado`) de um fato."""

    model_config = ConfigDict(extra="forbid")

    status: StatusFato
    valor: Any = None

    @model_validator(mode="after")
    def _coerente(self) -> "CorpoCorrecao":
        if self.status is StatusFato.AUTOMATICO:
            raise ValueError("status deve ser corrigido ou confirmado")
        if self.status is StatusFato.CORRIGIDO and self.valor is None:
            raise ValueError("informe o valor corrigido")
        return self


class CorpoAnotacao(BaseModel):
    """Nota sobre um achado ou um fato (exatamente um dos dois)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    achado_id: UUID | None = None
    fato_id: UUID | None = None
    texto: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _um_alvo(self) -> "CorpoAnotacao":
        if (self.achado_id is None) == (self.fato_id is None):
            raise ValueError("informe achado_id ou fato_id")
        return self


def _exigir_anotar(ator: Ator, processo: ProcessoTabela) -> None:
    if not pode(ator.papel, Permissao.ANOTAR, ator.gabinete_id, processo.gabinete_id):
        raise PermissaoNegadaError("ação não permitida para o seu papel")


@router.get("/processos/{processo_id}/achados")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def obter_achados(processo: Processo, sessao: SessaoBanco) -> dict[str, Any]:
    """Achados vigentes do processo.

    Args:
        processo: Processo autorizado.
        sessao: Sessão da requisição.

    Returns:
        `{processo_id, status, achados: [...]}`.
    """
    achados = repositorio_eventos.achados_vigentes(sessao, processo.id)
    return {
        "processo_id": str(processo.id),
        "status": processo.status,
        "achados": [a.model_dump(mode="json") for a in achados],
    }


@router.get("/processos/{processo_id}/achados/historico")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def obter_historico_achados(processo: Processo, sessao: SessaoBanco) -> dict[str, Any]:
    """Todos os achados gravados do processo, em ordem de criação, com o vigente marcado.

    Args:
        processo: Processo autorizado.
        sessao: Sessão da requisição.

    Returns:
        `{processo_id, achados: [{..., vigente}]}`.
    """
    vigentes = {a.id for a in repositorio_eventos.achados_vigentes(sessao, processo.id)}
    return {
        "processo_id": str(processo.id),
        "achados": [
            a.model_dump(mode="json") | {"vigente": a.id in vigentes}
            for a in listar_achados(sessao, processo.id)
        ],
    }


def _paginas(sessao: SessaoBanco, ids: set[UUID]) -> dict[UUID, tuple[UUID, int]]:
    if not ids:
        return {}
    linhas = sessao.execute(
        select(PaginaTabela.id, PaginaTabela.arquivo_id, PaginaTabela.numero).where(
            PaginaTabela.id.in_(ids)
        )
    )
    return {pagina_id: (arquivo_id, numero) for pagina_id, arquivo_id, numero in linhas}


@router.get("/processos/{processo_id}/fatos")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def listar_fatos(processo: Processo, sessao: SessaoBanco) -> dict[str, Any]:
    """Fatos do processo com evidências localizadas e a cadeia de correção.

    Args:
        processo: Processo autorizado.
        sessao: Sessão da requisição.

    Returns:
        `{processo_id, fatos: [{id, tipo, valor, status, vigente, substitui_fato_id,
        substituido_por, evidencias: [{id, arquivo_id, pagina, trecho, ...}]}]}`.
    """
    fatos = listar_fatos_por_processo(sessao, processo.id)
    substituto = correcoes.cadeia_de_substituicao(fatos)
    paginas = _paginas(sessao, {e.pagina_id for f in fatos for e in f.evidencias})
    serializados = []
    for fato in fatos:
        evidencias = []
        for evidencia in fato.evidencias:
            arquivo_id, numero = paginas.get(evidencia.pagina_id, (None, None))
            evidencias.append(
                {
                    "id": str(evidencia.id),
                    "pagina_id": str(evidencia.pagina_id),
                    "arquivo_id": str(arquivo_id) if arquivo_id else None,
                    "pagina": numero,
                    "trecho": evidencia.trecho,
                    "inicio": evidencia.inicio,
                    "fim": evidencia.fim,
                }
            )
        serializados.append(
            fato.model_dump(mode="json", exclude={"evidencias"})
            | {
                "vigente": fato.id not in substituto,
                "substituido_por": str(substituto[fato.id]) if fato.id in substituto else None,
                "evidencias": evidencias,
            }
        )
    return {"processo_id": str(processo.id), "fatos": serializados}


def _registrar(
    sessao: SessaoBanco,
    ctx: Contexto,
    ator: Ator,
    processo: ProcessoTabela,
    acao: AcaoAuditoria,
    objeto: tuple[str, UUID],
) -> None:
    auditar(
        sessao,
        ctx,
        acao,
        usuario_id=ator.usuario_id,
        gabinete_id=processo.gabinete_id,
        processo_id=processo.id,
        objeto_tipo=objeto[0],
        objeto_id=str(objeto[1]),
    )


@router.post("/processos/{processo_id}/fatos/{fato_id}/corrigir", status_code=201)
def corrigir_fato(
    processo: Processo,
    fato_id: UUID,
    corpo: CorpoCorrecao,
    ator: AtorAutenticado,
    sessao: SessaoBanco,
    ctx: ContextoReq,
) -> dict[str, Any]:
    """Corrige ou confirma um fato e reexecuta o catálogo.

    Args:
        processo: Processo autorizado.
        fato_id: Fato vigente.
        corpo: Status e valor.
        ator: Quem corrige.
        sessao: Sessão da requisição.
        ctx: Contexto para a auditoria (a data de referência das validações é a de hoje).

    Returns:
        `{fato, achados_gravados, achados}` com o fato novo e os achados vigentes.

    Raises:
        PermissaoNegadaError: Papel sem permissão de anotar no gabinete.
        NaoEncontradoError: Fato inexistente ou de outro processo.
        ConflitoError: Fato já substituído.
        DadosInvalidosError: Valor incoerente com o original.
    """
    _exigir_anotar(ator, processo)
    original = correcoes.obter_fato(sessao, processo.id, fato_id)
    if original is None:
        raise NaoEncontradoError("fato não encontrado")
    try:
        novo = correcoes.corrigir_fato(sessao, original, corpo.status, corpo.valor)
    except correcoes.FatoJaSubstituidoError as erro:
        raise ConflitoError(str(erro)) from None
    except correcoes.CorrecaoInvalidaError as erro:
        raise DadosInvalidosError(str(erro)) from None
    _registrar(sessao, ctx, ator, processo, AcaoAuditoria.FATO_CORRIGIDO, ("fato", novo.id))
    achados = achados_do_processo(sessao, processo.id, processo.materia, ctx.agora.date())
    gravados = repositorio_eventos.gravar_achados(sessao, processo.id, achados)
    objeto = ("processo", processo.id)
    _registrar(sessao, ctx, ator, processo, AcaoAuditoria.VALIDACAO_EXECUTADA, objeto)
    return {
        "fato": novo.model_dump(mode="json", exclude={"evidencias"}),
        "achados_gravados": gravados,
        "achados": [
            a.model_dump(mode="json")
            for a in repositorio_eventos.achados_vigentes(sessao, processo.id)
        ],
    }


def _alvo_no_processo(sessao: SessaoBanco, processo: ProcessoTabela, corpo: CorpoAnotacao) -> None:
    if corpo.achado_id is not None:
        achado = sessao.get(AchadoTabela, corpo.achado_id)
        encontrado = achado is not None and achado.processo_id == processo.id
    else:
        fato = sessao.get(FatoTabela, corpo.fato_id)
        encontrado = fato is not None and fato.processo_id == processo.id
    if not encontrado:
        raise NaoEncontradoError("achado ou fato não encontrado")


def _serializar_anotacao(anotacao: AnotacaoTabela, autor: str | None) -> dict[str, Any]:
    return {
        "id": str(anotacao.id),
        "achado_id": str(anotacao.achado_id) if anotacao.achado_id else None,
        "fato_id": str(anotacao.fato_id) if anotacao.fato_id else None,
        "usuario_id": str(anotacao.usuario_id),
        "autor": autor,
        "texto": anotacao.texto,
        "criado_em": anotacao.criado_em.isoformat(),
    }


@router.post("/processos/{processo_id}/anotacoes", status_code=201)
def anotar(
    processo: Processo,
    corpo: CorpoAnotacao,
    ator: AtorAutenticado,
    sessao: SessaoBanco,
    ctx: ContextoReq,
) -> dict[str, Any]:
    """Grava uma anotação sobre achado ou fato do processo.

    Args:
        processo: Processo autorizado.
        corpo: Alvo e texto.
        ator: Autor.
        sessao: Sessão da requisição.
        ctx: Contexto para a auditoria.

    Returns:
        Anotação criada.
    """
    _exigir_anotar(ator, processo)
    _alvo_no_processo(sessao, processo, corpo)
    anotacao = AnotacaoTabela(
        id=uuid4(),
        gabinete_id=processo.gabinete_id,
        achado_id=corpo.achado_id,
        fato_id=corpo.fato_id,
        usuario_id=ator.usuario_id,
        texto=corpo.texto,
    )
    sessao.add(anotacao)
    sessao.flush()
    sessao.refresh(anotacao)
    auditar(
        sessao,
        ctx,
        AcaoAuditoria.ANOTACAO,
        usuario_id=ator.usuario_id,
        gabinete_id=processo.gabinete_id,
        processo_id=processo.id,
        objeto_tipo="anotacao",
        objeto_id=str(anotacao.id),
    )
    return _serializar_anotacao(anotacao, ator.nome_usuario)


@router.get("/processos/{processo_id}/anotacoes")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def listar_anotacoes(processo: Processo, sessao: SessaoBanco) -> dict[str, Any]:
    """Anotações sobre achados e fatos do processo, em ordem de criação.

    Args:
        processo: Processo autorizado.
        sessao: Sessão da requisição.

    Returns:
        `{processo_id, anotacoes: [...]}`.
    """
    achados = select(AchadoTabela.id).where(AchadoTabela.processo_id == processo.id)
    fatos = select(FatoTabela.id).where(FatoTabela.processo_id == processo.id)
    linhas = sessao.execute(
        select(AnotacaoTabela, UsuarioTabela.nome_usuario)
        .outerjoin(UsuarioTabela, UsuarioTabela.id == AnotacaoTabela.usuario_id)
        .where(or_(AnotacaoTabela.achado_id.in_(achados), AnotacaoTabela.fato_id.in_(fatos)))
        .order_by(AnotacaoTabela.criado_em, AnotacaoTabela.id)
    ).all()
    return {
        "processo_id": str(processo.id),
        "anotacoes": [_serializar_anotacao(a, nome) for a, nome in linhas],
    }
