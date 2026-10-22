"""4B.3 a 4B.6: folhas nativas, digitalizadas, híbridas, vazias, capa e ruídos."""

import random

import fitz
import numpy as np
import pytest

from lupa.sinteticos.gabarito import Cenario, Composicao, Degradacao, Elemento, Gabarito
from lupa.sinteticos.render import DEGRADACOES, degradar, desenhar
from lupa.sinteticos.roteiro import Configuracao, montar_roteiro
from tests.sinteticos.conftest import ProcessoGerado


@pytest.fixture(scope="module")
def pdf_liso(processo: ProcessoGerado) -> fitz.Document:
    """PDF liso do processo de teste."""
    return fitz.open(processo.arquivos[Cenario.PDF_LISO].caminho)


def _limpa(gabarito: Gabarito, numero: int) -> bool:
    elementos = gabarito.pagina(numero).elementos
    return Elemento.MARCA_DAGUA not in elementos and Elemento.INJECAO not in elementos


def test_todas_as_composicoes_estao_presentes(gabarito: Gabarito) -> None:
    """Todas as composicoes estao presentes."""
    assert {p.composicao for p in gabarito.paginas} == set(Composicao)


def test_texto_nativo_extraido_bate_com_o_gabarito(
    gabarito: Gabarito, pdf_liso: fitz.Document
) -> None:
    """Texto nativo extraido bate com o gabarito."""
    nativas = [p for p in gabarito.paginas if p.composicao in (Composicao.NATIVA, Composicao.CAPA)]
    assert nativas
    for pagina in nativas:
        extraido = pdf_liso[pagina.numero - 1].get_text()
        assert extraido == pagina.texto_camada
        assert extraido.startswith(pagina.texto)
        if _limpa(gabarito, pagina.numero):
            assert extraido == pagina.texto


def test_offsets_dos_eventos_batem_no_texto_extraido(
    gabarito: Gabarito, pdf_liso: fitz.Document
) -> None:
    """Offsets dos eventos batem no texto extraido."""
    conferidos = 0
    for evento in gabarito.eventos:
        pagina = gabarito.pagina(evento.pagina)
        if pagina.composicao != Composicao.NATIVA:
            continue
        extraido = pdf_liso[evento.pagina - 1].get_text()
        assert extraido[evento.inicio : evento.fim] == evento.trecho
        conferidos += 1
    assert conferidos > 0


def test_fontes_sao_embutidas(pdf_liso: fitz.Document) -> None:
    """Fontes sao embutidas."""
    fontes = pdf_liso[0].get_fonts()
    assert fontes
    assert all(f[1] != "n/a" for f in fontes)


def test_cabecalho_e_numeracao_em_toda_folha_com_conteudo(gabarito: Gabarito) -> None:
    """Cabecalho e numeracao em toda folha com conteudo."""
    for pagina in gabarito.paginas:
        if pagina.composicao == Composicao.VAZIA:
            continue
        assert gabarito.processo.numero_cnj in pagina.texto
        assert f"Fls. {pagina.numero}\n" in pagina.texto
        assert {Elemento.CABECALHO_REPETIDO, Elemento.RODAPE_AUTENTICACAO} <= set(pagina.elementos)


def test_ultima_folha_de_cada_peca_tem_assinatura_eletronica(gabarito: Gabarito) -> None:
    """Ultima folha de cada peca tem assinatura eletronica."""
    for peca in gabarito.pecas[1:]:
        folhas = [gabarito.pagina(n) for n in range(peca.pagina_inicial, peca.pagina_final + 1)]
        com_texto = [f for f in folhas if f.composicao != Composicao.VAZIA]
        assert "assinado eletronicamente por" in com_texto[-1].texto


def test_cabecalho_repetido_e_igual_entre_pecas(gabarito: Gabarito) -> None:
    """Cabecalho repetido e igual entre pecas."""
    primeiras = {gabarito.pagina(p.pagina_inicial).texto.split("\n")[0] for p in gabarito.pecas}
    assert len(primeiras) == 1


def test_digitalizada_nao_tem_camada_de_texto_e_tem_imagem(
    gabarito: Gabarito, pdf_liso: fitz.Document
) -> None:
    """Digitalizada nao tem camada de texto e tem imagem."""
    for pagina in gabarito.paginas:
        if pagina.composicao != Composicao.DIGITALIZADA:
            continue
        fisica = pdf_liso[pagina.numero - 1]
        assert fisica.get_text() == ""
        assert fisica.get_images()
        assert pagina.degradacao is not None
        assert pagina.dpi == DEGRADACOES[pagina.degradacao].dpi
        assert pagina.rotacao_graus is not None
        assert abs(pagina.rotacao_graus) <= DEGRADACOES[pagina.degradacao].rotacao_max


def test_hibridas_tem_parte_nativa_e_parte_em_imagem(
    gabarito: Gabarito, pdf_liso: fitz.Document
) -> None:
    """Hibridas tem parte nativa e parte em imagem."""
    hibridas = (Composicao.HIBRIDA_CORPO, Composicao.HIBRIDA_ASSINATURA)
    for pagina in gabarito.paginas:
        if pagina.composicao not in hibridas:
            continue
        fisica = pdf_liso[pagina.numero - 1]
        assert fisica.get_images()
        assert pagina.texto_camada
        assert len(pagina.texto_camada) < len(pagina.texto)
        if pagina.composicao == Composicao.HIBRIDA_ASSINATURA:
            assert "assinado eletronicamente por" not in pagina.texto_camada
            assert "assinado eletronicamente por" in pagina.texto


def test_vazia_e_capa(gabarito: Gabarito, pdf_liso: fitz.Document) -> None:
    """Vazia e capa."""
    capa = gabarito.pagina(1)
    assert capa.composicao == Composicao.CAPA
    assert "AUTUAÇÃO" in capa.texto
    vazias = [p for p in gabarito.paginas if p.composicao == Composicao.VAZIA]
    assert vazias
    for pagina in vazias:
        fisica = pdf_liso[pagina.numero - 1]
        assert fisica.get_text() == ""
        assert not fisica.get_images()


def test_carimbo_e_marca_dagua_presentes(gabarito: Gabarito, pdf_liso: fitz.Document) -> None:
    """Carimbo e marca dagua presentes."""
    carimbadas = [p for p in gabarito.paginas if Elemento.CARIMBO in p.elementos]
    assert carimbadas
    assert all(pdf_liso[p.numero - 1].get_images() for p in carimbadas)
    marcadas = [p for p in gabarito.paginas if Elemento.MARCA_DAGUA in p.elementos]
    assert marcadas
    nativa = next((p for p in marcadas if p.composicao == Composicao.NATIVA), None)
    if nativa is not None:
        assert "SINTÉTICO" in nativa.texto_camada
        assert "SINTÉTICO" not in nativa.texto


@pytest.mark.parametrize("nivel", list(Degradacao))
def test_degradacao_produz_jpeg_e_rotacao_no_limite(nivel: Degradacao) -> None:
    """Degradacao produz jpeg e rotacao no limite."""
    matriz = np.full((300, 200), 255, dtype=np.uint8)
    matriz[100:120, 20:180] = 0
    jpeg, rotacao = degradar(matriz, nivel, random.Random(4), girar=True)  # noqa: S311
    assert jpeg[:2] == b"\xff\xd8"
    assert abs(rotacao) <= DEGRADACOES[nivel].rotacao_max


def test_composicao_com_imagem_exige_nivel() -> None:
    """Composicao com imagem exige nivel."""
    from lupa.sinteticos.paginacao import paginar

    plano = paginar(montar_roteiro(Configuracao(semente=1, paginas_alvo=5)), random.Random(1))[1]  # noqa: S311
    with pytest.raises(ValueError, match="degradação"):
        desenhar(fitz.open(), plano, Composicao.DIGITALIZADA, None, random.Random(1))  # noqa: S311
