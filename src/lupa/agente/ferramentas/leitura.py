"""Ferramentas de leitura estruturada (Etapa 5.2).

`listar_pecas`, `ler_pagina_estruturada`, `buscar_texto`, `listar_fatos` e `listar_achados`.
Todas leem só o processo da `SessaoAgente` (fechamento criado por requisição); argumentos a mais
vindos do modelo, como um `processo_id` forjado, são ignorados. Todo texto dos autos sai
pseudonimizado e entre os delimitadores da chamada. `ler_pagina_estruturada` usa o texto
normalizado e nunca devolve `trechos_ocultos`.
"""

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from lupa.agente.contexto import formatar_segmentos, segmentos
from lupa.agente.ferramentas.sessao import (
    PaginaForaDoProcessoError,
    SessaoAgente,
    flags_ligadas,
    peca_da_pagina,
    resolver_pagina,
)
from lupa.config import Settings, get_settings
from lupa.dominio.repositorios import listar_fatos_por_processo
from lupa.dominio.tabelas import ArquivoTabela, PaginaTabela
from lupa.ingestao import repositorio_eventos, repositorio_pecas
from lupa.ingestao.deteccao import dobrar
from lupa.ingestao.saneamento import normalizar

MAX_RESULTADOS_BUSCA = 20
PAGINAS_POR_BLOCO_BUSCA = 200
MAX_FATOS = 200
ESQUEMA_PAGINA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pagina_id": {"type": "string", "description": "Id da página (de listar_pecas ou busca)"},
        "numero": {"type": "integer", "description": "Número da página no arquivo"},
        "arquivo_id": {"type": "string", "description": "Arquivo, se o processo tiver vários"},
    },
}


def erro(mensagem: str) -> str:
    """Resultado de ferramenta que recusa o pedido.

    Args:
        mensagem: Motivo, sem conteúdo dos autos.

    Returns:
        JSON `{"erro": ...}`.
    """
    return json.dumps({"erro": mensagem}, ensure_ascii=False)


def texto_analise(pagina: PaginaTabela) -> str:
    """Texto normalizado da página (recalculado do original se não gravado).

    Args:
        pagina: Página.

    Returns:
        Texto normalizado.
    """
    return (
        pagina.texto_normalizado
        if pagina.texto_normalizado is not None
        else normalizar(pagina.texto).texto
    )


def cabecalho_pagina(sessao: SessaoAgente, pagina: PaginaTabela) -> dict[str, Any]:
    """Cabeçalho de origem da página.

    Args:
        sessao: Sessão do agente.
        pagina: Página.

    Returns:
        Página, arquivo, tipo e origem da peça, flags.
    """
    tipo, origem = peca_da_pagina(sessao, pagina)
    return {
        "pagina_id": str(pagina.id),
        "arquivo_id": str(pagina.arquivo_id),
        "numero": pagina.numero,
        "tipo_peca": tipo,
        "origem": origem,
        "flags": flags_ligadas(pagina.flags),
    }


def listar_pecas(sessao: SessaoAgente, _argumentos: dict[str, Any]) -> str:
    """Índice do processo: peças vigentes com tipo, origem, páginas, data e flags.

    Args:
        sessao: Sessão do agente.
        _argumentos: Ignorados.

    Returns:
        Índice delimitado.
    """
    pecas = [
        {
            "ordem": p["ordem"],
            "peca_id": p["id"],
            "arquivo_id": p["arquivo_id"],
            "tipo": p["tipo"],
            "origem": p["origem"],
            "pagina_inicial": p["pagina_inicial"],
            "pagina_final": p["pagina_final"],
            "data": p["data"],
            "flags": p["resumo_flags"],
        }
        for p in repositorio_pecas.indice_processo(sessao.session, sessao.processo_id)
    ]
    corpo = sessao.pseudonimizador.aplicar_json(pecas)
    return sessao.delimitador.envelopar({"tipo": "indice_de_pecas"}, corpo)


def ler_pagina_estruturada(sessao: SessaoAgente, argumentos: dict[str, Any]) -> str:
    """Texto normalizado da página em segmentos com hash, com origem e flags.

    Args:
        sessao: Sessão do agente.
        argumentos: `pagina_id` ou `numero` (+ `arquivo_id`).

    Returns:
        Página delimitada, ou erro.
    """
    try:
        pagina = resolver_pagina(sessao, argumentos)
    except PaginaForaDoProcessoError as motivo:
        return erro(str(motivo))
    itens = segmentos(sessao.pseudonimizador.aplicar(texto_analise(pagina)))
    return sessao.delimitador.envelopar(cabecalho_pagina(sessao, pagina), formatar_segmentos(itens))


def limite_paginas_busca() -> int:
    """Teto de páginas decifradas por busca (`LUPA_BUSCA_MAX_PAGINAS`).

    Returns:
        O teto configurado (padrão da configuração se o ambiente não carregar).
    """
    try:
        return get_settings().busca_max_paginas
    except ValidationError:
        return int(Settings.model_fields["busca_max_paginas"].default)


def _paginas_com_termo(
    sessao: SessaoAgente, termo: str, limite_paginas: int | None = None
) -> list[PaginaTabela]:
    """Busca em memória (Etapa 7.5): o texto está cifrado no banco, então ILIKE não serve.

    Percorre as páginas do processo na ordem dos autos, decifrando sob demanda em blocos, até
    `MAX_RESULTADOS_BUSCA` acertos ou `limite_paginas` páginas lidas.
    """
    limite = limite_paginas or limite_paginas_busca()
    alvo = termo.lower()
    consulta = (
        select(PaginaTabela)
        .join(ArquivoTabela, ArquivoTabela.id == PaginaTabela.arquivo_id)
        .where(ArquivoTabela.processo_id == sessao.processo_id)
        .order_by(ArquivoTabela.enviado_em, ArquivoTabela.id, PaginaTabela.numero)
        .limit(limite)
        .execution_options(yield_per=PAGINAS_POR_BLOCO_BUSCA)
    )
    achadas: list[PaginaTabela] = []
    for pagina in sessao.session.scalars(consulta):
        if pagina.texto_normalizado is not None and alvo in pagina.texto_normalizado.lower():
            achadas.append(pagina)
            if len(achadas) >= MAX_RESULTADOS_BUSCA:
                break
    return achadas


def buscar_texto(sessao: SessaoAgente, argumentos: dict[str, Any]) -> str:
    """Páginas do processo que contêm o termo, com os segmentos onde ele aparece.

    Args:
        sessao: Sessão do agente.
        argumentos: `termo` (3 a 100 caracteres).

    Returns:
        Resultados delimitados, ou erro.
    """
    termo = str(argumentos.get("termo") or "").strip()
    if not 3 <= len(termo) <= 100:
        return erro("termo deve ter de 3 a 100 caracteres")
    dobrado = dobrar(termo)
    blocos = []
    for pagina in _paginas_com_termo(sessao, termo):
        itens = segmentos(sessao.pseudonimizador.aplicar(texto_analise(pagina)))
        achados = [(s, h) for s, h in itens if dobrado in dobrar(s)] or itens[:1]
        blocos.append(
            sessao.delimitador.envelopar(
                cabecalho_pagina(sessao, pagina), formatar_segmentos(achados)
            )
        )
    if not blocos:
        return json.dumps({"resultados": 0}, ensure_ascii=False)
    return "\n".join(blocos)


def listar_fatos(sessao: SessaoAgente, argumentos: dict[str, Any]) -> str:
    """Fatos do processo com valor, status e evidências citáveis.

    Args:
        sessao: Sessão do agente.
        argumentos: `tipo` opcional.

    Returns:
        Fatos delimitados.
    """
    tipo = argumentos.get("tipo")
    fatos = [
        {
            "fato_id": str(f.id),
            "tipo": f.tipo.value,
            "valor": f.valor,
            "status": f.status.value,
            "confianca": f.confianca,
            "evidencias": [
                {"pagina_id": str(e.pagina_id), "trecho": e.trecho, "hash_trecho": e.hash_trecho}
                for e in f.evidencias
            ],
        }
        for f in listar_fatos_por_processo(sessao.session, sessao.processo_id)
        if not tipo or f.tipo.value == tipo
    ][:MAX_FATOS]
    corpo = sessao.pseudonimizador.aplicar_json(fatos)
    return sessao.delimitador.envelopar({"tipo": "fatos_extraidos"}, corpo)


def listar_achados(sessao: SessaoAgente, _argumentos: dict[str, Any]) -> str:
    """Achados vigentes das validações, com valores e explicação do template.

    Args:
        sessao: Sessão do agente.
        _argumentos: Ignorados.

    Returns:
        Achados delimitados.
    """
    achados = [
        {
            "achado_id": str(a.id),
            "validacao": a.validacao,
            "resultado": a.resultado.value,
            "valores": a.valores,
            "explicacao": a.explicacao,
        }
        for a in repositorio_eventos.achados_vigentes(sessao.session, sessao.processo_id)
    ]
    corpo = sessao.pseudonimizador.aplicar_json(achados)
    return sessao.delimitador.envelopar({"tipo": "achados_das_validacoes"}, corpo)
