"""4B.7: o mesmo conteúdo em três cenários, com diagnóstico esperado distinto."""

import re
import zipfile

import fitz

from lupa.sinteticos.gabarito import Cenario
from tests.sinteticos.conftest import ProcessoGerado

_NOME = re.compile(r"^\d{3}_[a-z_]+_\d{4}-\d{2}-\d{2}\.pdf$")


def test_conteudo_do_gabarito_e_identico_nos_tres_cenarios(processo: ProcessoGerado) -> None:
    """Conteudo do gabarito e identico nos tres cenarios."""
    conteudos = {
        g.model_dump_json(include={"pecas", "paginas", "eventos", "resultado_esperado", "injecoes"})
        for g in processo.gabaritos.values()
    }
    assert len(conteudos) == 1
    diagnosticos = {g.processo.diagnostico_esperado for g in processo.gabaritos.values()}
    assert len(diagnosticos) == 3
    assert {g.processo.cenario for g in processo.gabaritos.values()} == set(Cenario)


def test_zip_tem_um_pdf_por_peca_com_nome_e_data(processo: ProcessoGerado) -> None:
    """Zip tem um pdf por peca com nome e data."""
    gabarito = processo.gabaritos[Cenario.ZIP_POR_PECA]
    with zipfile.ZipFile(processo.arquivos[Cenario.ZIP_POR_PECA].caminho) as zip_entrada:
        nomes = zip_entrada.namelist()
        assert nomes == [a.nome for a in gabarito.arquivos]
        assert len(nomes) == len(gabarito.pecas)
        for nome, peca, arquivo in zip(nomes, gabarito.pecas, gabarito.arquivos, strict=True):
            assert _NOME.match(nome)
            assert peca.tipo.value in nome and peca.data.isoformat() in nome
            parte = fitz.open("pdf", zip_entrada.read(nome))
            assert len(parte) == len(arquivo.folhas) == peca.pagina_final - peca.pagina_inicial + 1


def test_pdf_com_indice_tem_bookmarks_que_apontam_para_a_peca(processo: ProcessoGerado) -> None:
    """Pdf com indice tem bookmarks que apontam para a peca."""
    gabarito = processo.gabaritos[Cenario.PDF_INDICE]
    documento = fitz.open(processo.arquivos[Cenario.PDF_INDICE].caminho)
    folhas = gabarito.arquivos[0].folhas
    deslocamento = folhas.count(None)
    assert deslocamento >= 1 and folhas[:deslocamento] == (None,) * deslocamento
    assert "ÍNDICE DE MOVIMENTAÇÕES" in documento[0].get_text()
    assert "Movimentação 001" in documento[0].get_text()
    sumario = documento.get_toc()
    assert len(sumario) == len(gabarito.pecas)
    for (nivel, _titulo, pagina), peca in zip(sumario, gabarito.pecas, strict=True):
        assert nivel == 1
        assert folhas[pagina - 1] == peca.pagina_inicial
    assert len(documento) == len(folhas)


def test_pdf_liso_nao_tem_bookmarks_e_preserva_o_texto(processo: ProcessoGerado) -> None:
    """Pdf liso nao tem bookmarks e preserva o texto."""
    gabarito = processo.gabaritos[Cenario.PDF_LISO]
    documento = fitz.open(processo.arquivos[Cenario.PDF_LISO].caminho)
    assert documento.get_toc() == []
    assert len(documento) == len(gabarito.paginas)
    for pagina in gabarito.paginas:
        assert documento[pagina.numero - 1].get_text() == pagina.texto_camada
