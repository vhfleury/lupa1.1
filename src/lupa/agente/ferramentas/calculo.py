"""Ferramenta de cálculo (Etapa 5.3): o motor da Etapa 2 como ferramenta do agente.

`executar_validacao(nome)` roda o catálogo da matéria sobre os fatos gravados do processo e
devolve o achado completo (resultado, valores, fatos usados e explicação do template). Não grava
achado: a fonte da verdade continua sendo a ingestão. Cada uso gera `validacao_executada` com
`objeto_tipo = "validacao_agente"`.
"""

from typing import Any

from lupa.agente.ferramentas.leitura import erro
from lupa.agente.ferramentas.sessao import SessaoAgente
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.dominio.repositorios import listar_fatos_por_processo
from lupa.validacoes.adaptador import para_modelo
from lupa.validacoes.catalogo import validacoes_de
from lupa.validacoes.motor import executar_catalogo


def nomes_validacoes(materia: str) -> list[str]:
    """Validações disponíveis na matéria.

    Args:
        materia: Matéria do processo.

    Returns:
        Nomes, na ordem do catálogo.
    """
    return [v.nome for v in validacoes_de(materia)]


def executar_validacao(sessao: SessaoAgente, argumentos: dict[str, Any]) -> str:
    """Executa uma validação determinística sobre os fatos do processo.

    Args:
        sessao: Sessão do agente.
        argumentos: `nome` da validação.

    Returns:
        Achado completo delimitado, ou erro.
    """
    nome = str(argumentos.get("nome") or "")
    disponiveis = nomes_validacoes(sessao.materia)
    if nome not in disponiveis:
        return erro(f"validação desconhecida; use uma de: {', '.join(disponiveis)}")
    modelo = para_modelo(listar_fatos_por_processo(sessao.session, sessao.processo_id))
    achado = next(
        a
        for a in executar_catalogo(modelo, sessao.materia, sessao.referencia)
        if a.validacao == nome
    )
    sessao.registrar(AcaoAuditoria.VALIDACAO_EXECUTADA, "validacao_agente", nome)
    corpo = sessao.pseudonimizador.aplicar_json(
        achado.model_dump(mode="json") | {"data_referencia": sessao.referencia.isoformat()}
    )
    return sessao.delimitador.envelopar({"tipo": "resultado_da_validacao"}, corpo)
