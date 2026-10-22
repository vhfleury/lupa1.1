"""Calibração da pipeline sobre um arquivo (Etapa 4F.10); roteiro em ``docs/calibracao-projudi.md``.

Roda dentro do contêiner ``api``: cria um gabinete de calibração no banco configurado, lacra o
arquivo no storage configurado, processa com o código do worker até os achados e escreve o
relatório Markdown (diagnóstico, páginas, peças, eventos com trecho e achados) com colunas
"Confere?" para o assessor. Também grava o JSON bruto ao lado.

Uso::

    docker compose exec api python scripts/calibrar.py /caminho/autos.pdf --saida /tmp/calib

O relatório contém trechos dos autos: fica no contêiner (``/tmp``) e não vai para o repositório.
"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lupa.config import get_settings
from lupa.ingestao.calibracao import coletar, enviar_e_processar, para_markdown, semear_gabinete
from lupa.ingestao.worker import dependencias_da_configuracao, sessao_gabinete
from lupa.logging import configurar_logging


def main(argv: list[str] | None = None) -> int:
    """Executa a calibração e grava ``relatorio.md`` e ``relatorio.json``.

    Args:
        argv: Argumentos (padrão: os da linha de comando).

    Returns:
        Código de saída (0 se o job terminou concluído ou parcial).
    """
    parser = argparse.ArgumentParser(prog="calibrar.py", description=__doc__.splitlines()[0])
    parser.add_argument("arquivo", type=Path, help="PDF ou ZIP dos autos")
    parser.add_argument("--saida", type=Path, default=Path("/tmp/calibracao"))  # noqa: S108
    parser.add_argument("--titulo", default="processo de calibração")
    args = parser.parse_args(argv)
    settings = get_settings()
    configurar_logging(nivel="WARNING")
    deps = replace(dependencias_da_configuracao(settings), fila=None, fatia_paginas=0)
    dono = sessionmaker(create_engine(settings.database_url.get_secret_value()))
    with dono() as session, session.begin():
        gabinete_id, usuario_id = semear_gabinete(session, "Gabinete de calibração")
    execucao = enviar_e_processar(deps, dono, gabinete_id, usuario_id, args.arquivo)
    with sessao_gabinete(deps.fabrica, gabinete_id) as session:
        dados = coletar(session, execucao.processo_id, execucao.arquivo_id)
    dados["execucao"] = {
        "processo_id": str(execucao.processo_id),
        "estado": execucao.estado.value if execucao.estado else None,
        "segundos": round(execucao.segundos, 2),
    }
    args.saida.mkdir(parents=True, exist_ok=True)
    (args.saida / "relatorio.md").write_text(para_markdown(dados, args.titulo), encoding="utf-8")
    (args.saida / "relatorio.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    concluiu = dados["execucao"]["estado"] in ("concluido", "parcial")
    return 0 if concluiu else 1


if __name__ == "__main__":
    raise SystemExit(main())
