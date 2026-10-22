"""4B.1: esquema do gabarito aceita o gerado e rejeita gabaritos inconsistentes."""

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from lupa.sinteticos.gabarito import VALIDACOES_CRIMINAIS, Gabarito

Mutacao = Callable[[dict[str, Any]], None]


def _mutado(gabarito: Gabarito, mutacao: Mutacao) -> dict[str, Any]:
    dados = gabarito.model_dump(mode="json")
    mutacao(dados)
    return dados


def test_gabarito_gerado_passa_no_esquema_e_cobre_as_tres_validacoes(gabarito: Gabarito) -> None:
    """Gabarito gerado passa no esquema e cobre as tres validacoes."""
    assert sorted(r.validacao for r in gabarito.resultado_esperado) == sorted(VALIDACOES_CRIMINAIS)
    assert gabarito.pagina(1).numero == 1
    assert Gabarito.model_validate_json(gabarito.model_dump_json()) == gabarito


def _primeiro_evento(d: dict[str, Any]) -> dict[str, Any]:
    evento: dict[str, Any] = d["eventos"][0]
    return evento


def _pagina_nativa(d: dict[str, Any]) -> dict[str, Any]:
    pagina: dict[str, Any] = next(p for p in d["paginas"] if p["composicao"] == "nativa")
    return pagina


def _pagina(d: dict[str, Any], composicao: str) -> dict[str, Any]:
    pagina: dict[str, Any] = next(p for p in d["paginas"] if p["composicao"] == composicao)
    return pagina


MUTACOES: dict[str, Mutacao] = {
    "offset_errado": lambda d: _primeiro_evento(d).update(
        inicio=_primeiro_evento(d)["inicio"] + 1, fim=_primeiro_evento(d)["fim"] + 1
    ),
    "tamanho_do_trecho": lambda d: _primeiro_evento(d).update(fim=_primeiro_evento(d)["fim"] + 1),
    "evento_em_folha_inexistente": lambda d: _primeiro_evento(d).update(pagina=99999),
    "tipo_de_fato_desconhecido": lambda d: _primeiro_evento(d).update(tipo="data_inventada"),
    "peca_com_lacuna": lambda d: d["pecas"][1].update(
        pagina_inicial=d["pecas"][1]["pagina_inicial"] + 1
    ),
    "peca_invertida": lambda d: d["pecas"][0].update(pagina_final=0),
    "pecas_nao_cobrem_tudo": lambda d: d["pecas"].pop(),
    "folha_de_outra_peca": lambda d: d["paginas"][0].update(peca=2),
    "tipo_de_peca_invalido": lambda d: d["pecas"][0].update(tipo="memorial"),
    "numeracao_de_folhas": lambda d: d["paginas"][0].update(numero=2),
    "tipo_incompativel": lambda d: _pagina_nativa(d).update(tipo="ocr"),
    "nativa_com_degradacao": lambda d: _pagina_nativa(d).update(degradacao="leve"),
    "digitalizada_sem_degradacao": lambda d: _pagina(d, "digitalizada").update(degradacao=None),
    "digitalizada_com_camada": lambda d: _pagina(d, "digitalizada").update(texto_camada="x"),
    "vazia_com_texto": lambda d: _pagina(d, "vazia").update(texto="algo"),
    "sem_validacao": lambda d: d["resultado_esperado"].pop(),
    "resultado_invalido": lambda d: d["resultado_esperado"][0].update(resultado="talvez"),
    "cnj_invalido": lambda d: d["processo"].update(numero_cnj="0000001-00.2020.8.99.0001"),
    "diagnostico_trocado": lambda d: d["processo"].update(diagnostico_esperado="zip_por_peca"),
    "arquivo_sem_folha": lambda d: d["arquivos"][0].update(folhas=d["arquivos"][0]["folhas"][1:]),
    "versao_desconhecida": lambda d: d.update(versao_esquema="99"),
    "campo_extra": lambda d: d.update(comentario="x"),
}


@pytest.mark.parametrize("nome", sorted(MUTACOES))
def test_gabarito_inconsistente_e_rejeitado(gabarito: Gabarito, nome: str) -> None:
    """Gabarito inconsistente e rejeitado."""
    with pytest.raises(ValidationError):
        Gabarito.model_validate(_mutado(gabarito, MUTACOES[nome]))
