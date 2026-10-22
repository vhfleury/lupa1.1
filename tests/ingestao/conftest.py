"""Fixtures da ingestão: processo semeado, dependências do worker e arquivo lacrado."""

import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from lupa.dominio.enums import EstadoJob, Materia, PapelUsuario, StatusProcesso
from lupa.dominio.tabelas import GabineteTabela, ProcessoTabela, UsuarioTabela
from lupa.ingestao.extracao import LimitadorGabinete, Paralelismo
from lupa.ingestao.inventario import LimitesZip
from lupa.ingestao.recepcao import ArquivoRecebido, TipoArquivo, detectar_tipo, lacrar
from lupa.ingestao.sandbox import LimitesSandbox
from lupa.ingestao.storage import ArmazenamentoMemoria
from lupa.ingestao.worker import Dependencias, processar_job
from lupa.sinteticos.empacotamento import exportar
from lupa.sinteticos.gabarito import TODOS_VETORES, Cenario, Composicao, Gabarito
from lupa.sinteticos.gerador import gerar_conteudo
from lupa.sinteticos.roteiro import Configuracao
from tests.conftest import (
    UsuarioTeste,
    criar_gabinete_teste,
    criar_usuario_teste,
    gerar_numero_cnj,
)

MISTURA_4C = {
    Composicao.NATIVA: 0.4,
    Composicao.DIGITALIZADA: 0.3,
    Composicao.HIBRIDA_CORPO: 0.15,
    Composicao.HIBRIDA_ASSINATURA: 0.15,
}


@dataclass(frozen=True)
class ProcessoSemeado:
    """Processo sintético com gabinete e usuário.

    Attributes:
        gabinete_id: Gabinete.
        usuario_id: Usuário autor.
        processo_id: Processo.
    """

    gabinete_id: UUID
    usuario_id: UUID
    processo_id: UUID


@dataclass(frozen=True)
class JobSemeado:
    """Job criado por `lacrar` para um arquivo sintético.

    Attributes:
        processo: Processo dono.
        arquivo_id: Arquivo.
        job_id: Job.
    """

    processo: ProcessoSemeado
    arquivo_id: UUID
    job_id: UUID


class Relogio:
    """Relógio controlável."""

    def __init__(self) -> None:
        """Começa no instante atual."""
        self.agora = datetime.now(UTC)

    def __call__(self) -> datetime:
        """Instante corrente."""
        return self.agora

    def avancar(self, segundos: float) -> None:
        """Avança o relógio.

        Args:
            segundos: Quanto avançar.
        """
        self.agora += timedelta(seconds=segundos)


def semear_processo(engine: Engine, *, sigiloso: bool = False) -> ProcessoSemeado:
    """Cria gabinete, usuário e processo sintéticos com commit.

    Args:
        engine: Engine do banco de teste.
        sigiloso: Se o processo é sigiloso.

    Returns:
        Ids criados.
    """
    gabinete_id, usuario_id, processo_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        session.add(GabineteTabela(id=gabinete_id, nome=f"Gabinete {gabinete_id.hex[:6]}"))
        session.flush()
        session.add(
            UsuarioTabela(
                id=usuario_id,
                gabinete_id=gabinete_id,
                nome_usuario=f"semeado_{usuario_id.hex[:10]}",
                papel=PapelUsuario.ASSESSOR.value,
                senha_hash="hash-ficticio",
            )
        )
        session.flush()
        session.add(
            ProcessoTabela(
                id=processo_id,
                gabinete_id=gabinete_id,
                numero_cnj=gerar_numero_cnj(int(processo_id.int % 9_000_000) + 1),
                classe="Apelação Criminal",
                materia=Materia.CRIMINAL.value,
                sigiloso=sigiloso,
                status=StatusProcesso.CRIADO.value,
                criado_por=usuario_id,
            )
        )
    return ProcessoSemeado(gabinete_id, usuario_id, processo_id)


@pytest.fixture
def relogio() -> Relogio:
    """Relógio controlável."""
    return Relogio()


@pytest.fixture
def storage_memoria() -> ArmazenamentoMemoria:
    """Storage em memória."""
    return ArmazenamentoMemoria()


@pytest.fixture
def deps(
    fabrica_sessao: sessionmaker[Session],
    storage_memoria: ArmazenamentoMemoria,
    relogio: Relogio,
) -> Dependencias:
    """Dependências do worker da fundação (4A): param em `validado`, sem retentativa automática.

    Os testes da Etapa 4C usam `deps_extracao`, que liga a extração e a política de retry.
    """
    return Dependencias(
        fabrica=fabrica_sessao,
        storage=storage_memoria,
        limites_sandbox=LimitesSandbox(memoria_mb=512, cpu_segundos=20, tempo_segundos=30),
        limites_zip=LimitesZip(),
        duracao_lease=timedelta(seconds=60),
        max_tentativas=3,
        relogio=relogio,
        dono="worker-teste-a",
        extrair=False,
        max_retentativas=0,
    )


def outro_worker(deps: Dependencias, dono: str) -> Dependencias:
    """Copia as dependências com outro identificador de worker.

    Args:
        deps: Dependências de base.
        dono: Novo identificador.

    Returns:
        Dependências do segundo worker.
    """
    return replace(deps, dono=dono)


SemearJob = Callable[..., JobSemeado]


@pytest.fixture
def semear_job(
    engine_teste: Engine, storage_memoria: ArmazenamentoMemoria, tmp_path: Path
) -> SemearJob:
    """Fábrica: grava os bytes no storage, registra `arquivo` e cria o job em `recebido`."""

    def _semear(dados: bytes, nome: str = "autos.pdf") -> JobSemeado:
        processo = semear_processo(engine_teste)
        caminho = tmp_path / uuid4().hex
        caminho.write_bytes(dados)
        tipo = detectar_tipo(dados) or TipoArquivo.PDF
        recebido = ArquivoRecebido(caminho, calcular_hash_bytes(dados), len(dados), tipo)
        with Session(engine_teste) as session, session.begin():
            lacre = lacrar(
                session,
                storage_memoria,
                recebido,
                gabinete_id=processo.gabinete_id,
                processo_id=processo.processo_id,
                enviado_por=processo.usuario_id,
                nome_original=nome,
            )
        return JobSemeado(processo, lacre.arquivo_id, lacre.job_id)

    return _semear


def calcular_hash_bytes(dados: bytes) -> str:
    """SHA-256 hexadecimal de bytes.

    Args:
        dados: Conteúdo.

    Returns:
        Hash.
    """
    return hashlib.sha256(dados).hexdigest()


def fluxo(dados: bytes) -> io.BytesIO:
    """Envolve bytes num arquivo binário em memória.

    Args:
        dados: Conteúdo.

    Returns:
        Arquivo em memória.
    """
    return io.BytesIO(dados)


@dataclass(frozen=True)
class AutosSinteticos:
    """Processo sintético pequeno gerado nos três cenários (Etapa 4B), para a Etapa 4C.

    Attributes:
        arquivos: Arquivo de autos por cenário.
        gabaritos: Gabarito por cenário.
    """

    arquivos: dict[Cenario, Path]
    gabaritos: dict[Cenario, Gabarito]


@pytest.fixture(scope="session")
def autos_sinteticos(tmp_path_factory: pytest.TempPathFactory) -> AutosSinteticos:
    """Processo de ~45 folhas com todas as composições de página e todas as injeções."""
    config = Configuracao(
        semente=7, paginas_alvo=45, mistura=MISTURA_4C, injecoes=TODOS_VETORES,
        proporcao_vazias=0.3,
    )  # fmt: skip
    destino = tmp_path_factory.mktemp("autos-4c")
    gerados = exportar(gerar_conteudo(config), destino)
    return AutosSinteticos(
        arquivos={a.cenario: a.caminho for a in gerados},
        gabaritos={
            a.cenario: Gabarito.model_validate_json(a.gabarito.read_text(encoding="utf-8"))
            for a in gerados
        },
    )


@pytest.fixture
def deps_extracao(deps: Dependencias) -> Dependencias:
    """Dependências da Etapa 4C: extração ligada, retry por motivo e paralelismo pequeno."""
    return replace(
        deps,
        extrair=True,
        max_retentativas=2,
        paralelismo=Paralelismo(paginas_por_lote=4, lotes_por_job=4, lotes_por_gabinete=4),
        limitador=LimitadorGabinete(),
        limites_sandbox=LimitesSandbox(memoria_mb=1024, cpu_segundos=60, tempo_segundos=120),
    )


def _assessor_novo(engine: Engine) -> UsuarioTeste:
    return criar_usuario_teste(engine, PapelUsuario.ASSESSOR, criar_gabinete_teste(engine))


@dataclass(frozen=True)
class ExtracaoSessao:
    """Worker, assessor e bytes do PDF já extraído uma vez na sessão.

    Attributes:
        deps: Dependências do worker (storage e relógio compartilhados na sessão).
        assessor: Assessor dono dos processos.
        dados: Bytes do PDF sintético com índice.
    """

    deps: Dependencias
    assessor: UsuarioTeste
    dados: bytes


def lacrar_e_processar(extracao: ExtracaoSessao, engine: Engine, tmp_path: Path) -> dict[str, Any]:
    """Lacra o PDF num processo novo do assessor e processa o job até `concluido`.

    Args:
        extracao: Extração da sessão.
        engine: Engine de testes.
        tmp_path: Diretório temporário.

    Returns:
        `{assessor, processo, lacre}`.
    """
    from tests.api.test_processos import _criar_processo

    assessor = extracao.assessor
    assert assessor.gabinete_id is not None
    processo = _criar_processo(engine, assessor)
    caminho = tmp_path / f"{processo}.pdf"
    caminho.write_bytes(extracao.dados)
    recebido = ArquivoRecebido(
        caminho, calcular_hash_bytes(extracao.dados), len(extracao.dados), TipoArquivo.PDF
    )
    with Session(engine) as session, session.begin():
        lacre = lacrar(
            session, extracao.deps.storage, recebido, gabinete_id=assessor.gabinete_id,
            processo_id=processo, enviado_por=assessor.id, nome_original="autos.pdf",
        )  # fmt: skip
    estado = processar_job(extracao.deps, lacre.job_id, assessor.gabinete_id)
    assert estado is EstadoJob.CONCLUIDO
    return {"assessor": assessor, "processo": processo, "lacre": lacre}


@pytest.fixture(scope="session")
def extracao_sessao(
    engine_teste: Engine,
    autos_sinteticos: AutosSinteticos,
    tmp_path_factory: pytest.TempPathFactory,
) -> ExtracaoSessao:
    """Extrai o PDF com índice uma única vez por sessão (OCR incluído).

    Cada teste recebe um processo novo do mesmo gabinete com o mesmo arquivo (`lacrar_e_processar`);
    a extração dele vem do cache por SHA-256 (4F.8), então o OCR roda uma vez, não uma por teste.
    """
    deps = Dependencias(
        fabrica=sessionmaker(engine_teste, expire_on_commit=False),
        storage=ArmazenamentoMemoria(),
        limites_sandbox=LimitesSandbox(memoria_mb=1024, cpu_segundos=60, tempo_segundos=120),
        limites_zip=LimitesZip(),
        duracao_lease=timedelta(seconds=60),
        max_tentativas=3,
        relogio=Relogio(),
        dono="worker-teste-sessao",
        max_retentativas=2,
        paralelismo=Paralelismo(paginas_por_lote=4, lotes_por_job=4, lotes_por_gabinete=4),
        limitador=LimitadorGabinete(),
    )
    extracao = ExtracaoSessao(
        deps,
        _assessor_novo(engine_teste),
        autos_sinteticos.arquivos[Cenario.PDF_INDICE].read_bytes(),
    )
    lacrar_e_processar(extracao, engine_teste, tmp_path_factory.mktemp("pecas-modulo"))
    return extracao
