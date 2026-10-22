"""Prepara os dados SINTÉTICOS dos testes ponta a ponta das telas de processo (Etapas 6.4 a 6.7).

Uso (no contêiner da API, depois de `scripts/e2e_preparar.py`): `python scripts/e2e_processos.py`.
Recusa rodar fora de `desenvolvimento`/`teste`.

1. Cria um gabinete e um assessor novos (senha temporária gerada agora, troca obrigatória; o
   E2E cadastra o autenticador pela tela), pelos mesmos casos de uso da gestão de usuários.
2. Cria um processo criminal sintético no gabinete e gera os autos sintéticos (lupa.sinteticos,
   só páginas nativas, para a ingestão ser rápida), lacra o PDF no storage real e enfileira o job:
   o worker real processa até os achados, e o E2E acompanha o status pela tela.

Saída: três linhas, o nome do assessor, a senha temporária e o id do processo. Nada é gravado
fora do banco e do storage da própria stack.
"""

import hashlib
import secrets
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from lupa.acesso.servico import (
    Ator,
    Contexto,
    auditar,
    criar_gabinete,
    criar_usuario,
    definir_contexto,
)
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.config import get_settings
from lupa.dominio.cnj import calcular_digito_verificador
from lupa.dominio.enums import Materia, PapelUsuario, StatusProcesso
from lupa.dominio.sessao import assumir_papel_aplicacao
from lupa.dominio.tabelas import ProcessoTabela, UsuarioTabela
from lupa.ingestao.fila import criar_fila
from lupa.ingestao.recepcao import ArquivoRecebido, TipoArquivo, lacrar
from lupa.ingestao.storage import criar_storage
from lupa.sinteticos.empacotamento import exportar
from lupa.sinteticos.gabarito import Cenario, Composicao
from lupa.sinteticos.gerador import gerar_conteudo
from lupa.sinteticos.roteiro import Configuracao

AMBIENTES_PERMITIDOS = frozenset({"desenvolvimento", "teste"})


def _numero_cnj() -> str:
    sequencial = f"{secrets.randbelow(9_000_000) + 1_000_000:07d}"
    ano, justica, tribunal, origem = "2025", "8", "09", "0001"
    digito = calcular_digito_verificador(sequencial, ano, justica, tribunal, origem)
    return f"{sequencial}-{digito}.{ano}.{justica}.{tribunal}.{origem}"


def _autos(destino: Path) -> Path:
    config = Configuracao(
        semente=secrets.randbelow(10_000) + 100,
        paginas_alvo=18,
        mistura={Composicao.NATIVA: 1.0},
        proporcao_vazias=0.0,
    )
    gerados = exportar(gerar_conteudo(config), destino, (Cenario.PDF_INDICE,))
    return gerados[0].caminho


def preparar() -> tuple[str, str, str]:
    """Cria gabinete, assessor e processo sintético com o job enfileirado.

    Returns:
        Nome do assessor, senha temporária e id do processo.
    """
    settings = get_settings()
    agora = datetime.now(UTC)
    ctx = Contexto(None, None, agora)
    sufixo = secrets.token_hex(3)
    engine = create_engine(settings.url_banco_aplicacao())
    storage = criar_storage(settings)
    try:
        with Session(engine) as session, session.begin():
            assumir_papel_aplicacao(session)
            definir_contexto(session, PapelUsuario.ADMINISTRADOR.value, None)
            admin = session.scalars(
                select(UsuarioTabela).where(UsuarioTabela.papel == PapelUsuario.ADMINISTRADOR.value)
            ).one()
            ator = Ator(admin.id, None, PapelUsuario.ADMINISTRADOR, admin.nome_usuario, "e2e")
            gabinete = criar_gabinete(session, ator, f"Gabinete Processos E2E {sufixo}", ctx)
            criado = criar_usuario(
                session, ator, f"proc.e2e.{sufixo}", PapelUsuario.ASSESSOR, gabinete.id, ctx
            )
            assessor_id, gabinete_id = criado.usuario.id, gabinete.id
            nome, senha = criado.usuario.nome_usuario, criado.senha_temporaria
        with Session(engine) as session, session.begin():
            assumir_papel_aplicacao(session)
            definir_contexto(session, PapelUsuario.ASSESSOR.value, gabinete_id)
            processo = ProcessoTabela(
                id=uuid4(),
                gabinete_id=gabinete_id,
                numero_cnj=_numero_cnj(),
                classe="Apelação Criminal",
                materia=Materia.CRIMINAL.value,
                sigiloso=False,
                status=StatusProcesso.CRIADO.value,
                criado_por=assessor_id,
            )
            session.add(processo)
            session.flush()
            auditar(
                session, ctx, AcaoAuditoria.PROCESSO_CRIADO, usuario_id=assessor_id,
                gabinete_id=gabinete_id, processo_id=processo.id, objeto_tipo="processo",
                objeto_id=str(processo.id),
            )  # fmt: skip
            with tempfile.TemporaryDirectory(prefix="lupa-e2e-") as diretorio:
                caminho = _autos(Path(diretorio))
                dados = caminho.read_bytes()
                recebido = ArquivoRecebido(
                    caminho, hashlib.sha256(dados).hexdigest(), len(dados), TipoArquivo.PDF
                )
                lacre = lacrar(
                    session, storage, recebido, gabinete_id=gabinete_id, processo_id=processo.id,
                    enviado_por=assessor_id, nome_original="autos-sinteticos.pdf",
                )  # fmt: skip
            processo_id = processo.id
    finally:
        engine.dispose()
    criar_fila(settings).enfileirar(lacre.job_id, gabinete_id)
    return nome, senha, str(processo_id)


if __name__ == "__main__":
    if get_settings().ambiente not in AMBIENTES_PERMITIDOS:
        sys.stderr.write("e2e_processos: recusado fora de desenvolvimento/teste\n")
        sys.exit(2)
    usuario, temporaria, processo_id = preparar()
    sys.stdout.write(f"{usuario}\n{temporaria}\n{processo_id}\n")
