"""Sinais de fronteira, classificador por regras e conferência com a origem (4E.1 a 4E.3)."""

from typing import Any

import fitz
import pytest

from lupa.ingestao import fronteiras
from lupa.ingestao.fronteiras import (
    FORTE,
    FRACA,
    ORIGEM,
    conferir_origem,
    nivel,
    pontuar,
    regras_padrao,
    segmentar,
    sinais_ativos,
)
from lupa.ingestao.sinais import medir_sinais
from lupa.ingestao.sinais_fronteira import (
    corpo,
    e_assinatura,
    linhas_repetidas,
    mascara,
    medir_sinais_fronteira,
    reconhecer_titulo,
    sinais_do_arquivo,
    titulos_padrao,
)

CABECALHO = "PODER JUDICIÁRIO - COMARCA DE VILA ESPERANÇA\nVara Criminal - Processo nº 1\n"
ASSINATURA = "Documento assinado eletronicamente por Fulano, Juiz de Direito, em 10/01/2020."
RODAPE = "Documento assinado digitalmente. Código de autenticação: ABCDEF0123456789ABCD"


def _pagina(corpo_texto: str, folha: int) -> str:
    return f"{CABECALHO}{corpo_texto}\nFls. {folha}\n{RODAPE}{folha}\n"


def _documento() -> list[str]:
    return [
        _pagina("DENÚNCIA\nO MINISTÉRIO PÚBLICO vem oferecer denúncia.\nParágrafo.", 1),
        _pagina(f"Continuação da denúncia.\n{ASSINATURA}", 2),
        _pagina("SENTENÇA\nVistos e examinados.\nÉ o relatório.", 3),
        _pagina("Fundamentação.\nRAZÕES DE APELAÇÃO\nTexto.", 4),
        _pagina(f"Dispositivo.\n{ASSINATURA}", 5),
        "",
        _pagina("CERTIDÃO DE PUBLICAÇÃO\nCertifico que.\nO referido é verdade e dou fé.", 7),
    ]


def _sinais(textos: list[str]) -> list[dict[str, Any]]:
    return sinais_do_arquivo([{"numero": n, "texto": t} for n, t in enumerate(textos, 1)])


def test_cabecalho_e_rodape_repetidos_saem_do_corpo() -> None:
    """Linhas que se repetem no topo e no fim das folhas não entram no corpo."""
    textos = _documento()
    repetidas = linhas_repetidas(textos)
    assert mascara("Fls. 12") in repetidas
    assert corpo(textos[0], repetidas)[0] == "DENÚNCIA"
    assert all("Código" not in linha for linha in corpo(textos[1], repetidas))


def test_titulo_reconhecido_com_variacao_e_erro_de_ocr() -> None:
    """Variação cadastrada e erro leve de OCR casam; frase comum não."""
    lista = titulos_padrao()
    assert reconhecer_titulo("Certidão de Intimação", lista).titulo == "CERTIDAO"  # type: ignore[union-attr]
    assert reconhecer_titulo("SENTENCA.", lista).tipo == "sentenca"  # type: ignore[union-attr]
    assert reconhecer_titulo("CONTRARRAZÔES DE APELACÀO", lista) is not None
    assert reconhecer_titulo("Vistos e examinados.", lista) is None
    assert reconhecer_titulo("x" * 90, lista) is None


def test_assinatura_tolera_ocr_e_recusa_rodape_de_autenticacao() -> None:
    """A linha de assinatura vale mesmo truncada; o rodapé de autenticação não."""
    assert e_assinatura(ASSINATURA)
    assert e_assinatura("Documento assinado eletronicame:«e por X, Perito Criminal, em 1/1/2020")
    assert not e_assinatura(RODAPE)
    assert not e_assinatura("Documento assinado digitalmente. Codigo de amentcação: 12")
    assert not e_assinatura("Assinado o termo, prosseguiu-se.")


def test_sinais_por_pagina() -> None:
    """Título, assinatura no fim, número da folha, protocolo e vazia."""
    sinais = _sinais(_documento())
    assert (sinais[0]["titulo"], sinais[0]["titulo_linha"]) == ("DENUNCIA", 0)
    assert sinais[0]["reinicio_numeracao"] is True
    assert sinais[1]["assinatura_fim"] is True and sinais[1]["titulo"] is None
    assert sinais[3]["titulo"] == "RAZOES DE APELACAO" and sinais[3]["titulo_secao"] is True
    assert sinais[5] == {"vazia": True, "versao_titulos": "1", "tipo_pagina": None}
    assert sinais[2]["numero_folha"] == 3
    protocolo = medir_sinais_fronteira("Protocolo nº 123\nPETIÇÃO", {}, frozenset())
    assert protocolo["protocolo_topo"] is True


def test_layout_em_duas_colunas_e_fonte_dominante() -> None:
    """Caixas das linhas dão altura mediana, margem e quantidade de colunas."""
    esquerda = [{"bbox": [70, 100 + 15 * i, 280, 110 + 15 * i]} for i in range(10)]
    direita = [{"bbox": [300, 100 + 15 * i, 535, 110 + 15 * i]} for i in range(10)]
    duas = medir_sinais_fronteira("a\nb", {"linhas": esquerda + direita}, frozenset())
    uma = medir_sinais_fronteira(
        "a", {"blocos": [{"linhas": [{"bbox": [70, 100, 535, 113]}]}]}, frozenset()
    )
    assert (duas["colunas"], duas["altura_linha"]) == (2, 10.0)
    assert (uma["colunas"], uma["margem_esquerda"]) == (1, 70)
    assert medir_sinais_fronteira("a", {}, frozenset())["colunas"] == 0


def test_pontuacao_titulo_com_assinatura_e_forte_e_so_titulo_e_fraca() -> None:
    """Pesos do YAML: título + assinatura anterior passa do limiar forte."""
    regras = regras_padrao()
    anterior = {"assinatura_fim": True, "vazia": False}
    atual = {"titulo": "SENTENCA", "titulo_secao": False, "vazia": False}
    assert pontuar(None, atual) == 1.0
    assert nivel(pontuar(anterior, atual)) == FORTE
    assert nivel(pontuar({"vazia": False}, atual)) == FRACA
    secao = atual | {"titulo_secao": True}
    assert pontuar({"vazia": False}, secao) == regras.pesos["titulo_secao"]
    assert nivel(pontuar({"vazia": False}, secao)) is None
    assert pontuar(anterior, {"vazia": True}) == 0.0
    assert sinais_ativos(anterior, {"vazia": True}) == []


def test_mudancas_de_fonte_cabecalho_e_numeracao_somam() -> None:
    """Sinais fracos entram na soma, cada um com seu peso."""
    comum: dict[str, Any] = {"tipo_pagina": "nativa"}
    anterior = comum | {"cabecalho": "AAAA | BBBB", "altura_linha": 10.0, "colunas": 1}
    atual = comum | {"cabecalho": "ZZZZZZ | YYYY", "altura_linha": 14.0, "colunas": 2,
                     "reinicio_numeracao": True, "protocolo_topo": True}  # fmt: skip
    ativos = sinais_ativos(anterior, atual)
    assert ativos == [
        "reinicio_numeracao", "cabecalho_novo", "protocolo_topo", "mudanca_fonte",
        "mudanca_layout",
    ]  # fmt: skip
    assert pontuar(anterior, atual) == pytest.approx(0.65)


def test_segmentar_documento_pula_verso_e_secao() -> None:
    """Peças começam em 1, 3 e 7; razões dentro da sentença e verso em branco não."""
    encontradas = segmentar(_sinais(_documento()))
    assert [f.posicao for f in encontradas] == [0, 2, 6]
    assert [f.nivel for f in encontradas] == [FORTE, FORTE, FORTE]


def test_origem_errada_gera_divergencias_dos_dois_lados() -> None:
    """Fronteira da origem deslocada: sem sinal forte num lado, sinal forte sem origem no outro."""
    sinais = _sinais(_documento())
    origem = [(0, {"fonte": "indice"}), (3, {"fonte": "indice"}), (6, {"fonte": "indice"})]
    encontradas, divergencias = conferir_origem(sinais, origem)
    assert [f.nivel for f in encontradas] == [ORIGEM] * 3
    assert [f.divergente for f in encontradas] == [False, True, False]
    assert [(d["pagina"], d["motivo"]) for d in divergencias] == [
        (2, "sinal_forte_sem_origem"),
        (3, "origem_sem_sinal_forte"),
    ]
    certas: list[tuple[int, dict[str, Any]]] = [(0, {}), (2, {}), (6, {})]
    assert conferir_origem(sinais, certas)[1] == []


def test_regras_e_titulos_sao_versionados() -> None:
    """Os dois YAML têm versão e os limiares são coerentes."""
    regras = fronteiras.regras_padrao()
    assert regras.versao and titulos_padrao().versao
    assert 0 < regras.fraca < regras.forte <= 1


def test_texto_branco_conta_como_invisivel_com_alfa_do_pymupdf() -> None:
    """PyMuPDF 1.25 devolve o branco como -1 (com alfa); a máscara 0xFFFFFF o reconhece (4E.0)."""
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), "Texto visível da página com conteúdo suficiente.")
    pagina.insert_text((72, 120), "instrucao escondida", color=(1, 1, 1))
    assert medir_sinais(pagina)["caracteres_invisiveis"] == len("instrucaoescondida")
