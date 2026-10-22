r"""Recepção e lacre: streaming com SHA-256, limite de tamanho, tipo pelo conteúdo e gravação.

O corpo chega em blocos e vai direto para um arquivo temporário, com o hash calculado no
caminho; nada é mantido inteiro em memória. O tipo é decidido pelos bytes mágicos (`%PDF-` ou
`PK\\x03\\x04`), nunca pelo nome; extensão `.pdf`/`.zip` que contradiz o conteúdo é recusada.
O objeto é gravado no storage pela chave do hash e o mesmo conteúdo no mesmo processo não gera
segundo `arquivo` nem segundo job.
"""

import hashlib
import os
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lupa.dominio.tabelas import ArquivoTabela, JobIngestaoTabela
from lupa.ingestao import repositorio
from lupa.ingestao.storage import ObjectStorage, chave_objeto

TAMANHO_CABECALHO = 8


class TipoArquivo(StrEnum):
    """Tipos aceitos, com o MIME gravado em `arquivo.mime`."""

    PDF = "application/pdf"
    ZIP = "application/zip"


MAGICOS = {b"%PDF-": TipoArquivo.PDF, b"PK\x03\x04": TipoArquivo.ZIP}
EXTENSOES = {".pdf": TipoArquivo.PDF, ".zip": TipoArquivo.ZIP}


class MotivoRecusa(StrEnum):
    """Motivo de recusa na recepção."""

    TAMANHO = "tamanho"
    VAZIO = "vazio"
    TIPO = "tipo"


class RecepcaoRecusadaError(ValueError):
    """Arquivo recusado na recepção (antes de qualquer gravação)."""

    def __init__(self, motivo: MotivoRecusa) -> None:
        """Cria o erro.

        Args:
            motivo: Motivo da recusa.
        """
        super().__init__(motivo.value)
        self.motivo = motivo


@dataclass(frozen=True)
class ArquivoRecebido:
    """Arquivo recebido e conferido, ainda só no disco temporário.

    Attributes:
        caminho: Arquivo temporário (apagar depois de lacrar).
        sha256: Hash do conteúdo.
        tamanho_bytes: Tamanho.
        tipo: Tipo detectado pelo conteúdo.
    """

    caminho: Path
    sha256: str
    tamanho_bytes: int
    tipo: TipoArquivo


@dataclass(frozen=True)
class ResultadoLacre:
    """Resultado do lacre.

    Attributes:
        arquivo_id: Arquivo (novo ou já existente).
        job_id: Job do arquivo.
        estado: Estado corrente do job.
        duplicado: Verdadeiro se o conteúdo já existia no processo.
    """

    arquivo_id: UUID
    job_id: UUID
    estado: str
    duplicado: bool


def detectar_tipo(cabecalho: bytes) -> TipoArquivo | None:
    """Detecta o tipo pelos primeiros bytes.

    Args:
        cabecalho: Início do arquivo.

    Returns:
        O tipo, ou None se não for PDF nem ZIP.
    """
    for magico, tipo in MAGICOS.items():
        if cabecalho.startswith(magico):
            return tipo
    return None


def extensao_confere(nome: str, tipo: TipoArquivo) -> bool:
    """Confere se a extensão, quando é `.pdf` ou `.zip`, coincide com o conteúdo.

    Args:
        nome: Nome original.
        tipo: Tipo detectado.

    Returns:
        Falso só quando a extensão conhecida contradiz o conteúdo.
    """
    esperado = EXTENSOES.get(Path(nome).suffix.lower())
    return esperado is None or esperado is tipo


async def receber(
    blocos: AsyncIterator[bytes], nome: str, limite_bytes: int, diretorio: Path | None
) -> ArquivoRecebido:
    """Grava o corpo em arquivo temporário calculando hash, tamanho e tipo.

    Args:
        blocos: Corpo da requisição em blocos.
        nome: Nome original (só para conferir a extensão).
        limite_bytes: Tamanho máximo aceito.
        diretorio: Diretório dos temporários (None = padrão do sistema).

    Returns:
        O arquivo recebido.

    Raises:
        RecepcaoRecusadaError: Vazio, acima do limite ou tipo inválido (o temporário é apagado).
    """
    resumo = hashlib.sha256()
    tamanho = 0
    cabecalho = b""
    descritor, nome_temporario = tempfile.mkstemp(prefix="lupa-upload-", dir=diretorio)
    destino = Path(nome_temporario)
    try:
        with os.fdopen(descritor, "wb") as saida:
            async for bloco in blocos:
                tamanho += len(bloco)
                if tamanho > limite_bytes:
                    raise RecepcaoRecusadaError(MotivoRecusa.TAMANHO)
                if len(cabecalho) < TAMANHO_CABECALHO:
                    cabecalho += bloco[: TAMANHO_CABECALHO - len(cabecalho)]
                resumo.update(bloco)
                saida.write(bloco)
        return _conferir(destino, resumo.hexdigest(), tamanho, cabecalho, nome)
    except BaseException:
        destino.unlink(missing_ok=True)
        raise


def _conferir(
    caminho: Path, sha256: str, tamanho: int, cabecalho: bytes, nome: str
) -> ArquivoRecebido:
    if tamanho == 0:
        raise RecepcaoRecusadaError(MotivoRecusa.VAZIO)
    tipo = detectar_tipo(cabecalho)
    if tipo is None or not extensao_confere(nome, tipo):
        raise RecepcaoRecusadaError(MotivoRecusa.TIPO)
    return ArquivoRecebido(caminho, sha256, tamanho, tipo)


def _existente(session: Session, processo_id: UUID, sha256: str) -> ResultadoLacre | None:
    linha = session.execute(
        select(ArquivoTabela.id, JobIngestaoTabela.id, JobIngestaoTabela.estado)
        .join(JobIngestaoTabela, JobIngestaoTabela.arquivo_id == ArquivoTabela.id)
        .where(ArquivoTabela.processo_id == processo_id, ArquivoTabela.sha256 == sha256)
    ).first()
    if linha is None:
        return None
    return ResultadoLacre(linha[0], linha[1], linha[2], duplicado=True)


def _gravar_objeto(storage: ObjectStorage, chave: str, recebido: ArquivoRecebido) -> None:
    if storage.existe(chave):
        return
    with recebido.caminho.open("rb") as origem:
        storage.gravar(chave, origem)


def lacrar(
    session: Session,
    storage: ObjectStorage,
    recebido: ArquivoRecebido,
    *,
    gabinete_id: UUID,
    processo_id: UUID,
    enviado_por: UUID,
    nome_original: str,
) -> ResultadoLacre:
    """Grava o objeto no storage, registra `arquivo` e cria o job em `recebido`.

    Args:
        session: Sessão da requisição (contexto de RLS já definido).
        storage: Object storage.
        recebido: Arquivo conferido.
        gabinete_id: Gabinete do processo.
        processo_id: Processo.
        enviado_por: Usuário que enviou.
        nome_original: Nome informado pelo cliente.

    Returns:
        Arquivo e job (novos, ou os existentes quando o conteúdo é repetido).
    """
    existente = _existente(session, processo_id, recebido.sha256)
    if existente is not None:
        return existente
    chave = chave_objeto(gabinete_id, processo_id, recebido.sha256)
    _gravar_objeto(storage, chave, recebido)
    arquivo_id = uuid4()
    try:
        with session.begin_nested():
            session.add(
                ArquivoTabela(
                    id=arquivo_id,
                    gabinete_id=gabinete_id,
                    processo_id=processo_id,
                    sha256=recebido.sha256,
                    tamanho_bytes=recebido.tamanho_bytes,
                    nome_original=nome_original,
                    mime=recebido.tipo.value,
                    chave_storage=chave,
                    enviado_por=enviado_por,
                )
            )
            session.flush()
            job = repositorio.criar_job(session, gabinete_id, processo_id, arquivo_id)
    except IntegrityError:
        concorrente = _existente(session, processo_id, recebido.sha256)
        if concorrente is None:
            raise
        return concorrente
    return ResultadoLacre(arquivo_id, job.id, job.estado, duplicado=False)
