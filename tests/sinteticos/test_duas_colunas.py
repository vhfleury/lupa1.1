"""Layout em duas colunas (4E.0): ordem de leitura no gabarito e na extração nativa."""

import fitz

from lupa.dominio.enums import TipoPeca
from lupa.ingestao.texto_nativo import extrair_texto_nativo
from lupa.sinteticos.gabarito import Composicao, Elemento
from lupa.sinteticos.gerador import gerar_conteudo
from lupa.sinteticos.paginacao import LARGURA_COLUNA, MARGEM_ESQUERDA
from lupa.sinteticos.render import TEXTO_MARCA_DAGUA
from lupa.sinteticos.roteiro import Configuracao

SO_NATIVA = {Composicao.NATIVA: 1.0}
TIPOS = (TipoPeca.LAUDO, TipoPeca.TERMO_DEPOIMENTO)


def _conteudo(duas: tuple[TipoPeca, ...]):  # type: ignore[no-untyped-def]
    config = Configuracao(
        semente=31, paginas_alvo=30, mistura=SO_NATIVA, proporcao_vazias=0.0, duas_colunas=duas
    )
    return gerar_conteudo(config)


def test_pecas_escolhidas_saem_em_duas_colunas_com_marcacao() -> None:
    """Folhas de laudo e termo de depoimento levam o elemento e linhas na coluna direita."""
    conteudo = _conteudo(TIPOS)
    tipos = {p.indice: p.tipo for p in conteudo.pecas}
    marcadas = [p for p in conteudo.paginas if Elemento.DUAS_COLUNAS in p.elementos]
    assert marcadas
    assert all(tipos[p.peca] in TIPOS for p in marcadas)
    assert not any(
        Elemento.DUAS_COLUNAS in p.elementos for p in conteudo.paginas if tipos[p.peca] not in TIPOS
    )
    xs = {round(b[0]) for b in conteudo.documento[marcadas[0].numero - 1].get_text("blocks")}
    assert any(x > MARGEM_ESQUERDA + LARGURA_COLUNA for x in xs)


def test_extracao_nativa_segue_a_ordem_de_leitura_do_gabarito() -> None:
    """A coluna esquerda inteira vem antes da direita no texto extraído."""
    conteudo = _conteudo(TIPOS)
    marcadas = [p for p in conteudo.paginas if Elemento.DUAS_COLUNAS in p.elementos]
    iguais = sum(
        extrair_texto_nativo(conteudo.documento[p.numero - 1])
        .texto.replace(TEXTO_MARCA_DAGUA, "")
        .split()
        == p.texto.split()
        for p in marcadas
    )
    assert iguais == len(marcadas)


def test_sem_configuracao_nada_muda() -> None:
    """Sem tipos em duas colunas, nenhuma folha recebe o elemento (referências intactas)."""
    conteudo = _conteudo(())
    assert not any(Elemento.DUAS_COLUNAS in p.elementos for p in conteudo.paginas)
    assert isinstance(conteudo.documento, fitz.Document)
