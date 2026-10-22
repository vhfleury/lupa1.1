"""Gera o conteúdo de um processo sintético: PDF das folhas e partes do gabarito.

Fluxo: roteiro (texto e datas) → paginação (linhas e offsets) → composição de cada folha
(nativa, digitalizada, híbrida, vazia, capa) → desenho em PDF → ruídos (carimbos, marca d'água,
injeções ocultas) → eventos e resultado esperado das validações, calculado pelo próprio motor
do Lupa a partir dos eventos do gabarito.
"""

import random
from dataclasses import dataclass
from datetime import date
from uuid import NAMESPACE_URL, UUID, uuid5

import fitz

from lupa.dominio.enums import TipoFato
from lupa.dominio.esquemas import Evidencia, Fato
from lupa.sinteticos import render
from lupa.sinteticos.gabarito import (
    COM_IMAGEM,
    TIPO_POR_COMPOSICAO,
    Composicao,
    Degradacao,
    Elemento,
    EventoGabarito,
    InjecaoGabarito,
    PaginaGabarito,
    PecaGabarito,
    ResultadoEsperado,
    VetorInjecao,
)
from lupa.sinteticos.injecao import INJECOES, OCULTOS_NA_PAGINA, ROTULO, VISIVEIS, texto_visivel
from lupa.sinteticos.paginacao import FONTE, LARGURA, PaginaPlano, paginar
from lupa.sinteticos.roteiro import Configuracao, Roteiro, montar_roteiro
from lupa.validacoes.adaptador import para_modelo
from lupa.validacoes.motor import executar_catalogo

_TIPOS_FATO = {t.value for t in TipoFato}
TENTATIVAS_TAMANHO = 6
PESOS_DEGRADACAO = {Degradacao.LEVE: 0.4, Degradacao.MEDIA: 0.4, Degradacao.FORTE: 0.2}


@dataclass
class Conteudo:
    """Processo gerado, antes do empacotamento.

    Attributes:
        roteiro: Roteiro de origem.
        documento: PDF com todas as folhas de conteúdo, em ordem.
        pecas: Peças do gabarito.
        paginas: Folhas do gabarito.
        eventos: Eventos do gabarito.
        resultado_esperado: Resultado das três validações.
        injecoes: Injeções plantadas.
    """

    roteiro: Roteiro
    documento: fitz.Document
    pecas: tuple[PecaGabarito, ...]
    paginas: tuple[PaginaGabarito, ...]
    eventos: tuple[EventoGabarito, ...]
    resultado_esperado: tuple[ResultadoEsperado, ...]
    injecoes: tuple[InjecaoGabarito, ...]

    @property
    def numero(self) -> str:
        """Número CNJ do processo."""
        return self.roteiro.partes.numero

    @property
    def referencia(self) -> date:
        """Data de referência das validações."""
        return self.roteiro.linha.referencia


def _sortear(rng: random.Random, pesos: dict[Composicao, float] | dict[Degradacao, float]) -> str:
    chaves = list(pesos)
    return str(rng.choices(chaves, weights=[pesos[k] for k in chaves])[0])  # type: ignore[index]


def _paginas_forcadas_nativas(
    roteiro: Roteiro, planos: list[PaginaPlano]
) -> dict[int, VetorInjecao]:
    alvos: dict[int, VetorInjecao] = {}
    for vetor in roteiro.configuracao.injecoes:
        if vetor not in OCULTOS_NA_PAGINA:
            continue
        tipo = OCULTOS_NA_PAGINA[vetor]
        indice = next(
            i for i, p in enumerate(roteiro.pecas, start=1) if p.tipo == tipo and not p.capa
        )
        folha = next(p.numero for p in planos if p.peca == indice and not p.vazia)
        alvos[folha] = vetor
    return alvos


def escolher_composicao(
    plano: PaginaPlano, config: Configuracao, rng: random.Random, forcar_nativa: bool
) -> Composicao:
    """Escolhe como fabricar a folha, respeitando a mistura da configuração.

    Args:
        plano: Folha paginada.
        config: Configuração (mistura de composições).
        rng: Gerador semeado.
        forcar_nativa: Folha que recebe injeção oculta (precisa de camada de texto).

    Returns:
        Composição.
    """
    if plano.vazia:
        return Composicao.VAZIA
    if plano.capa:
        return Composicao.CAPA
    escolha = Composicao(_sortear(rng, config.mistura))
    tem_assinatura = any(linha.papel == "assinatura" for linha in plano.linhas)
    if escolha == Composicao.HIBRIDA_ASSINATURA and not tem_assinatura:
        escolha = Composicao.HIBRIDA_CORPO
    if forcar_nativa and escolha in COM_IMAGEM:
        return Composicao.NATIVA
    return escolha


def _aplicar_oculta(pagina: fitz.Page, vetor: VetorInjecao) -> None:
    texto = INJECOES[vetor].texto
    if vetor == VetorInjecao.TEXTO_BRANCO:
        escritor = fitz.TextWriter(pagina.rect, color=(1, 1, 1))
        escritor.append((72, 740), texto, font=FONTE, fontsize=1)
        escritor.write_text(pagina)
    elif vetor == VetorInjecao.FORA_DA_PAGINA:
        escritor = fitz.TextWriter(pagina.rect)
        escritor.append((72, 900), texto, font=FONTE, fontsize=10)
        escritor.write_text(pagina)
    elif vetor == VetorInjecao.ANOTACAO:
        pagina.add_text_annot(fitz.Point(LARGURA - 50, 120), texto)
    else:
        png = render.imagem_texto(texto.replace(": ", ":|"), (20, 20, 20), 640, 0.0)
        pagina.insert_image(fitz.Rect(80, 600, 480, 660), stream=png, keep_proportion=True)


def _desenhar_pagina(
    documento: fitz.Document,
    plano: PaginaPlano,
    config: Configuracao,
    rng: random.Random,
    oculta: VetorInjecao | None,
    carimbo: bool,
) -> PaginaGabarito:
    composicao = escolher_composicao(plano, config, rng, oculta is not None)
    nivel = Degradacao(_sortear(rng, PESOS_DEGRADACAO)) if composicao in COM_IMAGEM else None
    pagina, digitalizacao = render.desenhar(documento, plano, composicao, nivel, rng)
    elementos: list[Elemento] = []
    if not plano.vazia:
        elementos += [Elemento.CABECALHO_REPETIDO, Elemento.RODAPE_AUTENTICACAO]
        if plano.marca_dagua:
            elementos.append(Elemento.MARCA_DAGUA)
        if carimbo:
            render.carimbar(pagina, f"JUNTADA|Fls. {plano.numero}", rng)
            elementos.append(Elemento.CARIMBO)
    if plano.duas_colunas:
        elementos.append(Elemento.DUAS_COLUNAS)
    if oculta is not None:
        _aplicar_oculta(pagina, oculta)
    if oculta is not None or any(m.rotulo == ROTULO for m in plano.marcas):
        elementos.append(Elemento.INJECAO)
    return PaginaGabarito(
        numero=plano.numero,
        peca=plano.peca,
        tipo=TIPO_POR_COMPOSICAO[composicao],
        composicao=composicao,
        degradacao=digitalizacao.degradacao if digitalizacao else None,
        dpi=digitalizacao.dpi if digitalizacao else None,
        rotacao_graus=digitalizacao.rotacao if digitalizacao else None,
        elementos=tuple(elementos),
        texto=plano.texto,
        texto_camada=str(pagina.get_text()),
    )


def _pecas(roteiro: Roteiro, planos: list[PaginaPlano]) -> tuple[PecaGabarito, ...]:
    pecas = []
    for indice, plano in enumerate(roteiro.pecas, start=1):
        folhas = [p.numero for p in planos if p.peca == indice]
        pecas.append(
            PecaGabarito(
                indice=indice, tipo=plano.tipo, origem=plano.origem, titulo=plano.titulo,
                pagina_inicial=min(folhas), pagina_final=max(folhas), data=plano.data,
                tipo_data=plano.tipo_data,
            )
        )  # fmt: skip
    return tuple(pecas)


def _valor_json(valor: object) -> object:
    return valor.isoformat() if isinstance(valor, date) else valor


def _eventos_e_injecoes(
    planos: list[PaginaPlano], ocultas: dict[int, VetorInjecao]
) -> tuple[tuple[EventoGabarito, ...], tuple[InjecaoGabarito, ...]]:
    eventos: list[EventoGabarito] = []
    injecoes: list[InjecaoGabarito] = []
    for plano in planos:
        texto = plano.texto
        for marca in plano.marcas:
            trecho = texto[marca.inicio : marca.fim]
            if marca.rotulo == ROTULO:
                vetor = next(v for v in VISIVEIS if texto_visivel(v) == trecho.replace("\n", " "))
                injecoes.append(
                    InjecaoGabarito(
                        vetor=vetor, objetivo=INJECOES[vetor].objetivo, pagina=plano.numero,
                        texto=INJECOES[vetor].texto, visivel=True,
                    )
                )  # fmt: skip
            elif marca.rotulo in _TIPOS_FATO:
                eventos.append(
                    EventoGabarito(
                        tipo=TipoFato(marca.rotulo), valor=_valor_json(marca.valor),
                        pagina=plano.numero, trecho=trecho, inicio=marca.inicio, fim=marca.fim,
                    )
                )  # fmt: skip
    for folha, vetor in sorted(ocultas.items()):
        injecoes.append(
            InjecaoGabarito(
                vetor=vetor, objetivo=INJECOES[vetor].objetivo, pagina=folha,
                texto=INJECOES[vetor].texto, visivel=vetor == VetorInjecao.IMAGEM_COM_TEXTO,
            )
        )  # fmt: skip
    return tuple(eventos), tuple(injecoes)


def fatos_do_gabarito(numero: str, eventos: tuple[EventoGabarito, ...]) -> list[Fato]:
    """Converte eventos do gabarito em fatos do domínio (ids determinísticos).

    Args:
        numero: Número CNJ (base dos ids).
        eventos: Eventos do gabarito.

    Returns:
        Fatos prontos para o motor de validações.
    """
    processo_id = uuid5(NAMESPACE_URL, f"lupa-sintetico:{numero}")
    fatos = []
    for i, evento in enumerate(eventos):
        pagina_id = uuid5(processo_id, f"folha:{evento.pagina}")
        evidencia = Evidencia(
            id=uuid5(processo_id, f"evidencia:{i}"), pagina_id=pagina_id, trecho=evento.trecho,
            inicio=evento.inicio, fim=evento.fim,
        )  # fmt: skip
        fatos.append(
            Fato(
                id=uuid5(processo_id, f"fato:{i}"), processo_id=processo_id, tipo=evento.tipo,
                valor=evento.valor, evidencias=(evidencia,), extraido_por="gabarito-sintetico",
                versao_extrator="1", confianca=1.0,
            )
        )  # fmt: skip
    return fatos


def resultado_esperado(
    numero: str, eventos: tuple[EventoGabarito, ...], referencia: date
) -> tuple[ResultadoEsperado, ...]:
    """Executa o catálogo criminal sobre os eventos do gabarito.

    Args:
        numero: Número CNJ.
        eventos: Eventos do gabarito.
        referencia: Data de referência.

    Returns:
        Um resultado esperado por validação.
    """
    achados = executar_catalogo(
        para_modelo(fatos_do_gabarito(numero, eventos)), "criminal", referencia
    )
    return tuple(
        ResultadoEsperado(
            validacao=a.validacao, resultado=a.resultado, valores=a.valores,
            explicacao=a.explicacao,
        )
        for a in achados
    )  # fmt: skip


def _folhas_com_carimbo(
    roteiro: Roteiro, planos: list[PaginaPlano], rng: random.Random
) -> set[int]:
    escolhidas = {p.numero for p in planos if not p.vazia and rng.random() < 0.12}
    recebimento = next(i for i, p in enumerate(roteiro.pecas, start=1) if p.tipo == "recebimento")
    escolhidas.add(next(p.numero for p in planos if p.peca == recebimento))
    return escolhidas


def _paginar_no_alvo(config: Configuracao) -> tuple[Roteiro, list[PaginaPlano], random.Random]:
    alvo = config.paginas_alvo
    for _ in range(TENTATIVAS_TAMANHO):
        roteiro = montar_roteiro(config, alvo)
        rng = random.Random(config.semente * 7919 + 1)  # noqa: S311
        planos = paginar(roteiro, rng)
        if abs(len(planos) - config.paginas_alvo) <= max(3, config.paginas_alvo // 50):
            break
        alvo = max(1, round(alvo * config.paginas_alvo / len(planos)))
    return roteiro, planos, rng


def gerar_conteudo(config: Configuracao) -> Conteudo:
    """Gera o PDF de conteúdo e as partes do gabarito comuns aos três cenários.

    Args:
        config: Configuração do processo.

    Returns:
        Conteúdo gerado.
    """
    roteiro, planos, rng = _paginar_no_alvo(config)
    ocultas = _paginas_forcadas_nativas(roteiro, planos)
    carimbos = _folhas_com_carimbo(roteiro, planos, rng)
    documento = fitz.open()
    paginas = tuple(
        _desenhar_pagina(documento, p, config, rng, ocultas.get(p.numero), p.numero in carimbos)
        for p in planos
    )
    eventos, injecoes = _eventos_e_injecoes(planos, ocultas)
    if VetorInjecao.METADADO_XMP in config.injecoes:
        injecoes += (
            InjecaoGabarito(
                vetor=VetorInjecao.METADADO_XMP,
                objetivo=INJECOES[VetorInjecao.METADADO_XMP].objetivo,
                pagina=None,
                texto=INJECOES[VetorInjecao.METADADO_XMP].texto,
                visivel=False,
            ),
        )
    numero = roteiro.partes.numero
    return Conteudo(
        roteiro, documento, _pecas(roteiro, planos), paginas, eventos,
        resultado_esperado(numero, eventos, roteiro.linha.referencia), injecoes,
    )  # fmt: skip


def id_processo(numero: str) -> UUID:
    """UUID determinístico do processo sintético.

    Args:
        numero: Número CNJ.

    Returns:
        UUID v5.
    """
    return uuid5(NAMESPACE_URL, f"lupa-sintetico:{numero}")
