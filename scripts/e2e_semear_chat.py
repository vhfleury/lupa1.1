"""Semeia dados SINTÉTICOS para o E2E do chat e da auditoria (Etapas 6.8 e 6.9).

Uso (no contêiner): `python scripts/e2e_semear_chat.py`. Recusa rodar fora de
`desenvolvimento`/`teste`.

Cria um gabinete novo, um desembargador com senha temporária aleatória (troca obrigatória, sem
autenticador: o E2E faz o primeiro acesso pela tela) e um processo `pronto` com três páginas
sintéticas (denúncia, razões, certidão de intimação). Etapa 6.10: cria também, no mesmo
gabinete, um processo com uma certidão de texto HOSTIL (`<script>`, link Markdown e URL crua) para
o E2E provar que nada dos autos vira HTML ou link clicável. Com `--carga`, garante também 1 milhão de
eventos sintéticos de auditoria (mesmo gerador de `tests/auditoria/test_carga.py`), só na
primeira vez.

Saída: quatro linhas, o usuário, a senha temporária, o id do processo e o id do processo
hostil. Nada em arquivo.
"""

import sys
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from lupa.acesso import senhas
from lupa.config import get_settings
from lupa.dominio.cnj import calcular_digito_verificador
from lupa.dominio.enums import Materia, PapelUsuario, StatusProcesso, TipoPagina
from lupa.dominio.esquemas import calcular_hash
from lupa.dominio.tabelas import (
    ArquivoTabela,
    GabineteTabela,
    PaginaTabela,
    ProcessoTabela,
    UsuarioTabela,
)
from lupa.ingestao.saneamento import normalizar

AMBIENTES_PERMITIDOS = frozenset({"desenvolvimento", "teste"})
TEXTOS = (
    "DENÚNCIA\nO Ministério Público oferece denúncia pelo fato ocorrido em 05/01/2024.",
    "RAZÕES DE APELAÇÃO\nA defesa interpõe apelação em 14/03/2025.",
    "CERTIDÃO\nCertifico que intimei o defensor em 10/03/2025.",
)
# 6.10: tudo numa linha só (um segmento citável), junto do termo que o roteiro falso busca.
TEXTOS_HOSTIS = (
    "CERTIDÃO\nCertifico que intimei o defensor <script>window.__lupaXss = 1</script> "
    "[link](http://x) http://exemplo em 10/03/2025.",
)


def _numero_cnj(processo_id: UUID) -> str:
    seq = f"{processo_id.int % 9_000_000 + 1:07d}"
    digito = calcular_digito_verificador(seq, "2025", "8", "09", "0001")
    return f"{seq}-{digito}.2025.8.09.0001"


def _semear_processo(
    session: Session, gabinete: UUID, autor: UUID, textos: tuple[str, ...] = TEXTOS
) -> UUID:
    processo_id, arquivo_id = uuid4(), uuid4()
    session.add(
        ProcessoTabela(
            id=processo_id, gabinete_id=gabinete, numero_cnj=_numero_cnj(processo_id),
            classe="Apelação Criminal", materia=Materia.CRIMINAL.value, sigiloso=False,
            status=StatusProcesso.PRONTO.value, criado_por=autor,
        )
    )  # fmt: skip
    session.flush()
    session.add(
        ArquivoTabela(
            id=arquivo_id, gabinete_id=gabinete, processo_id=processo_id,
            sha256=calcular_hash(str(arquivo_id)), tamanho_bytes=1024,
            nome_original="autos-sinteticos-e2e.pdf", mime="application/pdf",
            chave_storage=f"sintetico/{arquivo_id}", enviado_por=autor,
        )
    )  # fmt: skip
    session.flush()
    for numero, texto in enumerate(textos, start=1):
        session.add(
            PaginaTabela(
                id=uuid4(), gabinete_id=gabinete, arquivo_id=arquivo_id, numero=numero,
                tipo=TipoPagina.NATIVA.value, texto=texto, hash_texto=calcular_hash(texto),
                texto_normalizado=normalizar(texto).texto, flags={},
            )
        )  # fmt: skip
    return processo_id


def semear() -> tuple[str, str, UUID, UUID]:
    """Cria gabinete, desembargador e processo sintéticos.

    Returns:
        Usuário, senha temporária, id do processo e id do processo com texto hostil.
    """
    engine = create_engine(get_settings().database_url.get_secret_value())
    gabinete, usuario = uuid4(), uuid4()
    nome = f"des.chat.{usuario.hex[:6]}"
    senha = senhas.gerar_senha_temporaria()
    try:
        with Session(engine) as session, session.begin():
            session.add(GabineteTabela(id=gabinete, nome=f"Gabinete E2E chat {usuario.hex[:6]}"))
            session.flush()
            session.add(
                UsuarioTabela(
                    id=usuario, gabinete_id=gabinete, nome_usuario=nome,
                    papel=PapelUsuario.DESEMBARGADOR.value, senha_hash=senhas.gerar_hash(senha),
                    mfa_confirmado=False, ativo=True, troca_senha_obrigatoria=True,
                )
            )  # fmt: skip
            session.flush()
            processo = _semear_processo(session, gabinete, usuario)
            hostil = _semear_processo(session, gabinete, usuario, TEXTOS_HOSTIS)
    finally:
        engine.dispose()
    return nome, senha, processo, hostil


def garantir_carga() -> None:
    """Carrega 1 milhão de eventos sintéticos de auditoria se ainda não houver."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.auditoria.test_carga import TOTAL_EVENTOS, _copiar, _semear_donos

    engine = create_engine(get_settings().database_url.get_secret_value())
    try:
        with engine.connect() as conexao:
            existentes = conexao.execute(
                text("SELECT count(*) FROM evento_auditoria WHERE localizacao = 'rede interna'")
            ).scalar_one()
        if existentes < TOTAL_EVENTOS:
            _copiar(engine, _semear_donos(engine))
    finally:
        engine.dispose()


if __name__ == "__main__":
    if get_settings().ambiente not in AMBIENTES_PERMITIDOS:
        sys.stderr.write("e2e_semear_chat: recusado fora de desenvolvimento/teste\n")
        sys.exit(2)
    if "--carga" in sys.argv:
        garantir_carga()
    usuario_e2e, temporaria, processo_e2e, processo_hostil = semear()
    sys.stdout.write(f"{usuario_e2e}\n{temporaria}\n{processo_e2e}\n{processo_hostil}\n")
