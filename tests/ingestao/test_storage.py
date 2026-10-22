"""Teste de contrato do object storage, rodado nas implementações em memória e S3 (MinIO)."""

import io
import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from pydantic import SecretStr

from lupa.config import Settings
from lupa.ingestao.storage import (
    ArmazenamentoMemoria,
    ArmazenamentoS3,
    ObjectStorage,
    ObjetoAusenteError,
    chave_objeto,
    criar_cliente_s3,
    criar_storage,
)


def _settings_s3() -> Settings | None:
    if not os.environ.get("LUPA_MINIO_ENDPOINT") or not os.environ.get("LUPA_DATABASE_URL"):
        return None
    return Settings()


def _storage_s3() -> ArmazenamentoS3:
    settings = _settings_s3()
    if settings is None:
        pytest.skip("MinIO não configurado")
    cliente = criar_cliente_s3(settings)
    try:
        cliente.head_bucket(Bucket=settings.minio_bucket)
    except Exception:
        pytest.skip("MinIO inacessível")
    return ArmazenamentoS3(cliente, settings.minio_bucket)


@pytest.fixture(
    params=[
        pytest.param("memoria"),
        pytest.param("s3", marks=pytest.mark.integracao),
    ]
)
def storage(request: pytest.FixtureRequest) -> Iterator[tuple[ObjectStorage, str]]:
    """Implementação sob teste e um prefixo exclusivo; apaga o que o teste gravou."""
    implementacao: ObjectStorage = (
        ArmazenamentoMemoria() if request.param == "memoria" else _storage_s3()
    )
    prefixo = f"teste-contrato/{uuid4()}/"
    yield implementacao, prefixo
    for chave in implementacao.listar(prefixo):
        implementacao.apagar(chave)


def test_gravar_ler_existe_listar_apagar(storage: tuple[ObjectStorage, str]) -> None:
    """Ciclo completo do contrato."""
    implementacao, prefixo = storage
    chave_a, chave_b = f"{prefixo}b", f"{prefixo}a"
    assert not implementacao.existe(chave_a)
    implementacao.gravar(chave_a, io.BytesIO(b"conteudo-sintetico-1"))
    implementacao.gravar(chave_b, io.BytesIO(b"conteudo-sintetico-2"))
    assert implementacao.existe(chave_a)
    assert implementacao.ler(chave_a) == b"conteudo-sintetico-1"
    assert implementacao.listar(prefixo) == [chave_b, chave_a]
    implementacao.apagar(chave_a)
    implementacao.apagar(chave_a)
    assert not implementacao.existe(chave_a)
    assert implementacao.listar(prefixo) == [chave_b]


def test_ler_chave_ausente_lanca_erro_proprio(storage: tuple[ObjectStorage, str]) -> None:
    """Ausência vira `ObjetoAusenteError`, não erro do cliente."""
    implementacao, prefixo = storage
    with pytest.raises(ObjetoAusenteError):
        implementacao.ler(f"{prefixo}inexistente")


def test_gravar_de_novo_substitui(storage: tuple[ObjectStorage, str]) -> None:
    """A mesma chave regravada tem o conteúdo novo e continua sendo um objeto só."""
    implementacao, prefixo = storage
    chave = f"{prefixo}x"
    implementacao.gravar(chave, io.BytesIO(b"1"))
    implementacao.gravar(chave, io.BytesIO(b"2"))
    assert implementacao.ler(chave) == b"2"
    assert implementacao.listar(prefixo) == [chave]


def test_chave_por_gabinete_processo_e_hash() -> None:
    """Formato da chave."""
    gabinete, processo = uuid4(), uuid4()
    assert chave_objeto(gabinete, processo, "f" * 64) == (
        f"gabinete/{gabinete}/processo/{processo}/{'f' * 64}"
    )


def test_implementacao_escolhida_pela_configuracao(settings_ficticias: Settings) -> None:
    """`storage_backend` troca a implementação sem mudar quem usa."""
    memoria = settings_ficticias.model_copy(update={"storage_backend": "memoria"})
    assert isinstance(getattr(criar_storage(memoria), "interno", None), ArmazenamentoMemoria)
    s3 = settings_ficticias.model_copy(
        update={"storage_backend": "s3", "minio_secure": True, "minio_secret_key": SecretStr("x")}
    )
    assert isinstance(getattr(criar_storage(s3), "interno", None), ArmazenamentoS3)


class _ErroCliente:
    """Cliente S3 falso que responde erro diferente de ausência."""

    def head_object(self, **_kwargs: object) -> None:
        from botocore.exceptions import ClientError

        raise ClientError({"Error": {"Code": "403"}}, "HeadObject")

    def download_fileobj(self, *_args: object) -> None:
        self.head_object()


def test_erros_do_s3_que_nao_sao_ausencia_propagam() -> None:
    """Permissão negada não é confundida com objeto ausente."""
    from botocore.exceptions import ClientError

    armazenamento = ArmazenamentoS3(_ErroCliente(), "bucket")
    with pytest.raises(ClientError):
        armazenamento.existe("x")
    with pytest.raises(ClientError):
        armazenamento.ler("x")
