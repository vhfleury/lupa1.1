"""Esquemas pydantic do domínio: contratos de entrada e saída compartilhados entre etapas.

`Fato` e `Evidencia` são o contrato consumido pelas validações (Etapa 2).
"""

import hashlib
from datetime import UTC, date, datetime
from typing import Annotated, Any, Self
from uuid import UUID, uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from lupa.dominio.cnj import validar_numero_cnj
from lupa.dominio.enums import (
    CenarioArquivo,
    EstadoJob,
    EstadoLote,
    FlagPagina,
    Materia,
    MetodoClassificacao,
    MotivoFalha,
    MotivoQuarentena,
    OrigemPeca,
    PapelUsuario,
    ResultadoAchado,
    StatusFato,
    StatusProcesso,
    TipoFato,
    TipoPagina,
    TipoPeca,
)

NumeroCnj = Annotated[str, AfterValidator(validar_numero_cnj)]
Confianca = Annotated[float, Field(ge=0.0, le=1.0)]


def _agora() -> datetime:
    return datetime.now(UTC)


def calcular_hash(texto: str) -> str:
    """Calcula o SHA-256 hexadecimal de um texto em UTF-8.

    Args:
        texto: Texto de entrada.

    Returns:
        Hash hexadecimal com 64 caracteres.
    """
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class EsquemaBase(BaseModel):
    """Base dos esquemas: imutáveis e sem campos extras."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Gabinete(EsquemaBase):
    """Gabinete (tenant)."""

    id: UUID = Field(default_factory=uuid4)
    nome: str = Field(min_length=1)
    chave_criptografia_ref: str | None = None
    criado_em: datetime = Field(default_factory=_agora)


class Processo(EsquemaBase):
    """Processo judicial cadastrado em um gabinete."""

    id: UUID = Field(default_factory=uuid4)
    gabinete_id: UUID
    numero_cnj: NumeroCnj
    classe: str = Field(min_length=1)
    materia: Materia
    sigiloso: bool
    status: StatusProcesso = StatusProcesso.CRIADO
    criado_em: datetime = Field(default_factory=_agora)
    criado_por: UUID


class Arquivo(EsquemaBase):
    """Arquivo enviado (PDF dos autos); imutável."""

    id: UUID = Field(default_factory=uuid4)
    processo_id: UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tamanho_bytes: int = Field(gt=0)
    nome_original: str = Field(min_length=1)
    mime: str = Field(min_length=1)
    chave_storage: str = Field(min_length=1)
    enviado_por: UUID
    enviado_em: datetime = Field(default_factory=_agora)


class Peca(EsquemaBase):
    """Peça processual identificada dentro de um arquivo."""

    id: UUID = Field(default_factory=uuid4)
    arquivo_id: UUID
    tipo: TipoPeca
    pagina_inicial: int = Field(ge=1)
    pagina_final: int = Field(ge=1)
    confianca: Confianca
    metodo: MetodoClassificacao
    origem: OrigemPeca
    data: date | None = None
    tipo_data: str | None = None
    data_evidencia_id: UUID | None = None
    substitui_peca_id: UUID | None = None
    vigente: bool = True
    flags: dict[str, Any] = Field(default_factory=dict)
    classificacao: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _paginas_em_ordem(self) -> Self:
        if self.pagina_final < self.pagina_inicial:
            raise ValueError("pagina_final deve ser maior ou igual a pagina_inicial")
        return self


class Pagina(EsquemaBase):
    """Página de um arquivo com seu texto e marcadores de ingestão."""

    id: UUID = Field(default_factory=uuid4)
    arquivo_id: UUID
    numero: int = Field(ge=1)
    tipo: TipoPagina
    texto: str
    hash_texto: str = ""
    flags: dict[FlagPagina, bool] = Field(default_factory=dict)
    sinais: dict[str, Any] = Field(default_factory=dict)
    coordenadas: dict[str, Any] = Field(default_factory=dict)
    texto_nativo: str | None = None
    texto_ocr: str | None = None
    versao_extrator: str | None = None
    texto_normalizado: str | None = None
    trechos_ocultos: list[dict[str, Any]] = Field(default_factory=list)
    trechos_suspeitos: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _hash_confere(self) -> Self:
        esperado = calcular_hash(self.texto)
        if not self.hash_texto:
            object.__setattr__(self, "hash_texto", esperado)
        elif self.hash_texto != esperado:
            raise ValueError("hash_texto não corresponde a sha256(texto)")
        return self


class Evidencia(EsquemaBase):
    """Trecho de página que sustenta um fato; `hash_trecho` é calculado se omitido."""

    id: UUID = Field(default_factory=uuid4)
    pagina_id: UUID
    trecho: str = Field(min_length=1)
    hash_trecho: str = ""
    inicio: int = Field(ge=0)
    fim: int = Field(ge=1)
    bbox: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _consistente(self) -> Self:
        if self.fim <= self.inicio:
            raise ValueError("fim deve ser maior que inicio")
        esperado = calcular_hash(self.trecho)
        if not self.hash_trecho:
            object.__setattr__(self, "hash_trecho", esperado)
        elif self.hash_trecho != esperado:
            raise ValueError("hash_trecho não corresponde a sha256(trecho)")
        return self


class Fato(EsquemaBase):
    """Fato extraído dos autos; não existe sem ao menos uma evidência."""

    id: UUID = Field(default_factory=uuid4)
    processo_id: UUID
    tipo: TipoFato
    valor: Any
    evidencias: tuple[Evidencia, ...] = Field(min_length=1)
    extraido_por: str = Field(min_length=1)
    versao_extrator: str = Field(min_length=1)
    confianca: Confianca
    status: StatusFato = StatusFato.AUTOMATICO
    substitui_fato_id: UUID | None = None
    criado_em: datetime = Field(default_factory=_agora)


class Reu(EsquemaBase):
    """Réu identificado apenas por pseudônimo."""

    id: UUID = Field(default_factory=uuid4)
    processo_id: UUID
    pseudonimo: str = Field(min_length=1)


class ReuIdentidade(EsquemaBase):
    """Identidade real do réu; acesso só pela camada de apresentação."""

    reu_id: UUID
    nome: str = Field(min_length=1)
    documento: str | None = None


class Achado(EsquemaBase):
    """Resultado de uma validação, gerado só pelo motor; imutável."""

    id: UUID = Field(default_factory=uuid4)
    processo_id: UUID
    validacao: str = Field(min_length=1)
    versao_catalogo: str = Field(min_length=1)
    resultado: ResultadoAchado
    fatos_usados: tuple[UUID, ...] = ()
    valores: dict[str, Any] = Field(default_factory=dict)
    explicacao: str
    criado_em: datetime = Field(default_factory=_agora)


class Anotacao(EsquemaBase):
    """Nota de usuário sobre um achado ou um fato; não altera nenhum dos dois."""

    id: UUID = Field(default_factory=uuid4)
    achado_id: UUID | None = None
    fato_id: UUID | None = None
    usuario_id: UUID
    texto: str = Field(min_length=1)
    criado_em: datetime = Field(default_factory=_agora)

    @model_validator(mode="after")
    def _um_alvo(self) -> Self:
        if (self.achado_id is None) == (self.fato_id is None):
            raise ValueError("informe exatamente um entre achado_id e fato_id")
        return self


class Usuario(EsquemaBase):
    """Usuário do sistema (detalhado na Etapa 3)."""

    id: UUID = Field(default_factory=uuid4)
    gabinete_id: UUID | None
    nome_usuario: str = Field(min_length=1)
    papel: PapelUsuario
    senha_hash: str = Field(min_length=1, repr=False)
    mfa_segredo: str | None = Field(default=None, repr=False)
    mfa_confirmado: bool = False
    ativo: bool = True
    troca_senha_obrigatoria: bool = True
    criado_em: datetime = Field(default_factory=_agora)

    @model_validator(mode="after")
    def _gabinete_conforme_papel(self) -> Self:
        if (self.papel is PapelUsuario.ADMINISTRADOR) != (self.gabinete_id is None):
            raise ValueError("apenas o administrador não tem gabinete")
        return self


class EventoAuditoria(EsquemaBase):
    """Evento da trilha de auditoria encadeada por hash (ver `lupa.auditoria`)."""

    id: UUID = Field(default_factory=uuid4)
    ocorrido_em: datetime = Field(default_factory=_agora)
    usuario_id: UUID | None
    gabinete_id: UUID | None
    processo_id: UUID | None = None
    acao: str = Field(min_length=1)
    objeto_tipo: str | None = None
    objeto_id: str | None = None
    ip: str | None = None
    localizacao: str | None = None
    resultado: str = Field(min_length=1)
    versao_modelo: str | None = None
    versao_prompt: str | None = None
    hash_anterior: str | None = None
    hash_evento: str = Field(min_length=1)
    sequencia: int = Field(default=1, ge=1)


class EntradaManifesto(EsquemaBase):
    """Entrada do manifesto de um arquivo (uma por PDF; um ZIP tem várias).

    Attributes:
        ordem: Posição na ordem por nome, a partir de 1.
        nome: Nome da entrada (para PDF avulso, o nome original).
        tamanho_bytes: Tamanho descomprimido.
        sha256: Hash do conteúdo.
    """

    ordem: int = Field(ge=1)
    nome: str = Field(min_length=1)
    tamanho_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class JobIngestao(EsquemaBase):
    """Job de ingestão de um arquivo; as transições de estado ficam em `lupa.ingestao.estados`."""

    id: UUID = Field(default_factory=uuid4)
    processo_id: UUID
    arquivo_id: UUID
    estado: EstadoJob = EstadoJob.RECEBIDO
    motivo_quarentena: MotivoQuarentena | None = None
    motivo_falha: MotivoFalha | None = None
    tentativas: int = Field(default=0, ge=0)
    fencing_token: int = Field(default=0, ge=0)
    total_paginas: int | None = Field(default=None, ge=0)
    manifesto: tuple[EntradaManifesto, ...] | None = None
    criado_em: datetime = Field(default_factory=_agora)

    @model_validator(mode="after")
    def _motivo_conforme_estado(self) -> Self:
        if (self.estado is EstadoJob.QUARENTENA) != (self.motivo_quarentena is not None):
            raise ValueError("motivo_quarentena é obrigatório só no estado quarentena")
        return self


class LoteIngestao(EsquemaBase):
    """Resultado de um lote de trabalho do job, gravado uma única vez por `(job_id, numero)`."""

    id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    numero: int = Field(ge=1)
    estado: EstadoLote
    fencing_token: int = Field(ge=1)
    resultado: dict[str, Any] = Field(default_factory=dict)


class DiagnosticoArquivo(EsquemaBase):
    """Diagnóstico do arquivo: cenário de empacotamento e sinais medidos."""

    id: UUID = Field(default_factory=uuid4)
    arquivo_id: UUID
    cenario: CenarioArquivo
    total_paginas: int = Field(ge=0)
    tem_indice: bool
    sinais: dict[str, Any] = Field(default_factory=dict)
    fronteiras_origem: list[dict[str, Any]] = Field(default_factory=list)
    metadados_descartados: list[dict[str, Any]] = Field(default_factory=list)
    criado_em: datetime = Field(default_factory=_agora)
