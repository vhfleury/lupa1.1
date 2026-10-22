"""Prepara o banco de DESENVOLVIMENTO para os testes ponta a ponta do front (Etapa 6).

Uso (no contêiner): `python scripts/e2e_preparar.py`. Recusa rodar fora de `desenvolvimento`/`teste`.

1. Garante o administrador pelo mesmo caso de uso de `scripts/criar_admin.py`
   (`servico.criar_administrador`), com nome de `LUPA_ADMIN_USUARIO` (padrão `admin`).
2. Dá a ele uma senha temporária aleatória, gerada agora, com troca obrigatória; apaga o
   autenticador (o E2E cadastra outro lendo o segredo exibido na tela) e revoga as sessões.
   Grava `senha_resetada` na auditoria.
3. Limpa falhas e bloqueios de login: o E2E provoca bloqueios de propósito.

Saída: duas linhas na saída padrão, o nome do administrador e a senha temporária. Nada é
gravado em arquivo.
"""

import os
import sys
from datetime import UTC, datetime

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from lupa.acesso import senhas, sessoes
from lupa.acesso.servico import Contexto, auditar, criar_administrador, definir_contexto
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.config import get_settings
from lupa.dominio.enums import PapelUsuario
from lupa.dominio.sessao import assumir_papel_aplicacao
from lupa.dominio.tabelas import BloqueioLoginTabela, FalhaLoginTabela, UsuarioTabela

AMBIENTES_PERMITIDOS = frozenset({"desenvolvimento", "teste"})


def preparar() -> tuple[str, str]:
    """Garante e reseta o administrador e limpa os bloqueios de login.

    Returns:
        Nome do administrador e a senha temporária.
    """
    settings = get_settings()
    nome = os.environ.get("LUPA_ADMIN_USUARIO") or "admin"
    senha = senhas.gerar_senha_temporaria()
    ctx = Contexto(None, None, datetime.now(UTC))
    engine = create_engine(settings.url_banco_aplicacao())
    try:
        with Session(engine) as session, session.begin():
            assumir_papel_aplicacao(session)
            definir_contexto(session, PapelUsuario.ADMINISTRADOR.value, None)
            criado = criar_administrador(session, nome, senha, ctx)
            admin = session.scalars(
                select(UsuarioTabela).where(UsuarioTabela.papel == PapelUsuario.ADMINISTRADOR.value)
            ).one()
            if not criado:
                admin.senha_hash = senhas.gerar_hash(senha)
                admin.troca_senha_obrigatoria = True
                admin.ativo = True
                admin.mfa_segredo = None
                admin.mfa_confirmado = False
                admin.mfa_ultimo_passo = None
                sessoes.revogar_sessoes_do_usuario(session, admin.id)
                auditar(
                    session,
                    ctx,
                    AcaoAuditoria.SENHA_RESETADA,
                    usuario_id=admin.id,
                    objeto_tipo="usuario",
                    objeto_id=str(admin.id),
                )
            nome_admin = admin.nome_usuario
    finally:
        engine.dispose()
    dono = create_engine(settings.database_url.get_secret_value())
    try:
        with dono.begin() as conexao:
            conexao.execute(delete(FalhaLoginTabela))
            conexao.execute(delete(BloqueioLoginTabela))
    finally:
        dono.dispose()
    return nome_admin, senha


if __name__ == "__main__":
    if get_settings().ambiente not in AMBIENTES_PERMITIDOS:
        sys.stderr.write("e2e_preparar: recusado fora de desenvolvimento/teste\n")
        sys.exit(2)
    usuario, temporaria = preparar()
    sys.stdout.write(f"{usuario}\n{temporaria}\n")
