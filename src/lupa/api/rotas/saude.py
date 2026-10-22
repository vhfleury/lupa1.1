"""Rotas de saúde e de métricas de serviço (Prometheus) da API."""

import hmac
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lupa.acesso.autorizacao import ContextoReq, SessaoBanco
from lupa.acesso.servico import definir_contexto
from lupa.api import saude
from lupa.config import Settings, get_settings
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.tabelas import ChamadaModeloTabela, EventoAuditoriaTabela
from lupa.ingestao.metricas import gerar_metricas

router = APIRouter()
JANELA_DIA = timedelta(hours=24)


@router.get("/saude")
def obter_saude(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, str]:
    """Informa o estado da API, do banco, do MinIO e do cofre (Vault destravado e decifrando).

    Args:
        response: Resposta HTTP, para ajustar o status.
        settings: Configuração da aplicação.

    Returns:
        Estado de cada componente (`ok` ou `falha`); 503 se algum falhar.
    """
    corpo = {
        "api": "ok",
        "db": "ok" if saude.verificar_db(settings) else "falha",
        "minio": "ok" if saude.verificar_minio(settings) else "falha",
        "cofre": "ok" if saude.verificar_cofre(settings) else "falha",
    }
    if "falha" in corpo.values():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return corpo


class ColetorServico(Collector):
    """Métricas de uso das últimas 24 h: chamadas ao modelo, tokens e eventos de auditoria.

    Rótulos são só a ação de auditoria e o tipo de token (enumerados); nenhum id, nome ou texto.
    """

    def __init__(self, session: Session, agora: datetime, cofre_ok: bool) -> None:
        """Cria o coletor.

        Args:
            session: Sessão com contexto de administrador.
            agora: Instante de referência.
            cofre_ok: Resultado da verificação do cofre.
        """
        self._session = session
        self._desde = agora - JANELA_DIA
        self._cofre_ok = cofre_ok

    def collect(self) -> Iterator[Metric]:
        """Produz as métricas.

        Yields:
            Famílias de métricas.
        """
        yield GaugeMetricFamily(
            "lupa_cofre_ok", "1 se o cofre decifra o valor de teste", value=float(self._cofre_ok)
        )
        chamadas, entrada, saida = self._session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(ChamadaModeloTabela.tokens_entrada), 0),
                func.coalesce(func.sum(ChamadaModeloTabela.tokens_saida), 0),
            ).where(ChamadaModeloTabela.criado_em >= self._desde)
        ).one()
        yield GaugeMetricFamily(
            "lupa_modelo_chamadas_24h", "Chamadas ao modelo nas últimas 24 h", value=chamadas
        )
        tokens = GaugeMetricFamily(
            "lupa_modelo_tokens_24h", "Tokens do modelo nas últimas 24 h", labels=["tipo"]
        )
        tokens.add_metric(["entrada"], float(entrada))
        tokens.add_metric(["saida"], float(saida))
        yield tokens
        eventos = GaugeMetricFamily(
            "lupa_auditoria_eventos_24h",
            "Eventos de auditoria nas últimas 24 h por ação",
            labels=["acao"],
        )
        consulta = (
            select(EventoAuditoriaTabela.acao, func.count())
            .where(EventoAuditoriaTabela.ocorrido_em >= self._desde)
            .group_by(EventoAuditoriaTabela.acao)
        )
        for acao, total in self._session.execute(consulta):
            eventos.add_metric([str(acao)], float(total))
        yield eventos


def _conferir_token(settings: Settings, authorization: str | None) -> None:
    esperado = settings.metricas_token.get_secret_value() if settings.metricas_token else ""
    if not esperado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "não encontrado")
    recebido = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(recebido.encode(), esperado.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "não autenticado")


@router.get("/metricas/servico")
def metricas_servico(
    settings: Annotated[Settings, Depends(get_settings)],
    sessao: SessaoBanco,
    ctx: ContextoReq,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Métricas Prometheus para o raspador (Etapa 8.1), autenticadas por token de serviço.

    O Prometheus não faz login com senha e TOTP; usa `Authorization: Bearer <LUPA_METRICAS_TOKEN>`
    (lido de arquivo de segredo pelo Prometheus). Lê com a visão do administrador, só contagens.

    Args:
        settings: Configuração (token esperado).
        sessao: Sessão do banco.
        ctx: Contexto (instante de referência).
        authorization: Cabeçalho `Authorization`.

    Returns:
        Texto de exposição do Prometheus (ingestão, modelo, auditoria e cofre).
    """
    _conferir_token(settings, authorization)
    definir_contexto(sessao, PapelUsuario.ADMINISTRADOR.value, None)
    registro = CollectorRegistry(auto_describe=False)
    registro.register(ColetorServico(sessao, ctx.agora, saude.verificar_cofre(settings)))
    corpo = gerar_metricas(sessao, ctx.agora) + generate_latest(registro)
    return Response(content=corpo, media_type=CONTENT_TYPE_LATEST)
