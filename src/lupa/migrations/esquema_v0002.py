"""Revisão 0002, escrita à mão: sessões, rate limit de login, auditoria append-only e RLS do admin.

Resolve os pontos herdados da Etapa 1 (ver `docs/etapas/RELATORIO-ETAPA-3.md`):

- login sob RLS: função `lupa_localizar_usuario` (SECURITY DEFINER) devolve só id, gabinete e
  papel a partir do nome de usuário, para a aplicação definir o contexto antes de ler o usuário;
- administrador e eventos globais: política `<tabela>_administrador` liberada quando
  `lupa.papel = 'administrador'` e política de inserção de eventos sem gabinete;
- grants: tabelas novas recebem grant explícito e `ALTER DEFAULT PRIVILEGES` cobre as futuras.
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from lupa.dominio.tabelas import TABELAS_COM_GABINETE_V1

PAPEL_APLICACAO = "lupa_app"
TABELAS_NOVAS = ("sessao", "desafio_mfa", "falha_login", "bloqueio_login")
INDICES_AUDITORIA = {
    "ix_evento_auditoria_ocorrido_em": ["ocorrido_em"],
    "ix_evento_auditoria_usuario_id_ocorrido_em": ["usuario_id", "ocorrido_em"],
    "ix_evento_auditoria_gabinete_id_ocorrido_em": ["gabinete_id", "ocorrido_em"],
    "ix_evento_auditoria_processo_id_ocorrido_em": ["processo_id", "ocorrido_em"],
    "ix_evento_auditoria_acao_ocorrido_em": ["acao", "ocorrido_em"],
    "ix_evento_auditoria_ip_ocorrido_em": ["ip", "ocorrido_em"],
}
UQ_SEQUENCIA = "uq_evento_auditoria_gabinete_id_sequencia"


def _instante(nome: str) -> sa.Column[Any]:
    return sa.Column(nome, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _momento(nome: str) -> sa.Column[Any]:
    return sa.Column(nome, sa.DateTime(timezone=True), nullable=False)


def _usuario_fk() -> sa.Column[Any]:
    return sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False)


def _gabinete_fk() -> sa.Column[Any]:
    return sa.Column("gabinete_id", UUID(as_uuid=True), sa.ForeignKey("gabinete.id"), nullable=True)


def _falso(nome: str) -> sa.Column[Any]:
    return sa.Column(nome, sa.Boolean(), server_default=sa.false(), nullable=False)


def _criar_tabelas_acesso() -> None:
    op.create_table(
        "sessao",
        sa.Column("id", sa.Text(), primary_key=True),
        _usuario_fk(),
        _gabinete_fk(),
        sa.Column("papel", sa.Text(), nullable=False),
        _instante("criada_em"),
        _momento("expira_em"),
        _momento("ultimo_acesso_em"),
        sa.Column("ip_criacao", sa.Text(), nullable=True),
        _falso("revogada"),
    )
    op.create_index("ix_sessao_usuario_id", "sessao", ["usuario_id"])
    op.create_table(
        "desafio_mfa",
        sa.Column("id", sa.Text(), primary_key=True),
        _usuario_fk(),
        _gabinete_fk(),
        sa.Column("papel", sa.Text(), nullable=False),
        _instante("criado_em"),
        _momento("expira_em"),
        _falso("consumido"),
    )
    op.create_index("ix_desafio_mfa_usuario_id", "desafio_mfa", ["usuario_id"])
    op.create_table(
        "falha_login",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("chave", sa.Text(), nullable=False),
        _instante("ocorrida_em"),
    )
    op.create_index("ix_falha_login_chave_ocorrida_em", "falha_login", ["chave", "ocorrida_em"])
    op.create_table(
        "bloqueio_login",
        sa.Column("chave", sa.Text(), primary_key=True),
        _momento("bloqueado_ate"),
    )
    op.add_column("usuario", sa.Column("mfa_ultimo_passo", sa.BigInteger(), nullable=True))


SQL_NUMERAR_EVENTOS = """
UPDATE evento_auditoria e SET sequencia = n.posicao
FROM (
    SELECT id, row_number() OVER (PARTITION BY gabinete_id ORDER BY ocorrido_em, id) AS posicao
    FROM evento_auditoria
) n
WHERE e.id = n.id
"""


def _evoluir_auditoria() -> None:
    op.add_column("evento_auditoria", sa.Column("sequencia", sa.BigInteger(), nullable=True))
    op.execute(SQL_NUMERAR_EVENTOS)
    op.alter_column("evento_auditoria", "sequencia", nullable=False)
    op.create_unique_constraint(
        UQ_SEQUENCIA,
        "evento_auditoria",
        ["gabinete_id", "sequencia"],
        postgresql_nulls_not_distinct=True,
    )
    for nome, colunas in INDICES_AUDITORIA.items():
        op.create_index(nome, "evento_auditoria", colunas)


SQL_FUNCOES = """
CREATE FUNCTION lupa_bloquear_alteracao_auditoria() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'evento_auditoria é append-only: % bloqueado', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER evento_auditoria_append_only BEFORE UPDATE OR DELETE ON evento_auditoria
    FOR EACH ROW EXECUTE FUNCTION lupa_bloquear_alteracao_auditoria();
CREATE TRIGGER evento_auditoria_sem_truncate BEFORE TRUNCATE ON evento_auditoria
    FOR EACH STATEMENT EXECUTE FUNCTION lupa_bloquear_alteracao_auditoria();

CREATE FUNCTION lupa_localizar_usuario(p_nome text)
RETURNS TABLE (id uuid, gabinete_id uuid, papel text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT u.id, u.gabinete_id, u.papel FROM public.usuario u WHERE u.nome_usuario = p_nome
$$;

CREATE FUNCTION lupa_travar_cadeia(p_gabinete uuid)
RETURNS TABLE (hash_evento text, sequencia bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended('lupa_auditoria:' || coalesce(p_gabinete::text, 'global'), 0)
    );
    IF p_gabinete IS NULL THEN
        RETURN QUERY SELECT e.hash_evento, e.sequencia FROM public.evento_auditoria e
            WHERE e.gabinete_id IS NULL ORDER BY e.sequencia DESC LIMIT 1 FOR UPDATE;
    ELSE
        RETURN QUERY SELECT e.hash_evento, e.sequencia FROM public.evento_auditoria e
            WHERE e.gabinete_id = p_gabinete ORDER BY e.sequencia DESC LIMIT 1 FOR UPDATE;
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION lupa_localizar_usuario(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION lupa_travar_cadeia(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lupa_localizar_usuario(text) TO lupa_app;
GRANT EXECUTE ON FUNCTION lupa_travar_cadeia(uuid) TO lupa_app;
"""


def _criar_funcoes() -> None:
    op.execute(SQL_FUNCOES)


def _criar_politicas() -> None:
    for tabela in TABELAS_COM_GABINETE_V1:
        op.execute(
            f"""
            CREATE POLICY {tabela}_administrador ON {tabela}
                USING (current_setting('lupa.papel', true) = 'administrador')
                WITH CHECK (current_setting('lupa.papel', true) = 'administrador')
            """
        )
    op.execute(
        """
        CREATE POLICY evento_auditoria_global_insercao ON evento_auditoria
            FOR INSERT WITH CHECK (gabinete_id IS NULL)
        """
    )


def _conceder_privilegios() -> None:
    tabelas = ", ".join(TABELAS_NOVAS)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tabelas} TO {PAPEL_APLICACAO}")
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON evento_auditoria FROM {PAPEL_APLICACAO}")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {PAPEL_APLICACAO}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO {PAPEL_APLICACAO}"
    )


def upgrade() -> None:
    """Cria as estruturas de acesso e torna a auditoria append-only e encadeada."""
    _criar_tabelas_acesso()
    _evoluir_auditoria()
    _criar_funcoes()
    _criar_politicas()
    _conceder_privilegios()


def downgrade() -> None:
    """Desfaz a revisão 0002, voltando ao esquema da 0001."""
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE ON SEQUENCES FROM {PAPEL_APLICACAO}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {PAPEL_APLICACAO}"
    )
    op.execute(f"GRANT UPDATE, DELETE ON evento_auditoria TO {PAPEL_APLICACAO}")
    op.execute("DROP POLICY evento_auditoria_global_insercao ON evento_auditoria")
    for tabela in TABELAS_COM_GABINETE_V1:
        op.execute(f"DROP POLICY {tabela}_administrador ON {tabela}")
    op.execute("DROP FUNCTION lupa_travar_cadeia(uuid)")
    op.execute("DROP FUNCTION lupa_localizar_usuario(text)")
    op.execute("DROP TRIGGER evento_auditoria_sem_truncate ON evento_auditoria")
    op.execute("DROP TRIGGER evento_auditoria_append_only ON evento_auditoria")
    op.execute("DROP FUNCTION lupa_bloquear_alteracao_auditoria()")
    for nome in INDICES_AUDITORIA:
        op.drop_index(nome, "evento_auditoria")
    op.drop_constraint(UQ_SEQUENCIA, "evento_auditoria")
    op.drop_column("evento_auditoria", "sequencia")
    op.drop_column("usuario", "mfa_ultimo_passo")
    for tabela in reversed(TABELAS_NOVAS):
        op.drop_table(tabela)
