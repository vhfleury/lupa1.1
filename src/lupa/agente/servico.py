"""Caso de uso do chat (Etapas 5.5 a 5.9): pergunta → recusa, resposta conferida ou teto.

Ordem: conversa aberta → teto do processo → grava a pergunta (`pergunta_chat`) → recusa por
regras → monta contexto e ferramentas → chama o cliente (uma nova tentativa se a saída vier
fora do esquema) → registra `chamada_modelo` → confere citações → grava a resposta → aplica os
tetos de conversa e de processo.
"""

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from lupa.acesso.servico import Contexto, auditar
from lupa.agente import repositorio, revisao
from lupa.agente.citacoes import Conferencia, Desfecho, PaginaConferencia, conferir, interpretar
from lupa.agente.cliente import (
    ClienteAgente,
    ClienteAgenteError,
    PedidoAgente,
    RespostaAgente,
)
from lupa.agente.contexto import (
    Delimitador,
    Pseudonimizador,
    montar_mensagem,
    prompt_sistema,
    pseudonimizador_do_processo,
)
from lupa.agente.ferramentas.registro import criar_ferramentas
from lupa.agente.ferramentas.sessao import SessaoAgente
from lupa.agente.recusa import classificar
from lupa.auditoria.eventos import AcaoAuditoria, ResultadoEvento
from lupa.config import Settings
from lupa.dominio.enums import PapelMensagem, ResultadoChamada, StatusMensagem
from lupa.dominio.esquemas import calcular_hash
from lupa.dominio.tabelas import ConversaTabela, ProcessoTabela, ReuTabela

MSG_TETO_CONVERSA = (
    "Esta conversa atingiu o limite de uso e foi encerrada. Uma nova pergunta abre outra conversa."
)
MSG_TETO_PROCESSO = (
    "O limite de uso do assistente para este processo foi atingido; o chat fica indisponível "
    "neste processo. Fale com o administrador se precisar ampliar."
)
MSG_TETO_CHAMADA = "A resposta passou do limite de tamanho por chamada e foi descartada."
MSG_INDISPONIVEL = "O assistente está indisponível no momento. Tente de novo em instantes."
MSG_DESCARTADA = (
    "A resposta do assistente foi descartada pela conferência automática (formato inválido ou "
    "conteúdo não permitido). Reformule a pergunta."
)
AVISO_SEM_EVIDENCIA = (
    "Resposta sem evidência conferida nos autos: confira nas páginas antes de usar."
)


@dataclass(frozen=True)
class LimitesAgente:
    """Tetos e modelo do agente (de `Settings`).

    Attributes:
        modelo: Modelo.
        max_turnos: Turnos por pergunta.
        max_paginas_originais: Páginas originais por conversa.
        max_tokens_chamada: Tokens por chamada.
        max_tokens_conversa: Tokens por conversa.
        max_tokens_processo: Tokens por processo.
    """

    modelo: str
    max_turnos: int
    max_paginas_originais: int
    max_tokens_chamada: int
    max_tokens_conversa: int
    max_tokens_processo: int


def limites_de(settings: Settings) -> LimitesAgente:
    """Limites a partir da configuração.

    Args:
        settings: Configuração.

    Returns:
        Limites.
    """
    return LimitesAgente(
        settings.modelo,
        settings.agente_max_turnos,
        settings.agente_max_paginas_originais,
        settings.agente_max_tokens_chamada,
        settings.agente_max_tokens_conversa,
        settings.agente_max_tokens_processo,
    )


@dataclass(frozen=True)
class ContextoChat:
    """Quem pergunta, sobre qual processo, com qual cliente.

    Attributes:
        session: Sessão da requisição.
        processo: Processo autorizado por `exige_processo`.
        usuario_id: Usuário.
        ctx: Contexto da requisição (auditoria).
        cliente: Cliente do modelo.
        limites: Limites.
        referencia: Data de referência das validações.
    """

    session: Session
    processo: ProcessoTabela
    usuario_id: UUID
    ctx: Contexto
    cliente: ClienteAgente
    limites: LimitesAgente
    referencia: date


def auditar_agente(
    chat: ContextoChat,
    acao: AcaoAuditoria,
    objeto_tipo: str,
    objeto_id: str,
    resultado: ResultadoEvento = ResultadoEvento.OK,
    **extra: Any,
) -> None:
    """Grava um evento do agente na cadeia do gabinete do processo.

    Args:
        chat: Contexto.
        acao: Ação.
        objeto_tipo: Tipo do objeto.
        objeto_id: Id do objeto (nunca conteúdo).
        resultado: Desfecho.
        **extra: `versao_modelo`, `versao_prompt`.
    """
    auditar(
        chat.session,
        chat.ctx,
        acao,
        resultado,
        usuario_id=chat.usuario_id,
        gabinete_id=chat.processo.gabinete_id,
        processo_id=chat.processo.id,
        objeto_tipo=objeto_tipo,
        objeto_id=objeto_id,
        **extra,
    )


def ficha_do_processo(session: Session, processo: ProcessoTabela) -> dict[str, Any]:
    """Ficha enviada ao modelo: número, classe, matéria e pseudônimos dos réus.

    Args:
        session: Sessão.
        processo: Processo.

    Returns:
        Ficha.
    """
    reus = sorted(
        r.pseudonimo
        for r in session.query(ReuTabela).filter(ReuTabela.processo_id == processo.id).all()
    )
    return {
        "numero_cnj": processo.numero_cnj,
        "classe": processo.classe,
        "materia": processo.materia,
        "reus": reus,
    }


def nova_sessao_agente(
    chat: ContextoChat, pseudonimizador: Pseudonimizador, paginas_originais: int
) -> SessaoAgente:
    """Sessão das ferramentas, travada no processo do contexto.

    Args:
        chat: Contexto.
        pseudonimizador: Pseudonimizador do processo.
        paginas_originais: Páginas originais já usadas na conversa.

    Returns:
        Sessão do agente.
    """
    return SessaoAgente(
        session=chat.session,
        gabinete_id=chat.processo.gabinete_id,
        processo_id=chat.processo.id,
        materia=chat.processo.materia,
        numero_cnj=chat.processo.numero_cnj,
        pseudonimizador=pseudonimizador,
        delimitador=Delimitador(),
        registrar=lambda acao, tipo, ident: auditar_agente(chat, acao, tipo, ident),
        referencia=chat.referencia,
        limite_paginas_originais=chat.limites.max_paginas_originais,
        paginas_originais=paginas_originais,
    )


@dataclass(frozen=True)
class Tentativa:
    """Uma chamada ao modelo já conferida.

    Attributes:
        resposta: Resposta do cliente (None em erro).
        conferencia: Conferência (None em erro ou teto).
        resultado: Resultado registrado.
    """

    resposta: RespostaAgente | None
    conferencia: Conferencia | None
    resultado: ResultadoChamada


def _resultado_da(conferencia: Conferencia) -> ResultadoChamada:
    if conferencia.desfecho is Desfecho.BLOQUEADA:
        return ResultadoChamada.BLOQUEADA
    if conferencia.desfecho is Desfecho.INVALIDA:
        return ResultadoChamada.INVALIDA
    return ResultadoChamada.OK


def _evento_da(resultado: ResultadoChamada) -> ResultadoEvento:
    return {
        ResultadoChamada.OK: ResultadoEvento.OK,
        ResultadoChamada.BLOQUEADA: ResultadoEvento.BLOQUEADO,
    }.get(resultado, ResultadoEvento.FALHA)


def registrar_chamada(
    chat: ContextoChat,
    conversa_id: UUID | None,
    pedido: PedidoAgente,
    saidas: list[str],
    resposta: RespostaAgente | None,
    resultado: ResultadoChamada,
) -> None:
    """Grava `chamada_modelo` (hashes, tokens, latência) e o evento de auditoria.

    Args:
        chat: Contexto.
        conversa_id: Conversa (None no dossiê).
        pedido: Pedido enviado.
        saidas: Resultados de ferramenta enviados ao modelo.
        resposta: Resposta (None em erro do cliente).
        resultado: Resultado da chamada.
    """
    prompt = prompt_sistema()
    chamada = repositorio.gravar_chamada(
        chat.session,
        gabinete_id=chat.processo.gabinete_id,
        processo_id=chat.processo.id,
        conversa_id=conversa_id,
        modelo=resposta.modelo if resposta else pedido.modelo,
        versao_prompt=prompt.identificador,
        hash_prompt_sistema=calcular_hash(pedido.prompt_sistema),
        hash_entrada=calcular_hash(pedido.mensagem + "".join(saidas)),
        hash_saida=calcular_hash(resposta.texto if resposta else ""),
        tokens_entrada=resposta.tokens_entrada if resposta else 0,
        tokens_saida=resposta.tokens_saida if resposta else 0,
        latencia_ms=resposta.latencia_ms if resposta else 0,
        ferramentas=[c.nome for c in resposta.chamadas] if resposta else [],
        resultado=resultado,
    )
    auditar_agente(
        chat,
        AcaoAuditoria.CHAMADA_MODELO,
        "chamada_modelo",
        str(chamada.id),
        _evento_da(resultado),
        versao_modelo=chamada.modelo[:100],
        versao_prompt=prompt.identificador,
    )


def conferir_resposta(
    chat: ContextoChat, texto: str, pseudonimizador: Pseudonimizador, extra_ids: set[str]
) -> Conferencia:
    """Confere a saída do modelo contra o banco.

    Args:
        chat: Contexto.
        texto: Saída do modelo.
        pseudonimizador: Pseudonimizador usado no envio.
        extra_ids: Ids próprios a aceitar (conversa).

    Returns:
        Conferência.
    """
    ids = repositorio.ids_do_processo(chat.session, chat.processo.id) | extra_ids
    citados = _ids_citados(texto)
    paginas = {
        pid: PaginaConferencia(t, n)
        for pid, (t, n) in repositorio.paginas_citadas(
            chat.session, chat.processo.id, citados
        ).items()
    }
    return conferir(texto, paginas, chat.processo.numero_cnj, ids, pseudonimizador.aplicar)


def _ids_citados(texto: str) -> list[UUID]:
    try:
        return [c.pagina_id for c in interpretar(texto).citacoes]
    except ValueError:
        return []


def chamar(
    chat: ContextoChat,
    conversa: ConversaTabela | None,
    pergunta_ou_mensagem: str,
    sessao: SessaoAgente,
    *,
    com_ferramentas: bool = True,
) -> Tentativa:
    """Chama o modelo (no máximo duas vezes se a saída vier fora do esquema) e confere.

    Args:
        chat: Contexto.
        conversa: Conversa (None no dossiê).
        pergunta_ou_mensagem: Pergunta do assessor (ou mensagem já montada sem ferramentas).
        sessao: Sessão das ferramentas.
        com_ferramentas: Se oferece as ferramentas.

    Returns:
        Última tentativa.
    """
    pseudonimizador = sessao.pseudonimizador
    ficha = ficha_do_processo(chat.session, chat.processo)
    extra = {str(conversa.id)} if conversa else set()
    tentativa = Tentativa(None, None, ResultadoChamada.ERRO)
    for _ in range(2):
        sessao.delimitador = Delimitador()
        sessao.saidas.clear()
        mensagem = (
            montar_mensagem(sessao.delimitador, ficha, pergunta_ou_mensagem, pseudonimizador)
            if com_ferramentas
            else pergunta_ou_mensagem
        )
        pedido = PedidoAgente(
            prompt_sistema=prompt_sistema().texto,
            mensagem=mensagem,
            modelo=chat.limites.modelo,
            max_turnos=chat.limites.max_turnos,
            ferramentas=criar_ferramentas(sessao) if com_ferramentas else (),
        )
        tentativa = _uma_tentativa(chat, conversa, pedido, sessao, pseudonimizador, extra)
        if tentativa.resultado is not ResultadoChamada.INVALIDA:
            break
    return tentativa


def _uma_tentativa(
    chat: ContextoChat,
    conversa: ConversaTabela | None,
    pedido: PedidoAgente,
    sessao: SessaoAgente,
    pseudonimizador: Pseudonimizador,
    extra: set[str],
) -> Tentativa:
    conversa_id = conversa.id if conversa else None
    try:
        resposta = asyncio.run(chat.cliente.responder(pedido))
    except ClienteAgenteError:
        registrar_chamada(chat, conversa_id, pedido, sessao.saidas, None, ResultadoChamada.ERRO)
        return Tentativa(None, None, ResultadoChamada.ERRO)
    if conversa is not None:
        conversa.tokens_entrada += resposta.tokens_entrada
        conversa.tokens_saida += resposta.tokens_saida
    if resposta.tokens_entrada + resposta.tokens_saida > chat.limites.max_tokens_chamada:
        registrar_chamada(chat, conversa_id, pedido, sessao.saidas, resposta, ResultadoChamada.TETO)
        return Tentativa(resposta, None, ResultadoChamada.TETO)
    conferencia = conferir_resposta(chat, resposta.texto, pseudonimizador, extra)
    resultado = _resultado_da(conferencia)
    registrar_chamada(chat, conversa_id, pedido, sessao.saidas, resposta, resultado)
    if resultado is ResultadoChamada.BLOQUEADA:
        motivo = conferencia.motivos[0] if conferencia.motivos else "bloqueada"
        revisao.abrir(chat.session, chat.ctx, chat.processo, motivo, chat.usuario_id)
    return Tentativa(resposta, conferencia, resultado)


def _avisos(conferencia: Conferencia) -> list[str]:
    avisos = []
    if conferencia.descartadas:
        avisos.append(
            f"{conferencia.descartadas} citação(ões) não conferiram com o texto da página e "
            "foram removidas."
        )
    if conferencia.desfecho is Desfecho.SEM_EVIDENCIA:
        avisos.append(AVISO_SEM_EVIDENCIA)
    return avisos


def _desfecho(tentativa: Tentativa) -> tuple[StatusMensagem, str, list[dict[str, Any]], list[str]]:
    if tentativa.resultado is ResultadoChamada.ERRO:
        return StatusMensagem.DESCARTADA, MSG_INDISPONIVEL, [], []
    if tentativa.resultado is ResultadoChamada.TETO:
        return StatusMensagem.DESCARTADA, MSG_TETO_CHAMADA, [], []
    conferencia = tentativa.conferencia
    if conferencia is None or conferencia.desfecho in (Desfecho.BLOQUEADA, Desfecho.INVALIDA):
        return StatusMensagem.DESCARTADA, MSG_DESCARTADA, [], []
    citacoes = [c.model_dump(mode="json") for c in conferencia.citacoes]
    status = (
        StatusMensagem.RESPONDIDA
        if conferencia.desfecho is Desfecho.RESPONDIDA
        else StatusMensagem.SEM_EVIDENCIA
    )
    return status, conferencia.texto, citacoes, _avisos(conferencia)


def _encerrar(conversa: ConversaTabela, motivo: str) -> None:
    conversa.encerrada = True
    conversa.motivo_encerramento = motivo


def _aplicar_tetos(chat: ContextoChat, conversa: ConversaTabela) -> list[str]:
    avisos = []
    if repositorio.tokens_do_processo(chat.session, chat.processo.id) >= (
        chat.limites.max_tokens_processo
    ):
        _encerrar(conversa, "teto_processo")
        avisos.append(MSG_TETO_PROCESSO)
    elif conversa.tokens_entrada + conversa.tokens_saida >= chat.limites.max_tokens_conversa:
        _encerrar(conversa, "teto_conversa")
        avisos.append(MSG_TETO_CONVERSA)
    return avisos


def _resposta(chat: ContextoChat, conversa: ConversaTabela, mensagem: Any) -> dict[str, Any]:
    dados = repositorio.serializar_mensagem(mensagem)
    dados["citacoes"] = repositorio.localizar_citacoes(
        chat.session, chat.processo.id, dados["citacoes"]
    )
    return {
        "conversa_id": str(conversa.id),
        "conversa_encerrada": conversa.encerrada,
        "citacoes_descartadas_na_conversa": conversa.citacoes_descartadas,
        "processo_em_revisao": revisao.em_revisao(chat.processo),
    } | dados


def _responder_sem_modelo(
    chat: ContextoChat, conversa: ConversaTabela, status: StatusMensagem, texto: str
) -> dict[str, Any]:
    mensagem = repositorio.gravar_mensagem(
        chat.session, conversa, PapelMensagem.AGENTE, status, texto
    )
    return _resposta(chat, conversa, mensagem)


def perguntar(chat: ContextoChat, pergunta: str) -> dict[str, Any]:
    """Responde uma pergunta do assessor sobre o processo.

    Args:
        chat: Contexto.
        pergunta: Pergunta (já validada em tamanho).

    Returns:
        Mensagem do agente serializada, com a conversa e o contador de descartes.
    """
    sessao_bd, processo = chat.session, chat.processo
    conversa = repositorio.conversa_aberta(
        sessao_bd, processo.gabinete_id, processo.id, chat.usuario_id
    )
    pergunta_gravada = repositorio.gravar_mensagem(
        sessao_bd, conversa, PapelMensagem.USUARIO, StatusMensagem.PERGUNTA, pergunta
    )
    auditar_agente(chat, AcaoAuditoria.PERGUNTA_CHAT, "mensagem", str(pergunta_gravada.id))
    if repositorio.tokens_do_processo(sessao_bd, processo.id) >= chat.limites.max_tokens_processo:
        _encerrar(conversa, "teto_processo")
        return _responder_sem_modelo(chat, conversa, StatusMensagem.TETO, MSG_TETO_PROCESSO)
    if revisao.em_revisao(processo):
        return _responder_sem_modelo(chat, conversa, StatusMensagem.RECUSA, revisao.MSG_EM_REVISAO)
    recusa = classificar(pergunta)
    if recusa is not None:
        return _responder_sem_modelo(chat, conversa, StatusMensagem.RECUSA, recusa.mensagem)
    sessao = nova_sessao_agente(
        chat,
        pseudonimizador_do_processo(sessao_bd, processo.id, chat.usuario_id),
        conversa.paginas_originais,
    )
    tentativa = chamar(chat, conversa, pergunta, sessao)
    conversa.paginas_originais = sessao.paginas_originais
    if tentativa.conferencia is not None:
        conversa.citacoes_descartadas += tentativa.conferencia.descartadas
    status, texto, citacoes, avisos = _desfecho(tentativa)
    if tentativa.resultado is ResultadoChamada.BLOQUEADA:
        avisos.append(revisao.MSG_EM_REVISAO)
    avisos += _aplicar_tetos(chat, conversa)
    if conversa.encerrada and status is StatusMensagem.DESCARTADA:
        status = StatusMensagem.TETO
    mensagem = repositorio.gravar_mensagem(
        sessao_bd, conversa, PapelMensagem.AGENTE, status, texto, citacoes, avisos
    )
    sessao_bd.flush()
    return _resposta(chat, conversa, mensagem)
