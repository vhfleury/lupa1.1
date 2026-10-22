"""4B.8: cada vetor de injeção é plantado e registrado com objetivo no gabarito."""

import base64

import fitz
import pytest

from lupa.sinteticos.gabarito import (
    TODOS_VETORES,
    Cenario,
    Elemento,
    Gabarito,
    InjecaoGabarito,
    VetorInjecao,
)
from lupa.sinteticos.injecao import INJECOES, texto_visivel
from tests.sinteticos.conftest import ProcessoGerado


def _injecao(gabarito: Gabarito, vetor: VetorInjecao) -> InjecaoGabarito:
    return next(i for i in gabarito.injecoes if i.vetor == vetor)


@pytest.fixture(scope="module")
def documento(processo: ProcessoGerado) -> fitz.Document:
    """PDF liso com todas as injeções."""
    return fitz.open(processo.arquivos[Cenario.PDF_LISO].caminho)


def test_todos_os_vetores_registrados_com_objetivo(gabarito: Gabarito) -> None:
    """Todos os vetores registrados com objetivo."""
    assert {i.vetor for i in gabarito.injecoes} == set(TODOS_VETORES)
    for injecao in gabarito.injecoes:
        assert injecao.objetivo == INJECOES[injecao.vetor].objetivo
        if injecao.pagina is not None:
            assert Elemento.INJECAO in gabarito.pagina(injecao.pagina).elementos


def test_injecao_nao_vira_evento(gabarito: Gabarito) -> None:
    """Injecao nao vira evento."""
    trechos = " ".join(e.trecho for e in gabarito.eventos)
    for vetor in TODOS_VETORES:
        assert INJECOES[vetor].texto not in trechos


def test_texto_branco_esta_na_camada_mas_nao_no_texto_visivel(gabarito: Gabarito) -> None:
    """Texto branco esta na camada mas nao no texto visivel."""
    pagina = gabarito.pagina(_injecao(gabarito, VetorInjecao.TEXTO_BRANCO).pagina or 0)
    instrucao = INJECOES[VetorInjecao.TEXTO_BRANCO].texto
    assert instrucao in pagina.texto_camada
    assert instrucao not in pagina.texto


def test_texto_fora_da_pagina_so_aparece_sem_recorte(
    gabarito: Gabarito, documento: fitz.Document
) -> None:
    """Texto fora da pagina so aparece sem recorte."""
    numero = _injecao(gabarito, VetorInjecao.FORA_DA_PAGINA).pagina or 0
    instrucao = INJECOES[VetorInjecao.FORA_DA_PAGINA].texto
    pagina = documento[numero - 1]
    assert instrucao not in pagina.get_text()
    assert instrucao in pagina.get_text(clip=fitz.INFINITE_RECT())


def test_metadado_xmp_e_anotacao(gabarito: Gabarito, documento: fitz.Document) -> None:
    """Metadado xmp e anotacao."""
    assert INJECOES[VetorInjecao.METADADO_XMP].texto in documento.get_xml_metadata()
    numero = _injecao(gabarito, VetorInjecao.ANOTACAO).pagina or 0
    conteudos = [a.info["content"] for a in documento[numero - 1].annots()]
    assert INJECOES[VetorInjecao.ANOTACAO].texto in conteudos


def test_imagem_com_texto_fica_sem_camada(gabarito: Gabarito, documento: fitz.Document) -> None:
    """Imagem com texto fica sem camada."""
    injecao = _injecao(gabarito, VetorInjecao.IMAGEM_COM_TEXTO)
    pagina = documento[(injecao.pagina or 0) - 1]
    assert pagina.get_images()
    assert "SENTENCA" not in pagina.get_text()


def test_vetores_visiveis_aparecem_no_texto_da_folha(gabarito: Gabarito) -> None:
    """Vetores visiveis aparecem no texto da folha."""
    for vetor in (
        VetorInjecao.BASE64,
        VetorInjecao.HOMOGLIFOS,
        VetorInjecao.IDIOMA_ALTERNADO,
        VetorInjecao.TRANSCRICAO_CITADA,
    ):
        pagina = gabarito.pagina(_injecao(gabarito, vetor).pagina or 0)
        assert texto_visivel(vetor) in " ".join(pagina.texto.split())


def test_codificacoes_dos_vetores_visiveis() -> None:
    """Codificacoes dos vetores visiveis."""
    codificado = texto_visivel(VetorInjecao.BASE64)
    assert base64.b64decode(codificado).decode() == INJECOES[VetorInjecao.BASE64].texto
    homoglifos = texto_visivel(VetorInjecao.HOMOGLIFOS)
    assert homoglifos != INJECOES[VetorInjecao.HOMOGLIFOS].texto
    assert any("Ѐ" <= c <= "ӿ" for c in homoglifos)
