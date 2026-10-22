"""Saneamento do texto de uma página (Etapas 4D.3 a 4D.9), executado no filho do sandbox.

`sanear` recebe o texto original (que fica intacto em `pagina.texto`) e devolve o texto
normalizado com os blocos codificados trocados pelo marcador, os trechos suspeitos (padrões de
instrução, blocos codificados, idioma inesperado) com offsets no normalizado e no original,
hash do trecho original e origem da peça (`desconhecida` até a 4E), as flags da página e um
resumo com as versões dos YAML usados.
"""

from dataclasses import dataclass
from typing import Any

from lupa.dominio.enums import FlagPagina, OrigemPeca
from lupa.ingestao.deteccao import (
    CATEGORIA_BLOCO,
    CATEGORIA_IDIOMA,
    MARCADOR_BLOCO,
    Ocorrencia,
    densidade_anomala,
    densidade_padrao,
    detectar_blocos,
    detectar_idioma,
    encontrar_padroes,
    idiomas_padrao,
    padroes_padrao,
)
from lupa.ingestao.saneamento import TextoNormalizado, hash_trecho, homoglifos_padrao, normalizar

VERSAO_SANEAMENTO = "4d.1"


def versoes() -> dict[str, str]:
    """Versões do saneamento e de cada YAML usado.

    Returns:
        Versões por componente.
    """
    return {
        "saneamento": VERSAO_SANEAMENTO,
        "homoglifos": homoglifos_padrao().versao,
        "padroes_instrucao": padroes_padrao().versao,
        "idiomas": idiomas_padrao().versao,
        "densidade": densidade_padrao().versao,
    }


def categorias_de(texto: str) -> list[str]:
    """Categorias de instrução presentes num texto avulso (metadado, texto oculto).

    Args:
        texto: Texto original.

    Returns:
        Categorias distintas, ordenadas.
    """
    return sorted({o.categoria for o in encontrar_padroes(normalizar(texto).texto)})


@dataclass(frozen=True)
class ResultadoSaneamento:
    """Resultado do saneamento de uma página.

    Attributes:
        texto_normalizado: Texto de análise.
        trechos_suspeitos: Trechos `{inicio, fim, inicio_original, fim_original, hash,
            categoria, padrao, origem}`.
        flags: Flags ligadas.
        resumo: Contagens e versões.
    """

    texto_normalizado: str
    trechos_suspeitos: list[dict[str, Any]]
    flags: dict[str, bool]
    resumo: dict[str, Any]


def _trecho(
    original: str, normalizado: TextoNormalizado, ocorrencia: Ocorrencia, origem: OrigemPeca
) -> dict[str, Any]:
    inicio, fim = normalizado.para_original(ocorrencia.inicio, ocorrencia.fim)
    return {
        "inicio": ocorrencia.inicio,
        "fim": ocorrencia.fim,
        "inicio_original": inicio,
        "fim_original": fim,
        "hash": hash_trecho(original, inicio, fim) if fim > inicio else None,
        "categoria": ocorrencia.categoria,
        "padrao": ocorrencia.padrao,
        "origem": origem.value,
    }


def _remover_blocos(normalizado: TextoNormalizado) -> tuple[list[Ocorrencia], int]:
    ocorrencias: list[Ocorrencia] = []
    rodapes = 0
    deslocamento = 0
    for bloco in detectar_blocos(normalizado.texto):
        if bloco.rodape:
            rodapes += 1
            continue
        inicio = bloco.inicio + deslocamento
        normalizado.substituir(inicio, bloco.fim + deslocamento, MARCADOR_BLOCO)
        fim = inicio + len(MARCADOR_BLOCO)
        deslocamento += len(MARCADOR_BLOCO) - (bloco.fim - bloco.inicio)
        ocorrencias.append(Ocorrencia(inicio, fim, CATEGORIA_BLOCO, f"cod_{bloco.codificacao}"))
        if bloco.decodificado is not None:
            ocorrencias += [
                Ocorrencia(inicio, fim, o.categoria, f"decodificado:{o.padrao}")
                for o in encontrar_padroes(normalizar(bloco.decodificado).texto)
            ]
    return ocorrencias, rodapes


def _flags(
    ocorrencias: list[Ocorrencia], normalizado: TextoNormalizado, densa: bool
) -> dict[str, bool]:
    categorias = {o.categoria for o in ocorrencias}
    candidatas = {
        FlagPagina.BLOCO_CODIFICADO: CATEGORIA_BLOCO in categorias,
        FlagPagina.IDIOMA_INESPERADO: CATEGORIA_IDIOMA in categorias,
        FlagPagina.PADRAO_INSTRUCAO: bool(categorias - {CATEGORIA_BLOCO, CATEGORIA_IDIOMA}),
        FlagPagina.HOMOGLIFOS: normalizado.homoglifos > 0,
        FlagPagina.DENSIDADE_ANOMALA: densa,
    }
    return {flag.value: True for flag, ligada in candidatas.items() if ligada}


def sanear(
    texto: str, tipo: str, origem: OrigemPeca = OrigemPeca.DESCONHECIDA
) -> ResultadoSaneamento:
    """Saneia o texto de uma página.

    Args:
        texto: Texto original da página.
        tipo: Tipo da página (para o limite de densidade).
        origem: Origem da peça a que a página pertence.

    Returns:
        Normalizado, trechos suspeitos, flags e resumo.
    """
    normalizado = normalizar(texto)
    ocorrencias, rodapes = _remover_blocos(normalizado)
    ocorrencias += encontrar_padroes(normalizado.texto) + detectar_idioma(normalizado.texto)
    ocorrencias.sort(key=lambda o: (o.inicio, o.fim, o.padrao))
    densa = densidade_anomala(texto, tipo)
    return ResultadoSaneamento(
        texto_normalizado=normalizado.texto,
        trechos_suspeitos=[_trecho(texto, normalizado, o, origem) for o in ocorrencias],
        flags=_flags(ocorrencias, normalizado, densa),
        resumo={
            "versoes": versoes(),
            "caracteres": len(texto),
            "homoglifos": normalizado.homoglifos,
            "controles_removidos": normalizado.removidos,
            "blocos_removidos": sum(1 for o in ocorrencias if o.categoria == CATEGORIA_BLOCO),
            "blocos_rodape": rodapes,
            "ocorrencias": len(ocorrencias),
        },
    )
