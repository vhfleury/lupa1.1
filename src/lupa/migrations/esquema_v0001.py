"""Revisão 0001, escrita e revisada à mão: tabelas, índices, triggers e RLS por gabinete.

O arquivo `versions/v0001_inicial.py` reexporta `upgrade` e `downgrade` daqui para o código ficar
no pacote `lupa` (medido pela cobertura). O teste `test_migracao_coincide_com_tabelas` compara o
resultado com `lupa.dominio.tabelas` usando o autogenerate do Alembic.
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from lupa.dominio.enums import (
    Materia,
    MetodoClassificacao,
    OrigemPeca,
    PapelUsuario,
    ResultadoAchado,
    StatusFato,
    StatusProcesso,
    TipoFato,
    TipoPagina,
    TipoPeca,
)
from lupa.dominio.tabelas import TABELAS_COM_GABINETE_V1, checar_enum

PAPEL_APLICACAO = "lupa_app"


def _id() -> sa.Column[Any]:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _gabinete() -> sa.Column[Any]:
    return sa.Column("gabinete_id", UUID(as_uuid=True), nullable=False)


def _uuid(nome: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(nome, UUID(as_uuid=True), nullable=nullable)


def _texto(nome: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(nome, sa.Text(), nullable=nullable)


def _inteiro(nome: str) -> sa.Column[Any]:
    return sa.Column(nome, sa.Integer(), nullable=False)


def _booleano(nome: str) -> sa.Column[Any]:
    return sa.Column(nome, sa.Boolean(), nullable=False)


def _confianca() -> sa.Column[Any]:
    return sa.Column("confianca", sa.Float(), nullable=False)


def _instante(nome: str = "criado_em") -> sa.Column[Any]:
    return sa.Column(nome, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _jsonb(nome: str, *, nullable: bool = False, padrao: str | None = "{}") -> sa.Column[Any]:
    return sa.Column(nome, JSONB, nullable=nullable, server_default=padrao)


def _fk(coluna: str, alvo: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [coluna, "gabinete_id"], [f"{alvo}.id", f"{alvo}.gabinete_id"], ondelete="CASCADE"
    )


def _uq_id_gabinete() -> sa.UniqueConstraint:
    return sa.UniqueConstraint("id", "gabinete_id")


def _criar_tabelas_base() -> None:
    op.create_table(
        "gabinete",
        _id(),
        _texto("nome"),
        _texto("chave_criptografia_ref", nullable=True),
        _instante(),
    )
    op.create_table(
        "usuario",
        _id(),
        sa.Column("gabinete_id", UUID(as_uuid=True), sa.ForeignKey("gabinete.id"), nullable=True),
        _texto("nome_usuario"),
        _texto("papel"),
        _texto("senha_hash"),
        _texto("mfa_segredo", nullable=True),
        _booleano("mfa_confirmado"),
        _booleano("ativo"),
        _booleano("troca_senha_obrigatoria"),
        _instante(),
        sa.UniqueConstraint("nome_usuario"),
        checar_enum("papel", PapelUsuario),
        sa.CheckConstraint(
            "(papel = 'administrador') = (gabinete_id IS NULL)", name="admin_sem_gabinete"
        ),
    )
    op.create_table(
        "processo",
        _id(),
        sa.Column("gabinete_id", UUID(as_uuid=True), sa.ForeignKey("gabinete.id"), nullable=False),
        _texto("numero_cnj"),
        _texto("classe"),
        _texto("materia"),
        _booleano("sigiloso"),
        _texto("status"),
        _instante(),
        sa.Column("criado_por", UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.UniqueConstraint("gabinete_id", "numero_cnj"),
        _uq_id_gabinete(),
        checar_enum("materia", Materia),
        checar_enum("status", StatusProcesso),
    )


def _criar_tabelas_autos() -> None:
    op.create_table(
        "arquivo",
        _id(),
        _gabinete(),
        _uuid("processo_id"),
        _texto("sha256"),
        _inteiro("tamanho_bytes"),
        _texto("nome_original"),
        _texto("mime"),
        _texto("chave_storage"),
        sa.Column("enviado_por", UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        _instante("enviado_em"),
        _fk("processo_id", "processo"),
        sa.UniqueConstraint("processo_id", "sha256"),
        _uq_id_gabinete(),
        sa.CheckConstraint("tamanho_bytes > 0", name="tamanho_positivo"),
    )
    op.create_table(
        "pagina",
        _id(),
        _gabinete(),
        _uuid("arquivo_id"),
        _inteiro("numero"),
        _texto("tipo"),
        _texto("texto"),
        _texto("hash_texto"),
        _jsonb("flags"),
        _fk("arquivo_id", "arquivo"),
        sa.UniqueConstraint("arquivo_id", "numero"),
        _uq_id_gabinete(),
        checar_enum("tipo", TipoPagina),
    )
    op.create_table(
        "peca",
        _id(),
        _gabinete(),
        _uuid("arquivo_id"),
        _texto("tipo"),
        _inteiro("pagina_inicial"),
        _inteiro("pagina_final"),
        _confianca(),
        _texto("metodo"),
        _texto("origem"),
        _fk("arquivo_id", "arquivo"),
        sa.CheckConstraint("pagina_final >= pagina_inicial", name="paginas_em_ordem"),
        sa.CheckConstraint("confianca BETWEEN 0 AND 1", name="confianca_intervalo"),
        checar_enum("tipo", TipoPeca),
        checar_enum("metodo", MetodoClassificacao),
        checar_enum("origem", OrigemPeca),
    )
    op.create_table(
        "evidencia",
        _id(),
        _gabinete(),
        _uuid("pagina_id"),
        _texto("trecho"),
        _texto("hash_trecho"),
        _inteiro("inicio"),
        _inteiro("fim"),
        _jsonb("bbox", nullable=True, padrao=None),
        _fk("pagina_id", "pagina"),
        _uq_id_gabinete(),
        sa.CheckConstraint("inicio >= 0 AND fim > inicio", name="offsets_validos"),
    )


def _criar_tabelas_analise() -> None:
    op.create_table(
        "fato",
        _id(),
        _gabinete(),
        _uuid("processo_id"),
        _texto("tipo"),
        sa.Column("valor", JSONB, nullable=False),
        _texto("extraido_por"),
        _texto("versao_extrator"),
        _confianca(),
        _texto("status"),
        sa.Column("substitui_fato_id", UUID(as_uuid=True), sa.ForeignKey("fato.id"), nullable=True),
        _instante(),
        _fk("processo_id", "processo"),
        _uq_id_gabinete(),
        sa.CheckConstraint("confianca BETWEEN 0 AND 1", name="confianca_intervalo"),
        checar_enum("tipo", TipoFato),
        checar_enum("status", StatusFato),
    )
    op.create_table(
        "fato_evidencia",
        sa.Column("fato_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("evidencia_id", UUID(as_uuid=True), primary_key=True),
        _gabinete(),
        _fk("fato_id", "fato"),
        _fk("evidencia_id", "evidencia"),
    )
    op.create_table(
        "reu",
        _id(),
        _gabinete(),
        _uuid("processo_id"),
        _texto("pseudonimo"),
        _fk("processo_id", "processo"),
        _uq_id_gabinete(),
    )
    op.create_table(
        "reu_identidade",
        sa.Column("reu_id", UUID(as_uuid=True), primary_key=True),
        _gabinete(),
        _texto("nome"),
        _texto("documento", nullable=True),
        _fk("reu_id", "reu"),
    )
    op.create_table(
        "achado",
        _id(),
        _gabinete(),
        _uuid("processo_id"),
        _texto("validacao"),
        _texto("versao_catalogo"),
        _texto("resultado"),
        sa.Column(
            "fatos_usados", sa.ARRAY(UUID(as_uuid=True)), server_default="{}", nullable=False
        ),
        _jsonb("valores"),
        _texto("explicacao"),
        _instante(),
        _fk("processo_id", "processo"),
        _uq_id_gabinete(),
        checar_enum("resultado", ResultadoAchado),
    )
    op.create_table(
        "anotacao",
        _id(),
        _gabinete(),
        _uuid("achado_id", nullable=True),
        _uuid("fato_id", nullable=True),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        _texto("texto"),
        _instante(),
        _fk("achado_id", "achado"),
        _fk("fato_id", "fato"),
        sa.CheckConstraint("(achado_id IS NULL) <> (fato_id IS NULL)", name="um_alvo"),
    )
    op.create_table(
        "evento_auditoria",
        _id(),
        _instante("ocorrido_em"),
        sa.Column("usuario_id", UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("gabinete_id", UUID(as_uuid=True), sa.ForeignKey("gabinete.id"), nullable=True),
        _uuid("processo_id", nullable=True),
        _texto("acao"),
        _texto("objeto_tipo", nullable=True),
        _texto("objeto_id", nullable=True),
        _texto("ip", nullable=True),
        _texto("localizacao", nullable=True),
        _texto("resultado"),
        _texto("versao_modelo", nullable=True),
        _texto("versao_prompt", nullable=True),
        _texto("hash_anterior", nullable=True),
        _texto("hash_evento"),
    )


def _criar_indices() -> None:
    for tabela in TABELAS_COM_GABINETE_V1:
        op.create_index(f"ix_{tabela}_gabinete_id", tabela, ["gabinete_id"])
    op.create_index("ix_fato_processo_id_tipo", "fato", ["processo_id", "tipo"])


SQL_TRIGGERS = """
CREATE FUNCTION lupa_bloquear_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'tabela % é imutável: UPDATE bloqueado', TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER achado_imutavel BEFORE UPDATE ON achado
    FOR EACH ROW EXECUTE FUNCTION lupa_bloquear_update();
CREATE TRIGGER arquivo_imutavel BEFORE UPDATE ON arquivo
    FOR EACH ROW EXECUTE FUNCTION lupa_bloquear_update();

CREATE FUNCTION lupa_exigir_evidencia() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    alvo uuid;
BEGIN
    IF TG_TABLE_NAME = 'fato' THEN
        alvo := NEW.id;
    ELSE
        alvo := OLD.fato_id;
    END IF;
    IF EXISTS (SELECT 1 FROM fato WHERE id = alvo)
       AND NOT EXISTS (SELECT 1 FROM fato_evidencia WHERE fato_id = alvo) THEN
        RAISE EXCEPTION 'fato % sem evidência', alvo USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER fato_exige_evidencia AFTER INSERT ON fato
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION lupa_exigir_evidencia();
CREATE CONSTRAINT TRIGGER fato_evidencia_nao_orfa AFTER DELETE ON fato_evidencia
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION lupa_exigir_evidencia();
"""


def _criar_triggers() -> None:
    op.execute(SQL_TRIGGERS)


def _criar_papel_e_rls() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lupa_app') THEN
                CREATE ROLE lupa_app NOLOGIN;
            END IF;
        END $$;
        GRANT USAGE ON SCHEMA public TO lupa_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lupa_app;
        """
    )
    for tabela in TABELAS_COM_GABINETE_V1:
        op.execute(f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabela} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tabela}_por_gabinete ON {tabela}
                USING (gabinete_id = NULLIF(current_setting('lupa.gabinete_id', true), '')::uuid)
                WITH CHECK (
                    gabinete_id = NULLIF(current_setting('lupa.gabinete_id', true), '')::uuid
                )
            """
        )


def upgrade() -> None:
    """Cria todo o modelo de domínio da v1."""
    _criar_tabelas_base()
    _criar_tabelas_autos()
    _criar_tabelas_analise()
    _criar_indices()
    _criar_triggers()
    _criar_papel_e_rls()


def downgrade() -> None:
    """Remove todo o modelo de domínio; o papel `lupa_app` é global ao cluster e permanece."""
    for tabela in reversed(
        (
            "gabinete",
            "usuario",
            "processo",
            "arquivo",
            "pagina",
            "peca",
            "evidencia",
            "fato",
            "fato_evidencia",
            "reu",
            "reu_identidade",
            "achado",
            "anotacao",
            "evento_auditoria",
        )
    ):
        op.drop_table(tabela)
    op.execute("DROP FUNCTION lupa_exigir_evidencia()")
    op.execute("DROP FUNCTION lupa_bloquear_update()")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {PAPEL_APLICACAO}")
