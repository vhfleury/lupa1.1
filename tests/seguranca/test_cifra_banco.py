"""Cifra em repouso no banco e no storage (Etapa 7.3 a 7.7), com dados sintéticos.

Sentinelas são palavras inventadas: se aparecerem num dump lógico, a coluna não está cifrada.
"""

import io
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from lupa.agente.contexto import pseudonimizador_do_processo
from lupa.agente.ferramentas.leitura import _paginas_com_termo, limite_paginas_busca
from lupa.auditoria.eventos import AcaoAuditoria
from lupa.dominio.enums import Materia, PapelMensagem, PapelUsuario, StatusMensagem, TipoPagina
from lupa.dominio.esquemas import calcular_hash
from lupa.dominio.tabelas import (
    ArquivoTabela,
    ConversaTabela,
    EvidenciaTabela,
    MensagemTabela,
    PaginaTabela,
    ProcessoTabela,
    ReuIdentidadeTabela,
    ReuTabela,
)
from lupa.ingestao.renderizacao import chave_cache
from lupa.ingestao.storage import (
    ArmazenamentoMemoria,
    ChaveSemProcessoError,
    StorageCifrado,
    chave_objeto,
)
from lupa.seguranca.chaves import carregador_sql
from lupa.seguranca.cofre import ChaveAusenteError, nome_chave_gabinete
from lupa.seguranca.contexto import (
    ChaveIndisponivelError,
    abrir_dek,
    ativar_processo,
    contexto_cifra,
    dek_de,
    dek_para_gravar,
    obter_cofre,
)
from lupa.seguranca.envelope import CifraInvalidaError, decifrar_campo
from tests.conftest import (
    UsuarioTeste,
    criar_gabinete_teste,
    criar_usuario_teste,
    eventos_do_banco,
    gerar_numero_cnj,
    logar,
)

pytestmark = pytest.mark.integracao

SENTINELA = "Zorvagnitopluma"
SENTINELA_TRECHO = "Quiblarventossa"
SENTINELA_MENSAGEM = "Plutomarnevisca"
SENTINELA_NOME = "Xanderlino Fictivaldo"
PDF_SINTETICO = b"%PDF-1.7\n% sintetico\n" + b"0" * 70_000


@dataclass(frozen=True)
class Semeado:
    """Processo sintético com conteúdo cifrado.

    Attributes:
        gabinete_id: Gabinete.
        assessor: Assessor do gabinete.
        processo_id: Processo.
        paginas: Ids das páginas (1, 2, 3).
    """

    gabinete_id: UUID
    assessor: UsuarioTeste
    processo_id: UUID
    paginas: list[UUID]


def _fabrica(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def semear(engine: Engine, textos: list[str] | None = None) -> Semeado:
    """Cria gabinete, assessor e processo com páginas, evidência, mensagem e réu.

    Args:
        engine: Engine de teste.
        textos: Texto de cada página.

    Returns:
        Ids semeados.
    """
    textos = textos or [f"Certidão {SENTINELA} intimado em 10/03/2025.", "Página dois.", "Três."]
    gabinete_id = criar_gabinete_teste(engine)
    assessor = criar_usuario_teste(engine, PapelUsuario.ASSESSOR, gabinete_id)
    processo_id, arquivo_id = uuid4(), uuid4()
    with contexto_cifra(carregador_sql(_fabrica(engine))), Session(engine) as session:
        with session.begin():
            session.add(
                ProcessoTabela(
                    id=processo_id, gabinete_id=gabinete_id,
                    numero_cnj=gerar_numero_cnj(int(processo_id.int % 9_000_000) + 1),
                    classe="Apelação Criminal", materia=Materia.CRIMINAL.value, sigiloso=False,
                    status="pronto", criado_por=assessor.id,
                )
            )  # fmt: skip
            session.flush()
            session.add(
                ArquivoTabela(
                    id=arquivo_id, gabinete_id=gabinete_id, processo_id=processo_id,
                    sha256=calcular_hash(str(arquivo_id)), tamanho_bytes=len(PDF_SINTETICO),
                    nome_original="autos.pdf", mime="application/pdf",
                    chave_storage=chave_objeto(gabinete_id, processo_id, calcular_hash("x")),
                    enviado_por=assessor.id,
                )
            )  # fmt: skip
            session.flush()
            paginas = []
            for numero, texto in enumerate(textos, start=1):
                pagina = PaginaTabela(
                    id=uuid4(), gabinete_id=gabinete_id, arquivo_id=arquivo_id, numero=numero,
                    tipo=TipoPagina.NATIVA.value, texto=texto, hash_texto=calcular_hash(texto),
                    texto_normalizado=texto, texto_nativo=texto,
                    trechos_ocultos=[{"texto": SENTINELA, "motivo": "cor_do_fundo"}],
                    trechos_suspeitos=[{"padrao": "ig01", "trecho": SENTINELA}],
                )  # fmt: skip
                session.add(pagina)
                paginas.append(pagina.id)
            session.flush()
            session.add(
                EvidenciaTabela(
                    id=uuid4(), gabinete_id=gabinete_id, pagina_id=paginas[0],
                    trecho=SENTINELA_TRECHO, hash_trecho=calcular_hash(SENTINELA_TRECHO),
                    inicio=0, fim=5,
                )
            )  # fmt: skip
            conversa = ConversaTabela(
                id=uuid4(), gabinete_id=gabinete_id, processo_id=processo_id,
                usuario_id=assessor.id,
            )  # fmt: skip
            session.add(conversa)
            session.flush()
            session.add(
                MensagemTabela(
                    id=uuid4(), gabinete_id=gabinete_id, conversa_id=conversa.id,
                    papel=PapelMensagem.USUARIO.value, status=StatusMensagem.PERGUNTA.value,
                    texto=f"Pergunta {SENTINELA_MENSAGEM}?",
                )
            )  # fmt: skip
            reu = ReuTabela(
                id=uuid4(), gabinete_id=gabinete_id, processo_id=processo_id, pseudonimo="REU-01"
            )
            session.add(reu)
            session.flush()
            session.add(
                ReuIdentidadeTabela(
                    reu_id=reu.id, gabinete_id=gabinete_id, nome=SENTINELA_NOME,
                    documento="123.456.789-09",
                )
            )  # fmt: skip
    return Semeado(gabinete_id, assessor, processo_id, paginas)


@pytest.fixture
def semeado(engine_teste: Engine) -> Semeado:
    """Um processo semeado."""
    return semear(engine_teste)


def _texto_bruto(engine: Engine, pagina_id: UUID) -> str:
    with engine.connect() as conexao:
        valor = conexao.execute(
            text("SELECT texto FROM pagina WHERE id = :id"), {"id": pagina_id}
        ).scalar_one()
    return str(valor)


def _dek(engine: Engine, processo_id: UUID) -> bytes:
    with Session(engine) as session:
        processo = session.get_one(ProcessoTabela, processo_id)
        assert processo.chave_dados_cifrada is not None
        return abrir_dek(obter_cofre(), processo.gabinete_id, processo.chave_dados_cifrada)


def _ler_paginas(engine: Engine, processo_id: UUID) -> list[str]:
    with contexto_cifra(carregador_sql(_fabrica(engine))), Session(engine) as session:
        return list(
            session.scalars(
                select(PaginaTabela.texto)
                .join(ArquivoTabela, ArquivoTabela.id == PaginaTabela.arquivo_id)
                .where(ArquivoTabela.processo_id == processo_id)
                .order_by(PaginaTabela.numero)
            )
        )


def test_texto_gravado_cifrado_e_lido_em_claro(engine_teste: Engine, semeado: Semeado) -> None:
    """No banco só `lupa1:`; pela aplicação, o texto volta em claro."""
    bruto = _texto_bruto(engine_teste, semeado.paginas[0])
    assert bruto.startswith("lupa1:") and SENTINELA not in bruto
    assert SENTINELA in _ler_paginas(engine_teste, semeado.processo_id)[0]


def test_dek_de_um_processo_nao_abre_outro(engine_teste: Engine, semeado: Semeado) -> None:
    """A DEK de outro processo (mesmo gabinete ou não) não decifra o campo."""
    outro = semear(engine_teste)
    bruto = _texto_bruto(engine_teste, semeado.paginas[0])
    assert SENTINELA in decifrar_campo(
        _dek(engine_teste, semeado.processo_id), bruto, "pagina.texto"
    )
    with pytest.raises(CifraInvalidaError):
        decifrar_campo(_dek(engine_teste, outro.processo_id), bruto, "pagina.texto")


def test_destruir_chave_do_gabinete_torna_processos_ilegiveis(engine_teste: Engine) -> None:
    """Sem a chave do gabinete no cofre, nenhuma DEK dos processos dele abre."""
    primeiro = semear(engine_teste)
    with Session(engine_teste) as session, session.begin():
        assessor = primeiro.assessor
        segundo_id = uuid4()
        session.add(
            ProcessoTabela(
                id=segundo_id, gabinete_id=primeiro.gabinete_id,
                numero_cnj=gerar_numero_cnj(int(segundo_id.int % 9_000_000) + 1),
                classe="Apelação Criminal", materia=Materia.CRIMINAL.value, sigiloso=False,
                status="criado", criado_por=assessor.id,
            )
        )  # fmt: skip
    obter_cofre().destruir_chave(nome_chave_gabinete(primeiro.gabinete_id))
    for processo_id in (primeiro.processo_id, segundo_id):
        with pytest.raises(ChaveAusenteError):
            _dek(engine_teste, processo_id)
    with pytest.raises(ChaveAusenteError):
        _ler_paginas(engine_teste, primeiro.processo_id)


def test_sem_processo_ativo_nao_grava_e_sem_carregador_nao_le(semeado: Semeado) -> None:
    """Fora de contexto com processo ativo, a cifra recusa em vez de gravar em claro."""
    with contexto_cifra(), pytest.raises(ChaveIndisponivelError):
        dek_para_gravar()
    with contexto_cifra() as contexto:
        contexto.carregador = None
        with pytest.raises(ChaveIndisponivelError):
            ativar_processo(semeado.processo_id, semeado.gabinete_id, None)


def test_identidade_do_reu_cifrada_no_banco_e_lida_com_auditoria(
    engine_teste: Engine, semeado: Semeado
) -> None:
    """Consulta direta devolve token do Transit; a apresentação decifra e registra o evento."""
    with engine_teste.connect() as conexao:
        nome, documento = conexao.execute(
            text(
                "SELECT i.nome, i.documento FROM reu_identidade i JOIN reu r ON r.id = i.reu_id"
                " WHERE r.processo_id = :p"
            ),
            {"p": semeado.processo_id},
        ).one()
    assert nome.startswith(("vault:v", "mem:v")) and "Xanderlino" not in nome
    assert documento.startswith(("vault:v", "mem:v")) and "789" not in documento
    with Session(engine_teste) as session, session.begin():
        pseudo = pseudonimizador_do_processo(session, semeado.processo_id)
        assert pseudo.aplicar(f"Réu {SENTINELA_NOME}") == "Réu REU-01"
    eventos = eventos_do_banco(
        engine_teste, acao=AcaoAuditoria.IDENTIDADE_LIDA.value, processo_id=semeado.processo_id
    )
    assert len(eventos) == 1 and eventos[0].objeto_tipo == "reu_identidade"


def _dump_logico(engine: Engine) -> str:
    """Dump lógico: `pg_dump --data-only` se existir no contêiner, senão COPY de cada tabela."""
    url = engine.url
    if shutil.which("pg_dump"):
        return subprocess.run(  # noqa: S603
            ["pg_dump", "--data-only", "-d", url.render_as_string(hide_password=False)  # noqa: S607
             .replace("postgresql+psycopg", "postgresql")],
            check=True, capture_output=True, text=True,
        ).stdout  # fmt: skip
    partes = []
    bruta = engine.raw_connection()
    try:
        cursor = bruta.cursor()
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        for (tabela,) in cursor.fetchall():
            with cursor.copy(f'COPY public."{tabela}" TO STDOUT') as copia:
                partes.append(b"".join(bytes(bloco) for bloco in copia).decode())
    finally:
        bruta.close()
    return "\n".join(partes)


def test_dump_logico_nao_contem_sentinelas_em_claro(engine_teste: Engine, semeado: Semeado) -> None:
    """Texto, trechos, evidência, mensagem e identidade: nenhum aparece em claro no dump."""
    dump = _dump_logico(engine_teste)
    assert "lupa1:" in dump
    for sentinela in (SENTINELA, SENTINELA_TRECHO, SENTINELA_MENSAGEM, "Xanderlino"):
        assert sentinela not in dump


def test_busca_em_memoria_respeita_o_teto_de_paginas(engine_teste: Engine) -> None:
    """A busca decifra página a página e para no teto configurado."""
    semeado = semear(engine_teste, ["primeira", "segunda", f"terceira {SENTINELA}"])
    assert limite_paginas_busca() >= 1
    with contexto_cifra(carregador_sql(_fabrica(engine_teste))), Session(engine_teste) as session:
        sessao: Any = SimpleNamespace(session=session, processo_id=semeado.processo_id)
        assert [p.numero for p in _paginas_com_termo(sessao, SENTINELA.lower())] == [3]
        assert _paginas_com_termo(sessao, SENTINELA, limite_paginas=2) == []


def test_storage_cifrado_nao_guarda_pdf_em_claro() -> None:
    """O objeto no storage começa com `LUPAOBJ`, não `%PDF`; a leitura devolve o claro."""
    processo_id, gabinete_id = uuid4(), uuid4()
    interno = ArmazenamentoMemoria()
    storage = StorageCifrado(interno)
    chave = chave_objeto(gabinete_id, processo_id, calcular_hash("pdf"))
    with contexto_cifra():
        from lupa.seguranca.contexto import registrar_dek
        from lupa.seguranca.envelope import gerar_dek

        registrar_dek(processo_id, gerar_dek())
        storage.gravar(chave, io.BytesIO(PDF_SINTETICO))
        assert not interno.ler(chave).startswith(b"%PDF")
        assert interno.ler(chave).startswith(b"LUPAOBJ")
        assert storage.ler(chave) == PDF_SINTETICO
        assert storage.existe(chave) and storage.listar("gabinete/") == [chave]
        interno.gravar(f"{chave}-legado", io.BytesIO(b"%PDF-legado"))
        assert storage.ler(f"{chave}-legado") == b"%PDF-legado"
        storage.apagar(chave)
        assert not storage.existe(chave)
        with pytest.raises(ChaveSemProcessoError):
            storage.gravar("sem-processo", io.BytesIO(b"x"))


def _cliente(app: FastAPI, engine: Engine, usuario: UsuarioTeste) -> TestClient:
    cliente = TestClient(app, base_url="https://testserver")
    logar(cliente, engine, usuario)
    return cliente


@pytest.fixture
def storage_app(app_teste: FastAPI) -> Iterator[StorageCifrado]:
    """Storage cifrado em memória ligado à aplicação de teste."""
    storage = StorageCifrado(ArmazenamentoMemoria())
    app_teste.state.storage = storage
    yield storage


def test_descarte_apaga_tudo_e_nada_e_recuperavel(
    app_teste: FastAPI, engine_teste: Engine, semeado: Semeado, storage_app: StorageCifrado
) -> None:
    """Descarte: tombstone, sem DEK, sem linhas, sem objetos; cópia antiga ilegível."""
    original = chave_objeto(semeado.gabinete_id, semeado.processo_id, calcular_hash("x"))
    cache = chave_cache(original, 1, 2.0)
    with contexto_cifra(carregador_sql(_fabrica(engine_teste))):
        storage_app.gravar(original, io.BytesIO(PDF_SINTETICO))
        storage_app.gravar(cache, io.BytesIO(b"\x89PNG sintetico"))
    assert isinstance(storage_app.interno, ArmazenamentoMemoria)
    copia_de_backup = storage_app.interno.ler(original)
    rota = f"/processos/{semeado.processo_id}/descartar"
    assert _cliente(app_teste, engine_teste, semeado.assessor).post(rota).status_code == 403
    desembargador = criar_usuario_teste(
        engine_teste, PapelUsuario.DESEMBARGADOR, semeado.gabinete_id
    )
    cliente = _cliente(app_teste, engine_teste, desembargador)
    resposta = cliente.post(rota)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {
        "processo_id": str(semeado.processo_id), "status": "descartado", "objetos_apagados": 2,
    }  # fmt: skip
    assert storage_app.listar("") == []
    with Session(engine_teste) as session:
        processo = session.get_one(ProcessoTabela, semeado.processo_id)
        assert processo.status == "descartado" and processo.chave_dados_cifrada is None
    with engine_teste.connect() as conexao:
        for tabela in ("arquivo", "conversa", "reu", "fato", "achado", "chamada_modelo"):
            total = conexao.execute(
                text(f"SELECT count(*) FROM {tabela} WHERE processo_id = :p"),  # noqa: S608
                {"p": semeado.processo_id},
            ).scalar_one()
            assert total == 0, tabela
        for pagina in semeado.paginas:
            assert (
                conexao.execute(
                    text("SELECT count(*) FROM pagina WHERE id = :id"), {"id": pagina}
                ).scalar_one()
                == 0
            )
    eventos = eventos_do_banco(
        engine_teste, acao=AcaoAuditoria.PROCESSO_DESCARTADO.value, processo_id=semeado.processo_id
    )
    assert [e.usuario_id for e in eventos] == [desembargador.id]
    assert eventos[0].objeto_id is not None and len(eventos[0].objeto_id) == 64
    with (
        contexto_cifra(carregador_sql(_fabrica(engine_teste))),
        pytest.raises(ChaveIndisponivelError),
    ):
        dek_de(semeado.processo_id)
    assert obter_cofre().existe_chave(nome_chave_gabinete(semeado.gabinete_id))
    assert copia_de_backup.startswith(b"LUPAOBJ")
    assert cliente.post(rota).status_code == 404
    assert cliente.get(f"/processos/{semeado.processo_id}/dossie").status_code == 404


def test_rotacao_da_chave_do_gabinete_recifra_as_deks(
    app_teste: FastAPI, engine_teste: Engine, semeado: Semeado
) -> None:
    """Admin rotaciona; as DEKs passam à versão nova e o conteúdo continua legível."""
    admin = criar_usuario_teste(engine_teste, PapelUsuario.ADMINISTRADOR, None)
    rota = f"/gabinetes/{semeado.gabinete_id}/rotacionar-chave"
    assert _cliente(app_teste, engine_teste, semeado.assessor).post(rota).status_code == 403
    resposta = _cliente(app_teste, engine_teste, admin).post(rota)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["deks_recifradas"] == 1
    with Session(engine_teste) as session:
        token = session.get_one(ProcessoTabela, semeado.processo_id).chave_dados_cifrada
    assert token is not None and token.split(":")[1] == "v2"
    assert SENTINELA in _ler_paginas(engine_teste, semeado.processo_id)[0]
    eventos = eventos_do_banco(engine_teste, acao=AcaoAuditoria.CHAVE_ROTACIONADA.value)
    assert str(semeado.gabinete_id) in [e.objeto_id for e in eventos]


def test_worker_decifra_em_temporario_0600_e_apaga_mesmo_em_falha(
    engine_teste: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O original decifrado fica só no diretório do job (0600) e some mesmo se o job falhar."""
    from datetime import timedelta

    from lupa.ingestao import worker
    from lupa.ingestao.inventario import LimitesZip
    from lupa.ingestao.recepcao import ArquivoRecebido, TipoArquivo, lacrar
    from lupa.ingestao.sandbox import LimitesSandbox
    from tests.ingestao.conftest import calcular_hash_bytes, semear_processo

    processo = semear_processo(engine_teste)
    storage = StorageCifrado(ArmazenamentoMemoria())
    caminho = tmp_path / "upload.pdf"
    caminho.write_bytes(PDF_SINTETICO)
    recebido = ArquivoRecebido(
        caminho, calcular_hash_bytes(PDF_SINTETICO), len(PDF_SINTETICO), TipoArquivo.PDF
    )
    with contexto_cifra(carregador_sql(_fabrica(engine_teste))), Session(engine_teste) as s:
        with s.begin():
            lacre = lacrar(
                s, storage, recebido, gabinete_id=processo.gabinete_id,
                processo_id=processo.processo_id, enviado_por=processo.usuario_id,
                nome_original="autos.pdf",
            )  # fmt: skip
    assert isinstance(storage.interno, ArmazenamentoMemoria)
    assert not storage.interno.ler(
        chave_objeto(processo.gabinete_id, processo.processo_id, recebido.sha256)
    ).startswith(b"%PDF")
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    vistos: list[int] = []

    def _falhar(_deps: Any, _lease: Any, unidades: list[Any], _gancho: Any) -> Any:
        vistos.append(unidades[0].caminho.stat().st_mode & 0o777)
        assert unidades[0].caminho.read_bytes() == PDF_SINTETICO
        raise RuntimeError("falha sintética no meio do job")

    monkeypatch.setattr(worker, "_processar_lotes", _falhar)
    deps = worker.Dependencias(
        fabrica=_fabrica(engine_teste), storage=storage,
        limites_sandbox=LimitesSandbox(memoria_mb=512, cpu_segundos=20, tempo_segundos=30),
        limites_zip=LimitesZip(), duracao_lease=timedelta(seconds=60), max_tentativas=3,
        dono="worker-teste-cifra", extrair=False, max_retentativas=0, dir_temporario=trabalho,
    )  # fmt: skip
    with pytest.raises(RuntimeError):
        worker.processar_job(deps, lacre.job_id, processo.gabinete_id)
    assert vistos == [0o600]
    assert list(trabalho.iterdir()) == []


def test_identidade_lida_registra_o_usuario_informado(
    engine_teste: Engine, semeado: Semeado
) -> None:
    """Com `usuario_id`, o evento `identidade_lida` diz quem leu (revisão 7.1-7.9, item 4)."""
    with Session(engine_teste) as session, session.begin():
        pseudonimizador_do_processo(session, semeado.processo_id, semeado.assessor.id)
    eventos = eventos_do_banco(
        engine_teste, acao=AcaoAuditoria.IDENTIDADE_LIDA.value, processo_id=semeado.processo_id
    )
    assert eventos[-1].usuario_id == semeado.assessor.id
