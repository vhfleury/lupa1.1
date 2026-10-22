"""Ponta a ponta nos processos de referência (Etapa 4F.9), pelo código do worker.

Roda dentro do contêiner ``api`` (``.sinteticos`` montado só leitura). Para cada processo e
cenário pedido: lacra o arquivo no storage configurado (MinIO) num processo novo do banco
configurado e roda ``processar_job`` (validação no sandbox, diagnóstico, extração ou cache,
índice, eventos e achados). Depois lê do banco fatos, peças e achados, mede eventos e datas com
``lupa.sinteticos.medicao.medir`` e compara os achados com o ``resultado_esperado`` na data de
referência do gabarito.

``--volume DIR`` reaproveita a extração de páginas da 4E (``DIR/<processo>/pdf_liso/
linhas.json.gz``): antes do upload, as páginas são gravadas num arquivo-fonte do mesmo gabinete
com o SHA-256 do PDF, e o upload as recebe pelo cache da 4F.8 (sem OCR). Só vale para o cenário
``pdf_liso`` (o cache é por hash do arquivo). As páginas do volume foram extraídas pela versão
4e.0 e são gravadas com a versão corrente só para que o cache as aceite: a única diferença da
4f.0 é o OCR de detecção em imagens de páginas nativas, que não muda texto nem eventos.
``--repetir`` envia o mesmo arquivo uma segunda vez em outro processo do gabinete e mede o tempo
do cache.

Saída em JSON no stdout; o progresso vai para stderr.
"""

import argparse
import gzip
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session, sessionmaker

from lupa.config import get_settings
from lupa.dominio.esquemas import calcular_hash
from lupa.dominio.repositorios import listar_fatos_por_processo
from lupa.dominio.tabelas import ArquivoTabela, PaginaTabela, PecaTabela
from lupa.ingestao import repositorio
from lupa.ingestao.calibracao import (
    enviar_e_processar,
    novo_processo,
    semear_gabinete,
    sha256_arquivo,
)
from lupa.ingestao.eventos.etapa import achados_do_processo
from lupa.ingestao.eventos.modelo import PaginaTexto
from lupa.ingestao.eventos.saida import eventos_saida
from lupa.ingestao.extrator_paginas import VERSAO_EXTRATOR
from lupa.ingestao.worker import Dependencias, dependencias_da_configuracao, sessao_gabinete
from lupa.logging import configurar_logging
from lupa.sinteticos.achados import comparar
from lupa.sinteticos.gabarito import Cenario, Gabarito
from lupa.sinteticos.medicao import medir
from lupa.sinteticos.saida_pipeline import PecaSaida, RefPagina, SaidaPipeline

RAIZ = Path("/app/.sinteticos/referencia")
NOMES = {
    Cenario.ZIP_POR_PECA: "autos.zip",
    Cenario.PDF_INDICE: "autos.pdf",
    Cenario.PDF_LISO: "autos.pdf",
}


def _semear_paginas(
    dono: sessionmaker[Session], gabinete: UUID, usuario: UUID, pdf: Path, linhas_gz: Path
) -> int:
    with gzip.open(linhas_gz, "rt", encoding="utf-8") as arquivo:
        linhas = json.load(arquivo)["linhas"]
    with dono() as session, session.begin():
        processo = novo_processo(session, gabinete, usuario)
        arquivo_id = uuid4()
        session.add(
            ArquivoTabela(
                id=arquivo_id, gabinete_id=gabinete, processo_id=processo,
                sha256=sha256_arquivo(pdf), tamanho_bytes=pdf.stat().st_size,
                nome_original="autos.pdf", mime="application/pdf",
                chave_storage=f"volume-4e/{arquivo_id}", enviado_por=usuario,
            )
        )  # fmt: skip
        session.flush()
        for inicio in range(0, len(linhas), 500):
            session.execute(
                insert(PaginaTabela),
                [
                    linha | {"id": uuid4(), "gabinete_id": gabinete, "arquivo_id": arquivo_id,
                             "hash_texto": calcular_hash(linha["texto"]),
                             "versao_extrator": VERSAO_EXTRATOR}
                    for linha in linhas[inicio : inicio + 500]
                ],
            )  # fmt: skip
    return len(linhas)


def _saida(session: Session, processo: UUID, arquivo: UUID) -> tuple[SaidaPipeline, int]:
    paginas = {
        p.id: PaginaTexto(p.id, p.numero, p.texto, p.origem_arquivo, p.pagina_origem)
        for p in session.scalars(select(PaginaTabela).where(PaginaTabela.arquivo_id == arquivo))
    }
    por_numero = {p.numero: p for p in paginas.values()}

    def ref(numero: int) -> RefPagina:
        pagina = por_numero[numero]
        return RefPagina(
            arquivo=pagina.origem_arquivo or "autos.pdf", pagina=pagina.pagina_origem or numero
        )

    pecas = session.scalars(
        select(PecaTabela).where(PecaTabela.arquivo_id == arquivo, PecaTabela.vigente.is_(True))
    )
    fatos = listar_fatos_por_processo(session, processo)
    saida = SaidaPipeline(
        pecas=tuple(
            PecaSaida(
                tipo=p.tipo,
                origem=p.origem,
                inicio=ref(p.pagina_inicial),
                fim=ref(p.pagina_final),
                data=p.data,
            )
            for p in pecas
        ),  # fmt: skip
        eventos=eventos_saida(fatos, paginas),
    )
    literais = sum(
        1
        for f in fatos
        for e in f.evidencias
        if paginas[e.pagina_id].texto[e.inicio : e.fim] != e.trecho
    )
    return saida, literais


def _rodar(
    deps: Dependencias, dono: sessionmaker[Session], gabinete: UUID, usuario: UUID,
    pasta: Path, cenario: Cenario,
) -> dict[str, Any]:  # fmt: skip
    gabarito = Gabarito.model_validate_json((pasta / "gabarito.json").read_text(encoding="utf-8"))
    execucao = enviar_e_processar(deps, dono, gabinete, usuario, pasta / NOMES[cenario])
    with sessao_gabinete(deps.fabrica, gabinete) as session:
        saida, nao_literais = _saida(session, execucao.processo_id, execucao.arquivo_id)
        achados = achados_do_processo(
            session, execucao.processo_id, "criminal", gabarito.processo.data_referencia
        )
        job = repositorio.obter_relatorio(session, execucao.arquivo_id) or {}
    medicao = medir(gabarito, saida)
    comparacao = comparar(gabarito.resultado_esperado, achados)
    relatorio = job.get("relatorio") or {}
    return {
        "processo": pasta.parent.name,
        "cenario": cenario.value,
        "folhas": len(gabarito.paginas),
        "estado": execucao.estado.value if execucao.estado else None,
        "segundos_total": round(execucao.segundos, 2),
        "segundos_por_mil_paginas": round(execucao.segundos / len(gabarito.paginas) * 1000, 1),
        "extracao_parede_segundos": (relatorio.get("tempo") or {}).get("parede_segundos"),
        "por_tipo_pagina": relatorio.get("por_tipo"),
        "fronteira": medicao.fronteira.model_dump(),
        "tipo_peca": medicao.tipo_peca.model_dump(),
        "eventos": medicao.eventos.model_dump(),
        "datas": medicao.datas.model_dump() if medicao.datas else None,
        "fatos": len(saida.eventos),
        "evidencias_nao_literais": nao_literais,
        "eventos_relatorio": relatorio.get("eventos"),
        "achados": [c.model_dump() for c in comparacao],
        "achados_iguais": sum(c.resultado_igual and c.valores_iguais for c in comparacao),
    }


def main() -> int:
    """Interpreta a linha de comando, roda e imprime o JSON.

    Returns:
        Código de saída.
    """
    parser = argparse.ArgumentParser(prog="ponta_a_ponta.py")
    parser.add_argument("--processos", default="semente_01")
    parser.add_argument("--cenarios", default="pdf_liso")
    parser.add_argument("--volume", type=Path, default=None)
    parser.add_argument("--repetir", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    configurar_logging(nivel="WARNING")
    deps = replace(dependencias_da_configuracao(settings), fila=None, fatia_paginas=0)
    dono = sessionmaker(create_engine(settings.database_url.get_secret_value()))
    with dono() as session, session.begin():
        gabinete, usuario = semear_gabinete(session, "Gabinete ponta a ponta 4F")
    linhas = []
    for processo in args.processos.split(","):
        for cenario in (Cenario(c) for c in args.cenarios.split(",")):
            pasta = RAIZ / processo / cenario.value
            semeadas = 0
            if args.volume and cenario is Cenario.PDF_LISO:
                linhas_gz = args.volume / processo / "pdf_liso" / "linhas.json.gz"
                semeadas = _semear_paginas(dono, gabinete, usuario, pasta / "autos.pdf", linhas_gz)
            linha = _rodar(deps, dono, gabinete, usuario, pasta, cenario) | {
                "paginas_do_volume": semeadas
            }
            if args.repetir:
                repetida = _rodar(deps, dono, gabinete, usuario, pasta, cenario)
                linha["repeticao_segundos"] = repetida["segundos_total"]
            linhas.append(linha)
            resumo = {
                k: linha[k]
                for k in ("processo", "cenario", "estado", "segundos_total", "achados_iguais")
            }
            print(json.dumps(resumo | {"eventos": linha["eventos"]}), file=sys.stderr, flush=True)
    configuracao = {
        "cpus": os.cpu_count(),
        "paginas_por_lote": settings.extracao_paginas_por_lote,
        "lotes_por_job": settings.extracao_lotes_por_job,
        "lotes_por_gabinete": settings.extracao_lotes_por_gabinete,
        "sandbox": {
            "memoria_mb": settings.sandbox_memoria_mb,
            "cpu_segundos": settings.sandbox_cpu_segundos,
        },
    }
    print(
        json.dumps({"configuracao": configuracao, "linhas": linhas}, ensure_ascii=False, indent=1)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
