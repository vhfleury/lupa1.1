"""Rotas do visualizador de páginas (Etapa 6.6).

`GET /processos/{id}/arquivos/{arquivo_id}/paginas/{numero}/imagem` devolve a página como PNG
renderizado pelo servidor a partir do original no storage (`lupa.ingestao.renderizacao`), com
`Cache-Control: private`; é auditada como `pagina_vista` (com `admin_acesso_conteudo` para o
administrador). Só existem as páginas gravadas pela ingestão (arquivo em quarentena não tem
página). Num ZIP, a página aponta para a entrada de origem (`origem_arquivo`/`pagina_origem`),
guardada no storage pelo hash do manifesto.

`GET /processos/{id}/evidencias/{evidencia_id}/bbox` calcula onde está o trecho da evidência:
os offsets `[inicio, fim)` no texto da página são cruzados com as linhas gravadas em
`pagina.coordenadas` (blocos nativos ou linhas de OCR/fusão, cada uma com `inicio`, `fim` e
`bbox` em pontos PDF com origem no canto superior esquerdo da `CropBox`), as caixas das linhas
atingidas são unidas e convertidas em fração da página. Fecha o item pendente da Revisão 4F.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from lupa.acesso.autorizacao import SessaoBanco, exige_processo
from lupa.acesso.erros import NaoEncontradoError
from lupa.api.middleware import auditar_rota
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.dominio.tabelas import (
    ArquivoTabela,
    EvidenciaTabela,
    JobIngestaoTabela,
    PaginaTabela,
    ProcessoTabela,
)
from lupa.ingestao import renderizacao
from lupa.ingestao.recepcao import TipoArquivo
from lupa.ingestao.storage import chave_objeto

router = APIRouter()

Processo = Annotated[ProcessoTabela, Depends(exige_processo)]
MENSAGEM_INDISPONIVEL = "página indisponível para visualização"


def _linhas(coordenadas: dict[str, Any]) -> list[dict[str, Any]]:
    if "blocos" in coordenadas:
        return [linha for bloco in coordenadas["blocos"] for linha in bloco.get("linhas", [])]
    return list(coordenadas.get("linhas", []))


def caixas_da_evidencia(
    coordenadas: dict[str, Any], inicio: int, fim: int
) -> list[tuple[float, float, float, float]]:
    """Caixas (em pontos) das linhas que contêm algum caractere de `[inicio, fim)`.

    Args:
        coordenadas: `pagina.coordenadas`.
        inicio: Offset inicial no texto da página.
        fim: Offset final (exclusivo).

    Returns:
        Caixas `(x0, y0, x1, y1)` na ordem das linhas; vazia se não há coordenadas.
    """
    caixas = []
    for linha in _linhas(coordenadas):
        if "inicio" not in linha or "fim" not in linha or "bbox" not in linha:
            continue
        if int(linha["inicio"]) < fim and int(linha["fim"]) > inicio:
            x0, y0, x1, y1 = (float(v) for v in linha["bbox"])
            caixas.append((x0, y0, x1, y1))
    return caixas


def fracao(
    caixa: tuple[float, float, float, float], largura: float, altura: float
) -> dict[str, float]:
    """Converte uma caixa em pontos para fração da página, recortada a `[0, 1]`.

    Args:
        caixa: `(x0, y0, x1, y1)` em pontos.
        largura: Largura da página em pontos.
        altura: Altura da página em pontos.

    Returns:
        `{x, y, largura, altura}` em fração da página.
    """

    def _limitar(valor: float) -> float:
        return min(max(valor, 0.0), 1.0)

    x0, y0 = _limitar(caixa[0] / largura), _limitar(caixa[1] / altura)
    x1, y1 = _limitar(caixa[2] / largura), _limitar(caixa[3] / altura)
    return {"x": x0, "y": y0, "largura": max(x1 - x0, 0.0), "altura": max(y1 - y0, 0.0)}


def _uniao(caixas: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (
        min(c[0] for c in caixas),
        min(c[1] for c in caixas),
        max(c[2] for c in caixas),
        max(c[3] for c in caixas),
    )


def _origem(sessao: SessaoBanco, arquivo: ArquivoTabela, pagina: PaginaTabela) -> tuple[str, int]:
    """Chave do PDF de origem no storage e o número da página dentro dele."""
    if arquivo.mime != TipoArquivo.ZIP.value or not pagina.origem_arquivo:
        return arquivo.chave_storage, pagina.pagina_origem or pagina.numero
    manifesto = sessao.scalar(
        select(JobIngestaoTabela.manifesto).where(JobIngestaoTabela.arquivo_id == arquivo.id)
    )
    for entrada in manifesto or []:
        if entrada.get("nome") == pagina.origem_arquivo:
            chave = chave_objeto(arquivo.gabinete_id, arquivo.processo_id, entrada["sha256"])
            return chave, pagina.pagina_origem or 1
    raise NaoEncontradoError(MENSAGEM_INDISPONIVEL)


def _pagina(
    sessao: SessaoBanco, processo: ProcessoTabela, arquivo_id: UUID, numero: int
) -> tuple[ArquivoTabela, PaginaTabela]:
    arquivo = sessao.get(ArquivoTabela, arquivo_id)
    if arquivo is None or arquivo.processo_id != processo.id:
        raise NaoEncontradoError("arquivo não encontrado")
    pagina = sessao.scalar(
        select(PaginaTabela).where(
            PaginaTabela.arquivo_id == arquivo_id, PaginaTabela.numero == numero
        )
    )
    if pagina is None:
        raise NaoEncontradoError("página não encontrada")
    return arquivo, pagina


@router.get("/processos/{processo_id}/arquivos/{arquivo_id}/paginas/{numero}/imagem")
@auditar_rota(AcaoAuditoria.PAGINA_VISTA, conteudo=True)
def imagem_pagina(
    request: Request,
    processo: Processo,
    arquivo_id: UUID,
    numero: int,
    sessao: SessaoBanco,
    zoom: Annotated[
        float, Query(ge=renderizacao.ZOOM_MINIMO, le=renderizacao.ZOOM_MAXIMO)
    ] = renderizacao.ZOOM_PADRAO,
) -> Response:
    """PNG da página do arquivo, renderizado no servidor a partir do original.

    Args:
        request: Requisição (storage da aplicação).
        processo: Processo autorizado.
        arquivo_id: Arquivo do processo.
        numero: Página no arquivo (numeração contínua da ingestão).
        sessao: Sessão da requisição.
        zoom: Escala (1.0 = 72 dpi).

    Returns:
        `image/png` com `Cache-Control: private`, ou 503 se a página não pôde ser desenhada.
    """
    arquivo, pagina = _pagina(sessao, processo, arquivo_id, numero)
    chave, numero_origem = _origem(sessao, arquivo, pagina)
    try:
        imagem = renderizacao.renderizar(request.app.state.storage, chave, numero_origem, zoom)
    except renderizacao.RenderizacaoError:
        return JSONResponse(status_code=503, content={"detail": MENSAGEM_INDISPONIVEL})
    return Response(
        content=imagem.png,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "X-Lupa-Pagina-Largura": f"{imagem.largura:.2f}",
            "X-Lupa-Pagina-Altura": f"{imagem.altura:.2f}",
        },
    )


@router.get("/processos/{processo_id}/evidencias/{evidencia_id}/bbox")
@auditar_rota(AcaoAuditoria.PROCESSO_ABERTO, conteudo=True)
def bbox_evidencia(
    request: Request, processo: Processo, evidencia_id: UUID, sessao: SessaoBanco
) -> dict[str, Any]:
    """Onde está o trecho da evidência: arquivo, página e retângulos em fração da página.

    Args:
        request: Requisição (storage, para o tamanho da página).
        processo: Processo autorizado.
        evidencia_id: Evidência de fato ou de peça do processo.
        sessao: Sessão da requisição.

    Returns:
        `{evidencia_id, arquivo_id, pagina, trecho, uniao, retangulos, sistema}`; `uniao` é
        None quando a página não tem coordenadas (página vazia ou sem texto localizável).

    Raises:
        NaoEncontradoError: Evidência inexistente ou de outro processo.
    """
    linha = sessao.execute(
        select(EvidenciaTabela, PaginaTabela, ArquivoTabela)
        .join(PaginaTabela, PaginaTabela.id == EvidenciaTabela.pagina_id)
        .join(ArquivoTabela, ArquivoTabela.id == PaginaTabela.arquivo_id)
        .where(EvidenciaTabela.id == evidencia_id)
    ).one_or_none()
    if linha is None or linha[2].processo_id != processo.id:
        raise NaoEncontradoError("evidência não encontrada")
    evidencia, pagina, arquivo = linha
    caixas = caixas_da_evidencia(pagina.coordenadas or {}, evidencia.inicio, evidencia.fim)
    corpo: dict[str, Any] = {
        "evidencia_id": str(evidencia.id),
        "arquivo_id": str(arquivo.id),
        "pagina": pagina.numero,
        "trecho": evidencia.trecho,
        "sistema": "fracao_da_pagina_origem_superior_esquerda",
        "uniao": None,
        "retangulos": [],
    }
    if not caixas:
        return corpo
    chave, numero_origem = _origem(sessao, arquivo, pagina)
    try:
        medida = renderizacao.renderizar(request.app.state.storage, chave, numero_origem)
    except renderizacao.RenderizacaoError:
        return corpo
    corpo["uniao"] = fracao(_uniao(caixas), medida.largura, medida.altura)
    corpo["retangulos"] = [fracao(c, medida.largura, medida.altura) for c in caixas]
    return corpo
