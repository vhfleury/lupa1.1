"""Montagem das ferramentas do agente para uma chamada (fechamento sobre a `SessaoAgente`)."""

from collections.abc import Callable
from typing import Any

from lupa.agente.cliente import FerramentaAgente
from lupa.agente.ferramentas.calculo import executar_validacao, nomes_validacoes
from lupa.agente.ferramentas.leitura import (
    ESQUEMA_PAGINA,
    buscar_texto,
    ler_pagina_estruturada,
    listar_achados,
    listar_fatos,
    listar_pecas,
)
from lupa.agente.ferramentas.original import ler_pagina_original
from lupa.agente.ferramentas.sessao import SessaoAgente

Funcao = Callable[[SessaoAgente, dict[str, Any]], str]
SEM_ARGUMENTOS: dict[str, Any] = {"type": "object", "properties": {}}


def _ligar(sessao: SessaoAgente, funcao: Funcao) -> Callable[[dict[str, Any]], Any]:
    async def _executar(argumentos: dict[str, Any]) -> str:
        saida = funcao(sessao, argumentos)
        sessao.saidas.append(saida)
        return saida

    return _executar


def _definicoes(sessao: SessaoAgente) -> list[tuple[str, str, dict[str, Any], Funcao]]:
    validacoes = nomes_validacoes(sessao.materia)
    return [
        ("listar_pecas", "Índice de peças do processo (tipo, origem, páginas, data, flags).",
         SEM_ARGUMENTOS, listar_pecas),
        ("ler_pagina_estruturada",
         "Texto saneado de uma página em segmentos citáveis [hash=H], com origem e flags.",
         ESQUEMA_PAGINA, ler_pagina_estruturada),
        ("buscar_texto", "Busca um termo nas páginas do processo; devolve os segmentos.",
         {"type": "object", "properties": {"termo": {"type": "string"}}, "required": ["termo"]},
         buscar_texto),
        ("listar_fatos", "Fatos extraídos (datas, recurso) com evidências citáveis.",
         {"type": "object", "properties": {"tipo": {"type": "string"}}}, listar_fatos),
        ("listar_achados", "Achados vigentes das validações, com valores e explicação.",
         SEM_ARGUMENTOS, listar_achados),
        ("executar_validacao",
         "Executa a validação determinística (prazo, prescrição, preventiva) e devolve o achado.",
         {"type": "object", "properties": {"nome": {"type": "string", "enum": validacoes}},
          "required": ["nome"]}, executar_validacao),
        ("ler_pagina_original",
         "Texto ORIGINAL da página (uso limitado e registrado); só se a estruturada falhou.",
         ESQUEMA_PAGINA, ler_pagina_original),
    ]  # fmt: skip


def criar_ferramentas(sessao: SessaoAgente) -> tuple[FerramentaAgente, ...]:
    """Ferramentas da chamada, todas travadas no processo da sessão.

    Args:
        sessao: Sessão do agente.

    Returns:
        Ferramentas prontas para o cliente.
    """
    return tuple(
        FerramentaAgente(nome, descricao, esquema, _ligar(sessao, funcao))
        for nome, descricao, esquema, funcao in _definicoes(sessao)
    )
