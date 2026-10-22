"""Política de quarentena: motivos enumerados, texto legível e leitura do resultado do parser.

Um job em `quarentena` é final (ver `lupa.ingestao.estados`): nada nele avança para a extração.
A tela de quarentena (etapa futura) lê `job_ingestao.motivo_quarentena` e `DESCRICOES`.
"""

from types import MappingProxyType
from typing import Any, Final

from lupa.dominio.enums import EstadoJob, MotivoQuarentena

M = MotivoQuarentena

DESCRICOES: Final = MappingProxyType(
    {
        M.CORROMPIDO: "Arquivo corrompido: a estrutura não pôde ser lida.",
        M.SENHA: "Arquivo protegido por senha: envie uma cópia sem senha.",
        M.TRUNCADO: "Arquivo truncado: o envio parece ter sido interrompido.",
        M.ASSINATURA_INVALIDA: (
            "Assinatura digital inválida: o arquivo foi alterado depois de assinado."
        ),
        M.TIPO_INVALIDO: "Tipo inválido: o conteúdo não é PDF.",
        M.ZIP_MALICIOSO: "ZIP recusado: caminho perigoso, link simbólico ou limites excedidos.",
    }
)


def descrever(motivo: MotivoQuarentena) -> str:
    """Texto legível do motivo.

    Args:
        motivo: Motivo de quarentena.

    Returns:
        Frase curta para o usuário.
    """
    return DESCRICOES[motivo]


def motivo_do_parser(dados: dict[str, Any]) -> MotivoQuarentena | None:
    """Lê o motivo de quarentena do JSON devolvido pelo parser no sandbox.

    Args:
        dados: Objeto devolvido pelo parser.

    Returns:
        O motivo, ou None se o arquivo passou; motivo desconhecido vira `corrompido`.
    """
    if dados.get("ok") is True:
        return None
    try:
        return MotivoQuarentena(str(dados.get("motivo_quarentena")))
    except ValueError:
        return MotivoQuarentena.CORROMPIDO


def pode_extrair(estado: EstadoJob) -> bool:
    """Diz se o job pode entrar na extração (só a partir de `validado`).

    Args:
        estado: Estado corrente.

    Returns:
        Verdadeiro apenas para `validado`; quarentena nunca entra.
    """
    return estado is EstadoJob.VALIDADO
