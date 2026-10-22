"""Ingere um processo SINTÉTICO pequeno no banco e bucket de teste do backup (Etapa 7.8).

Roda dentro do contêiner ``api`` (lido do stdin por ``tests/backup/test_restauracao.py``), com
``LUPA_DATABASE_URL`` e ``LUPA_MINIO_BUCKET`` apontando para o banco e o bucket de teste. Gera
autos sintéticos nativos (``lupa.sinteticos``) e roda o worker em processo até os achados.
Saída: JSON com o id do processo e o estado final do job.
"""

import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lupa.config import get_settings
from lupa.ingestao.calibracao import enviar_e_processar, semear_gabinete
from lupa.ingestao.worker import dependencias_da_configuracao
from lupa.sinteticos.empacotamento import exportar
from lupa.sinteticos.gabarito import Cenario, Composicao
from lupa.sinteticos.gerador import gerar_conteudo
from lupa.sinteticos.roteiro import Configuracao


def semear() -> dict[str, str]:
    """Cria gabinete e processo sintéticos e processa os autos.

    Returns:
        Id do processo e estado final do job.
    """
    settings = get_settings()
    deps = replace(dependencias_da_configuracao(settings), fila=None, fatia_paginas=0)
    dono = sessionmaker(create_engine(settings.database_url.get_secret_value()))
    with dono() as session, session.begin():
        gabinete, usuario = semear_gabinete(session, "Gabinete backup teste")
    config = Configuracao(
        semente=718, paginas_alvo=12, mistura={Composicao.NATIVA: 1.0}, proporcao_vazias=0.0
    )
    with tempfile.TemporaryDirectory(prefix="lupa-backup-") as diretorio:
        gerados = exportar(gerar_conteudo(config), Path(diretorio), (Cenario.PDF_INDICE,))
        execucao = enviar_e_processar(deps, dono, gabinete, usuario, gerados[0].caminho)
    estado = execucao.estado.value if execucao.estado else ""
    return {"processo_id": str(execucao.processo_id), "estado": estado}


if __name__ == "__main__":
    sys.stdout.write(json.dumps(semear()) + "\n")
