"""Tabelas SQLAlchemy do domínio; espelham a migração inicial do Alembic.

Toda tabela que pertence a um gabinete carrega `gabinete_id` (desnormalizado a partir do
processo) para que a Row Level Security filtre sem junções. Chaves estrangeiras compostas
`(x_id, gabinete_id)` garantem que o filho fique no mesmo gabinete do pai.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column

from lupa.dominio.enums import (
    CenarioArquivo,
    EstadoJob,
    EstadoLote,
    Materia,
    MetodoClassificacao,
    MotivoQuarentena,
    OrigemPeca,
    PapelMensagem,
    PapelUsuario,
    ResultadoAchado,
    ResultadoChamada,
    StatusFato,
    StatusMensagem,
    StatusProcesso,
    TipoFato,
    TipoPagina,
    TipoPeca,
)
from lupa.seguranca.chaves import cifrar_identidade
from lupa.seguranca.contexto import nova_dek, obter_cofre, registrar_dek
from lupa.seguranca.tipos import JsonCifrado, TextoCifrado

CONVENCAO_NOMES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}

TABELAS_COM_GABINETE_V1 = (
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
"""Tabelas com gabinete das revisões 0001 e 0002 (congeladas: as migrações antigas usam esta)."""

TABELAS_INGESTAO = ("job_ingestao", "lote_ingestao", "diagnostico_arquivo")
"""Tabelas com gabinete criadas pela revisão 0003 (ingestão)."""

TABELAS_AGENTE = ("conversa", "mensagem", "chamada_modelo")
"""Tabelas com gabinete criadas pela revisão 0007 (agente e chat)."""

TABELAS_REVISAO = ("revisao_processo",)
"""Tabela com gabinete criada pela revisão 0009 (processo em revisão após incidente)."""

TABELAS_COM_GABINETE = TABELAS_COM_GABINETE_V1 + TABELAS_INGESTAO + TABELAS_AGENTE + TABELAS_REVISAO
"""Todas as tabelas com `gabinete_id` e RLS no esquema corrente."""


def checar_enum(coluna: str, enum: type[StrEnum]) -> CheckConstraint:
    """Cria CHECK que restringe a coluna de texto aos valores do enum.

    Args:
        coluna: Nome da coluna.
        enum: Enum com os valores permitidos.

    Returns:
        A constraint nomeada `<coluna>_valido`.
    """
    valores = ", ".join(f"'{membro.value}'" for membro in enum)
    return CheckConstraint(f"{coluna} IN ({valores})", name=f"{coluna}_valido")


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True)


def _gabinete() -> Mapped[UUID]:
    return mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)


def _instante() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _fk_composta(coluna: str, alvo: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        [coluna, "gabinete_id"], [f"{alvo}.id", f"{alvo}.gabinete_id"], ondelete="CASCADE"
    )


class Base(DeclarativeBase):
    """Base declarativa com convenção de nomes de constraints."""

    metadata = MetaData(naming_convention=CONVENCAO_NOMES)


class GabineteTabela(Base):
    """Tabela `gabinete` (tenant)."""

    __tablename__ = "gabinete"

    id: Mapped[UUID] = _uuid_pk()
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    chave_criptografia_ref: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = _instante()


class UsuarioTabela(Base):
    """Tabela `usuario`; `gabinete_id` nulo só para administrador."""

    __tablename__ = "usuario"
    __table_args__ = (
        checar_enum("papel", PapelUsuario),
        CheckConstraint(
            "(papel = 'administrador') = (gabinete_id IS NULL)", name="admin_sem_gabinete"
        ),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("gabinete.id"), index=True
    )
    nome_usuario: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    papel: Mapped[str] = mapped_column(Text, nullable=False)
    senha_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mfa_segredo: Mapped[str | None] = mapped_column(Text)
    mfa_confirmado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    troca_senha_obrigatoria: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = _instante()
    mfa_ultimo_passo: Mapped[int | None] = mapped_column(BigInteger)


class ProcessoTabela(Base):
    """Tabela `processo`."""

    __tablename__ = "processo"
    __table_args__ = (
        UniqueConstraint("gabinete_id", "numero_cnj"),
        UniqueConstraint("id", "gabinete_id"),
        checar_enum("materia", Materia),
        checar_enum("status", StatusProcesso),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("gabinete.id"), nullable=False, index=True
    )
    numero_cnj: Mapped[str] = mapped_column(Text, nullable=False)
    classe: Mapped[str] = mapped_column(Text, nullable=False)
    materia: Mapped[str] = mapped_column(Text, nullable=False)
    sigiloso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = _instante()
    criado_por: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
    chave_dados_cifrada: Mapped[str | None] = mapped_column(Text)


@event.listens_for(ProcessoTabela, "before_insert")
def _gerar_dek_do_processo(_mapper: Mapper[Any], _conexao: Connection, alvo: Any) -> None:
    """Etapa 7.3: todo processo nasce com DEK própria, cifrada pela chave do gabinete.

    A DEK em claro fica só no contexto de cifra do escopo, que passa a gravar com ela.
    """
    if alvo.chave_dados_cifrada is not None:
        return
    if alvo.id is None:
        alvo.id = uuid4()
    dek, token = nova_dek(obter_cofre(), alvo.gabinete_id)
    alvo.chave_dados_cifrada = token
    registrar_dek(alvo.id, dek)


class ArquivoTabela(Base):
    """Tabela `arquivo`; imutável (trigger bloqueia UPDATE)."""

    __tablename__ = "arquivo"
    __table_args__ = (
        _fk_composta("processo_id", "processo"),
        UniqueConstraint("processo_id", "sha256"),
        UniqueConstraint("id", "gabinete_id"),
        CheckConstraint("tamanho_bytes > 0", name="tamanho_positivo"),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    processo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    nome_original: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    chave_storage: Mapped[str] = mapped_column(Text, nullable=False)
    enviado_por: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
    enviado_em: Mapped[datetime] = _instante()


class PaginaTabela(Base):
    """Tabela `pagina`."""

    __tablename__ = "pagina"
    __table_args__ = (
        _fk_composta("arquivo_id", "arquivo"),
        UniqueConstraint("arquivo_id", "numero"),
        UniqueConstraint("id", "gabinete_id"),
        checar_enum("tipo", TipoPagina),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    arquivo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    texto: Mapped[str] = mapped_column(TextoCifrado("pagina.texto"), nullable=False)
    hash_texto: Mapped[str] = mapped_column(Text, nullable=False)
    flags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    sinais: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    coordenadas: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    extracao: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    texto_nativo: Mapped[str | None] = mapped_column(TextoCifrado("pagina.texto_nativo"))
    texto_ocr: Mapped[str | None] = mapped_column(TextoCifrado("pagina.texto_ocr"))
    versao_extrator: Mapped[str | None] = mapped_column(Text)
    origem_arquivo: Mapped[str | None] = mapped_column(Text)
    pagina_origem: Mapped[int | None] = mapped_column(Integer)
    texto_normalizado: Mapped[str | None] = mapped_column(TextoCifrado("pagina.texto_normalizado"))
    trechos_ocultos: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonCifrado("pagina.trechos_ocultos"), nullable=False, server_default="[]"
    )
    trechos_suspeitos: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonCifrado("pagina.trechos_suspeitos"), nullable=False, server_default="[]"
    )
    sinais_fronteira: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )


class PecaTabela(Base):
    """Tabela `peca`; reclassificação grava linha nova e a anterior deixa de ser vigente (4E)."""

    __tablename__ = "peca"
    __table_args__ = (
        _fk_composta("arquivo_id", "arquivo"),
        ForeignKeyConstraint(
            ["data_evidencia_id", "gabinete_id"], ["evidencia.id", "evidencia.gabinete_id"]
        ),
        ForeignKeyConstraint(["substitui_peca_id", "gabinete_id"], ["peca.id", "peca.gabinete_id"]),
        UniqueConstraint("id", "gabinete_id"),
        CheckConstraint("pagina_final >= pagina_inicial", name="paginas_em_ordem"),
        CheckConstraint("confianca BETWEEN 0 AND 1", name="confianca_intervalo"),
        CheckConstraint(
            "tipo_data IS NULL OR tipo_data IN ('assinatura', 'protocolo', 'juntada')",
            name="tipo_data_valido",
        ),
        checar_enum("tipo", TipoPeca),
        checar_enum("metodo", MetodoClassificacao),
        checar_enum("origem", OrigemPeca),
        Index("ix_peca_arquivo_id_vigente", "arquivo_id", "vigente"),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    arquivo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    pagina_inicial: Mapped[int] = mapped_column(Integer, nullable=False)
    pagina_final: Mapped[int] = mapped_column(Integer, nullable=False)
    confianca: Mapped[float] = mapped_column(Float, nullable=False)
    metodo: Mapped[str] = mapped_column(Text, nullable=False)
    origem: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[date | None] = mapped_column(Date)
    tipo_data: Mapped[str | None] = mapped_column(Text)
    data_evidencia_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    substitui_peca_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    vigente: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    flags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    classificacao: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )


class EvidenciaTabela(Base):
    """Tabela `evidencia`."""

    __tablename__ = "evidencia"
    __table_args__ = (
        _fk_composta("pagina_id", "pagina"),
        UniqueConstraint("id", "gabinete_id"),
        CheckConstraint("inicio >= 0 AND fim > inicio", name="offsets_validos"),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    pagina_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    trecho: Mapped[str] = mapped_column(TextoCifrado("evidencia.trecho"), nullable=False)
    hash_trecho: Mapped[str] = mapped_column(Text, nullable=False)
    inicio: Mapped[int] = mapped_column(Integer, nullable=False)
    fim: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class FatoTabela(Base):
    """Tabela `fato`; trigger adiado exige ao menos uma linha em `fato_evidencia`."""

    __tablename__ = "fato"
    __table_args__ = (
        _fk_composta("processo_id", "processo"),
        UniqueConstraint("id", "gabinete_id"),
        Index("ix_fato_processo_id_tipo", "processo_id", "tipo"),
        CheckConstraint("confianca BETWEEN 0 AND 1", name="confianca_intervalo"),
        checar_enum("tipo", TipoFato),
        checar_enum("status", StatusFato),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    processo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    valor: Mapped[Any] = mapped_column(JSONB, nullable=False)
    extraido_por: Mapped[str] = mapped_column(Text, nullable=False)
    versao_extrator: Mapped[str] = mapped_column(Text, nullable=False)
    confianca: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    substitui_fato_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fato.id")
    )
    criado_em: Mapped[datetime] = _instante()


class FatoEvidenciaTabela(Base):
    """Associação N:N entre `fato` e `evidencia`."""

    __tablename__ = "fato_evidencia"
    __table_args__ = (
        _fk_composta("fato_id", "fato"),
        _fk_composta("evidencia_id", "evidencia"),
    )

    fato_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    evidencia_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    gabinete_id: Mapped[UUID] = _gabinete()


class ReuTabela(Base):
    """Tabela `reu`: só pseudônimo, sem nome real."""

    __tablename__ = "reu"
    __table_args__ = (
        _fk_composta("processo_id", "processo"),
        UniqueConstraint("id", "gabinete_id"),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    processo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    pseudonimo: Mapped[str] = mapped_column(Text, nullable=False)


class ReuIdentidadeTabela(Base):
    """Tabela `reu_identidade`: nome e documento cifrados no Transit (7.6)."""

    __tablename__ = "reu_identidade"
    __table_args__ = (_fk_composta("reu_id", "reu"),)

    reu_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    gabinete_id: Mapped[UUID] = _gabinete()
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    documento: Mapped[str | None] = mapped_column(Text)


@event.listens_for(ReuIdentidadeTabela, "before_insert")
@event.listens_for(ReuIdentidadeTabela, "before_update")
def _cifrar_identidade(_mapper: Mapper[Any], _conexao: Connection, alvo: Any) -> None:
    """Etapa 7.6: nome e documento só chegam ao banco cifrados pelo Transit do gabinete."""
    cofre = obter_cofre()
    alvo.nome = cifrar_identidade(cofre, alvo.gabinete_id, alvo.nome)
    alvo.documento = cifrar_identidade(cofre, alvo.gabinete_id, alvo.documento)


class AchadoTabela(Base):
    """Tabela `achado`; imutável (trigger bloqueia UPDATE)."""

    __tablename__ = "achado"
    __table_args__ = (
        _fk_composta("processo_id", "processo"),
        UniqueConstraint("id", "gabinete_id"),
        checar_enum("resultado", ResultadoAchado),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    processo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    validacao: Mapped[str] = mapped_column(Text, nullable=False)
    versao_catalogo: Mapped[str] = mapped_column(Text, nullable=False)
    resultado: Mapped[str] = mapped_column(Text, nullable=False)
    fatos_usados: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False, server_default="{}"
    )
    valores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    explicacao: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = _instante()


class AnotacaoTabela(Base):
    """Tabela `anotacao`: nota sobre achado ou fato."""

    __tablename__ = "anotacao"
    __table_args__ = (
        _fk_composta("achado_id", "achado"),
        _fk_composta("fato_id", "fato"),
        CheckConstraint("(achado_id IS NULL) <> (fato_id IS NULL)", name="um_alvo"),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    achado_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    fato_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    usuario_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = _instante()


class EventoAuditoriaTabela(Base):
    """Tabela `evento_auditoria`: append-only, encadeada por hash dentro de cada gabinete.

    `sequencia` é a posição do evento na cadeia do gabinete (ou na cadeia global, quando
    `gabinete_id` é nulo); a unicidade `(gabinete_id, sequencia)` com `NULLS NOT DISTINCT`
    impede dois eventos com o mesmo antecessor.
    """

    __tablename__ = "evento_auditoria"
    __table_args__ = (
        UniqueConstraint("gabinete_id", "sequencia", postgresql_nulls_not_distinct=True),
        Index("ix_evento_auditoria_ocorrido_em", "ocorrido_em"),
        Index("ix_evento_auditoria_usuario_id_ocorrido_em", "usuario_id", "ocorrido_em"),
        Index("ix_evento_auditoria_gabinete_id_ocorrido_em", "gabinete_id", "ocorrido_em"),
        Index("ix_evento_auditoria_processo_id_ocorrido_em", "processo_id", "ocorrido_em"),
        Index("ix_evento_auditoria_acao_ocorrido_em", "acao", "ocorrido_em"),
        Index("ix_evento_auditoria_ip_ocorrido_em", "ip", "ocorrido_em"),
    )

    id: Mapped[UUID] = _uuid_pk()
    ocorrido_em: Mapped[datetime] = _instante()
    usuario_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("usuario.id"))
    gabinete_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("gabinete.id"), index=True
    )
    processo_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    acao: Mapped[str] = mapped_column(Text, nullable=False)
    objeto_tipo: Mapped[str | None] = mapped_column(Text)
    objeto_id: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(Text)
    localizacao: Mapped[str | None] = mapped_column(Text)
    resultado: Mapped[str] = mapped_column(Text, nullable=False)
    versao_modelo: Mapped[str | None] = mapped_column(Text)
    versao_prompt: Mapped[str | None] = mapped_column(Text)
    hash_anterior: Mapped[str | None] = mapped_column(Text)
    hash_evento: Mapped[str] = mapped_column(Text, nullable=False)
    sequencia: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SessaoTabela(Base):
    """Tabela `sessao`: sessão server-side; `id` é o SHA-256 do token entregue no cookie.

    `gabinete_id` e `papel` são copiados do usuário para que a requisição defina o contexto
    da RLS antes de ler o próprio usuário.
    """

    __tablename__ = "sessao"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    usuario_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False, index=True
    )
    gabinete_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("gabinete.id")
    )
    papel: Mapped[str] = mapped_column(Text, nullable=False)
    criada_em: Mapped[datetime] = _instante()
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ultimo_acesso_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_criacao: Mapped[str | None] = mapped_column(Text)
    revogada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DesafioMfaTabela(Base):
    """Tabela `desafio_mfa`: etapa intermediária do login (senha ok, TOTP pendente)."""

    __tablename__ = "desafio_mfa"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    usuario_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False, index=True
    )
    gabinete_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("gabinete.id")
    )
    papel: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = _instante()
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FalhaLoginTabela(Base):
    """Tabela `falha_login`: falhas recentes, para o rate limit.

    `chave` é o SHA-256 do nome de usuário digitado; o nome em si não é guardado, porque às
    vezes a pessoa digita a senha no campo de usuário.
    """

    __tablename__ = "falha_login"
    __table_args__ = (Index("ix_falha_login_chave_ocorrida_em", "chave", "ocorrida_em"),)

    id: Mapped[UUID] = _uuid_pk()
    chave: Mapped[str] = mapped_column(Text, nullable=False)
    ocorrida_em: Mapped[datetime] = _instante()


class BloqueioLoginTabela(Base):
    """Tabela `bloqueio_login`: chave (SHA-256 do nome de usuário) bloqueada até um instante."""

    __tablename__ = "bloqueio_login"

    chave: Mapped[str] = mapped_column(Text, primary_key=True)
    bloqueado_ate: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobIngestaoTabela(Base):
    """Tabela `job_ingestao`: um job por arquivo, com estado, lease e fencing token.

    `fencing_token` cresce a cada aquisição de lease; gravações de lote só são aceitas com o
    token corrente, o que impede um worker que perdeu o lease de gravar depois do sucessor.
    """

    __tablename__ = "job_ingestao"
    __table_args__ = (
        _fk_composta("arquivo_id", "arquivo"),
        _fk_composta("processo_id", "processo"),
        UniqueConstraint("arquivo_id"),
        UniqueConstraint("id", "gabinete_id"),
        checar_enum("estado", EstadoJob),
        checar_enum("motivo_quarentena", MotivoQuarentena),
        CheckConstraint(
            "(estado = 'quarentena') = (motivo_quarentena IS NOT NULL)",
            name="quarentena_com_motivo",
        ),
        Index("ix_job_ingestao_estado_lease_expira_em", "estado", "lease_expira_em"),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    processo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    arquivo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    motivo_quarentena: Mapped[str | None] = mapped_column(Text)
    motivo_falha: Mapped[str | None] = mapped_column(Text)
    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    lease_dono: Mapped[str | None] = mapped_column(Text)
    lease_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_paginas: Mapped[int | None] = mapped_column(Integer)
    manifesto: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    relatorio: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    versao_extrator: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = _instante()
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoteIngestaoTabela(Base):
    """Tabela `lote_ingestao`: resultado de cada lote; único por `(job_id, numero)`."""

    __tablename__ = "lote_ingestao"
    __table_args__ = (
        _fk_composta("job_id", "job_ingestao"),
        UniqueConstraint("job_id", "numero"),
        checar_enum("estado", EstadoLote),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    resultado: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    gravado_em: Mapped[datetime] = _instante()


class DiagnosticoArquivoTabela(Base):
    """Tabela `diagnostico_arquivo`: cenário e sinais do arquivo (um por arquivo)."""

    __tablename__ = "diagnostico_arquivo"
    __table_args__ = (
        _fk_composta("arquivo_id", "arquivo"),
        UniqueConstraint("arquivo_id"),
        checar_enum("cenario", CenarioArquivo),
        CheckConstraint("total_paginas >= 0", name="paginas_nao_negativas"),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    arquivo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    cenario: Mapped[str] = mapped_column(Text, nullable=False)
    total_paginas: Mapped[int] = mapped_column(Integer, nullable=False)
    tem_indice: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sinais: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    fronteiras_origem: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    metadados_descartados: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    criado_em: Mapped[datetime] = _instante()


class ConversaTabela(Base):
    """Tabela `conversa`: uma conversa do chat de um usuário sobre um processo (Etapa 5).

    Guarda os contadores usados nos tetos (tokens, páginas originais) e o contador de citações
    descartadas. Conversa encerrada (teto) não recebe mais perguntas.
    """

    __tablename__ = "conversa"
    __table_args__ = (
        _fk_composta("processo_id", "processo"),
        UniqueConstraint("id", "gabinete_id"),
        Index("ix_conversa_processo_id_usuario_id", "processo_id", "usuario_id"),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    processo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
    criada_em: Mapped[datetime] = _instante()
    encerrada: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    motivo_encerramento: Mapped[str | None] = mapped_column(Text)
    tokens_entrada: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    tokens_saida: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    paginas_originais: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    citacoes_descartadas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class MensagemTabela(Base):
    """Tabela `mensagem`: pergunta ou resposta do chat; `texto` cifrado com a DEK do processo."""

    __tablename__ = "mensagem"
    __table_args__ = (
        _fk_composta("conversa_id", "conversa"),
        Index("ix_mensagem_conversa_id_criado_em", "conversa_id", "criado_em"),
        checar_enum("papel", PapelMensagem),
        checar_enum("status", StatusMensagem),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    conversa_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    papel: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    texto: Mapped[str] = mapped_column(TextoCifrado("mensagem.texto"), nullable=False)
    citacoes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    avisos: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    criado_em: Mapped[datetime] = _instante()


class ChamadaModeloTabela(Base):
    """Tabela `chamada_modelo`: metadados de cada chamada ao modelo, sem conteúdo (Etapa 5.9).

    O evento `chamada_modelo` da auditoria aponta para a linha (`objeto_id`); aqui ficam os
    hashes, tokens e latência, que não cabem no formato fixo do evento.
    """

    __tablename__ = "chamada_modelo"
    __table_args__ = (
        _fk_composta("processo_id", "processo"),
        Index("ix_chamada_modelo_processo_id_criado_em", "processo_id", "criado_em"),
        checar_enum("resultado", ResultadoChamada),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    processo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    conversa_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    modelo: Mapped[str] = mapped_column(Text, nullable=False)
    versao_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    hash_prompt_sistema: Mapped[str] = mapped_column(Text, nullable=False)
    hash_entrada: Mapped[str] = mapped_column(Text, nullable=False)
    hash_saida: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_entrada: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_saida: Mapped[int] = mapped_column(Integer, nullable=False)
    latencia_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ferramentas: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    resultado: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = _instante()


class RevisaoProcessoTabela(Base):
    """Tabela `revisao_processo`: incidente que pôs o processo em revisão (Etapa 6.8).

    Aberta quando a conferência bloqueia uma resposta do modelo (instrução refletida ou
    identificador de outro processo); fechada quando um desembargador ou administrador libera.
    Guarda o status anterior para devolvê-lo na liberação. Sem conteúdo dos autos.
    """

    __tablename__ = "revisao_processo"
    __table_args__ = (
        _fk_composta("processo_id", "processo"),
        Index("ix_revisao_processo_processo_id", "processo_id"),
    )

    id: Mapped[UUID] = _uuid_pk()
    gabinete_id: Mapped[UUID] = _gabinete()
    processo_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    status_anterior: Mapped[str] = mapped_column(Text, nullable=False)
    aberta_em: Mapped[datetime] = _instante()
    liberada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    liberada_por: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("usuario.id")
    )
