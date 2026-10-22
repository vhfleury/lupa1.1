"""Identificação de réus pela qualificação na denúncia e pseudonimização (Etapa 4F.5).

Na denúncia, cada réu aparece qualificado: nome seguido de vírgula e de um termo de
qualificação ("brasileiro", "inscrito no CPF", "nascido em", "vulgo"...). O nome, o CPF e a
posição ficam só aqui e em ``reu_identidade``; fatos, achados e logs usam o pseudônimo
(``REU-01``) ou o id do réu. ``sem_nomes`` recorta o trecho de evidência para que ele não
carregue o nome nem o documento do réu.
"""

import re
from collections.abc import Sequence

from lupa.dominio.enums import TipoPeca
from lupa.ingestao.eventos.modelo import Candidato, PecaTexto, ReuQualificado

_MAIUSCULA = "A-ZÀ-ÖØ-Þ"
_MINUSCULA = "a-zß-öø-ÿ'"
_PALAVRA = rf"(?:[{_MAIUSCULA}][{_MINUSCULA}]+|[{_MAIUSCULA}]{{2,}})"
NOME = rf"{_PALAVRA}(?:\s+(?:(?:[dD][aeoAEO][sS]?|e|E)\s+)?{_PALAVRA}){{1,7}}"
QUALIFICACAO = re.compile(
    rf"(?P<nome>{NOME})\s*,\s*(?:brasileir[oa]|estrangeir[oa]|nacional|solteir[oa]|casad[oa]|"
    r"vulgo|qualificad[oa]|portador[a]?|inscrit[oa]|nascid[oa]|natural)"
)
CPF = re.compile(r"CPF[^0-9\n]{0,30}(?P<cpf>\d{3}\.?\d{3}\.?\d{3}-?\d{2})")
DISTANCIA_CPF = 250
PREFIXO_PSEUDONIMO = "REU"


def pseudonimo(ordem: int) -> str:
    """Pseudônimo do réu pela ordem em que aparece.

    Args:
        ordem: 1, 2, ...

    Returns:
        ``REU-01``, ``REU-02``...
    """
    return f"{PREFIXO_PSEUDONIMO}-{ordem:02d}"


def identificar_reus(pecas: Sequence[PecaTexto]) -> list[ReuQualificado]:
    """Réus qualificados nas denúncias do processo, na ordem em que aparecem.

    Args:
        pecas: Peças do processo.

    Returns:
        Réus distintos (pelo nome, sem diferença de caixa).
    """
    reus: list[ReuQualificado] = []
    vistos: set[str] = set()
    for peca in pecas:
        if peca.tipo is not TipoPeca.DENUNCIA:
            continue
        for pagina in peca.paginas:
            texto = pagina.texto
            for casamento in QUALIFICACAO.finditer(texto):
                nome = " ".join(casamento.group("nome").split())
                if nome.casefold() in vistos:
                    continue
                vistos.add(nome.casefold())
                janela = texto[casamento.end() : casamento.end() + DISTANCIA_CPF]
                cpf = CPF.search(janela)
                reus.append(
                    ReuQualificado(
                        pseudonimo(len(reus) + 1),
                        nome,
                        cpf.group("cpf") if cpf else None,
                        pagina.id,
                        casamento.start("nome"),
                    )
                )
    return reus


def _ocorrencias(texto: str, termo: str) -> list[tuple[int, int]]:
    padrao = r"\s+".join(re.escape(parte) for parte in termo.split())
    return [m.span() for m in re.finditer(padrao, texto, re.IGNORECASE)]


def sensiveis(reus: Sequence[ReuQualificado]) -> list[str]:
    """Nomes e documentos que não podem sair da identidade do réu.

    Args:
        reus: Réus.

    Returns:
        Termos sensíveis.
    """
    return [t for r in reus for t in (r.nome, r.documento) if t]


def sem_nomes(texto: str, inicio: int, fim: int, termos: Sequence[str]) -> int:
    """Novo início do trecho, depois do último nome ou documento sensível dentro dele.

    Args:
        texto: Texto original da página.
        inicio: Início do trecho.
        fim: Fim do trecho.
        termos: Termos sensíveis.

    Returns:
        Início recortado (igual a ``inicio`` se não há termo sensível; pode chegar a ``fim``).
    """
    novo = inicio
    for termo in termos:
        for comeco, final in _ocorrencias(texto, termo):
            if comeco < fim and final > novo:
                novo = max(novo, min(final, fim))
    while novo < fim and not texto[novo].isalnum():
        novo += 1
    return novo


def reu_do_candidato(candidato: Candidato, reus: Sequence[ReuQualificado]) -> str | None:
    """Pseudônimo do réu a que o valor pertence.

    Nascimento: o réu qualificado mais próximo antes do trecho, na mesma página. Demais fatos por
    réu: o réu cujo nome aparece no trecho. Com um único réu, é sempre ele.

    Args:
        candidato: Candidato por réu.
        reus: Réus do processo.

    Returns:
        Pseudônimo, ou None se não dá para saber.
    """
    if len(reus) == 1:
        return reus[0].pseudonimo
    texto = candidato.pagina.texto
    anteriores = [
        r for r in reus if r.pagina_id == candidato.pagina.id and r.inicio <= candidato.inicio
    ]
    citados = [
        r
        for r in reus
        if any(candidato.inicio <= c < candidato.fim for c, _ in _ocorrencias(texto, r.nome))
    ]
    if citados:
        return citados[-1].pseudonimo
    if anteriores:
        return max(anteriores, key=lambda r: r.inicio).pseudonimo
    return None
