"""Relatório de qualidade por arquivo (4C.10) e conversão para a saída medida em 4B.10.

O relatório resume as páginas gravadas de um job: quantas por tipo e por rota, quantas o
roteador absteve, quantas faltam e por quê, flags, CER estimado (só onde há texto nativo e OCR
da mesma página para comparar), confiança média do OCR e tempos. Não carrega texto dos autos.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from lupa.dominio.enums import FlagPagina, TipoPagina
from lupa.ingestao.saneamento_pagina import versoes
from lupa.sinteticos.saida_pipeline import PaginaSaida, RefPagina, SaidaPipeline

CASAS = 4
MAX_FALTANDO_LISTADAS = 200
MAX_SINALIZADAS_LISTADAS = 500
FLAGS_SANEAMENTO = tuple(f.value for f in FlagPagina)


def _taxa(numerador: float, denominador: float) -> float | None:
    return round(numerador / denominador, CASAS) if denominador else None


def relatorio_qualidade(
    paginas: Sequence[dict[str, Any]],
    *,
    total_paginas: int,
    tempo_parede_segundos: float,
    falhas: dict[str, int] | None = None,
    versao_extrator: str,
    metadados: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Monta o relatório de qualidade.

    Args:
        paginas: Páginas gravadas, cada uma com `numero`, `tipo`, `flags` e `extracao` (`rota`,
            `segundos`, `ocr`, `divergencia`).
        total_paginas: Páginas esperadas no arquivo.
        tempo_parede_segundos: Tempo de parede somado das execuções do job.
        falhas: Páginas sem resultado por motivo.
        versao_extrator: Versão do extrator.
        metadados: Metadados descartados do arquivo (4D.2), para o resumo de saneamento.

    Returns:
        Relatório serializável em JSON.
    """
    extracoes = [p.get("extracao") or {} for p in paginas]
    rotas = Counter(str(e.get("rota", "desconhecida")) for e in extracoes)
    tipos = Counter(str(p["tipo"]) for p in paginas)
    flags = Counter(f for p in paginas for f, ligada in (p.get("flags") or {}).items() if ligada)
    divergencias = [e["divergencia"] for e in extracoes if e.get("divergencia")]
    caracteres = sum(int(d["caracteres"]) for d in divergencias)
    distancia = sum(int(d["distancia"]) for d in divergencias)
    confiancas = [float(e["ocr"]["confianca_media"]) for e in extracoes if e.get("ocr")]
    gravadas = {int(p["numero"]) for p in paginas}
    faltando = [n for n in range(1, total_paginas + 1) if n not in gravadas]
    return {
        "versao_extrator": versao_extrator,
        "versao_roteador": next((e.get("versao_roteador") for e in extracoes), None),
        "paginas_total": total_paginas,
        "paginas_extraidas": len(gravadas),
        "paginas_faltando": len(faltando),
        "paginas_faltando_lista": faltando[:MAX_FALTANDO_LISTADAS],
        "falhas_por_motivo": dict(sorted((falhas or {}).items())),
        "por_tipo": {t.value: tipos.get(t.value, 0) for t in TipoPagina},
        "por_rota": dict(sorted(rotas.items())),
        "abstidas": rotas.get("abstencao", 0),
        "flags": dict(sorted(flags.items())),
        "cer_estimado": _taxa(distancia, caracteres),
        "paginas_com_cer_estimado": sum(1 for d in divergencias if d["caracteres"]),
        "confianca_media_ocr": _taxa(sum(confiancas), len(confiancas)),
        "rotacoes_corrigidas": sum(
            1 for e in extracoes if e.get("ocr") and e["ocr"].get("rotacao_correcao")
        ),
        "tempo": {
            "parede_segundos": round(tempo_parede_segundos, 3),
            "paginas_segundos": round(sum(float(e.get("segundos", 0)) for e in extracoes), 3),
            "por_mil_paginas": _taxa(tempo_parede_segundos * 1000, total_paginas),
        },
        "saneamento": resumo_saneamento(paginas, metadados),
    }


def _ligadas(pagina: dict[str, Any]) -> list[str]:
    return sorted(f for f, ligada in (pagina.get("flags") or {}).items() if ligada)


def resumo_saneamento(
    paginas: Sequence[dict[str, Any]], metadados: Sequence[dict[str, Any]] = ()
) -> dict[str, Any]:
    """Resumo das flags de saneamento (4D.10) por página e por arquivo, sem texto dos autos.

    Args:
        paginas: Páginas com `numero`, `flags`, `ocultos` (quantidade) e `suspeitos` (trechos
            sem texto: categoria, padrão, offsets e hash).
        metadados: Metadados descartados do arquivo (só hash e categorias).

    Returns:
        Versões, páginas por flag, páginas sinalizadas, trechos por categoria e metadados.
    """
    por_flag = Counter(f for p in paginas for f in _ligadas(p))
    categorias = Counter(
        str(t.get("categoria")) for p in paginas for t in (p.get("suspeitos") or [])
    )
    sinalizadas = [
        {
            "numero": int(p["numero"]),
            "flags": _ligadas(p),
            "trechos_ocultos": int(p.get("ocultos") or 0),
            "trechos_suspeitos": len(p.get("suspeitos") or []),
        }
        for p in paginas
        if _ligadas(p)
    ]
    return {
        "versoes": versoes(),
        "paginas_por_flag": {f: por_flag.get(f, 0) for f in FLAGS_SANEAMENTO},
        "paginas_sinalizadas": len(sinalizadas),
        "paginas": sinalizadas[:MAX_SINALIZADAS_LISTADAS],
        "trechos_ocultos": sum(int(p.get("ocultos") or 0) for p in paginas),
        "trechos_suspeitos_por_categoria": dict(sorted(categorias.items())),
        "metadados_descartados": len(metadados),
        "metadado_suspeito": any(m.get("categorias") for m in metadados),
    }


def para_saida_pipeline(
    paginas: Iterable[dict[str, Any]], tempo_segundos: float | None
) -> SaidaPipeline:
    """Converte páginas extraídas para o formato de `scripts/medir.py` (só páginas).

    Args:
        paginas: Páginas com `origem_arquivo`, `pagina_origem`, `tipo` e `texto`.
        tempo_segundos: Tempo de parede da extração.

    Returns:
        Saída sem peças nem eventos (Etapas 4E e 4F).
    """
    return SaidaPipeline(
        paginas=tuple(
            PaginaSaida(
                ref=RefPagina(arquivo=str(p["origem_arquivo"]), pagina=int(p["pagina_origem"])),
                tipo=TipoPagina(p["tipo"]),
                texto=str(p.get("texto") or ""),
            )
            for p in sorted(paginas, key=lambda p: int(p["numero"]))
        ),
        tempo_segundos=tempo_segundos,
    )
