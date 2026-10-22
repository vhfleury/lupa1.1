"""Válvula de escape (Etapa 5.4): `ler_pagina_original`.

Devolve `pagina.texto` (o texto original como gravado, com o texto oculto já removido na
ingestão) em segmentos com hash e os `trechos_suspeitos` (posições, categoria e padrão; sem
texto). Limite de páginas por conversa; acima dele a ferramenta recusa com mensagem clara. Cada
uso gera `pagina_vista` com `objeto_tipo = "pagina_original_agente"`.
"""

from typing import Any

from lupa.agente.contexto import formatar_segmentos, segmentos
from lupa.agente.ferramentas.leitura import cabecalho_pagina, erro
from lupa.agente.ferramentas.sessao import PaginaForaDoProcessoError, SessaoAgente, resolver_pagina
from lupa.auditoria.eventos import AcaoAuditoria

CAMPOS_SUSPEITO = ("inicio_original", "fim_original", "hash", "categoria", "padrao", "origem")
OBJETO_PAGINA_ORIGINAL = "pagina_original_agente"


def mensagem_limite(limite: int) -> str:
    """Recusa clara quando o limite de páginas originais acaba.

    Args:
        limite: Limite da conversa.

    Returns:
        Mensagem.
    """
    return (
        f"limite de {limite} páginas originais por conversa atingido; use ler_pagina_estruturada "
        "ou peça ao assessor que abra a página no visualizador"
    )


def ler_pagina_original(sessao: SessaoAgente, argumentos: dict[str, Any]) -> str:
    """Texto original da página e trechos suspeitos, dentro do limite da conversa.

    Args:
        sessao: Sessão do agente.
        argumentos: `pagina_id` ou `numero` (+ `arquivo_id`).

    Returns:
        Página original delimitada, ou erro (inclusive de limite).
    """
    if sessao.paginas_originais >= sessao.limite_paginas_originais:
        return erro(mensagem_limite(sessao.limite_paginas_originais))
    try:
        pagina = resolver_pagina(sessao, argumentos)
    except PaginaForaDoProcessoError as motivo:
        return erro(str(motivo))
    sessao.paginas_originais += 1
    sessao.registrar(AcaoAuditoria.PAGINA_VISTA, OBJETO_PAGINA_ORIGINAL, str(pagina.id))
    suspeitos = [{c: t.get(c) for c in CAMPOS_SUSPEITO} for t in (pagina.trechos_suspeitos or [])]
    cabecalho = cabecalho_pagina(sessao, pagina) | {
        "texto": "original",
        "trechos_suspeitos": suspeitos,
    }
    itens = segmentos(sessao.pseudonimizador.aplicar(pagina.texto))
    return sessao.delimitador.envelopar(cabecalho, formatar_segmentos(itens))
