"""Medições da Etapa 4C nos processos de referência (``.sinteticos/referencia``).

Roda dentro do contêiner ``api`` (que monta ``.sinteticos`` só para leitura) e usa as mesmas
funções da pipeline: ``parser_pdf``/``diagnostico`` no sandbox, ``sinais`` + ``roteador`` e
``extracao`` (lotes em processos filhos do sandbox). Saídas em ``/tmp/medicao-4c`` (dentro do
contêiner); o resumo vai para stdout em JSON.

Subcomandos:

- ``diagnostico``: os três cenários dos dez processos contra ``diagnostico_esperado`` e, no
  cenário com índice, as fronteiras do índice e dos bookmarks contra as peças do gabarito.
- ``roteador``: matriz de confusão do roteador sobre as folhas do cenário ``pdf_liso`` e
  conferência do texto nativo das páginas nativas com ``texto_camada``.
- ``ocr``: CER e datas literais por nível de degradação numa amostra de páginas digitalizadas.
- ``tempo``: tempo por mil páginas, nativo e digitalizado, com o paralelismo padrão.
- ``extrair``: pipeline completa (sem banco) de um processo; grava ``saida.json`` no formato de
  ``lupa.sinteticos.saida_pipeline`` e ``relatorio.json`` (relatório de qualidade).
- ``eventos`` (4F.9): sobre as páginas já extraídas por ``extrair`` (cenário liso, as mesmas
  folhas nos três cenários), monta o índice com o diagnóstico real de cada cenário, extrai os
  eventos, mede precisão e recall de eventos e de datas e compara os achados do catálogo com o
  ``resultado_esperado`` do gabarito (na ``data_referencia`` do gabarito).
"""

import argparse
import gzip
import json
import random
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from uuid import uuid4

import fitz

from lupa.ingestao.diagnostico import diagnosticar_pdf, diagnosticar_zip
from lupa.ingestao.eventos.etapa import executar_validacoes
from lupa.ingestao.eventos.fatos import extrair_fatos
from lupa.ingestao.eventos.modelo import PaginaTexto, PecaTexto
from lupa.ingestao.eventos.reus import identificar_reus
from lupa.ingestao.eventos.saida import eventos_saida
from lupa.ingestao.extracao import (
    FontePaginas,
    LimitadorGabinete,
    Paralelismo,
    executar_em_paralelo,
    linha_pagina,
    planejar,
)
from lupa.ingestao.extrator_paginas import VERSAO_EXTRATOR
from lupa.ingestao.indice import montar_indice, pecas_saida
from lupa.ingestao.inventario import LimitesZip, inventariar
from lupa.ingestao.ocr import ocr_pagina
from lupa.ingestao.qualidade import para_saida_pipeline, relatorio_qualidade
from lupa.ingestao.roteador import rotear
from lupa.ingestao.sandbox import LimitesSandbox, inspecionar_pdf, inspecionar_pdfs
from lupa.ingestao.sinais import medir_sinais
from lupa.ingestao.texto_nativo import extrair_texto_nativo
from lupa.sinteticos.achados import comparar as comparar_achados
from lupa.sinteticos.gabarito import Cenario, Gabarito
from lupa.sinteticos.medicao import levenshtein, mapa_folhas, medir, normalizar
from lupa.sinteticos.saida_pipeline import PaginaSaida, RefPagina, SaidaPipeline
from lupa.validacoes.adaptador import para_modelo

RAIZ = Path("/app/.sinteticos/referencia")
SAIDA = Path("/tmp/medicao-4c")
LIMITES_INSPECAO = LimitesSandbox(memoria_mb=2048, cpu_segundos=300, tempo_segundos=600)
LIMITES_LOTE = LimitesSandbox(memoria_mb=1024, cpu_segundos=120, tempo_segundos=300)
DATA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
ESPERADO_ROTA = {
    "nativa": {"nativa"},
    "capa": {"nativa"},
    "vazia": {"vazia"},
    "digitalizada": {"ocr"},
    "hibrida_corpo": {"ocr", "abstencao"},
    "hibrida_assinatura": {"ocr", "abstencao"},
}


def _sementes() -> list[Path]:
    return sorted(p for p in RAIZ.iterdir() if p.is_dir())


def _gabarito(pasta: Path) -> Gabarito:
    return Gabarito.model_validate_json((pasta / "gabarito.json").read_text(encoding="utf-8"))


def _diagnosticar(pasta: Path, cenario: Cenario) -> Any:
    if cenario is Cenario.ZIP_POR_PECA:
        with tempfile.TemporaryDirectory() as tmp:
            extraidas = inventariar(pasta / "autos.zip", Path(tmp), LimitesZip())
            inspecoes = inspecionar_pdfs([e.caminho for e in extraidas], LIMITES_INSPECAO)
            entradas = [
                (e.manifesto.nome, r.dados) for e, r in zip(extraidas, inspecoes, strict=False)
            ]
        return diagnosticar_zip(uuid4(), entradas)
    resultado = inspecionar_pdf(pasta / "autos.pdf", LIMITES_INSPECAO)
    if not resultado.ok:
        raise RuntimeError(f"inspeção falhou: {resultado.motivo_falha}")
    return diagnosticar_pdf(uuid4(), "autos.pdf", resultado.dados)


def comando_diagnostico(_args: argparse.Namespace) -> dict[str, Any]:
    """Diagnóstico dos 30 arquivos e fronteiras do cenário com índice."""
    linhas = []
    for semente in _sementes():
        for cenario in Cenario:
            pasta = semente / cenario.value
            gabarito = _gabarito(pasta)
            inicio = time.perf_counter()
            diagnostico = _diagnosticar(pasta, cenario)
            linha: dict[str, Any] = {
                "processo": semente.name,
                "cenario": cenario.value,
                "esperado": gabarito.processo.diagnostico_esperado,
                "obtido": diagnostico.cenario.value,
                "segundos": round(time.perf_counter() - inicio, 2),
            }
            if cenario is Cenario.PDF_INDICE:
                deslocamento = gabarito.arquivos[0].folhas.count(None)
                esperadas = [p.pagina_inicial + deslocamento for p in gabarito.pecas]
                datas = [p.data.isoformat() for p in gabarito.pecas]
                for fonte in ("indice", "bookmark"):
                    obtidas = [f for f in diagnostico.fronteiras_origem if f["fonte"] == fonte]
                    linha[f"fronteiras_{fonte}"] = {
                        "esperadas": len(esperadas),
                        "obtidas": len(obtidas),
                        "paginas_iguais": sum(
                            a == b
                            for a, b in zip(esperadas, [f["pagina"] for f in obtidas], strict=False)
                        ),
                        "datas_iguais": sum(
                            a == b
                            for a, b in zip(datas, [f["data"] for f in obtidas], strict=False)
                        ),
                    }
                linha["paginas_indice"] = {
                    "esperadas": deslocamento,
                    "obtidas": diagnostico.sinais["paginas_indice"],
                }
            if cenario is Cenario.ZIP_POR_PECA:
                continuas = [f["pagina_continua"] for f in diagnostico.fronteiras_origem]
                inicios = [p.pagina_inicial for p in gabarito.pecas]
                linha["fronteiras_manifesto"] = {
                    "esperadas": len(inicios),
                    "iguais": sum(a == b for a, b in zip(inicios, continuas, strict=False)),
                }
            linhas.append(linha)
            print(json.dumps(linha, ensure_ascii=False), file=sys.stderr, flush=True)
    acertos = sum(linha["esperado"] == linha["obtido"] for linha in linhas)
    return {"acertos": acertos, "total": len(linhas), "linhas": linhas}


def comando_roteador(_args: argparse.Namespace) -> dict[str, Any]:
    """Matriz de confusão do roteador e conferência do texto nativo."""
    matriz: Counter[tuple[str, str]] = Counter()
    nativo = Counter()
    divergencias_nativo: list[dict[str, Any]] = []
    for semente in _sementes():
        pasta = semente / Cenario.PDF_LISO.value
        gabarito = _gabarito(pasta)
        documento = fitz.open(pasta / "autos.pdf")
        for pagina in gabarito.paginas:
            folha = documento[pagina.numero - 1]
            rota = rotear(medir_sinais(folha))
            matriz[(pagina.composicao.value, rota.value if rota else "abstencao")] += 1
            if pagina.composicao.value in ("nativa", "capa"):
                texto = extrair_texto_nativo(folha).texto
                if texto == pagina.texto_camada:
                    nativo["igual"] += 1
                elif sorted(texto.splitlines()) == sorted(pagina.texto_camada.splitlines()):
                    nativo["mesmas_linhas_outra_ordem"] += 1
                    divergencias_nativo.append(
                        {"processo": semente.name, "folha": pagina.numero,
                         "elementos": [e.value for e in pagina.elementos]}
                    )  # fmt: skip
                else:
                    nativo["diferente"] += 1
        print(semente.name, file=sys.stderr, flush=True)
    perigosos = sum(
        n
        for (composicao, rota), n in matriz.items()
        if composicao in ("digitalizada", "hibrida_corpo", "hibrida_assinatura")
        and rota == "nativa"
    )
    com_imagem = sum(
        n
        for (composicao, _), n in matriz.items()
        if composicao in ("digitalizada", "hibrida_corpo", "hibrida_assinatura")
    )
    corretos = sum(n for (c, r), n in matriz.items() if r in ESPERADO_ROTA[c])
    return {
        "matriz": {f"{c}|{r}": n for (c, r), n in sorted(matriz.items())},
        "total": sum(matriz.values()),
        "corretos": corretos,
        "falso_negativo_perigoso": perigosos,
        "paginas_com_imagem": com_imagem,
        "texto_nativo": dict(nativo),
        "texto_nativo_ordem_diferente": divergencias_nativo,
    }


def comando_ocr(args: argparse.Namespace) -> dict[str, Any]:
    """CER e datas literais por nível, em amostra estratificada de páginas digitalizadas."""
    rng = random.Random(args.semente)
    acumulado: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0.0])
    for semente in _sementes():
        pasta = semente / Cenario.PDF_LISO.value
        gabarito = _gabarito(pasta)
        documento = fitz.open(pasta / "autos.pdf")
        por_nivel: dict[str, list[Any]] = defaultdict(list)
        for pagina in gabarito.paginas:
            if pagina.composicao.value == "digitalizada" and pagina.degradacao:
                por_nivel[pagina.degradacao.value].append(pagina)
        for nivel, paginas in sorted(por_nivel.items()):
            for pagina in rng.sample(paginas, min(args.por_nivel, len(paginas))):
                inicio = time.perf_counter()
                resultado = ocr_pagina(documento[pagina.numero - 1])
                segundos = time.perf_counter() - inicio
                esperado = normalizar(pagina.texto)
                lido = normalizar(resultado.texto)
                datas = DATA.findall(pagina.texto)
                a = acumulado[nivel]
                a[0] += 1
                a[1] += len(esperado)
                a[2] += levenshtein(esperado, lido)
                a[3] += len(datas)
                a[4] += sum(1 for d in datas if d in resultado.texto)
                a[5] += segundos
        print(semente.name, file=sys.stderr, flush=True)
    return {
        nivel: {
            "paginas": int(a[0]),
            "caracteres": int(a[1]),
            "cer": round(a[2] / a[1], 4) if a[1] else None,
            "datas": int(a[3]),
            "datas_encontradas": int(a[4]),
            "taxa_datas": round(a[4] / a[3], 4) if a[3] else None,
            "segundos_por_pagina": round(a[5] / a[0], 2) if a[0] else None,
        }
        for nivel, a in sorted(acumulado.items())
    }


def _rodar(caminho: Path, nome: str, paginas: int, paralelismo: Paralelismo) -> tuple[list, float]:
    tarefas = planejar([FontePaginas(caminho, nome, paginas, 0)], paralelismo.paginas_por_lote)
    inicio = time.perf_counter()
    resultados = list(
        executar_em_paralelo(
            tarefas, LIMITES_LOTE, paralelismo, "medicao", limitador=LimitadorGabinete()
        )
    )
    return resultados, time.perf_counter() - inicio


def _subconjunto(composicoes: set[str], quantidade: int, destino: Path) -> int:
    saida = fitz.open()
    for semente in _sementes():
        pasta = semente / Cenario.PDF_LISO.value
        gabarito = _gabarito(pasta)
        documento = fitz.open(pasta / "autos.pdf")
        for pagina in gabarito.paginas:
            if pagina.composicao.value in composicoes and saida.page_count < quantidade:
                saida.insert_pdf(documento, from_page=pagina.numero - 1, to_page=pagina.numero - 1)
        if saida.page_count >= quantidade:
            break
    saida.save(destino, garbage=3, deflate=True)
    return saida.page_count


def comando_tempo(args: argparse.Namespace) -> dict[str, Any]:
    """Tempo por mil páginas com o paralelismo padrão (4 lotes de 8 páginas)."""
    paralelismo = Paralelismo(args.lote, args.lotes, args.lotes)
    resultado: dict[str, Any] = {"paralelismo": paralelismo.__dict__}
    SAIDA.mkdir(parents=True, exist_ok=True)
    for nome, composicoes, quantidade in (
        ("nativo", {"nativa"}, args.nativas),
        ("digitalizado", {"digitalizada"}, args.digitalizadas),
    ):
        caminho = SAIDA / f"tempo_{nome}.pdf"
        paginas = _subconjunto(composicoes, quantidade, caminho)
        resultados, segundos = _rodar(caminho, caminho.name, paginas, paralelismo)
        falhas = sum(1 for r in resultados if r.motivo_falha)
        resultado[nome] = {
            "paginas": paginas,
            "segundos": round(segundos, 2),
            "por_mil_paginas": round(segundos / paginas * 1000, 1),
            "lotes_falhos": falhas,
        }
        print(json.dumps(resultado[nome]), file=sys.stderr, flush=True)
    return resultado


def comando_extrair(args: argparse.Namespace) -> dict[str, Any]:
    """Pipeline completa de um processo de referência, sem banco."""
    pasta = RAIZ / args.processo / args.cenario
    gabarito = _gabarito(pasta)
    paralelismo = Paralelismo(args.lote, args.lotes, args.lotes)
    caminho = pasta / ("autos.zip" if args.cenario == "zip_por_peca" else "autos.pdf")
    if args.cenario == "zip_por_peca":
        raise SystemExit("extrair mede os cenários de PDF único")
    total = fitz.open(caminho).page_count
    resultados, segundos = _rodar(caminho, caminho.name, total, paralelismo)
    falhas: Counter[str] = Counter()
    linhas = []
    for r in resultados:
        if r.motivo_falha:
            falhas[r.motivo_falha.value] += len(r.tarefa.numeros)
        for p in r.paginas:
            if "erro" in p:
                falhas["erro_ocr"] += 1
                continue
            linhas.append(
                linha_pagina(p, VERSAO_EXTRATOR)
                | {"origem_arquivo": p["origem_arquivo"], "pagina_origem": p["pagina_origem"]}
            )
    relatorio = relatorio_qualidade(
        linhas,
        total_paginas=total,
        tempo_parede_segundos=segundos,
        falhas=dict(falhas),
        versao_extrator=VERSAO_EXTRATOR,
    )
    destino = Path(args.destino) / args.processo / args.cenario
    destino.mkdir(parents=True, exist_ok=True)
    with gzip.open(destino / "linhas.json.gz", "wt", encoding="utf-8") as arquivo:
        json.dump({"segundos": segundos, "linhas": linhas}, arquivo, ensure_ascii=False)
    saida = para_saida_pipeline(linhas, segundos)
    (destino / "saida.json").write_text(saida.model_dump_json(), encoding="utf-8")
    (destino / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False), "utf-8")
    datas: Counter[str] = Counter()
    textos = {(p["pagina_origem"]): p["texto"] for p in linhas}
    mapa = dict(enumerate(gabarito.arquivos[0].folhas, start=1))
    for fisica, folha in mapa.items():
        if folha is None:
            continue
        pagina = gabarito.paginas[folha - 1]
        if pagina.degradacao is None:
            continue
        esperadas = DATA.findall(pagina.texto)
        datas[f"{pagina.degradacao.value}_total"] += len(esperadas)
        datas[f"{pagina.degradacao.value}_encontradas"] += sum(
            1 for d in esperadas if d in textos.get(fisica, "")
        )
    return {"processo": args.processo, "relatorio": relatorio, "datas_ocr": dict(datas),
            "gabarito": str(pasta / "gabarito.json"), "saida": str(destino / "saida.json")}  # fmt: skip


def _linhas_liso(destino: Path, processo: str) -> list[dict[str, Any]]:
    caminho = destino / processo / Cenario.PDF_LISO.value / "linhas.json.gz"
    with gzip.open(caminho, "rt", encoding="utf-8") as arquivo:
        return sorted(json.load(arquivo)["linhas"], key=lambda p: int(p["numero"]))


def _paginas_do_cenario(
    pasta: Path, gabarito: Gabarito, liso: Gabarito, linhas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Páginas físicas do cenário com o texto já extraído do `pdf_liso` (mesmas folhas)."""
    por_folha = {
        folha: linhas[posicao]
        for posicao, folha in enumerate(liso.arquivos[0].folhas)
        if folha is not None
    }
    paginas: list[dict[str, Any]] = []
    documento = None
    for arquivo in gabarito.arquivos:
        for posicao, folha in enumerate(arquivo.folhas, start=1):
            numero = len(paginas) + 1
            if folha is None:
                documento = documento or fitz.open(pasta / arquivo.nome)
                nativo = extrair_texto_nativo(documento[posicao - 1])
                base = {"tipo": "nativa", "texto": nativo.texto, "flags": {},
                        "coordenadas": {"blocos": nativo.blocos}}  # fmt: skip
            else:
                base = dict(por_folha[folha])
            paginas.append(
                base | {"numero": numero, "origem_arquivo": arquivo.nome, "pagina_origem": posicao}
            )
    return paginas


def _erros_fronteira(
    gabarito: Gabarito, resultado: Any, paginas: list[dict[str, Any]]
) -> dict[str, Any]:
    mapa = mapa_folhas(gabarito)
    folha = {
        int(p["numero"]): mapa.get((p["origem_arquivo"], int(p["pagina_origem"]))) for p in paginas
    }
    esperadas = {p.pagina_inicial for p in gabarito.pecas}
    previstas = {folha[p.pagina_inicial]: p for p in resultado.pecas}
    tipos_gab = {p.pagina_inicial: p.tipo.value for p in gabarito.pecas}
    sinais = {int(p["numero"]): s for p, s in zip(paginas, resultado.sinais, strict=False)}
    numero_da_folha = {f: n for n, f in folha.items() if f is not None}
    faltando: Counter[str] = Counter()
    exemplos: list[dict[str, Any]] = []
    for f in sorted(esperadas - set(previstas)):
        s = sinais[numero_da_folha[f]]
        composicao = gabarito.paginas[f - 1].composicao.value
        faltando[f"{tipos_gab[f]}|titulo={s.get('titulo')}|{composicao}"] += 1
        if len(exemplos) < 5:
            exemplos.append({"folha": f, "sinais": s})
    sobrando = Counter(
        f"{p.classificacao['fronteira']['nivel']}|{','.join(p.classificacao['fronteira']['sinais'])}"
        for f, p in previstas.items()
        if f not in esperadas
    )
    return {"faltando": dict(faltando.most_common(10)), "sobrando": dict(sobrando.most_common(10)),
            "exemplos_faltando": exemplos}  # fmt: skip


def _erros_classificacao(gabarito: Gabarito, saida: SaidaPipeline) -> dict[str, Any]:
    mapa = mapa_folhas(gabarito)
    previstas = {mapa.get((p.inicio.arquivo, p.inicio.pagina)): p for p in saida.pecas}
    tipo: Counter[str] = Counter()
    origem: Counter[str] = Counter()
    data: Counter[str] = Counter()
    for peca in gabarito.pecas:
        prevista = previstas.get(peca.pagina_inicial)
        if prevista is None:
            continue
        if prevista.tipo != peca.tipo:
            tipo[f"{peca.tipo.value}->{prevista.tipo.value}"] += 1
        if prevista.origem != peca.origem:
            origem[f"{peca.origem.value}->{prevista.origem.value}"] += 1
        if prevista.data != peca.data:
            estado = "ausente" if prevista.data is None else "diferente"
            data[f"{peca.tipo.value}:{estado}"] += 1
    return {"tipo": dict(tipo), "origem": dict(origem), "data": dict(data)}


def _medir_cenario(
    destino: Path, semente: Path, cenario: Cenario, liso: Gabarito, linhas: list[dict[str, Any]]
) -> dict[str, Any]:
    pasta = semente / cenario.value
    gabarito = _gabarito(pasta)
    paginas = _paginas_do_cenario(pasta, gabarito, liso, linhas)
    diagnostico = _diagnosticar(pasta, cenario).model_dump(mode="json")
    inicio = time.perf_counter()
    resultado = montar_indice(paginas, diagnostico)
    segundos = time.perf_counter() - inicio
    saida = SaidaPipeline(
        pecas=pecas_saida(resultado.pecas, paginas, "autos.pdf"),
        paginas=tuple(
            PaginaSaida(
                ref=RefPagina(arquivo=p["origem_arquivo"], pagina=p["pagina_origem"]),
                tipo=p["tipo"],
                texto="",
            )  # fmt: skip
            for p in paginas
        ),
    )
    pasta_saida = destino / semente.name / cenario.value
    pasta_saida.mkdir(parents=True, exist_ok=True)
    (pasta_saida / "saida_pecas.json").write_text(saida.model_dump_json(), "utf-8")
    relatorio = medir(gabarito, saida)
    mapa = mapa_folhas(gabarito)
    por_inicio = {
        mapa.get((s.inicio.arquivo, s.inicio.pagina)): p
        for s, p in zip(saida.pecas, resultado.pecas, strict=True)
    }
    tipo_data_igual = sum(
        1
        for g in gabarito.pecas
        if (p := por_inicio.get(g.pagina_inicial)) is not None and p.tipo_data == g.tipo_data.value
    )
    return {
        "processo": semente.name,
        "cenario": cenario.value,
        "fonte": resultado.fonte,
        "pecas_gabarito": len(gabarito.pecas),
        "pecas_saida": len(resultado.pecas),
        "fronteira": relatorio.fronteira.model_dump(),
        "tipo": relatorio.tipo_peca.model_dump(),
        "origem": relatorio.origem_peca.model_dump(),
        "data": relatorio.data_peca.model_dump() if relatorio.data_peca else None,
        "tipo_data_igual": tipo_data_igual,
        "divergencias": len(resultado.divergencias),
        "divergencias_motivos": dict(Counter(d["motivo"] for d in resultado.divergencias)),
        "fracas": sum(1 for p in resultado.pecas if "fronteira_fraca" in p.flags["peca"]),
        "origem_desconhecida": sum(1 for p in resultado.pecas if p.origem.value == "desconhecida"),
        "tipo_outros_ambiguo": sum(1 for p in resultado.pecas if "tipo_ambiguo" in p.flags["peca"]),
        "data_com_evidencia": sum(1 for p in resultado.pecas if p.evidencia_data),
        "segundos_indice": round(segundos, 2),
        "erros_fronteira": _erros_fronteira(gabarito, resultado, paginas),
        "erros_classificacao": _erros_classificacao(gabarito, saida),
    }


def comando_pecas(args: argparse.Namespace) -> dict[str, Any]:
    """Fronteiras, tipo, origem e data da peça nos três cenários (4E.9), sem banco.

    Usa as páginas extraídas por `extrair` (cenário liso, `linhas.json.gz`): as folhas são as
    mesmas nos três cenários, então o texto é reaproveitado e só as páginas de índice do
    `pdf_indice` são lidas aqui. O diagnóstico (fronteiras da origem) roda de verdade.
    """
    destino = Path(args.destino)
    linhas_saida = []
    for semente in _sementes():
        if args.somente and semente.name not in args.somente.split(","):
            continue
        linhas = _linhas_liso(destino, semente.name)
        liso = _gabarito(semente / Cenario.PDF_LISO.value)
        cenarios = [Cenario(c) for c in args.cenarios.split(",")]
        for cenario in cenarios:
            linha = _medir_cenario(destino, semente, cenario, liso, linhas)
            linhas_saida.append(linha)
            resumo = {k: linha[k] for k in ("processo", "cenario", "fronteira", "tipo")}
            print(json.dumps(resumo), file=sys.stderr, flush=True)
    return {"linhas": linhas_saida}


def _pecas_texto(
    paginas: list[dict[str, Any]], resultado: Any
) -> tuple[list[PecaTexto], dict[Any, PaginaTexto]]:
    por_numero = {
        int(p["numero"]): PaginaTexto(
            uuid4(),
            int(p["numero"]),
            str(p.get("texto") or ""),
            p["origem_arquivo"],
            int(p["pagina_origem"]),
        )  # fmt: skip
        for p in paginas
    }
    pecas = [
        PecaTexto(
            p.tipo,
            p.origem,
            tuple(por_numero[n] for n in range(p.pagina_inicial, p.pagina_final + 1)),
        )  # fmt: skip
        for p in resultado.pecas
    ]
    return pecas, {p.id: p for p in por_numero.values()}


def _evidencias_nao_literais(fatos: list[Any], paginas: dict[Any, PaginaTexto]) -> int:
    return sum(
        1
        for f in fatos
        for e in f.evidencias
        if paginas[e.pagina_id].texto[e.inicio : e.fim] != e.trecho
    )


def _eventos_cenario(
    destino: Path, semente: Path, cenario: Cenario, liso: Gabarito, linhas: list[dict[str, Any]]
) -> dict[str, Any]:
    pasta = semente / cenario.value
    gabarito = _gabarito(pasta)
    paginas = _paginas_do_cenario(pasta, gabarito, liso, linhas)
    resultado = montar_indice(paginas, _diagnosticar(pasta, cenario).model_dump(mode="json"))
    pecas, por_id = _pecas_texto(paginas, resultado)
    inicio = time.perf_counter()
    reus = identificar_reus(pecas)
    extracao = extrair_fatos(uuid4(), pecas, reus, {r.pseudonimo: uuid4() for r in reus})
    segundos = time.perf_counter() - inicio
    achados = executar_validacoes(
        para_modelo(extracao.fatos), "criminal", gabarito.processo.data_referencia
    )
    saida = SaidaPipeline(
        pecas=pecas_saida(resultado.pecas, paginas, "autos.pdf"),
        eventos=eventos_saida(extracao.fatos, por_id),
    )
    pasta_saida = destino / semente.name / cenario.value
    pasta_saida.mkdir(parents=True, exist_ok=True)
    (pasta_saida / "saida_eventos.json").write_text(saida.model_dump_json(), "utf-8")
    relatorio = medir(gabarito, saida)
    comparacao = comparar_achados(gabarito.resultado_esperado, achados)
    return {
        "processo": semente.name,
        "cenario": cenario.value,
        "folhas": len(gabarito.paginas),
        "eventos": relatorio.eventos.model_dump(),
        "datas": relatorio.datas.model_dump() if relatorio.datas else None,
        "fatos": len(extracao.fatos),
        "fatos_sem_evidencia": sum(1 for f in extracao.fatos if not f.evidencias),
        "evidencias_nao_literais": _evidencias_nao_literais(extracao.fatos, por_id),
        "extracao": extracao.resumo(),
        "reus": len(reus),
        "segundos_eventos": round(segundos, 3),
        "achados": [c.model_dump() for c in comparacao],
        "achados_iguais": sum(c.resultado_igual and c.valores_iguais for c in comparacao),
    }


def _taxa_somada(linhas: list[dict[str, Any]], chave: str) -> dict[str, Any]:
    corretos = sum(int(linha[chave]["corretos"]) for linha in linhas)
    previstos = sum(int(linha[chave]["previstos"]) for linha in linhas)
    esperados = sum(int(linha[chave]["esperados"]) for linha in linhas)
    return {
        "corretos": corretos, "previstos": previstos, "esperados": esperados,
        "precisao": corretos / previstos if previstos else 0.0,
        "recall": corretos / esperados if esperados else 0.0,
    }  # fmt: skip


def consolidar_eventos(linhas: list[dict[str, Any]]) -> dict[str, Any]:
    """Soma as medições de eventos de vários processos e cenários.

    Args:
        linhas: Saídas de ``_eventos_cenario``.

    Returns:
        Totais: eventos, datas, achados iguais, fatos sem evidência e tempo.
    """
    achados = [c for linha in linhas for c in linha["achados"]]
    iguais = sum(1 for c in achados if c["resultado_igual"] and c["valores_iguais"])
    folhas = sum(int(linha["folhas"]) for linha in linhas)
    segundos = sum(float(linha["segundos_eventos"]) for linha in linhas)
    return {
        "eventos": _taxa_somada(linhas, "eventos"),
        "datas": _taxa_somada(linhas, "datas"),
        "achados": {
            "iguais": iguais,
            "total": len(achados),
            "resultado_igual": sum(1 for c in achados if c["resultado_igual"]),
            "taxa": iguais / len(achados) if achados else 0.0,
        },  # fmt: skip
        "fatos_sem_evidencia": sum(int(linha["fatos_sem_evidencia"]) for linha in linhas),
        "evidencias_nao_literais": sum(int(linha["evidencias_nao_literais"]) for linha in linhas),
        "segundos_eventos_por_mil_paginas": segundos / folhas * 1000 if folhas else 0.0,
    }


def comando_eventos(args: argparse.Namespace) -> dict[str, Any]:
    """Eventos e achados nos cenários dos dez processos (4F.9), sem banco e sem OCR novo."""
    destino = Path(args.destino)
    linhas_saida = []
    for semente in _sementes():
        if args.somente and semente.name not in args.somente.split(","):
            continue
        linhas = _linhas_liso(destino, semente.name)
        liso = _gabarito(semente / Cenario.PDF_LISO.value)
        for cenario in (Cenario(c) for c in args.cenarios.split(",")):
            linha = _eventos_cenario(destino, semente, cenario, liso, linhas)
            linhas_saida.append(linha)
            chaves = ("processo", "cenario", "achados_iguais", "eventos")
            resumo = {k: linha[k] for k in chaves}
            print(json.dumps(resumo), file=sys.stderr, flush=True)
    return {"linhas": linhas_saida, "consolidado": consolidar_eventos(linhas_saida)}


def main() -> None:
    """Interpreta a linha de comando e imprime o resultado em JSON."""
    parser = argparse.ArgumentParser(prog="medir_extracao.py")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("diagnostico")
    sub.add_parser("roteador")
    ocr = sub.add_parser("ocr")
    ocr.add_argument("--por-nivel", type=int, default=6)
    ocr.add_argument("--semente", type=int, default=20261020)
    tempo = sub.add_parser("tempo")
    tempo.add_argument("--nativas", type=int, default=1000)
    tempo.add_argument("--digitalizadas", type=int, default=200)
    extrair = sub.add_parser("extrair")
    extrair.add_argument("processo")
    extrair.add_argument("--cenario", default="pdf_liso")
    extrair.add_argument("--destino", default=str(SAIDA), help="grava linhas.json.gz e saida.json")
    for alvo in (tempo, extrair):
        alvo.add_argument("--lote", type=int, default=8)
        alvo.add_argument("--lotes", type=int, default=4)
    pecas = sub.add_parser("pecas")
    pecas.add_argument("--destino", default=str(SAIDA))
    pecas.add_argument("--somente", default="")
    pecas.add_argument("--cenarios", default=",".join(c.value for c in Cenario))
    eventos = sub.add_parser("eventos")
    eventos.add_argument("--destino", default=str(SAIDA))
    eventos.add_argument("--somente", default="")
    eventos.add_argument("--cenarios", default=",".join(c.value for c in Cenario))
    args = parser.parse_args()
    comandos = {
        "diagnostico": comando_diagnostico,
        "roteador": comando_roteador,
        "ocr": comando_ocr,
        "tempo": comando_tempo,
        "extrair": comando_extrair,
        "pecas": comando_pecas,
        "eventos": comando_eventos,
    }
    print(json.dumps(comandos[args.comando](args), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
