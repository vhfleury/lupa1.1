"""Índice do processo, tipo, origem e data da peça por regras (4E.3 a 4E.7)."""

from datetime import date
from typing import Any

from lupa.dominio.enums import OrigemPeca, TipoPeca
from lupa.ingestao.classificacao import (
    assinatura_da_peca,
    cargo_aproximado,
    classificar_origem,
    classificar_tipo,
)
from lupa.ingestao.data_peca import data_da_peca, interpretar
from lupa.ingestao.indice import montar_indice, pecas_saida, versoes
from lupa.sinteticos.gabarito import Cenario, Gabarito
from lupa.sinteticos.medicao import medir
from lupa.sinteticos.saida_pipeline import SaidaPipeline
from tests.ingestao.conftest import AutosSinteticos


def _paginas(gabarito: Gabarito) -> list[dict[str, Any]]:
    """Páginas físicas do cenário com o texto visível do gabarito (OCR perfeito)."""
    paginas: list[dict[str, Any]] = []
    for arquivo in gabarito.arquivos:
        for posicao, folha in enumerate(arquivo.folhas, start=1):
            texto = gabarito.pagina(folha).texto if folha else "Movimentação 1 - índice"
            paginas.append(
                {
                    "numero": len(paginas) + 1,
                    "tipo": gabarito.pagina(folha).tipo.value if folha else "nativa",
                    "texto": texto,
                    "coordenadas": {},
                    "flags": {"texto_oculto": True} if folha == 2 else {},
                    "origem_arquivo": arquivo.nome,
                    "pagina_origem": posicao,
                }
            )
    return paginas


def _fronteiras_origem(gabarito: Gabarito, deslocar: int | None = None) -> list[dict[str, Any]]:
    inicios = [p.pagina_inicial for p in gabarito.pecas]
    if deslocar is not None:
        inicios[deslocar] += 2
    return [
        {"peca": n, "fonte": "indice", "pagina": pagina, "titulo": "x", "data": None}
        for n, pagina in enumerate(inicios, start=1)
    ]


def test_indice_do_processo_sintetico_acerta_fronteira_tipo_origem_e_data(
    autos_sinteticos: AutosSinteticos,
) -> None:
    """Cenário liso com texto perfeito: tudo 100% e nenhuma peça inventada."""
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_LISO]
    paginas = _paginas(gabarito)
    resultado = montar_indice(paginas, {"fronteiras_origem": [], "sinais": {}})
    saida = SaidaPipeline(pecas=pecas_saida(resultado.pecas, paginas, "autos.pdf"))
    relatorio = medir(gabarito, saida)
    assert resultado.fonte == "regras"
    assert relatorio.fronteira.precisao == relatorio.fronteira.recall == 1.0
    assert relatorio.tipo_peca.acuracia == 1.0
    assert relatorio.origem_peca.acuracia == 1.0
    assert relatorio.data_peca is not None and relatorio.data_peca.acuracia == 1.0
    assert len(resultado.pecas) == len(gabarito.pecas)
    primeira = resultado.pecas[0]
    assert primeira.flags["paginas"] == {"texto_oculto": 1} or resultado.pecas[1].flags[
        "paginas"
    ] == {"texto_oculto": 1}
    for peca in resultado.pecas:
        evidencia = peca.evidencia_data
        assert evidencia is not None
        texto = paginas[evidencia["pagina"] - 1]["texto"]
        assert texto[evidencia["inicio"] : evidencia["fim"]] == evidencia["trecho"]
    assert set(versoes()) == {"fronteiras", "titulos", "classificacao"}


def test_indice_correto_nao_diverge_e_errado_gera_divergencia_marcada(
    autos_sinteticos: AutosSinteticos,
) -> None:
    """Índice com uma fronteira movida duas páginas: divergência listada e flag na peça."""
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_LISO]
    paginas = _paginas(gabarito)
    certo = montar_indice(paginas, {"fronteiras_origem": _fronteiras_origem(gabarito)})
    fortes = [p for p in certo.pecas if not p.classificacao["fronteira"]["divergente"]]
    assert certo.fonte == "indice"
    assert len(certo.divergencias) <= 1
    assert len(fortes) >= len(certo.pecas) - 1
    alvo = next(i for i, p in enumerate(gabarito.pecas) if p.pagina_final - p.pagina_inicial >= 2)
    errado = montar_indice(paginas, {"fronteiras_origem": _fronteiras_origem(gabarito, alvo)})
    motivos = {(d["pagina"], d["motivo"]) for d in errado.divergencias}
    inicio = gabarito.pecas[alvo].pagina_inicial
    assert (inicio + 2, "origem_sem_sinal_forte") in motivos
    assert (inicio, "sinal_forte_sem_origem") in motivos
    movida = next(p for p in errado.pecas if p.pagina_inicial == inicio + 2)
    assert movida.flags["peca"]["divergencia_fronteira"] is True
    anterior = next(p for p in errado.pecas if p.pagina_final == inicio + 1)
    assert anterior.flags["peca"]["divergencia_fronteira"] is True


def test_pdf_com_indice_ignora_paginas_de_indice_e_zip_usa_o_manifesto(
    autos_sinteticos: AutosSinteticos,
) -> None:
    """Páginas do índice ficam fora das peças; no ZIP, cada entrada é uma peça."""
    gabarito = autos_sinteticos.gabaritos[Cenario.PDF_INDICE]
    paginas = _paginas(gabarito)
    deslocamento = gabarito.arquivos[0].folhas.count(None)
    diagnostico = {"fronteiras_origem": [], "sinais": {"paginas_indice": deslocamento}}
    resultado = montar_indice(paginas, diagnostico)
    assert resultado.pecas[0].pagina_inicial == deslocamento + 1
    assert all(s.get("indice") for s in resultado.sinais[:deslocamento])
    zipado = autos_sinteticos.gabaritos[Cenario.ZIP_POR_PECA]
    paginas_zip = _paginas(zipado)
    inicio, manifesto = 1, []
    for ordem, arquivo in enumerate(zipado.arquivos, start=1):
        manifesto.append({"fonte": "manifesto", "pagina": 1, "pagina_continua": inicio,
                          "arquivo": arquivo.nome, "peca": ordem})  # fmt: skip
        inicio += len(arquivo.folhas)
    resultado_zip = montar_indice(paginas_zip, {"fronteiras_origem": manifesto})
    saida = SaidaPipeline(pecas=pecas_saida(resultado_zip.pecas, paginas_zip, "autos.zip"))
    relatorio = medir(zipado, saida)
    assert resultado_zip.fonte == "manifesto"
    assert relatorio.fronteira.precisao == relatorio.fronteira.recall == 1.0
    assert relatorio.tipo_peca.acuracia == 1.0


def test_bookmarks_e_indice_discordantes_viram_divergencia() -> None:
    """Duas fontes de origem com páginas diferentes: divergência `origens_discordam`."""
    paginas = [{"numero": n, "texto": f"SENTENÇA\nTexto {n}", "tipo": "nativa"} for n in (1, 2, 3)]
    origem = [
        {"fonte": "bookmark", "pagina": 1},
        {"fonte": "bookmark", "pagina": 3},
        {"fonte": "indice", "pagina": 1},
        {"fonte": "indice", "pagina": 2},
    ]
    resultado = montar_indice(paginas, {"fronteiras_origem": origem})
    assert resultado.fonte == "bookmark"
    assert {(d["pagina"], d["motivo"]) for d in resultado.divergencias} >= {
        (2, "origens_discordam"),
        (3, "origens_discordam"),
    }


def test_tipo_ambiguo_vira_outros_com_confianca_baixa() -> None:
    """Sem título nem fórmula, ou com empate, a peça é `outros` com confiança baixa."""
    vazio = classificar_tipo(["Texto qualquer sem marca."])
    assert (vazio.valor, vazio.motivo) == (TipoPeca.OUTROS.value, "sem_indicio")
    assert vazio.confianca < 0.5
    empate = classificar_tipo(["DECISÃO", "Recebo a denúncia; custódia cautelar."])
    assert (empate.valor, empate.motivo) == (TipoPeca.OUTROS.value, "ambiguo")
    recebimento = classificar_tipo(["DECISÃO", "Vistos.", "Assim, recebo a denúncia em 1/1/2020."])
    assert recebimento.valor == TipoPeca.RECEBIMENTO.value
    prisao = classificar_tipo(["DECISÃO", "Vistos.", "Decreto a prisão preventiva de X."])
    assert prisao.valor == TipoPeca.DECISAO_PRISAO.value
    sem_titulo = classificar_tipo(["Vistos e examinados.", "É o relatório.", "JULGO PROCEDENTE"])
    assert (sem_titulo.valor, sem_titulo.motivo) == (TipoPeca.SENTENCA.value, "formulas")


def test_origem_por_assinatura_cargo_aproximado_vocabulario_e_desconhecida() -> None:
    """Assinatura decide; cargo com erro de OCR é aproximado; sem nada, `desconhecida`."""
    assinada = classificar_origem(["Texto.", "Documento assinado eletronicamente por Y,",
                                   "Promotor de Justiça, em 1/1/2020."])  # fmt: skip
    assert (assinada.valor, assinada.motivo) == (OrigemPeca.MP.value, "assinatura")
    advogado = classificar_origem(["Assinado eletronicamente por Z, OAB/GO 1234, em 2/2/2020."])
    assert advogado.valor == OrigemPeca.DEFESA.value
    ocr = classificar_origem(["Documento assinado eletronicamente por W, Perivo rirúinal, em 1."])
    assert (ocr.valor, ocr.motivo) == (OrigemPeca.TERCEIRO.value, "assinatura_aproximada")
    vocabulario = classificar_origem(["O MINISTÉRIO PÚBLICO DO ESTADO vem apresentar."])
    assert (vocabulario.valor, vocabulario.motivo) == (OrigemPeca.MP.value, "vocabulario")
    nada = classificar_origem(["Texto sem autoria."])
    assert (nada.valor, nada.confianca) == (OrigemPeca.DESCONHECIDA.value, 0.0)
    conflito = classificar_origem(["Vistos.", "O Ministério Público requereu."])
    assert conflito.valor == OrigemPeca.DESCONHECIDA.value
    assert assinatura_da_peca(["sem assinatura"]) is None
    assert cargo_aproximado("xyz qwe") is None


def test_data_da_peca_com_evidencia_e_sem_invencao() -> None:
    """Protocolo vence assinatura; data inválida ou ausente não vira data."""
    textos = [
        "PETIÇÃO\nTermos em que pede deferimento. Petição protocolada em 9 de junho de 2025.",
        f"Vila Esperança, 08/06/2025.\n{'Documento assinado eletronicamente por A, Advogado,'}"
        "\nem 08/06/2025.\nDocumento assinado digitalmente. Código de autenticação: 12",
    ]
    achada = data_da_peca(textos)
    assert achada is not None
    assert (achada.data, achada.tipo_data, achada.pagina) == (date(2025, 6, 9), "protocolo", 0)
    assert textos[0][achada.inicio : achada.fim] == achada.trecho == "9 de junho de 2025"
    assinatura = data_da_peca(textos[1:])
    assert assinatura is not None
    assert (assinatura.data, assinatura.tipo_data) == (date(2025, 6, 8), "assinatura")
    juntada = data_da_peca(["Junto os documentos recebidos em 03/02/2019.", "recebido em 1/1/2020"])
    assert juntada is not None and juntada.data == date(2019, 2, 3)
    assert data_da_peca(["Sem data nenhuma.", "Ofício nº 12/2020."]) is None
    assert data_da_peca(["Documento assinado eletronicamente por A, em 31/02/2020."]) is None
    assert interpretar("12 de brumário de 2020") is None
    assert interpretar("01/01/1800") is None
