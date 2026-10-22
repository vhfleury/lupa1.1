"""Matriz de permissões por papel, como dados.

Cada papel mapeia permissões para um escopo: `PROPRIO_GABINETE` ou `TODOS`. Permissão ausente
significa negada. A verificação fica em `pode`; nenhum outro módulo decide por `if` de papel.
"""

from enum import StrEnum
from types import MappingProxyType
from typing import Final
from uuid import UUID

from lupa.dominio.enums import PapelUsuario


class Permissao(StrEnum):
    """Ações sujeitas a autorização (linhas da matriz do plano)."""

    VER_PROCESSO = "ver_processo"
    SUBIR_PROCESSO = "subir_processo"
    ANOTAR = "anotar"
    VER_AUDITORIA = "ver_auditoria"
    GERIR_ASSESSOR = "gerir_assessor"
    RESETAR_ASSESSOR = "resetar_assessor"
    GERIR_DESEMBARGADOR = "gerir_desembargador"
    GERIR_GABINETES = "gerir_gabinetes"


class Escopo(StrEnum):
    """Alcance de uma permissão."""

    PROPRIO_GABINETE = "proprio_gabinete"
    TODOS = "todos"


_ASSESSOR = {
    Permissao.VER_PROCESSO: Escopo.PROPRIO_GABINETE,
    Permissao.SUBIR_PROCESSO: Escopo.PROPRIO_GABINETE,
    Permissao.ANOTAR: Escopo.PROPRIO_GABINETE,
}
_DESEMBARGADOR = _ASSESSOR | {
    Permissao.VER_AUDITORIA: Escopo.PROPRIO_GABINETE,
    Permissao.GERIR_ASSESSOR: Escopo.PROPRIO_GABINETE,
    Permissao.RESETAR_ASSESSOR: Escopo.PROPRIO_GABINETE,
}
_ADMINISTRADOR = {permissao: Escopo.TODOS for permissao in Permissao}

MATRIZ: Final = MappingProxyType(
    {
        PapelUsuario.ASSESSOR: MappingProxyType(_ASSESSOR),
        PapelUsuario.DESEMBARGADOR: MappingProxyType(_DESEMBARGADOR),
        PapelUsuario.ADMINISTRADOR: MappingProxyType(_ADMINISTRADOR),
    }
)

PERMISSAO_PARA_GERIR = MappingProxyType(
    {
        PapelUsuario.ASSESSOR: Permissao.GERIR_ASSESSOR,
        PapelUsuario.DESEMBARGADOR: Permissao.GERIR_DESEMBARGADOR,
    }
)
PERMISSAO_PARA_RESETAR = MappingProxyType(
    {
        PapelUsuario.ASSESSOR: Permissao.RESETAR_ASSESSOR,
        PapelUsuario.DESEMBARGADOR: Permissao.GERIR_DESEMBARGADOR,
    }
)


def tem_permissao(papel: PapelUsuario, permissao: Permissao) -> bool:
    """Diz se o papel tem a permissão em algum escopo.

    Args:
        papel: Papel do usuário.
        permissao: Ação desejada.

    Returns:
        Verdadeiro se a matriz concede a permissão.
    """
    return permissao in MATRIZ[papel]


def pode(
    papel: PapelUsuario,
    permissao: Permissao,
    gabinete_usuario: UUID | None,
    gabinete_alvo: UUID | None,
) -> bool:
    """Diz se o papel pode executar a ação sobre um alvo de determinado gabinete.

    Args:
        papel: Papel do usuário.
        permissao: Ação desejada.
        gabinete_usuario: Gabinete do usuário (None para o administrador).
        gabinete_alvo: Gabinete do objeto da ação.

    Returns:
        Verdadeiro se a matriz concede a permissão naquele escopo.
    """
    escopo = MATRIZ[papel].get(permissao)
    if escopo is Escopo.TODOS:
        return True
    return (
        escopo is Escopo.PROPRIO_GABINETE
        and gabinete_usuario is not None
        and gabinete_usuario == gabinete_alvo
    )
