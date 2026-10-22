"""Persistência do chat: conversa, mensagem e chamada ao modelo (migração 0007)."""

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lupa.dominio.enums import PapelMensagem, ResultadoChamada, StatusMensagem
from lupa.dominio.tabelas import (
    AchadoTabela,
    ArquivoTabela,
    ChamadaModeloTabela,
    ConversaTabela,
    EvidenciaTabela,
    FatoTabela,
    MensagemTabela,
    PaginaTabela,
    PecaTabela,
)


def conversa_aberta(
    session: Session, gabinete_id: UUID, processo_id: UUID, usuario_id: UUID
) -> ConversaTabela:
    """Conversa aberta do usuário no processo; cria uma se não houver.

    Args:
        session: Sessão (RLS do gabinete).
        gabinete_id: Gabinete do processo.
        processo_id: Processo.
        usuario_id: Usuário.

    Returns:
        Conversa não encerrada.
    """
    consulta = (
        select(ConversaTabela)
        .where(
            ConversaTabela.processo_id == processo_id,
            ConversaTabela.usuario_id == usuario_id,
            ConversaTabela.encerrada.is_(False),
        )
        .order_by(ConversaTabela.criada_em.desc())
        .limit(1)
    )
    conversa = session.scalar(consulta)
    if conversa is None:
        conversa = ConversaTabela(
            id=uuid4(),
            gabinete_id=gabinete_id,
            processo_id=processo_id,
            usuario_id=usuario_id,
            encerrada=False,
            tokens_entrada=0,
            tokens_saida=0,
            paginas_originais=0,
            citacoes_descartadas=0,
        )
        session.add(conversa)
        session.flush()
    return conversa


def tokens_do_processo(session: Session, processo_id: UUID) -> int:
    """Tokens (entrada + saída) já gastos em todas as conversas do processo.

    Args:
        session: Sessão.
        processo_id: Processo.

    Returns:
        Total.
    """
    consulta = select(
        func.coalesce(func.sum(ConversaTabela.tokens_entrada + ConversaTabela.tokens_saida), 0)
    ).where(ConversaTabela.processo_id == processo_id)
    return int(session.scalar(consulta) or 0)


def gravar_mensagem(
    session: Session,
    conversa: ConversaTabela,
    papel: PapelMensagem,
    status: StatusMensagem,
    texto: str,
    citacoes: list[dict[str, Any]] | None = None,
    avisos: list[str] | None = None,
) -> MensagemTabela:
    """Grava uma mensagem.

    Args:
        session: Sessão.
        conversa: Conversa.
        papel: Usuário ou agente.
        status: Desfecho.
        texto: Texto.
        citacoes: Citações conferidas.
        avisos: Avisos mostrados com a mensagem.

    Returns:
        Mensagem gravada.
    """
    mensagem = MensagemTabela(
        id=uuid4(),
        gabinete_id=conversa.gabinete_id,
        conversa_id=conversa.id,
        papel=papel.value,
        status=status.value,
        texto=texto,
        citacoes=citacoes or [],
        avisos=avisos or [],
        criado_em=datetime.now(UTC),
    )
    session.add(mensagem)
    session.flush()
    return mensagem


def gravar_chamada(session: Session, **campos: Any) -> ChamadaModeloTabela:
    """Grava os metadados de uma chamada ao modelo (sem conteúdo).

    Args:
        session: Sessão.
        **campos: Colunas de `chamada_modelo` (sem `id`).

    Returns:
        Linha gravada.
    """
    resultado = campos.pop("resultado")
    chamada = ChamadaModeloTabela(id=uuid4(), resultado=ResultadoChamada(resultado).value, **campos)
    session.add(chamada)
    session.flush()
    return chamada


def ids_do_processo(session: Session, processo_id: UUID) -> set[str]:
    """Todos os UUIDs que pertencem ao processo (para detectar identificador estranho).

    Args:
        session: Sessão.
        processo_id: Processo.

    Returns:
        Ids em minúsculas: processo, arquivos, páginas, peças, evidências, fatos, achados.
    """
    arquivos = select(ArquivoTabela.id).where(ArquivoTabela.processo_id == processo_id)
    paginas = select(PaginaTabela.id).where(PaginaTabela.arquivo_id.in_(arquivos))
    consultas = [
        arquivos,
        paginas,
        select(PecaTabela.id).where(PecaTabela.arquivo_id.in_(arquivos)),
        select(EvidenciaTabela.id).where(EvidenciaTabela.pagina_id.in_(paginas)),
        select(FatoTabela.id).where(FatoTabela.processo_id == processo_id),
        select(AchadoTabela.id).where(AchadoTabela.processo_id == processo_id),
    ]
    ids = {str(processo_id)}
    for consulta in consultas:
        ids.update(str(i) for i in session.scalars(consulta))
    return ids


def paginas_citadas(
    session: Session, processo_id: UUID, ids: list[UUID]
) -> dict[UUID, tuple[str, str | None]]:
    """Texto gravado das páginas citadas que pertencem ao processo.

    Args:
        session: Sessão.
        processo_id: Processo.
        ids: Páginas citadas pelo modelo.

    Returns:
        `{pagina_id: (texto, texto_normalizado)}`; páginas de fora ficam de fora.
    """
    if not ids:
        return {}
    consulta = (
        select(PaginaTabela.id, PaginaTabela.texto, PaginaTabela.texto_normalizado)
        .join(ArquivoTabela, ArquivoTabela.id == PaginaTabela.arquivo_id)
        .where(ArquivoTabela.processo_id == processo_id, PaginaTabela.id.in_(ids))
    )
    return {linha[0]: (linha[1], linha[2]) for linha in session.execute(consulta)}


def historico(session: Session, processo_id: UUID, usuario_id: UUID) -> list[dict[str, Any]]:
    """Conversas do usuário no processo, com as mensagens em ordem.

    Args:
        session: Sessão.
        processo_id: Processo.
        usuario_id: Usuário.

    Returns:
        Conversas serializadas, da mais antiga para a mais recente.
    """
    conversas = list(
        session.scalars(
            select(ConversaTabela)
            .where(
                ConversaTabela.processo_id == processo_id, ConversaTabela.usuario_id == usuario_id
            )
            .order_by(ConversaTabela.criada_em, ConversaTabela.id)
        )
    )
    saida = []
    for conversa in conversas:
        mensagens = session.scalars(
            select(MensagemTabela)
            .where(MensagemTabela.conversa_id == conversa.id)
            .order_by(MensagemTabela.criado_em, MensagemTabela.papel.desc(), MensagemTabela.id)
        )
        saida.append(
            {
                "conversa_id": str(conversa.id),
                "criada_em": conversa.criada_em.isoformat(),
                "encerrada": conversa.encerrada,
                "motivo_encerramento": conversa.motivo_encerramento,
                "citacoes_descartadas": conversa.citacoes_descartadas,
                "mensagens": [
                    serializar_mensagem(m)
                    | {"citacoes": localizar_citacoes(session, processo_id, list(m.citacoes))}
                    for m in mensagens
                ],
            }
        )
    return saida


def serializar_mensagem(mensagem: MensagemTabela) -> dict[str, Any]:
    """Mensagem para a API; resposta do agente leva o rótulo de conteúdo gerado.

    Args:
        mensagem: Mensagem.

    Returns:
        Dicionário.
    """
    return {
        "mensagem_id": str(mensagem.id),
        "papel": mensagem.papel,
        "status": mensagem.status,
        "texto": mensagem.texto,
        "citacoes": mensagem.citacoes,
        "avisos": mensagem.avisos,
        "citacoes_descartadas": descartadas_dos_avisos(mensagem.avisos),
        "rotulo": "gerado por IA" if mensagem.papel == PapelMensagem.AGENTE.value else None,
        "criado_em": mensagem.criado_em.isoformat() if mensagem.criado_em else None,
    }


AVISO_DESCARTE = re.compile(r"^(\d+) citação\(ões\) não conferiram")


def descartadas_dos_avisos(avisos: list[str]) -> int:
    """Quantas citações a resposta perdeu na conferência (lido do aviso gravado).

    Args:
        avisos: Avisos da mensagem.

    Returns:
        Número de citações descartadas (0 se não houve).
    """
    for aviso in avisos:
        achado = AVISO_DESCARTE.match(aviso)
        if achado:
            return int(achado.group(1))
    return 0


def localizar_citacoes(
    session: Session, processo_id: UUID, citacoes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Acrescenta a cada citação o número da página e o arquivo, para o link do visualizador.

    Args:
        session: Sessão.
        processo_id: Processo.
        citacoes: Citações gravadas (`pagina_id`, `trecho`, `hash_trecho`).

    Returns:
        Citações com `pagina_numero` e `arquivo_id` (None se a página não for do processo).
    """
    ids = []
    for citacao in citacoes:
        try:
            ids.append(UUID(str(citacao.get("pagina_id"))))
        except ValueError:
            continue
    locais: dict[str, tuple[int, str]] = {}
    if ids:
        consulta = (
            select(PaginaTabela.id, PaginaTabela.numero, PaginaTabela.arquivo_id)
            .join(ArquivoTabela, ArquivoTabela.id == PaginaTabela.arquivo_id)
            .where(ArquivoTabela.processo_id == processo_id, PaginaTabela.id.in_(ids))
        )
        locais = {str(i): (n, str(a)) for i, n, a in session.execute(consulta)}
    saida = []
    for citacao in citacoes:
        numero, arquivo = locais.get(str(citacao.get("pagina_id")), (None, None))
        saida.append(citacao | {"pagina_numero": numero, "arquivo_id": arquivo})
    return saida
