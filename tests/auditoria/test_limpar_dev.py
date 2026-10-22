"""`scripts/limpar_dev.py`: remove gabinetes sintéticos e seus eventos (Etapa 6.10)."""

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from lupa.acesso.servico import definir_contexto
from lupa.auditoria.eventos import AcaoAuditoria, NovoEvento
from lupa.auditoria.registrador import registrar, verificar_cadeia
from lupa.dominio.enums import Materia, PapelUsuario, StatusProcesso
from lupa.dominio.sessao import assumir_papel_aplicacao
from lupa.dominio.tabelas import GabineteTabela, ProcessoTabela, UsuarioTabela
from tests.conftest import criar_usuario_teste, gerar_numero_cnj

pytestmark = pytest.mark.integracao

CAMINHO = Path(__file__).resolve().parents[2] / "scripts" / "limpar_dev.py"


def _modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("limpar_dev", CAMINHO)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _gabinete(engine: Engine, nome: str) -> UUID:
    gabinete_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(GabineteTabela(id=gabinete_id, nome=nome))
    return gabinete_id


def _eventos(fabrica: sessionmaker[Session], gabinete_id: UUID, n: int) -> None:
    for _ in range(n):
        with fabrica() as session, session.begin():
            assumir_papel_aplicacao(session)
            definir_contexto(session, PapelUsuario.ASSESSOR.value, gabinete_id)
            registrar(session, NovoEvento(acao=AcaoAuditoria.BUSCA, gabinete_id=gabinete_id))


def _contar(engine: Engine, sql: str, gabinete_id: UUID) -> int:
    with engine.connect() as conexao:
        return int(conexao.execute(text(sql), {"g": gabinete_id}).scalar_one())


def test_simula_sem_sim_e_remove_so_os_sinteticos_com_sim(
    engine_teste: Engine, fabrica_sessao: sessionmaker[Session]
) -> None:
    """Sem `executar` nada muda; com ele somem gabinete, usuários, processo e eventos."""
    limpar_dev = _modulo()
    marca = f"Sintetico teste {uuid4().hex[:8]}"
    sintetico = _gabinete(engine_teste, f"{marca} A")
    real = _gabinete(engine_teste, f"Gabinete real {uuid4().hex[:8]}")
    usuario = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, sintetico)
    _eventos(fabrica_sessao, sintetico, 3)
    _eventos(fabrica_sessao, real, 2)

    simulado = limpar_dev.limpar(
        engine_teste, executar=False, prefixos=(marca,), ambiente="desenvolvimento"
    )
    assert (simulado.gabinetes, simulado.eventos, simulado.executado) == (1, 3, False)
    assert simulado.linhas == {"usuario": 1}
    with Session(engine_teste) as session:
        assert session.get(GabineteTabela, sintetico) is not None

    feito = limpar_dev.limpar(
        engine_teste, executar=True, prefixos=(marca.upper(),), ambiente="teste"
    )
    assert (feito.gabinetes, feito.eventos, feito.executado) == (1, 3, True)
    with Session(engine_teste) as session:
        assert session.get(GabineteTabela, sintetico) is None
        assert session.get(UsuarioTabela, usuario.id) is None
        assert session.get(GabineteTabela, real) is not None
    sql = "SELECT count(*) FROM evento_auditoria WHERE gabinete_id = :g"
    assert _contar(engine_teste, sql, sintetico) == 0
    assert _contar(engine_teste, sql, real) == 2
    with fabrica_sessao() as session, session.begin():
        assumir_papel_aplicacao(session)
        definir_contexto(session, PapelUsuario.ADMINISTRADOR.value, None)
        assert verificar_cadeia(session, real).integra
    # A trava append-only voltou a valer depois da limpeza.
    with pytest.raises(DBAPIError, match="append-only"), engine_teste.begin() as conexao:
        conexao.execute(text("DELETE FROM evento_auditoria WHERE gabinete_id = :g"), {"g": real})


def test_remove_dados_em_cascata_do_processo(engine_teste: Engine) -> None:
    """Processo e filhos do gabinete sintético saem na ordem das chaves estrangeiras."""
    limpar_dev = _modulo()
    marca = f"Sintetico processo {uuid4().hex[:8]}"
    gabinete = _gabinete(engine_teste, marca)
    usuario = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, gabinete)
    with Session(engine_teste) as session, session.begin():
        session.add(
            ProcessoTabela(
                id=uuid4(), gabinete_id=gabinete,
                numero_cnj=gerar_numero_cnj(int(uuid4().int % 9_000_000) + 1),
                classe="Apelação Criminal", materia=Materia.CRIMINAL.value, sigiloso=False,
                status=StatusProcesso.CRIADO.value, criado_por=usuario.id,
            )
        )  # fmt: skip
    feito = limpar_dev.limpar(engine_teste, executar=True, prefixos=(marca,), ambiente="teste")
    assert feito.gabinetes == 1
    assert feito.linhas == {"processo": 1, "usuario": 1}
    sql = "SELECT count(*) FROM processo WHERE gabinete_id = :g"
    assert _contar(engine_teste, sql, gabinete) == 0


def test_recusa_fora_de_desenvolvimento(engine_teste: Engine) -> None:
    """Em produção não toca no banco."""
    limpar_dev = _modulo()
    with pytest.raises(limpar_dev.RecusaError, match="fora de desenvolvimento"):
        limpar_dev.limpar(engine_teste, executar=True, ambiente="producao")


def test_recusa_se_a_cadeia_global_aponta_para_usuario_sintetico(
    engine_teste: Engine, fabrica_sessao: sessionmaker[Session]
) -> None:
    """Apagar evento global quebraria a cadeia global: recusa e não remove nada."""
    limpar_dev = _modulo()
    marca = f"Sintetico global {uuid4().hex[:8]}"
    gabinete = _gabinete(engine_teste, marca)
    usuario = criar_usuario_teste(engine_teste, PapelUsuario.ASSESSOR, gabinete)
    with fabrica_sessao() as session, session.begin():
        assumir_papel_aplicacao(session)
        definir_contexto(session, PapelUsuario.ADMINISTRADOR.value, None)
        registrar(session, NovoEvento(acao=AcaoAuditoria.BUSCA, usuario_id=usuario.id))
    with pytest.raises(limpar_dev.RecusaError, match="cadeia global"):
        limpar_dev.limpar(engine_teste, executar=True, prefixos=(marca,), ambiente="teste")
    with Session(engine_teste) as session:
        assert session.get(GabineteTabela, gabinete) is not None


def test_main_simula_e_imprime_contagens(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], engine_teste: Engine
) -> None:
    """A linha de comando sem `--sim` só simula; fora de desenvolvimento devolve 2."""
    limpar_dev = _modulo()
    url = engine_teste.url.render_as_string(hide_password=False)
    monkeypatch.setenv("LUPA_DATABASE_URL", url)
    monkeypatch.setenv("LUPA_AMBIENTE", "teste")
    monkeypatch.setattr(limpar_dev, "PREFIXOS", (f"nada {uuid4().hex}",))
    monkeypatch.setattr(
        limpar_dev, "limpar",
        lambda engine, **kw: limpar_dev.Resultado(0, 0, {"usuario": 1}, kw["executar"]),
    )  # fmt: skip
    from lupa.config import get_settings

    get_settings.cache_clear()
    try:
        assert limpar_dev.main([]) == 0
        assert "seriam removidos" in capsys.readouterr().out
        monkeypatch.setenv("LUPA_AMBIENTE", "producao")
        get_settings.cache_clear()
        monkeypatch.setattr(
            limpar_dev, "limpar",
            lambda engine, **kw: (_ for _ in ()).throw(limpar_dev.RecusaError("recusado")),
        )  # fmt: skip
        assert limpar_dev.main(["--sim"]) == 2
    finally:
        get_settings.cache_clear()
