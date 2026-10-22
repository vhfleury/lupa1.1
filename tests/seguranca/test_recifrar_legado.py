"""`scripts/recifrar_objetos_legado.py`: objetos em claro anteriores à 7.4 (Etapa 7.10)."""

import importlib.util
import io
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest

from lupa.ingestao.storage import ArmazenamentoMemoria, StorageCifrado, chave_objeto
from lupa.seguranca.cofre import Cofre, CofreMemoria, nome_chave_gabinete
from lupa.seguranca.contexto import (
    ChaveIndisponivelError,
    contexto_cifra,
    definir_cofre,
    obter_cofre,
    registrar_dek,
)
from lupa.seguranca.envelope import gerar_dek, objeto_cifrado

CAMINHO = Path(__file__).resolve().parents[2] / "scripts" / "recifrar_objetos_legado.py"
CLARO = b"%PDF-1.7\n% sintetico legado\n" + b"7" * 200_000


def _modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("recifrar_objetos_legado", CAMINHO)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def cofre_memoria() -> Iterator[Cofre]:
    """Cofre em memória registrado só durante o teste."""
    anterior = obter_cofre()
    cofre = CofreMemoria()
    definir_cofre(cofre)
    yield cofre
    definir_cofre(anterior)


def test_recifra_so_os_em_claro_confere_e_e_idempotente(cofre_memoria: Cofre) -> None:
    """Simula sem tocar; executa cifrando o claro; a segunda passada não muda nada."""
    gabinete, processo, descartado = uuid4(), uuid4(), uuid4()
    nome = nome_chave_gabinete(gabinete)
    cofre_memoria.criar_chave(nome)
    dek = gerar_dek()
    envelopes: dict[UUID, str | None] = {
        processo: cofre_memoria.cifrar(nome, dek),
        descartado: None,
    }

    def carregador(processo_id: UUID) -> tuple[UUID, str | None]:
        if processo_id not in envelopes:
            raise ChaveIndisponivelError(str(processo_id))
        return gabinete, envelopes[processo_id]

    interno = ArmazenamentoMemoria()
    legado = chave_objeto(gabinete, processo, "a" * 64)
    novo = chave_objeto(gabinete, processo, "b" * 64)
    orfao = chave_objeto(gabinete, descartado, "c" * 64)
    estranho = f"gabinete/{gabinete}/solto"
    for chave in (legado, orfao, estranho):
        interno.gravar(chave, io.BytesIO(CLARO))
    with contexto_cifra():
        registrar_dek(processo, dek)
        StorageCifrado(interno).gravar(novo, io.BytesIO(b"ja cifrado"))
    modulo = _modulo()

    simulado = modulo.recifrar(interno, carregador, executar=False)
    assert (simulado.total, simulado.recifrados, simulado.ja_cifrados) == (4, 1, 1)
    assert (simulado.sem_dek, simulado.sem_processo) == (1, 1)
    assert interno.ler(legado) == CLARO

    executado = modulo.recifrar(interno, carregador, executar=True)
    assert executado.recifrados == 1 and executado.bytes_recifrados == len(CLARO)
    assert objeto_cifrado(interno.ler(legado)) and CLARO[:20] not in interno.ler(legado)
    assert interno.ler(orfao) == CLARO and interno.ler(estranho) == CLARO
    with contexto_cifra(carregador):
        assert StorageCifrado(interno).ler(legado) == CLARO

    de_novo = modulo.recifrar(interno, carregador, executar=True)
    assert (de_novo.recifrados, de_novo.ja_cifrados) == (0, 2)


def test_para_se_o_objeto_regravado_nao_confere(
    cofre_memoria: Cofre, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se a releitura não decifra para o claro original, o script para com erro."""
    gabinete, processo = uuid4(), uuid4()
    nome = nome_chave_gabinete(gabinete)
    cofre_memoria.criar_chave(nome)
    envelope = cofre_memoria.cifrar(nome, gerar_dek())
    interno = ArmazenamentoMemoria()
    interno.gravar(chave_objeto(gabinete, processo, "d" * 64), io.BytesIO(CLARO))
    modulo = _modulo()
    monkeypatch.setattr(modulo, "decifrar_objeto", lambda _dek, _dados: b"outro")
    with pytest.raises(modulo.ConferenciaError):
        modulo.recifrar(interno, lambda _p: (gabinete, envelope), executar=True)
