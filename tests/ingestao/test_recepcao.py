"""Testes da recepção em streaming e do lacre."""

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lupa.dominio.tabelas import ArquivoTabela, JobIngestaoTabela
from lupa.ingestao.recepcao import (
    ArquivoRecebido,
    MotivoRecusa,
    RecepcaoRecusadaError,
    ResultadoLacre,
    TipoArquivo,
    detectar_tipo,
    extensao_confere,
    lacrar,
    receber,
)
from lupa.ingestao.storage import ArmazenamentoMemoria
from tests.ingestao.arquivos import pdf_minimo, zip_por_peca
from tests.ingestao.conftest import ProcessoSemeado, semear_processo


async def _blocos(dados: bytes, tamanho: int = 7) -> AsyncIterator[bytes]:
    for inicio in range(0, len(dados), tamanho):
        yield dados[inicio : inicio + tamanho]


def _lacrar(
    session: Session,
    storage: ArmazenamentoMemoria,
    recebido: ArquivoRecebido,
    processo: ProcessoSemeado,
) -> ResultadoLacre:
    return lacrar(
        session,
        storage,
        recebido,
        gabinete_id=processo.gabinete_id,
        processo_id=processo.processo_id,
        enviado_por=processo.usuario_id,
        nome_original="autos.pdf",
    )


def test_tipo_pelo_conteudo() -> None:
    """Bytes mágicos decidem o tipo."""
    assert detectar_tipo(b"%PDF-1.7") is TipoArquivo.PDF
    assert detectar_tipo(b"PK\x03\x04rest") is TipoArquivo.ZIP
    assert detectar_tipo(b"MZ\x90\x00") is None
    assert detectar_tipo(b"PK\x05\x06") is None


def test_extensao_conhecida_que_contradiz_o_conteudo() -> None:
    """`.pdf` com ZIP dentro é recusado; extensão desconhecida não decide nada."""
    assert extensao_confere("autos.PDF", TipoArquivo.PDF)
    assert not extensao_confere("autos.pdf", TipoArquivo.ZIP)
    assert extensao_confere("autos.bin", TipoArquivo.ZIP)


async def test_recebe_em_blocos_com_hash_tamanho_e_tipo(tmp_path: Path) -> None:
    """Hash calculado no streaming é igual ao hash do conteúdo inteiro."""
    dados = pdf_minimo(2)
    recebido = await receber(_blocos(dados), "autos.pdf", 10_000_000, tmp_path)
    assert recebido.sha256 == hashlib.sha256(dados).hexdigest()
    assert (recebido.tamanho_bytes, recebido.tipo) == (len(dados), TipoArquivo.PDF)
    assert recebido.caminho.read_bytes() == dados


@pytest.mark.parametrize(
    ("dados", "nome", "limite", "motivo"),
    [
        (b"MZ" + b"\x00" * 100, "autos.pdf", 10_000, MotivoRecusa.TIPO),
        (zip_por_peca(1), "autos.pdf", 10_000_000, MotivoRecusa.TIPO),
        (b"", "autos.pdf", 10_000, MotivoRecusa.VAZIO),
        (pdf_minimo(), "autos.pdf", 100, MotivoRecusa.TAMANHO),
    ],
    ids=["extensao_falsa", "zip_com_nome_de_pdf", "vazio", "grande"],
)
async def test_recusas_apagam_o_temporario(
    tmp_path: Path, dados: bytes, nome: str, limite: int, motivo: MotivoRecusa
) -> None:
    """Toda recusa tem motivo e não deixa arquivo para trás."""
    with pytest.raises(RecepcaoRecusadaError) as erro:
        await receber(_blocos(dados), nome, limite, tmp_path)
    assert erro.value.motivo is motivo
    assert list(tmp_path.iterdir()) == []


@pytest.mark.integracao
async def test_mesmo_arquivo_duas_vezes_nao_duplica(engine_teste: Engine, tmp_path: Path) -> None:
    """Segundo lacre do mesmo conteúdo devolve o arquivo e o job existentes."""
    processo = semear_processo(engine_teste)
    storage = ArmazenamentoMemoria()
    resultados = []
    for _ in range(2):
        recebido = await receber(_blocos(pdf_minimo()), "autos.pdf", 10_000_000, tmp_path)
        with Session(engine_teste) as session, session.begin():
            resultados.append(
                lacrar(
                    session,
                    storage,
                    recebido,
                    gabinete_id=processo.gabinete_id,
                    processo_id=processo.processo_id,
                    enviado_por=processo.usuario_id,
                    nome_original="autos.pdf",
                )
            )
    primeiro, segundo = resultados
    assert (primeiro.duplicado, segundo.duplicado) == (False, True)
    assert (primeiro.arquivo_id, primeiro.job_id) == (segundo.arquivo_id, segundo.job_id)
    assert len(storage.listar(f"gabinete/{processo.gabinete_id}/")) == 1
    with Session(engine_teste) as session:
        filtro = ArquivoTabela.processo_id == processo.processo_id
        assert session.scalar(select(func.count()).where(filtro)) == 1
        jobs = select(func.count()).where(JobIngestaoTabela.processo_id == processo.processo_id)
        assert session.scalar(jobs) == 1


@pytest.mark.integracao
async def test_corrida_no_lacre_devolve_o_arquivo_do_concorrente(
    engine_teste: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se outro envio gravou o mesmo hash entre a consulta e o insert, o resultado é o dele."""
    from lupa.ingestao import recepcao

    processo = semear_processo(engine_teste)
    storage = ArmazenamentoMemoria()
    recebido = await receber(_blocos(pdf_minimo()), "autos.pdf", 10_000_000, tmp_path)
    with Session(engine_teste) as session, session.begin():
        primeiro = _lacrar(session, storage, recebido, processo)
    real = recepcao._existente
    chamadas: list[int] = []

    def _cego_na_primeira(*args: object) -> object:
        chamadas.append(1)
        return None if len(chamadas) == 1 else real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(recepcao, "_existente", _cego_na_primeira)
    with Session(engine_teste) as session, session.begin():
        segundo = _lacrar(session, storage, recebido, processo)
    assert segundo.duplicado
    assert segundo.arquivo_id == primeiro.arquivo_id
