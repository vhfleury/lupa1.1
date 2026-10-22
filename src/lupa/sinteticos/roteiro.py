"""Roteiro do processo sintético: partes, linha do tempo, peças e parágrafos com eventos.

O roteiro é puro (sem PDF): a partir de uma ``Configuracao`` e da semente, decide o crime, as
datas, as peças em ordem cronológica e o texto de cada uma. As datas inseridas nos textos são as
mesmas que vão para o gabarito.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from lupa.dominio.enums import OrigemPeca, TipoFato, TipoPeca
from lupa.sinteticos import identidades as ids
from lupa.sinteticos.gabarito import Composicao, TipoData, VetorInjecao
from lupa.sinteticos.injecao import VISIVEIS, paragrafo_injecao
from lupa.sinteticos.textos import Paragrafo, enchimento, renderizar_peca

PARAGRAFOS_POR_PAGINA = 13


@dataclass(frozen=True)
class Crime:
    """Tipo penal usado na denúncia.

    Attributes:
        artigo: Dispositivo legal.
        conduta: Descrição da conduta.
        pena_meses: Pena máxima em abstrato, em meses.
        pena_texto: Pena por extenso, como aparece na denúncia.
    """

    artigo: str
    conduta: str
    pena_meses: int
    pena_texto: str


CRIMES_GRAVES = (
    Crime(
        "art. 155, caput, do Código Penal",
        "subtraiu, para si, um aparelho celular e uma carteira",
        48,
        "cuja pena é de reclusão, de 1 (um) a 4 (quatro) anos, e multa",
    ),
    Crime(
        "art. 157, caput, do Código Penal",
        "subtraiu, mediante grave ameaça exercida com simulação de arma, uma bolsa",
        120,
        "cuja pena é de reclusão, de 4 (quatro) a 10 (dez) anos, e multa",
    ),
    Crime(
        "art. 180, caput, do Código Penal",
        "adquiriu, em proveito próprio, uma motocicleta que sabia ser produto de crime",
        48,
        "cuja pena é de reclusão, de 1 (um) a 4 (quatro) anos, e multa",
    ),
)
CRIMES_LEVES = (
    Crime(
        "art. 129, caput, do Código Penal",
        "ofendeu a integridade corporal, desferindo socos",
        12,
        "cuja pena é de detenção, de 3 (três) meses a 1 (um) ano",
    ),
    Crime(
        "art. 147 do Código Penal",
        "ameaçou, por palavras, causar mal injusto e grave",
        6,
        "cuja pena é de detenção, de 1 (um) a 6 (seis) meses, ou multa",
    ),
)


@dataclass(frozen=True)
class Configuracao:
    """Parâmetros de geração de um processo.

    Attributes:
        semente: Semente de tudo o que é sorteado.
        paginas_alvo: Tamanho aproximado do processo em folhas.
        mistura: Proporção de composições das folhas de conteúdo (nativa, digitalizada, híbridas).
        tempestivo: Recurso no prazo (``None`` sorteia).
        prescrito: Prescrição pela pena em abstrato (``None`` sorteia).
        preventiva: ``conforme``, ``atencao``, ``ausente`` ou ``None`` (sorteia).
        injecoes: Vetores de injeção a plantar.
        proporcao_vazias: Chance de uma peça terminar com verso em branco.
        duas_colunas: Tipos de peça diagramados em duas colunas (4E.0; vazio nos dez processos
            de referência, para não mudá-los).
    """

    semente: int
    paginas_alvo: int = 40
    mistura: dict[Composicao, float] = field(
        default_factory=lambda: {
            Composicao.NATIVA: 0.6,
            Composicao.DIGITALIZADA: 0.25,
            Composicao.HIBRIDA_CORPO: 0.1,
            Composicao.HIBRIDA_ASSINATURA: 0.05,
        }
    )
    tempestivo: bool | None = None
    prescrito: bool | None = None
    preventiva: str | None = None
    injecoes: tuple[VetorInjecao, ...] = ()
    proporcao_vazias: float = 0.08
    duas_colunas: tuple[TipoPeca, ...] = ()


@dataclass
class PecaPlano:
    """Peça com texto e valores dos eventos marcados.

    Attributes:
        tipo: Tipo da peça.
        origem: Quem produziu.
        titulo: Título.
        data: Data da peça.
        tipo_data: O que a data representa.
        paragrafos: Texto paginável (título, corpo, assinatura).
        valores: Valor de cada evento marcado, por rótulo.
        capa: Se é a capa de autuação.
        marca_dagua: Se as folhas levam marca d'água.
        verso_branco: Se a peça termina com uma folha em branco.
    """

    tipo: TipoPeca
    origem: OrigemPeca
    titulo: str
    data: date
    tipo_data: TipoData
    paragrafos: list[Paragrafo]
    valores: dict[str, Any] = field(default_factory=dict)
    capa: bool = False
    marca_dagua: bool = False
    verso_branco: bool = False


@dataclass
class Partes:
    """Pessoas e dados fixos do processo.

    Attributes:
        numero: Número CNJ.
        reu: Nome do réu.
        variaveis: Variáveis comuns aos templates.
        crime: Crime imputado.
    """

    numero: str
    reu: str
    variaveis: dict[str, str]
    crime: Crime


@dataclass
class Linha:
    """Datas-chave do processo.

    Attributes:
        fato: Data do fato.
        nascimento: Nascimento do réu.
        denuncia: Oferecimento da denúncia.
        recebimento: Recebimento da denúncia.
        sentenca: Sentença.
        publicacao: Publicação da sentença.
        intimacao_mp: Intimação do MP.
        intimacao_defesa: Intimação do defensor.
        intimacao_reu: Intimação do réu.
        interposicao: Interposição da apelação.
        contrarrazoes: Contrarrazões.
        acordao: Acórdão.
        referencia: Data de referência das validações.
        decretacao: Decretação da preventiva, se houver.
        revisoes: Revisões da preventiva.
    """

    fato: date
    nascimento: date
    denuncia: date
    recebimento: date
    sentenca: date
    publicacao: date
    intimacao_mp: date
    intimacao_defesa: date
    intimacao_reu: date
    interposicao: date
    contrarrazoes: date
    acordao: date
    referencia: date
    decretacao: date | None
    revisoes: list[date]


@dataclass
class Roteiro:
    """Resultado do roteiro: partes, datas e peças em ordem.

    Attributes:
        configuracao: Configuração usada.
        partes: Partes e variáveis.
        linha: Linha do tempo.
        pecas: Peças na ordem dos autos (a primeira é a capa).
    """

    configuracao: Configuracao
    partes: Partes
    linha: Linha
    pecas: list[PecaPlano]


def _dias(rng: random.Random, minimo: int, maximo: int) -> timedelta:
    return timedelta(days=rng.randint(minimo, maximo))


def _revisoes(rng: random.Random, decretacao: date, referencia: date, estourar: bool) -> list[date]:
    revisoes: list[date] = []
    ultima = decretacao
    estouro_pendente = estourar
    while (referencia - ultima).days > 85:
        if estouro_pendente and (referencia - ultima).days > 160:
            passo = _dias(rng, 100, 150)
            estouro_pendente = False
        else:
            passo = _dias(rng, 55, 85)
        ultima = ultima + passo
        revisoes.append(ultima)
    return revisoes


def montar_linha(config: Configuracao, rng: random.Random, prescrito: bool) -> Linha:
    """Sorteia a linha do tempo coerente com os resultados pretendidos.

    Args:
        config: Configuração.
        rng: Gerador semeado.
        prescrito: Se a prescrição deve ocorrer entre recebimento e sentença.

    Returns:
        Datas do processo.
    """
    fato = date(rng.randint(2014, 2019), rng.randint(1, 12), rng.randint(1, 28))
    idade = rng.choice((19, 20)) if rng.random() < 0.25 else rng.randint(25, 60)
    nascimento = date(fato.year - idade, rng.randint(1, 12), rng.randint(1, 28))
    if nascimento + timedelta(days=365 * idade) > fato:
        nascimento = nascimento - timedelta(days=366)
    denuncia = fato + _dias(rng, 30, 180)
    recebimento = denuncia + _dias(rng, 5, 40)
    lacuna = _dias(rng, 1900, 2400) if prescrito else _dias(rng, 200, 900)
    sentenca = recebimento + lacuna
    publicacao = sentenca + _dias(rng, 0, 5)
    intimacao_mp = publicacao + _dias(rng, 1, 10)
    intimacao_defesa = publicacao + _dias(rng, 1, 15)
    intimacao_reu = publicacao + _dias(rng, 3, 30)
    ultima = max(intimacao_defesa, intimacao_reu)
    tempestivo = config.tempestivo if config.tempestivo is not None else rng.random() < 0.6
    interposicao = ultima + (_dias(rng, 0, 3) if tempestivo else _dias(rng, 9, 20))
    contrarrazoes = interposicao + _dias(rng, 8, 20)
    acordao = contrarrazoes + _dias(rng, 60, 200)
    referencia = acordao + _dias(rng, 10, 60)
    modo = config.preventiva or rng.choice(("conforme", "atencao", "ausente"))
    decretacao = None if modo == "ausente" else fato + _dias(rng, 2, 20)
    revisoes = (
        [] if decretacao is None else _revisoes(rng, decretacao, referencia, modo == "atencao")
    )
    return Linha(
        fato, nascimento, denuncia, recebimento, sentenca, publicacao, intimacao_mp,
        intimacao_defesa, intimacao_reu, interposicao, contrarrazoes, acordao, referencia,
        decretacao, revisoes,
    )  # fmt: skip


def montar_partes(rng: random.Random, prescrito: bool, ano: int) -> Partes:
    """Sorteia pessoas, número do processo e crime.

    Args:
        rng: Gerador semeado.
        prescrito: Se o crime deve ter pena baixa (prescrição alcançável).
        ano: Ano de autuação.

    Returns:
        Partes e variáveis comuns.
    """
    crime = rng.choice(CRIMES_LEVES if prescrito else CRIMES_GRAVES)
    reu = ids.gerar_nome(rng)
    variaveis = {
        "reu": reu,
        "cpf": ids.gerar_cpf_invalido(rng),
        "endereco": ids.gerar_endereco(rng),
        "vitima": ids.gerar_nome(rng),
        "testemunha": ids.gerar_nome(rng),
        "perito": ids.gerar_nome(rng),
        "defensor": ids.gerar_nome(rng),
        "relator": ids.gerar_nome(rng),
        "promotor": ids.gerar_nome(rng),
        "juiz": ids.gerar_nome(rng),
        "artigo": crime.artigo,
        "conduta": crime.conduta,
        "pena_texto": crime.pena_texto,
        "local": ids.gerar_endereco(rng),
        "hora": f"{rng.randint(0, 23)}h{rng.randint(0, 59):02d}",
    }
    return Partes(ids.gerar_numero_cnj(rng, ano), reu, variaveis, crime)


_TEMPLATE_PECA: dict[str, tuple[TipoPeca, OrigemPeca, TipoData]] = {
    "denuncia": (TipoPeca.DENUNCIA, OrigemPeca.MP, TipoData.PROTOCOLO),
    "recebimento": (TipoPeca.RECEBIMENTO, OrigemPeca.JUIZO, TipoData.ASSINATURA),
    "decisao_prisao": (TipoPeca.DECISAO_PRISAO, OrigemPeca.JUIZO, TipoData.ASSINATURA),
    "revisao_prisao": (TipoPeca.DECISAO_PRISAO, OrigemPeca.JUIZO, TipoData.ASSINATURA),
    "laudo": (TipoPeca.LAUDO, OrigemPeca.TERCEIRO, TipoData.JUNTADA),
    "termo_depoimento": (TipoPeca.TERMO_DEPOIMENTO, OrigemPeca.TERCEIRO, TipoData.ASSINATURA),
    "sentenca": (TipoPeca.SENTENCA, OrigemPeca.JUIZO, TipoData.ASSINATURA),
    "certidao_publicacao": (TipoPeca.CERTIDAO, OrigemPeca.JUIZO, TipoData.ASSINATURA),
    "certidao_intimacao_mp": (TipoPeca.CERTIDAO, OrigemPeca.JUIZO, TipoData.ASSINATURA),
    "certidao_intimacao_defesa": (TipoPeca.CERTIDAO, OrigemPeca.JUIZO, TipoData.ASSINATURA),
    "certidao_intimacao_reu": (TipoPeca.CERTIDAO, OrigemPeca.JUIZO, TipoData.ASSINATURA),
    "recurso": (TipoPeca.RECURSO, OrigemPeca.DEFESA, TipoData.PROTOCOLO),
    "contrarrazoes": (TipoPeca.CONTRARRAZOES, OrigemPeca.MP, TipoData.PROTOCOLO),
    "acordao": (TipoPeca.ACORDAO, OrigemPeca.JUIZO, TipoData.ASSINATURA),
    "juntada": (TipoPeca.OUTROS, OrigemPeca.TERCEIRO, TipoData.JUNTADA),
}
_SIGNATARIO = {
    OrigemPeca.MP: ("promotor", "Promotor de Justiça"),
    OrigemPeca.DEFESA: ("defensor", "Advogado"),
    OrigemPeca.JUIZO: ("juiz", "Juiz de Direito"),
    OrigemPeca.TERCEIRO: ("perito", "Perito Criminal"),
}


class _Fabrica:
    def __init__(self, partes: Partes, rng: random.Random, config: Configuracao) -> None:
        self.partes = partes
        self.rng = rng
        self.config = config

    def peca(
        self,
        template: str,
        dia: date,
        valores: dict[str, Any] | None = None,
        extra: dict[str, str] | None = None,
        enchimento_paragrafos: int = 0,
    ) -> PecaPlano:
        tipo, origem, tipo_data = _TEMPLATE_PECA[template]
        variaveis = {
            **self.partes.variaveis,
            "data": ids.formatar_data(dia, self.rng),
            **(extra or {}),
        }
        titulo, paragrafos = renderizar_peca(template, variaveis, self.rng)
        if enchimento_paragrafos:
            fim = paragrafos.pop() if template in ("laudo", "contrarrazoes") else None
            paragrafos.extend(enchimento(variaveis, self.rng, enchimento_paragrafos))
            if fim is not None:
                paragrafos.append(fim)
        chave, cargo = _SIGNATARIO[origem]
        assinatura = (
            f"Documento assinado eletronicamente por {self.partes.variaveis[chave]}, {cargo}, "
            f"em {dia.strftime('%d/%m/%Y')}."
        )
        paragrafos.append(Paragrafo(assinatura, papel="assinatura"))
        return PecaPlano(
            tipo, origem, titulo, dia, tipo_data, paragrafos, dict(valores or {}),
            marca_dagua=template in ("laudo", "juntada", "termo_depoimento"),
            verso_branco=self.rng.random() < self.config.proporcao_vazias,
        )  # fmt: skip


def _capa(partes: Partes, linha: Linha) -> PecaPlano:
    v = partes.variaveis
    textos = [
        "AUTUAÇÃO",
        f"Processo nº {partes.numero}",
        "Classe: Ação Penal - Procedimento Ordinário",
        f"Autor: Ministério Público do Estado. Réu: {v['reu']}.",
        f"Assunto: {v['artigo']}.",
        f"Autuado em {linha.denuncia.strftime('%d/%m/%Y')}.",
    ]
    paragrafos = [Paragrafo(textos[0], papel="titulo")]
    paragrafos.extend(Paragrafo(t) for t in textos[1:])
    return PecaPlano(
        TipoPeca.OUTROS, OrigemPeca.JUIZO, "Autuação", linha.denuncia, TipoData.JUNTADA,
        paragrafos, capa=True,
    )  # fmt: skip


def _nucleo(fab: _Fabrica, linha: Linha, crime: Crime) -> list[PecaPlano]:
    rng = fab.rng
    nasc = ids.formatar_data(linha.nascimento, rng)
    data_fato = fab.partes.variaveis["data_fato"]
    reincidente = rng.random() < 0.3
    pecas = [
        fab.peca(
            "denuncia", linha.denuncia,
            {
                TipoFato.DATA_FATO: linha.fato, TipoFato.DATA_NASCIMENTO_REU: linha.nascimento,
                TipoFato.PENA_MAXIMA_ABSTRATA: crime.pena_meses,
                TipoFato.DATA_DENUNCIA: linha.denuncia,
            },
            {"nascimento": nasc, "data_fato": data_fato},
        ),
        fab.peca("recebimento", linha.recebimento,
                 {TipoFato.DATA_RECEBIMENTO_DENUNCIA: linha.recebimento}),
        fab.peca(
            "sentenca", linha.sentenca,
            {TipoFato.DATA_SENTENCA: linha.sentenca, TipoFato.REINCIDENTE: reincidente},
            {
                "data_fato": data_fato,
                "reincidencia_texto": "o réu é reincidente, conforme certidão de antecedentes"
                if reincidente else "o réu é primário e não registra antecedentes",
            },
        ),
        fab.peca("certidao_publicacao", linha.publicacao,
                 {TipoFato.DATA_PUBLICACAO_SENTENCA: linha.publicacao}),
        fab.peca("certidao_intimacao_mp", linha.intimacao_mp,
                 {TipoFato.DATA_INTIMACAO_MP: linha.intimacao_mp}),
        fab.peca("certidao_intimacao_defesa", linha.intimacao_defesa,
                 {TipoFato.DATA_INTIMACAO_DEFESA: linha.intimacao_defesa}),
        fab.peca("certidao_intimacao_reu", linha.intimacao_reu,
                 {TipoFato.DATA_INTIMACAO_REU: linha.intimacao_reu}),
        fab.peca(
            "recurso", linha.interposicao,
            {
                TipoFato.TIPO_RECURSO: {"tipo": "apelacao", "recorrente": "defesa"},
                TipoFato.DATA_INTERPOSICAO_RECURSO: linha.interposicao,
            },
        ),
        fab.peca("contrarrazoes", linha.contrarrazoes),
        fab.peca("acordao", linha.acordao),
    ]  # fmt: skip
    if linha.decretacao is not None:
        pecas.append(
            fab.peca(
                "decisao_prisao",
                linha.decretacao,
                {TipoFato.DATA_DECRETACAO_PREVENTIVA: linha.decretacao},
            )
        )
        pecas.extend(
            fab.peca("revisao_prisao", dia, {TipoFato.DATA_REVISAO_PREVENTIVA: dia})
            for dia in linha.revisoes
        )
    return pecas


def _paginas_estimadas(pecas: list[PecaPlano]) -> int:
    return sum(len(p.paragrafos) // PARAGRAFOS_POR_PAGINA + 1 for p in pecas)


def _volume(fab: _Fabrica, linha: Linha, pecas: list[PecaPlano], alvo: int) -> list[PecaPlano]:
    rng = fab.rng
    extras: list[PecaPlano] = []
    data_fato = fab.partes.variaveis["data_fato"]
    modelos = ("laudo", "termo_depoimento", "juntada", "juntada")
    while _paginas_estimadas(pecas + extras) < alvo:
        restante = alvo - _paginas_estimadas(pecas + extras)
        folhas = min(restante, rng.choice((1, 1, 2, 3, 5, 8, 15, 30)))
        dia = linha.fato + _dias(rng, 5, max(6, (linha.acordao - linha.fato).days))
        template = rng.choice(modelos)
        extras.append(
            fab.peca(
                template,
                dia,
                extra={"data_fato": data_fato},
                enchimento_paragrafos=max(0, folhas * PARAGRAFOS_POR_PAGINA - 6),
            )
        )
    return extras


def _plantar_visiveis(pecas: list[PecaPlano], vetores: tuple[VetorInjecao, ...]) -> None:
    for vetor in vetores:
        if vetor not in VISIVEIS:
            continue
        alvo_tipo = VISIVEIS[vetor]
        alvo = next(p for p in pecas if p.tipo == alvo_tipo)
        alvo.paragrafos.insert(len(alvo.paragrafos) - 1, paragrafo_injecao(vetor))


def montar_roteiro(config: Configuracao, alvo: int | None = None) -> Roteiro:
    """Monta o roteiro completo de um processo.

    Args:
        config: Configuração (a semente define todo o resto).
        alvo: Folhas estimadas a pedir ao enchimento (padrão: ``config.paginas_alvo``); o
            gerador ajusta esse valor até a paginação real chegar perto do alvo.

    Returns:
        Roteiro com peças em ordem cronológica, capa primeiro.
    """
    rng = random.Random(config.semente)  # noqa: S311
    prescrito = config.prescrito if config.prescrito is not None else rng.random() < 0.4
    linha = montar_linha(config, rng, prescrito)
    partes = montar_partes(rng, prescrito, linha.denuncia.year)
    partes.variaveis["data_fato"] = ids.formatar_data(linha.fato, rng)
    fab = _Fabrica(partes, rng, config)
    pecas = _nucleo(fab, linha, partes.crime)
    if config.injecoes:
        pecas.append(fab.peca("laudo", linha.recebimento + timedelta(days=20)))
        pecas.append(fab.peca("juntada", linha.recebimento + timedelta(days=30)))
    pecas.extend(_volume(fab, linha, pecas, (alvo or config.paginas_alvo) - 1))
    ordenadas = [p for _, p in sorted(enumerate(pecas), key=lambda par: (par[1].data, par[0]))]
    _plantar_visiveis(ordenadas, config.injecoes)
    return Roteiro(config, partes, linha, [_capa(partes, linha), *ordenadas])
