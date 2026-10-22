"""Object storage com interface própria: S3 (MinIO no piloto) e memória (testes).

A implementação é escolhida por configuração (`LUPA_STORAGE_BACKEND`). As chaves seguem
`gabinete/<id>/processo/<id>/<sha256>`, de modo que o conteúdo é endereçado pelo hash e
gravar o mesmo arquivo duas vezes não cria um segundo objeto.

Etapa 7.4: `criar_storage` devolve o storage embrulhado em `StorageCifrado`, que cifra cada
objeto em stream com a DEK do processo (tirado da chave `.../processo/<id>/...`) e decifra na
leitura. O que está no MinIO nunca é o PDF em claro; o `sha256` da chave continua o do claro.
"""

import io
import re
from typing import Any, BinaryIO, Protocol
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from lupa.config import Settings
from lupa.logging import get_logger
from lupa.seguranca.contexto import dek_de
from lupa.seguranca.envelope import LeitorCifrado, decifrar_objeto, objeto_cifrado

CODIGOS_AUSENTE = frozenset({"404", "NoSuchKey", "NotFound"})
PROCESSO_NA_CHAVE = re.compile(r"(?:^|/)processo/([0-9a-fA-F-]{36})/")


class ObjetoAusenteError(LookupError):
    """O objeto pedido não existe no storage."""


def chave_objeto(gabinete_id: UUID, processo_id: UUID, sha256: str) -> str:
    """Monta a chave do objeto de um arquivo.

    Args:
        gabinete_id: Gabinete dono.
        processo_id: Processo dono.
        sha256: Hash do conteúdo.

    Returns:
        `gabinete/<id>/processo/<id>/<sha256>`.
    """
    return f"gabinete/{gabinete_id}/processo/{processo_id}/{sha256}"


class ObjectStorage(Protocol):
    """Contrato do object storage usado pela ingestão."""

    def gravar(self, chave: str, origem: BinaryIO) -> None:
        """Grava o conteúdo lido de `origem` (até o fim) na chave."""

    def ler(self, chave: str) -> bytes:
        """Lê o objeto inteiro; lança `ObjetoAusenteError` se não existir."""

    def existe(self, chave: str) -> bool:
        """Diz se a chave existe."""

    def apagar(self, chave: str) -> None:
        """Apaga a chave (sem erro se não existir)."""

    def listar(self, prefixo: str) -> list[str]:
        """Lista, em ordem, as chaves que começam com o prefixo."""


class ArmazenamentoMemoria:
    """Storage em memória, para testes e desenvolvimento."""

    def __init__(self) -> None:
        """Cria o storage vazio."""
        self._objetos: dict[str, bytes] = {}

    def gravar(self, chave: str, origem: BinaryIO) -> None:
        """Grava o conteúdo.

        Args:
            chave: Chave do objeto.
            origem: Arquivo binário lido até o fim.
        """
        self._objetos[chave] = origem.read()

    def ler(self, chave: str) -> bytes:
        """Lê o objeto.

        Args:
            chave: Chave do objeto.

        Returns:
            Conteúdo.

        Raises:
            ObjetoAusenteError: Se a chave não existir.
        """
        try:
            return self._objetos[chave]
        except KeyError:
            raise ObjetoAusenteError(chave) from None

    def existe(self, chave: str) -> bool:
        """Diz se a chave existe.

        Args:
            chave: Chave do objeto.

        Returns:
            Verdadeiro se existir.
        """
        return chave in self._objetos

    def apagar(self, chave: str) -> None:
        """Apaga a chave.

        Args:
            chave: Chave do objeto.
        """
        self._objetos.pop(chave, None)

    def listar(self, prefixo: str) -> list[str]:
        """Lista chaves pelo prefixo.

        Args:
            prefixo: Prefixo.

        Returns:
            Chaves em ordem.
        """
        return sorted(chave for chave in self._objetos if chave.startswith(prefixo))


class ArmazenamentoS3:
    """Storage S3 via boto3; no piloto aponta para o MinIO (troca de endpoint para a AWS)."""

    def __init__(self, cliente: Any, bucket: str) -> None:
        """Cria o adaptador.

        Args:
            cliente: Cliente `boto3` de S3.
            bucket: Bucket dos autos.
        """
        self._cliente = cliente
        self._bucket = bucket

    def gravar(self, chave: str, origem: BinaryIO) -> None:
        """Grava o conteúdo em streaming (multipart quando grande).

        Args:
            chave: Chave do objeto.
            origem: Arquivo binário lido até o fim.
        """
        self._cliente.upload_fileobj(origem, self._bucket, chave)

    def ler(self, chave: str) -> bytes:
        """Lê o objeto.

        Args:
            chave: Chave do objeto.

        Returns:
            Conteúdo.

        Raises:
            ObjetoAusenteError: Se a chave não existir.
        """
        destino = io.BytesIO()
        try:
            self._cliente.download_fileobj(self._bucket, chave, destino)
        except ClientError as erro:
            if _ausente(erro):
                raise ObjetoAusenteError(chave) from None
            raise
        return destino.getvalue()

    def existe(self, chave: str) -> bool:
        """Diz se a chave existe.

        Args:
            chave: Chave do objeto.

        Returns:
            Verdadeiro se existir.
        """
        try:
            self._cliente.head_object(Bucket=self._bucket, Key=chave)
        except ClientError as erro:
            if _ausente(erro):
                return False
            raise
        return True

    def apagar(self, chave: str) -> None:
        """Apaga a chave.

        Args:
            chave: Chave do objeto.
        """
        self._cliente.delete_object(Bucket=self._bucket, Key=chave)

    def listar(self, prefixo: str) -> list[str]:
        """Lista chaves pelo prefixo, percorrendo todas as páginas.

        Args:
            prefixo: Prefixo.

        Returns:
            Chaves em ordem.
        """
        paginador = self._cliente.get_paginator("list_objects_v2")
        chaves = [
            objeto["Key"]
            for pagina in paginador.paginate(Bucket=self._bucket, Prefix=prefixo)
            for objeto in pagina.get("Contents", [])
        ]
        return sorted(chaves)


class ChaveSemProcessoError(ValueError):
    """A chave do objeto não identifica o processo (não há DEK para cifrar)."""


def processo_da_chave(chave: str) -> UUID:
    """Processo dono do objeto, pela chave.

    Args:
        chave: Chave do objeto (`.../processo/<id>/...`).

    Returns:
        Id do processo.

    Raises:
        ChaveSemProcessoError: Chave sem segmento `processo/<id>/`.
    """
    achado = PROCESSO_NA_CHAVE.search(chave)
    if achado is None:
        raise ChaveSemProcessoError("chave sem processo")
    return UUID(achado.group(1))


class StorageCifrado:
    """Embrulho que cifra em stream na gravação e decifra na leitura (Etapa 7.4)."""

    def __init__(self, interno: ObjectStorage) -> None:
        """Cria o embrulho.

        Args:
            interno: Storage real (S3 ou memória).
        """
        self.interno = interno

    def gravar(self, chave: str, origem: BinaryIO) -> None:
        """Cifra `origem` em blocos com a DEK do processo e grava.

        Args:
            chave: Chave do objeto.
            origem: Conteúdo em claro.
        """
        dek = dek_de(processo_da_chave(chave))
        self.interno.gravar(chave, io.BufferedReader(LeitorCifrado(dek, origem)))

    def ler(self, chave: str) -> bytes:
        """Lê e decifra.

        Args:
            chave: Chave do objeto.

        Returns:
            Conteúdo em claro.
        """
        dados = self.interno.ler(chave)
        if not objeto_cifrado(dados):
            get_logger(__name__).warning("objeto_legado_em_claro")
            return dados
        return decifrar_objeto(dek_de(processo_da_chave(chave)), dados)

    def existe(self, chave: str) -> bool:
        """Diz se a chave existe.

        Args:
            chave: Chave do objeto.

        Returns:
            Verdadeiro se existir.
        """
        return self.interno.existe(chave)

    def apagar(self, chave: str) -> None:
        """Apaga a chave.

        Args:
            chave: Chave do objeto.
        """
        self.interno.apagar(chave)

    def listar(self, prefixo: str) -> list[str]:
        """Lista chaves pelo prefixo.

        Args:
            prefixo: Prefixo.

        Returns:
            Chaves em ordem.
        """
        return self.interno.listar(prefixo)


def _ausente(erro: ClientError) -> bool:
    return str(erro.response.get("Error", {}).get("Code")) in CODIGOS_AUSENTE


def criar_cliente_s3(settings: Settings) -> Any:
    """Cria o cliente boto3 para o endpoint configurado.

    Args:
        settings: Configuração (endpoint, chaves, TLS).

    Returns:
        Cliente S3.
    """
    esquema = "https" if settings.minio_secure else "http"
    return boto3.client(
        "s3",
        endpoint_url=f"{esquema}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key.get_secret_value(),
        aws_secret_access_key=settings.minio_secret_key.get_secret_value(),
        region_name=settings.storage_regiao,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def criar_storage(settings: Settings) -> ObjectStorage:
    """Escolhe a implementação pelo `storage_backend` da configuração.

    Args:
        settings: Configuração.

    Returns:
        Storage S3 ou em memória, sempre embrulhado em `StorageCifrado`.
    """
    if settings.storage_backend == "memoria":
        return StorageCifrado(ArmazenamentoMemoria())
    return StorageCifrado(ArmazenamentoS3(criar_cliente_s3(settings), settings.minio_bucket))
