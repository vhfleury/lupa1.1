"""Conferência da resposta do modelo (Etapa 5.6): barreira decisiva, só código.

1. Esquema estrito (`RespostaModelo`, `extra="forbid"`); texto fora do JSON é rejeitado.
2. Instrução refletida (`padroes_instrucao.yaml` da ingestão, mais URLs) ou identificador de
   outro processo (número CNJ diferente, UUID que não é do processo): resposta descartada.
3. Cada citação: página do processo; trecho literal dentro do segmento cujo hash é
   `hash_trecho` (segmentos recalculados do texto gravado, normalizado e original, depois da
   pseudonimização), ou `hash_trecho == sha256(trecho)` com o trecho literal no texto da
   página. Citação que falha é removida e contada; sem nenhuma válida, `sem_evidencia`.
"""

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from lupa.agente.contexto import segmentos
from lupa.dominio.esquemas import calcular_hash
from lupa.ingestao.deteccao import encontrar_padroes
from lupa.ingestao.saneamento import normalizar

PADRAO_CNJ = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}")
PADRAO_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
PADRAO_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
CERCA = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class Citacao(BaseModel):
    """Citação devolvida pelo modelo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pagina_id: UUID
    trecho: str = Field(min_length=1, max_length=600)
    hash_trecho: str = Field(pattern=r"^[0-9a-f]{64}$")


class RespostaModelo(BaseModel):
    """Esquema estrito da resposta do modelo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    texto: str = Field(min_length=1, max_length=4000)
    citacoes: list[Citacao] = Field(default_factory=list, max_length=20)


class Desfecho(StrEnum):
    """Resultado da conferência."""

    RESPONDIDA = "respondida"
    SEM_EVIDENCIA = "sem_evidencia"
    INVALIDA = "invalida"
    BLOQUEADA = "bloqueada"


@dataclass(frozen=True)
class PaginaConferencia:
    """Texto gravado de uma página do processo.

    Attributes:
        texto: `pagina.texto` (original, sem texto oculto).
        texto_normalizado: `pagina.texto_normalizado` (ou None).
    """

    texto: str
    texto_normalizado: str | None


@dataclass
class Conferencia:
    """Resposta conferida.

    Attributes:
        desfecho: Respondida, sem evidência, inválida (esquema) ou bloqueada.
        texto: Texto a exibir (vazio se inválida ou bloqueada).
        citacoes: Citações válidas.
        descartadas: Quantas citações foram removidas.
        motivos: Motivos de descarte ou bloqueio (sem conteúdo).
    """

    desfecho: Desfecho
    texto: str = ""
    citacoes: list[Citacao] = field(default_factory=list)
    descartadas: int = 0
    motivos: list[str] = field(default_factory=list)


def interpretar(bruto: str) -> RespostaModelo:
    """Lê a saída do modelo no esquema estrito (aceita só a cerca ```json em volta).

    Args:
        bruto: Texto devolvido.

    Returns:
        Resposta validada.

    Raises:
        ValidationError: Fora do esquema.
        ValueError: Não é JSON.
    """
    texto = bruto.strip()
    cercado = CERCA.match(texto)
    return RespostaModelo.model_validate(json.loads(cercado.group(1) if cercado else texto))


def instrucao_refletida(texto: str) -> bool:
    """Se o texto tem forma de instrução dirigida a sistema ou ao usuário, ou URL.

    Args:
        texto: Texto da resposta ou de um trecho.

    Returns:
        Verdadeiro se deve ser bloqueado.
    """
    return bool(PADRAO_URL.search(texto)) or bool(encontrar_padroes(normalizar(texto).texto))


def outro_processo(texto: str, numero_cnj: str, ids_processo: frozenset[str]) -> bool:
    """Se o texto cita número CNJ ou UUID que não é deste processo.

    Args:
        texto: Texto.
        numero_cnj: Número do processo da conversa.
        ids_processo: UUIDs (minúsculos) que pertencem ao processo.

    Returns:
        Verdadeiro se há identificador estranho.
    """
    proprio = re.sub(r"\D", "", numero_cnj)
    if any(re.sub(r"\D", "", m) != proprio for m in PADRAO_CNJ.findall(texto)):
        return True
    return any(m.lower() not in ids_processo for m in PADRAO_UUID.findall(texto))


def _bases(pagina: PaginaConferencia, pseudonimizar: Callable[[str], str]) -> list[str]:
    normalizado = (
        pagina.texto_normalizado
        if pagina.texto_normalizado is not None
        else normalizar(pagina.texto).texto
    )
    return [pseudonimizar(normalizado), pseudonimizar(pagina.texto)]


def citacao_confere(
    citacao: Citacao, pagina: PaginaConferencia | None, pseudonimizar: Callable[[str], str]
) -> bool:
    """Confere uma citação contra o texto gravado da página.

    Args:
        citacao: Citação.
        pagina: Página do processo, ou None se não pertence a ele.
        pseudonimizar: Pseudonimização aplicada ao que foi enviado ao modelo.

    Returns:
        Verdadeiro se o trecho existe e o hash bate.
    """
    if pagina is None:
        return False
    bases = _bases(pagina, pseudonimizar)
    for base in bases:
        for segmento, hash_segmento in segmentos(base):
            if hash_segmento == citacao.hash_trecho and citacao.trecho in segmento:
                return True
    textos = (pagina.texto, *bases)
    return calcular_hash(citacao.trecho) == citacao.hash_trecho and any(
        citacao.trecho in t for t in textos
    )


def _bloqueio(
    resposta: RespostaModelo, numero_cnj: str, ids_processo: frozenset[str]
) -> str | None:
    textos = [resposta.texto, *(c.trecho for c in resposta.citacoes)]
    if instrucao_refletida(resposta.texto):
        return "instrucao_refletida"
    if any(outro_processo(t, numero_cnj, ids_processo) for t in textos):
        return "outro_processo"
    return None


def conferir(
    bruto: str,
    paginas: Mapping[UUID, PaginaConferencia],
    numero_cnj: str,
    ids_processo: Iterable[str],
    pseudonimizar: Callable[[str], str],
) -> Conferencia:
    """Confere a saída do modelo.

    Args:
        bruto: Texto devolvido pelo modelo.
        paginas: Páginas do processo citadas (as de fora não aparecem aqui).
        numero_cnj: Número do processo.
        ids_processo: UUIDs que pertencem ao processo.
        pseudonimizar: Pseudonimização usada no envio.

    Returns:
        Conferência com o desfecho e as citações válidas.
    """
    try:
        resposta = interpretar(bruto)
    except (ValueError, ValidationError):
        return Conferencia(Desfecho.INVALIDA, motivos=["esquema"])
    ids = frozenset(i.lower() for i in ids_processo)
    motivo = _bloqueio(resposta, numero_cnj, ids)
    if motivo:
        return Conferencia(Desfecho.BLOQUEADA, motivos=[motivo])
    validas = [
        c for c in resposta.citacoes if citacao_confere(c, paginas.get(c.pagina_id), pseudonimizar)
    ]
    descartadas = len(resposta.citacoes) - len(validas)
    motivos = ["citacao_invalida"] * descartadas
    desfecho = Desfecho.RESPONDIDA if validas else Desfecho.SEM_EVIDENCIA
    return Conferencia(desfecho, resposta.texto, validas, descartadas, motivos)
