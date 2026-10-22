"""Testes do diagnóstico do contêiner (4C.1) e da leitura de bookmarks e índice (4C.2)."""

from pathlib import Path
from uuid import uuid4

import fitz
import pytest

from lupa.dominio.enums import CenarioArquivo
from lupa.ingestao.diagnostico import (
    cenario_pdf,
    data_no_nome,
    data_no_texto,
    diagnosticar_pdf,
    diagnosticar_zip,
    fronteiras_do_sumario,
    ler_indice,
    linhas_de_indice,
)
from lupa.ingestao.inventario import LimitesZip, inventariar
from lupa.ingestao.parser_pdf import inspecionar
from lupa.sinteticos.gabarito import DIAGNOSTICO_ESPERADO, Cenario
from tests.ingestao.arquivos import pdf_texto
from tests.ingestao.conftest import AutosSinteticos

LINHA = "Movimentação 001 - 08/07/2014 - Autuação - fls. 3"


def test_linha_de_indice_e_lida_com_numero_data_titulo_e_folha() -> None:
    """Padrão `Movimentação N - data - título - fls. P`."""
    assert linhas_de_indice(LINHA) == [
        {"numero": 1, "data": "2014-07-08", "titulo": "Autuação", "pagina": 3}
    ]


def test_variantes_evento_e_pagina_sao_aceitas() -> None:
    """`Evento 12 - ... - pág. 40` também é linha de índice."""
    entradas = linhas_de_indice("Evento 12 - 01/02/2025 - SENTENÇA - pág. 40")
    assert entradas[0]["numero"] == 12
    assert entradas[0]["pagina"] == 40


def test_pagina_de_texto_comum_nao_e_indice() -> None:
    """Uma única linha parecida dentro de uma peça não faz índice."""
    paginas, entradas = ler_indice([f"Certidão\nTexto\n{LINHA}\nMais texto\nFim"])
    assert (paginas, entradas) == (0, [])


def test_indice_ocupa_paginas_consecutivas_e_para_no_conteudo() -> None:
    """Duas páginas de índice seguidas de conteúdo."""
    pagina1 = "ÍNDICE\nProcesso\n" + "\n".join(
        f"Movimentação {n:03d} - 01/01/2020 - PEÇA {n} - fls. {n + 2}" for n in range(1, 4)
    )
    pagina2 = "ÍNDICE\nProcesso\nMovimentação 004 - 02/01/2020 - PEÇA 4 - fls. 9"
    paginas, entradas = ler_indice([pagina1, pagina2, "DENÚNCIA\nTexto da peça"])
    assert paginas == 2
    assert [e["pagina"] for e in entradas] == [3, 4, 5, 9]


def test_datas_de_nome_e_de_titulo() -> None:
    """Datas ISO ou brasileiras no nome; dd/mm/aaaa no título; inválidas são ignoradas."""
    assert data_no_nome("001_denuncia_2024-03-05.pdf") == "2024-03-05"
    assert data_no_nome("peca_05-03-2024.pdf") == "2024-03-05"
    assert data_no_nome("peca_2024-13-40.pdf") is None
    assert data_no_texto("001 - Sentença - 31/02/2024 e 01/03/2024") == "2024-03-01"
    assert data_no_texto("sem data") is None


@pytest.mark.parametrize(
    ("bookmarks", "indice", "esperado"),
    [
        (True, True, CenarioArquivo.PDF_COM_BOOKMARKS_E_INDICE),
        (True, False, CenarioArquivo.PDF_COM_BOOKMARKS),
        (False, True, CenarioArquivo.PDF_COM_INDICE),
        (False, False, CenarioArquivo.PDF_LISO),
    ],
)
def test_cenario_pelo_que_o_pdf_traz(
    bookmarks: bool, indice: bool, esperado: CenarioArquivo
) -> None:
    """Quatro combinações de bookmarks e índice."""
    assert cenario_pdf(bookmarks, indice) is esperado


def test_bookmark_sem_destino_ou_de_segundo_nivel_nao_vira_fronteira() -> None:
    """Só nível 1 com página válida."""
    toc = [[1, "001 - Denúncia - 05/03/2024", 2], [2, "anexo", 3], [1, "sem destino", -1]]
    fronteiras = fronteiras_do_sumario(toc, "autos.pdf")
    assert [(f["pagina"], f["data"]) for f in fronteiras] == [(2, "2024-03-05")]


def _diagnostico_do_cenario(autos: AutosSinteticos, cenario: Cenario, pasta: Path) -> str:
    caminho = autos.arquivos[cenario]
    if cenario is Cenario.ZIP_POR_PECA:
        extraidas = inventariar(caminho, pasta, LimitesZip())
        entradas = [(e.manifesto.nome, inspecionar(e.caminho.read_bytes())) for e in extraidas]
        return diagnosticar_zip(uuid4(), entradas).cenario.value
    inspecao = inspecionar(caminho.read_bytes())
    return diagnosticar_pdf(uuid4(), caminho.name, inspecao).cenario.value


@pytest.mark.parametrize("cenario", list(Cenario))
def test_tres_cenarios_sinteticos_tem_o_diagnostico_esperado_do_gabarito(
    autos_sinteticos: AutosSinteticos, cenario: Cenario, tmp_path: Path
) -> None:
    """ZIP por peça, PDF com bookmarks e índice, PDF liso."""
    obtido = _diagnostico_do_cenario(autos_sinteticos, cenario, tmp_path)
    assert obtido == autos_sinteticos.gabaritos[cenario].processo.diagnostico_esperado
    assert obtido == DIAGNOSTICO_ESPERADO[cenario]


def test_fronteiras_do_indice_batem_com_as_pecas_do_gabarito(
    autos_sinteticos: AutosSinteticos,
) -> None:
    """Página física do índice = página inicial da peça + páginas de índice."""
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_INDICE]
    inspecao = inspecionar(autos_sinteticos.arquivos[Cenario.PDF_INDICE].read_bytes())
    diagnostico = diagnosticar_pdf(uuid4(), "autos.pdf", inspecao)
    deslocamento = gabarito.arquivos[0].folhas.count(None)
    esperadas = [p.pagina_inicial + deslocamento for p in gabarito.pecas]
    for fonte in ("indice", "bookmark"):
        obtidas = [f["pagina"] for f in diagnostico.fronteiras_origem if f["fonte"] == fonte]
        assert obtidas == esperadas
    assert diagnostico.sinais["paginas_indice"] == deslocamento
    datas = [f["data"] for f in diagnostico.fronteiras_origem if f["fonte"] == "indice"]
    assert datas == [p.data.isoformat() for p in gabarito.pecas]


def test_zip_por_peca_tem_uma_fronteira_por_entrada_em_numeracao_continua(
    autos_sinteticos: AutosSinteticos, tmp_path: Path
) -> None:
    """Cada entrada começa uma peça; a página contínua acumula as anteriores."""
    gabarito = autos_sinteticos.gabaritos[Cenario.ZIP_POR_PECA]
    extraidas = inventariar(autos_sinteticos.arquivos[Cenario.ZIP_POR_PECA], tmp_path, LimitesZip())
    entradas = [(e.manifesto.nome, inspecionar(e.caminho.read_bytes())) for e in extraidas]
    diagnostico = diagnosticar_zip(uuid4(), entradas)
    continuas = [f["pagina_continua"] for f in diagnostico.fronteiras_origem]
    assert continuas == [p.pagina_inicial for p in gabarito.pecas]
    assert diagnostico.sinais["nomes_datados"] == len(gabarito.pecas)
    assert diagnostico.total_paginas == len(gabarito.paginas)


def test_zip_com_um_unico_pdf_e_diagnosticado_pelo_pdf() -> None:
    """Uma entrada só: o cenário é o do PDF dentro."""
    inspecao = inspecionar(pdf_texto(["DENÚNCIA"]))
    diagnostico = diagnosticar_zip(uuid4(), [("autos.pdf", inspecao)])
    assert diagnostico.cenario is CenarioArquivo.PDF_LISO
    assert diagnostico.sinais["zip_com_um_pdf"] is True


def test_pdf_com_pagina_sem_conteudo_nao_e_corrompido() -> None:
    """Página em branco sem stream de conteúdo (comum nos autos) passa na inspeção."""
    documento = fitz.open()
    documento.new_page().insert_text((72, 72), "Folha com texto")
    documento.new_page()
    resultado = inspecionar(documento.tobytes())
    assert resultado["ok"] is True
    assert resultado["paginas"] == 2
