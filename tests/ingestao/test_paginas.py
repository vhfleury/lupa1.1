"""Testes de sinais por página (4C.3), roteador (4C.4) e texto nativo (4C.5)."""

import io
from typing import Any

import fitz
import pytest
from PIL import Image

from lupa.dominio.enums import TipoPagina
from lupa.dominio.esquemas import calcular_hash
from lupa.ingestao.roteador import Limiares, limiares_de, limiares_padrao, rotear
from lupa.ingestao.sinais import medir_sinais
from lupa.ingestao.texto_nativo import Bloco, Linha, extrair_texto_nativo, ordenar_blocos
from lupa.sinteticos.gabarito import Cenario, Composicao, Elemento
from tests.ingestao.conftest import AutosSinteticos

TEXTO_PADRAO = "Certidão de intimação do defensor em 10/03/2025, conforme os autos."


def _png(largura: int, altura: int, *, transparente: bool = False) -> bytes:
    modo, cor = ("RGBA", (200, 0, 0, 120)) if transparente else ("L", 90)
    saida = io.BytesIO()
    Image.new(modo, (largura, altura), cor).save(saida, format="PNG")
    return saida.getvalue()


def _pagina(documento: fitz.Document, texto: str = TEXTO_PADRAO) -> fitz.Page:
    pagina = documento.new_page()
    if texto:
        pagina.insert_text((72, 100), texto, fontsize=11)
    return pagina


def _sinais(**alterados: Any) -> dict[str, Any]:
    base = {
        "caracteres_imprimiveis": 800,
        "caracteres_substituicao": 0,
        "caracteres_invisiveis": 0,
        "cobertura_texto": 0.4,
        "area_imagem": 0.0,
        "area_imagem_opaca": 0.0,
        "imagens": 0,
        "palavras": 150,
        "fragmentacao": 0.05,
        "rotacao": 0,
        "tinta": 0.03,
        "visualmente_vazia": False,
    }
    return base | alterados


def test_sinais_de_pagina_nativa() -> None:
    """Texto contado, sem imagem, com tinta, sem rotação."""
    sinais = medir_sinais(_pagina(fitz.open()))
    assert sinais["caracteres_imprimiveis"] == len(TEXTO_PADRAO.replace(" ", ""))
    assert sinais["area_imagem"] == 0.0
    assert sinais["cobertura_texto"] > 0
    assert sinais["visualmente_vazia"] is False
    assert sinais["rotacao"] == 0


def test_pagina_em_branco_e_visualmente_vazia() -> None:
    """Sem texto e sem tinta."""
    sinais = medir_sinais(fitz.open().new_page())
    assert sinais["visualmente_vazia"] is True
    assert sinais["caracteres_imprimiveis"] == 0
    assert sinais["fragmentacao"] == 0.0


def test_imagem_opaca_e_carimbo_transparente_sao_separados() -> None:
    """Carimbo com transparência conta em `area_imagem`, não em `area_imagem_opaca`."""
    documento = fitz.open()
    pagina = _pagina(documento)
    pagina.insert_image(fitz.Rect(300, 300, 400, 350), stream=_png(200, 100, transparente=True))
    sinais = medir_sinais(pagina)
    assert sinais["area_imagem"] > 0
    assert sinais["area_imagem_opaca"] == 0.0
    pagina.insert_image(pagina.rect, stream=_png(100, 130), keep_proportion=False)
    assert medir_sinais(documento.reload_page(pagina))["area_imagem_opaca"] == 1.0


def test_texto_minusculo_ou_fora_da_pagina_conta_como_invisivel() -> None:
    """Fonte de 1 pt e texto além da borda."""
    documento = fitz.open()
    pagina = _pagina(documento)
    pagina.insert_text((72, 700), "oculto", fontsize=1)
    escritor = fitz.TextWriter(pagina.rect)
    escritor.append((72, 2000), "fora", fontsize=11)
    escritor.write_text(pagina)
    assert medir_sinais(pagina)["caracteres_invisiveis"] == len("oculto") + len("fora")


def test_rotacao_declarada_e_sinais_reproduziveis() -> None:
    """Mesma página, mesmos sinais; a rotação do /Rotate aparece."""
    documento = fitz.open()
    pagina = _pagina(documento)
    pagina.set_rotation(90)
    assert medir_sinais(pagina) == medir_sinais(pagina)
    assert medir_sinais(pagina)["rotacao"] == 90


def test_substituicao_e_fragmentacao_medem_texto_ilegivel() -> None:
    """U+FFFD e palavras de uma letra."""
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 100), "a b c d " + chr(0xFFFD) * 3, fontsize=11)
    sinais = medir_sinais(pagina)
    assert sinais["fragmentacao"] > 0.5


@pytest.mark.parametrize(
    ("alterados", "esperado"),
    [
        ({}, TipoPagina.NATIVA),
        ({"caracteres_imprimiveis": 0, "visualmente_vazia": True, "tinta": 0.0}, TipoPagina.VAZIA),
        ({"caracteres_imprimiveis": 0, "area_imagem_opaca": 1.0}, TipoPagina.OCR),
        ({"caracteres_imprimiveis": 200, "area_imagem_opaca": 0.77}, None),
        ({"area_imagem_opaca": 0.03}, None),
        ({"caracteres_invisiveis": 40}, None),
        ({"caracteres_substituicao": 100}, None),
        ({"fragmentacao": 0.9}, None),
        ({"caracteres_imprimiveis": 5}, None),
        (
            {"caracteres_imprimiveis": 0, "visualmente_vazia": True, "area_imagem_opaca": 1.0},
            (TipoPagina.OCR),
        ),
    ],
)
def test_roteador_por_sinais(alterados: dict[str, Any], esperado: TipoPagina | None) -> None:
    """Nativa, vazia, OCR ou abstenção; digitalização em branco vai ao OCR, não a vazia."""
    assert rotear(_sinais(**alterados)) is esperado


def test_limiares_versionados_com_fonte() -> None:
    """O YAML tem versão e fonte; limiares explícitos substituem o padrão."""
    padrao = limiares_padrao()
    assert padrao.versao and padrao.fonte
    rigido = Limiares(**(padrao.__dict__ | {"nativa_min_caracteres": 10_000}))
    assert rotear(_sinais(), rigido) is None
    dados = {
        "versao": "x",
        "fonte": "teste",
        "vazia": {"max_caracteres": 0},
        "nativa": {
            "min_caracteres": 1,
            "max_area_imagem_opaca": 1.0,
            "max_fragmentacao": 1.0,
            "max_substituicao": 1.0,
            "max_caracteres_invisiveis": 99,
        },
        "digitalizada": {"min_area_imagem_opaca": 2.0, "max_caracteres": 0},
    }
    assert rotear(_sinais(area_imagem_opaca=0.5), limiares_de(dados)) is TipoPagina.NATIVA


def test_nenhuma_pagina_com_imagem_do_sintetico_e_roteada_como_nativa(
    autos_sinteticos: AutosSinteticos,
) -> None:
    """Falso negativo perigoso zero; nativas sem injeção não vão para OCR.

    Nativa com texto invisível plantado (texto branco, fora da página) se abstém de propósito.
    """
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_LISO]
    documento = fitz.open(autos_sinteticos.arquivos[Cenario.PDF_LISO])
    perigosos = acertos_nativa = nativas_limpas = 0
    for posicao, pagina in enumerate(gabarito.paginas):
        rota = rotear(medir_sinais(documento[posicao]))
        com_imagem = pagina.composicao not in (Composicao.NATIVA, Composicao.CAPA, Composicao.VAZIA)
        perigosos += com_imagem and rota is TipoPagina.NATIVA
        limpa = pagina.composicao is Composicao.NATIVA and Elemento.INJECAO not in pagina.elementos
        acertos_nativa += limpa and rota is TipoPagina.NATIVA
        nativas_limpas += limpa
    assert perigosos == 0
    assert acertos_nativa == nativas_limpas


def test_texto_nativo_igual_a_camada_do_gabarito_com_offsets(
    autos_sinteticos: AutosSinteticos,
) -> None:
    """Páginas nativas: texto igual a `texto_camada`; offsets de cada linha conferem.

    Na página com injeção de texto branco a linha oculta foi escrita por último no arquivo;
    desde a 4D.1 ela sai do texto (vai para `trechos_ocultos`), então o conjunto de linhas é o
    da camada menos as injeções ocultas.
    """
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_LISO]
    documento = fitz.open(autos_sinteticos.arquivos[Cenario.PDF_LISO])
    nativas = [p for p in gabarito.paginas if p.composicao in (Composicao.NATIVA, Composicao.CAPA)]
    for pagina in nativas:
        extraido = extrair_texto_nativo(documento[pagina.numero - 1])
        if Elemento.INJECAO in pagina.elementos:
            ocultas = {
                i.texto for i in gabarito.injecoes if i.pagina == pagina.numero and not i.visivel
            }
            esperadas = [x for x in pagina.texto_camada.splitlines() if x not in ocultas]
            assert sorted(extraido.texto.splitlines()) == sorted(esperadas)
            continue
        assert extraido.texto == pagina.texto_camada
        for bloco in extraido.blocos:
            for linha in bloco["linhas"]:
                trecho = extraido.texto[linha["inicio"] : linha["fim"]]
                assert "\n" not in trecho
        assert extrair_texto_nativo(documento[pagina.numero - 1]) == extraido
        assert extraido.texto and calcular_hash(extraido.texto) == calcular_hash(
            pagina.texto_camada
        )


def test_duas_colunas_sao_lidas_coluna_por_coluna() -> None:
    """Título em largura total, depois a coluna esquerda inteira e só então a direita."""
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 60), "TITULO DA PECA", fontsize=14)
    for n in range(5):
        pagina.insert_text((300, 120 + 20 * n), f"direita {n}", fontsize=10)
    for n in range(5):
        pagina.insert_text((72, 120 + 20 * n), f"esquerda {n}", fontsize=10)
    pagina.insert_text((72, 400), "RODAPE COMUM", fontsize=10)
    linhas = extrair_texto_nativo(pagina).texto.splitlines()
    assert linhas == (
        ["TITULO DA PECA"]
        + [f"esquerda {n}" for n in range(5)]
        + [f"direita {n}" for n in range(5)]
        + ["RODAPE COMUM"]
    )


def test_texto_diagonal_vai_para_o_fim_fora_do_fluxo() -> None:
    """Marca d'água girada não interrompe a leitura."""
    documento = fitz.open()
    pagina = documento.new_page()
    escritor = fitz.TextWriter(pagina.rect)
    escritor.append((100, 400), "MARCA DAGUA", fontsize=30)
    escritor.write_text(pagina, morph=(fitz.Point(300, 400), fitz.Matrix(-45)))
    pagina.insert_text((72, 100), "linha um", fontsize=11)
    pagina.insert_text((72, 700), "linha dois", fontsize=11)
    extraido = extrair_texto_nativo(pagina)
    assert extraido.texto.splitlines() == ["linha um", "linha dois", "MARCA DAGUA"]
    assert [b["fluxo"] for b in extraido.blocos][-1] is False
    assert len(extraido.linhas_fora_do_fluxo) == 1


def test_ordenacao_sem_vao_cai_em_topo_e_esquerda() -> None:
    """Blocos sobrepostos nos dois eixos seguem (topo, esquerda)."""
    a = Bloco((10, 10, 100, 100), [Linha("a", (10, 10, 100, 100))])
    b = Bloco((50, 5, 150, 90), [Linha("b", (50, 5, 150, 90))])
    assert [blk.linhas[0].texto for blk in ordenar_blocos([a, b])] == ["b", "a"]
