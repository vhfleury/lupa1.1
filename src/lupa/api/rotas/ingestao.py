"""Rotas da ingestão: envio de arquivo, diagnóstico, relatório de qualidade, alertas e métricas.

`POST /processos/{id}/arquivos` recebe o arquivo como corpo binário (`application/octet-stream`)
com o nome em `?nome=`, em streaming; não há multipart. A rota usa `exige_processo` (404 para
processo de outro gabinete, com a tentativa auditada) e grava `arquivo_enviado` na transação da
requisição, inclusive nas recusas. As leituras de diagnóstico e de relatório de um arquivo
do processo são auditadas automaticamente (`processo_aberto`).
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.concurrency import run_in_threadpool

from lupa.acesso.autorizacao import (
    AtorAutenticado,
    ContextoReq,
    SessaoBanco,
    exige_papel,
    exige_processo,
)
from lupa.acesso.erros import NaoEncontradoError, PermissaoNegadaError
from lupa.acesso.papeis import Permissao, pode
from lupa.acesso.servico import Ator, Contexto, auditar
from lupa.api.middleware import auditar_rota
from lupa.auditoria.eventos import AcaoAuditoria, ResultadoEvento
from lupa.config import Settings, get_settings
from lupa.dominio.tabelas import ArquivoTabela, ProcessoTabela
from lupa.ingestao import repositorio
from lupa.ingestao.fila import FilaIngestao
from lupa.ingestao.metricas import gerar_metricas
from lupa.ingestao.recepcao import (
    MotivoRecusa,
    RecepcaoRecusadaError,
    ResultadoLacre,
    lacrar,
    receber,
)
from lupa.logging import get_logger

router = APIRouter()
log = get_logger(__name__)

STATUS_RECUSA = {MotivoRecusa.TAMANHO: 413, MotivoRecusa.VAZIO: 422, MotivoRecusa.TIPO: 415}
MENSAGEM_RECUSA = {
    MotivoRecusa.TAMANHO: "arquivo acima do tamanho máximo",
    MotivoRecusa.VAZIO: "arquivo vazio",
    MotivoRecusa.TIPO: "tipo de arquivo não aceito: envie PDF ou ZIP",
}
MENSAGEM_SIGILOSO = "processo sigiloso: ingestão bloqueada na v1"

Processo = Annotated[ProcessoTabela, Depends(exige_processo)]
Configuracao = Annotated[Settings, Depends(get_settings)]
Administrador = Annotated[Ator, Depends(exige_papel(Permissao.GERIR_GABINETES))]


def _auditar_envio(
    sessao: SessaoBanco,
    ctx: Contexto,
    ator: Ator,
    processo: ProcessoTabela,
    resultado: ResultadoEvento,
    arquivo_id: UUID | None = None,
) -> None:
    auditar(
        sessao,
        ctx,
        AcaoAuditoria.ARQUIVO_ENVIADO,
        resultado,
        usuario_id=ator.usuario_id,
        gabinete_id=processo.gabinete_id,
        processo_id=processo.id,
        objeto_tipo="arquivo",
        objeto_id=str(arquivo_id) if arquivo_id else None,
    )


def _enfileirar(fila: FilaIngestao, job_id: UUID, gabinete_id: UUID) -> None:
    try:
        fila.enfileirar(job_id, gabinete_id)
    except Exception:
        log.warning("fila_indisponivel", job_id=str(job_id))


def _resposta(lacre: ResultadoLacre, sha256: str, tamanho: int, mime: str) -> JSONResponse:
    corpo = {
        "arquivo_id": str(lacre.arquivo_id),
        "job_id": str(lacre.job_id),
        "estado": lacre.estado,
        "sha256": sha256,
        "tamanho_bytes": tamanho,
        "mime": mime,
        "duplicado": lacre.duplicado,
    }
    return JSONResponse(status_code=200 if lacre.duplicado else 201, content=corpo)


def _conferir_permissao(
    sessao: SessaoBanco, ctx: Contexto, ator: Ator, processo: ProcessoTabela
) -> None:
    permitido = pode(ator.papel, Permissao.SUBIR_PROCESSO, ator.gabinete_id, processo.gabinete_id)
    if not permitido or processo.sigiloso:
        _auditar_envio(sessao, ctx, ator, processo, ResultadoEvento.NEGADO)
        raise PermissaoNegadaError(
            MENSAGEM_SIGILOSO if permitido else "ação não permitida para o seu papel"
        )


@router.post("/processos/{processo_id}/arquivos", status_code=201)
async def enviar_arquivo(
    request: Request,
    processo: Processo,
    ator: AtorAutenticado,
    sessao: SessaoBanco,
    ctx: ContextoReq,
    settings: Configuracao,
    tarefas: BackgroundTasks,
    nome: Annotated[str, Query(min_length=1, max_length=255)],
) -> JSONResponse:
    """Recebe PDF ou ZIP do processo, lacra com SHA-256 e cria o job em `recebido`.

    Args:
        request: Requisição (corpo em streaming).
        processo: Processo autorizado.
        ator: Ator autenticado.
        sessao: Sessão da requisição.
        ctx: Contexto para auditoria.
        settings: Configuração (limite de tamanho, diretório temporário).
        tarefas: Tarefas pós-resposta (enfileiramento depois do commit).
        nome: Nome original do arquivo.

    Returns:
        201 com arquivo e job novos, ou 200 quando o conteúdo já existia no processo.
    """
    await run_in_threadpool(_conferir_permissao, sessao, ctx, ator, processo)
    try:
        recebido = await receber(
            request.stream(), nome, settings.upload_limite_bytes, settings.ingestao_dir_temporario
        )
    except RecepcaoRecusadaError as recusa:
        await run_in_threadpool(_auditar_envio, sessao, ctx, ator, processo, ResultadoEvento.NEGADO)
        return JSONResponse(
            status_code=STATUS_RECUSA[recusa.motivo],
            content={"detail": MENSAGEM_RECUSA[recusa.motivo], "motivo": recusa.motivo.value},
        )
    try:
        lacre = await run_in_threadpool(
            lacrar,
            sessao,
            request.app.state.storage,
            recebido,
            gabinete_id=processo.gabinete_id,
            processo_id=processo.id,
            enviado_por=ator.usuario_id,
            nome_original=nome,
        )
    finally:
        recebido.caminho.unlink(missing_ok=True)
    await run_in_threadpool(
        _auditar_envio, sessao, ctx, ator, processo, ResultadoEvento.OK, lacre.arquivo_id
    )
    if not lacre.duplicado:
        tarefas.add_task(_enfileirar, request.app.state.fila, lacre.job_id, processo.gabinete_id)
    return _resposta(lacre, recebido.sha256, recebido.tamanho_bytes, recebido.tipo.value)


@router.get("/metricas")
def metricas(_admin: Administrador, sessao: SessaoBanco, ctx: ContextoReq) -> Response:
    """Métricas Prometheus da ingestão; só para o administrador.

    Args:
        _admin: Administrador autenticado.
        sessao: Sessão com visão de todos os gabinetes (política do administrador).
        ctx: Contexto (instante de referência).

    Returns:
        Texto de exposição do Prometheus.
    """
    return Response(content=gerar_metricas(sessao, ctx.agora), media_type=CONTENT_TYPE_LATEST)


def _conferir_arquivo(sessao: SessaoBanco, processo: ProcessoTabela, arquivo_id: UUID) -> None:
    arquivo = sessao.get(ArquivoTabela, arquivo_id)
    if arquivo is None or arquivo.processo_id != processo.id:
        raise NaoEncontradoError("arquivo não encontrado")


@router.get("/processos/{processo_id}/arquivos/{arquivo_id}/diagnostico")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def obter_diagnostico(processo: Processo, arquivo_id: UUID, sessao: SessaoBanco) -> dict[str, Any]:
    """Diagnóstico do arquivo: cenário, sinais e fronteiras candidatas da origem.

    Args:
        processo: Processo autorizado.
        arquivo_id: Arquivo do processo.
        sessao: Sessão da requisição.

    Returns:
        Diagnóstico serializado.

    Raises:
        NaoEncontradoError: Arquivo de outro processo, inexistente ou ainda sem diagnóstico.
    """
    _conferir_arquivo(sessao, processo, arquivo_id)
    diagnostico = repositorio.obter_diagnostico(sessao, arquivo_id)
    if diagnostico is None:
        raise NaoEncontradoError("diagnóstico ainda não disponível")
    return diagnostico.model_dump(mode="json")


@router.get("/processos/{processo_id}/arquivos/{arquivo_id}/relatorio")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=False)
def obter_relatorio(processo: Processo, arquivo_id: UUID, sessao: SessaoBanco) -> dict[str, Any]:
    """Relatório de qualidade da extração do arquivo (sem texto dos autos).

    Args:
        processo: Processo autorizado.
        arquivo_id: Arquivo do processo.
        sessao: Sessão da requisição.

    Returns:
        Estado do job, versão do extrator e relatório (vazio enquanto não houver).

    Raises:
        NaoEncontradoError: Arquivo de outro processo ou inexistente.
    """
    _conferir_arquivo(sessao, processo, arquivo_id)
    relatorio = repositorio.obter_relatorio(sessao, arquivo_id)
    if relatorio is None:
        raise NaoEncontradoError("arquivo sem job de ingestão")
    return relatorio


@router.get("/processos/{processo_id}/arquivos/{arquivo_id}/alertas")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=False)
def obter_alertas(processo: Processo, arquivo_id: UUID, sessao: SessaoBanco) -> dict[str, Any]:
    """Painel de alertas de injeção do arquivo (4D.10), sem texto dos autos.

    Lista páginas com texto oculto, blocos codificados, padrões de instrução, idioma
    inesperado, homóglifos e densidade anômala, e os metadados com instrução (só hash).

    Args:
        processo: Processo autorizado.
        arquivo_id: Arquivo do processo.
        sessao: Sessão da requisição.

    Returns:
        Resumo, metadados suspeitos e páginas sinalizadas com seus trechos.

    Raises:
        NaoEncontradoError: Arquivo de outro processo ou inexistente.
    """
    _conferir_arquivo(sessao, processo, arquivo_id)
    return repositorio.alertas_arquivo(sessao, arquivo_id)
