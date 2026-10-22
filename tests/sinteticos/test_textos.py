"""4B.2: templates, identidades inventadas e coerência entre texto e gabarito."""

import random
from datetime import date

import pytest

from lupa.dominio.cnj import validar_numero_cnj
from lupa.sinteticos import identidades as ids
from lupa.sinteticos.gabarito import Gabarito
from lupa.sinteticos.roteiro import Configuracao, montar_roteiro
from lupa.sinteticos.textos import carregar_template, extrair_marcas, renderizar_texto

TEMPLATES = (
    "denuncia", "recebimento", "decisao_prisao", "revisao_prisao", "laudo", "termo_depoimento",
    "sentenca", "certidao_publicacao", "certidao_intimacao_mp", "certidao_intimacao_defesa",
    "certidao_intimacao_reu", "recurso", "contrarrazoes", "acordao", "juntada", "enchimento",
)  # fmt: skip


def test_nenhum_cpf_gerado_e_valido() -> None:
    """Nenhum cpf gerado e valido."""
    rng = random.Random(1)  # noqa: S311
    cpfs = [ids.gerar_cpf_invalido(rng) for _ in range(5000)]
    assert not any(ids.cpf_valido(c) for c in cpfs)
    assert all(len(c) == 14 for c in cpfs)


def test_conferencia_de_cpf_reconhece_valido_e_rejeita_repetido() -> None:
    """Conferencia de cpf reconhece valido e rejeita repetido."""
    assert ids.cpf_valido("529.982.247-25")
    assert not ids.cpf_valido("111.111.111-11")
    assert not ids.cpf_valido("123")


def test_numero_cnj_valido_no_digito_e_na_faixa_de_teste() -> None:
    """Numero cnj valido no digito e na faixa de teste."""
    rng = random.Random(2)  # noqa: S311
    for _ in range(200):
        numero = ids.gerar_numero_cnj(rng, 2020)
        assert validar_numero_cnj(numero) == numero
        assert numero.split(".")[2:4] == [ids.JUSTICA_TESTE, ids.TRIBUNAL_TESTE]
        sequencial = int(numero[:7])
        assert ids.FAIXA_SEQUENCIAL_TESTE[0] <= sequencial <= ids.FAIXA_SEQUENCIAL_TESTE[1]


@pytest.mark.parametrize("nome", TEMPLATES)
def test_templates_existem_e_tem_conteudo(nome: str) -> None:
    """Templates existem e tem conteudo."""
    assert carregar_template(nome).strip()


def test_mesma_semente_gera_mesmo_texto_e_semente_diferente_varia() -> None:
    """Mesma semente gera mesmo texto e semente diferente varia."""

    def textos(semente: int) -> list[str]:
        roteiro = montar_roteiro(Configuracao(semente=semente, paginas_alvo=20))
        return [p.texto for peca in roteiro.pecas for p in peca.paragrafos]

    assert textos(11) == textos(11)
    assert textos(11) != textos(12)


def test_marcas_sao_removidas_e_offsets_apontam_o_trecho() -> None:
    """Marcas sao removidas e offsets apontam o trecho."""
    paragrafo = extrair_marcas("Antes {{data_fato:em 01/02/2020}} e {{data_denuncia:hoje}}.")
    assert paragrafo.texto == "Antes em 01/02/2020 e hoje."
    trechos = [paragrafo.texto[m.inicio : m.fim] for m in paragrafo.marcas]
    assert trechos == ["em 01/02/2020", "hoje"]


def test_escolhas_e_variaveis_sao_resolvidas() -> None:
    """Escolhas e variaveis sao resolvidas."""
    paragrafos = renderizar_texto("[[a||b]] $x\n\n\n\nsegundo", {"x": "valor"}, random.Random(3))  # noqa: S311
    assert [p.texto for p in paragrafos][1] == "segundo"
    assert paragrafos[0].texto in ("a valor", "b valor")


def test_datas_dos_eventos_aparecem_no_trecho_como_no_gabarito(gabarito: Gabarito) -> None:
    """Datas dos eventos aparecem no trecho como no gabarito."""
    for evento in gabarito.eventos:
        if not evento.tipo.startswith("data_"):
            continue
        dia = date.fromisoformat(evento.valor)
        formas = (dia.strftime("%d/%m/%Y"), ids.data_por_extenso(dia))
        trecho = " ".join(evento.trecho.split())
        assert any(f in trecho for f in formas), evento


def test_textos_nao_contem_cpf_valido(gabarito: Gabarito) -> None:
    """Textos nao contem cpf valido."""
    import re

    for pagina in gabarito.paginas:
        for cpf in re.findall(r"\d{3}\.\d{3}\.\d{3}-\d{2}", pagina.texto):
            assert not ids.cpf_valido(cpf)
