"""Extratores por tipo de peça, evidência, reconferência, conflitos e réus (4F.2 a 4F.5).

Os textos são os dos autos sintéticos (4B): cada extrator roda sobre as peças do seu tipo e
precisa achar exatamente os eventos do gabarito nessas peças (tipo, valor e folha).
"""

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

import pytest
from structlog.testing import capture_logs

from lupa.dominio.enums import OrigemPeca, TipoFato, TipoPeca
from lupa.dominio.esquemas import Fato
from lupa.ingestao.eventos import fatos as modulo_fatos
from lupa.ingestao.eventos.base import aplicar_regra
from lupa.ingestao.eventos.denuncia import pena_maxima
from lupa.ingestao.eventos.fatos import extrair_fatos
from lupa.ingestao.eventos.modelo import Candidato, PaginaTexto, PecaTexto
from lupa.ingestao.eventos.padroes import Padroes, padroes_de, padroes_padrao
from lupa.ingestao.eventos.recurso import especie, recorrente
from lupa.ingestao.eventos.reus import identificar_reus, sem_nomes
from lupa.sinteticos.gerador import Conteudo, gerar_conteudo
from lupa.sinteticos.roteiro import Configuracao
from lupa.validacoes.adaptador import para_modelo
from lupa.validacoes.modelo import valor_de
from lupa.validacoes.motor import executar_catalogo

SEMENTES = (1101, 1102, 1103)


@dataclass(frozen=True)
class Processo:
    """Processo sintético convertido para peças com texto.

    Attributes:
        conteudo: Conteúdo gerado (gabarito).
        pecas: Peças com o texto visível de cada folha.
        folha: Folha de cada página (pelo id).
    """

    conteudo: Conteudo
    pecas: list[PecaTexto]
    folha: dict[UUID, int]


def _processo(semente: int) -> Processo:
    conteudo = gerar_conteudo(Configuracao(semente=semente, paginas_alvo=40, preventiva="atencao"))
    paginas = {p.numero: PaginaTexto(uuid4(), p.numero, p.texto) for p in conteudo.paginas}
    pecas = [
        PecaTexto(
            p.tipo,
            p.origem,
            tuple(paginas[n] for n in range(p.pagina_inicial, p.pagina_final + 1)),
        )
        for p in conteudo.pecas
    ]
    return Processo(conteudo, pecas, {p.id: p.numero for p in paginas.values()})


@pytest.fixture(scope="module")
def processos() -> list[Processo]:
    """Três processos sintéticos com preventiva, recurso e certidões."""
    return [_processo(s) for s in SEMENTES]


def _chaves_fatos(fatos: list[Fato], folha: dict[UUID, int]) -> Counter[str]:
    return Counter(
        json.dumps([str(f.tipo), valor_de(f), folha[f.evidencias[0].pagina_id]]) for f in fatos
    )


def _chaves_gabarito(processo: Processo, tipo_peca: TipoPeca) -> Counter[str]:
    folhas = {
        n
        for p in processo.conteudo.pecas
        if p.tipo is tipo_peca
        for n in range(p.pagina_inicial, p.pagina_final + 1)
    }
    return Counter(
        json.dumps([str(e.tipo), e.valor, e.pagina])
        for e in processo.conteudo.eventos
        if e.pagina in folhas
    )


@pytest.mark.parametrize(
    "tipo_peca",
    [
        TipoPeca.DENUNCIA,
        TipoPeca.RECEBIMENTO,
        TipoPeca.DECISAO_PRISAO,
        TipoPeca.SENTENCA,
        TipoPeca.CERTIDAO,
        TipoPeca.RECURSO,
    ],
)
def test_extrator_do_tipo_acha_os_eventos_do_gabarito(
    processos: list[Processo], tipo_peca: TipoPeca
) -> None:
    """Em cada processo, o extrator do tipo devolve exatamente os eventos das peças do tipo.

    Na sentença sozinha, a pena pelo artigo citado aparece como reserva e não é comparada.
    """
    for processo in processos:
        pecas = [p for p in processo.pecas if p.tipo is tipo_peca]
        assert pecas, f"processo sem {tipo_peca}"
        reus = identificar_reus(processo.pecas)
        resultado = extrair_fatos(uuid4(), pecas, reus, {r.pseudonimo: uuid4() for r in reus})
        esperados = _chaves_gabarito(processo, tipo_peca)
        assert esperados, f"gabarito sem eventos em {tipo_peca}"
        fatos = [
            f
            for f in resultado.fatos
            if not (tipo_peca is TipoPeca.SENTENCA and f.tipo is TipoFato.PENA_MAXIMA_ABSTRATA)
        ]
        assert _chaves_fatos(fatos, processo.folha) == esperados
        assert resultado.datas_rejeitadas == Counter()


def test_processo_inteiro_bate_com_o_gabarito_e_com_o_resultado_esperado(
    processos: list[Processo],
) -> None:
    """Todos os eventos de todas as peças; o catálogo sobre eles dá o resultado do gabarito."""
    for processo in processos:
        reus = identificar_reus(processo.pecas)
        resultado = extrair_fatos(
            uuid4(), processo.pecas, reus, {r.pseudonimo: uuid4() for r in reus}
        )
        esperados = Counter(
            json.dumps([str(e.tipo), e.valor, e.pagina]) for e in processo.conteudo.eventos
        )
        assert _chaves_fatos(resultado.fatos, processo.folha) == esperados
        achados = executar_catalogo(
            para_modelo(resultado.fatos), "criminal", processo.conteudo.referencia
        )
        obtidos = {a.validacao: a.resultado for a in achados}
        assert obtidos == {r.validacao: r.resultado for r in processo.conteudo.resultado_esperado}


def test_todo_fato_tem_evidencia_literal_no_texto_original(processos: list[Processo]) -> None:
    """Trecho, offsets e hash conferem com o texto original da página (4F.3)."""
    for processo in processos:
        paginas = {p.id: p for peca in processo.pecas for p in peca.paginas}
        resultado = extrair_fatos(uuid4(), processo.pecas)
        assert resultado.fatos
        for fato in resultado.fatos:
            assert fato.evidencias
            assert fato.extraido_por == "regra"
            assert fato.versao_extrator == padroes_padrao().versao_extrator
            for evidencia in fato.evidencias:
                texto = paginas[evidencia.pagina_id].texto
                assert texto[evidencia.inicio : evidencia.fim] == evidencia.trecho
                assert len(evidencia.hash_trecho) == 64


def _pagina(texto: str) -> PaginaTexto:
    return PaginaTexto(uuid4(), 1, texto)


def _peca(tipo: TipoPeca, *textos: str, origem: OrigemPeca = OrigemPeca.JUIZO) -> PecaTexto:
    return PecaTexto(tipo, origem, tuple(_pagina(t) for t in textos))


def _extrator_fixo(candidatos: Callable[[PecaTexto], list[Candidato]]) -> modulo_fatos.Extrator:
    def extrair(peca: PecaTexto, _padroes: Padroes) -> list[Candidato]:
        return candidatos(peca)

    return extrair


def test_valor_sem_trecho_e_descartado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Candidato com trecho vazio ou só de espaços não vira fato (4F.3)."""
    peca = _peca(TipoPeca.CERTIDAO, "Certidão:     publicada em 17/03/2016.")

    def candidatos(p: PecaTexto) -> list[Candidato]:
        pagina = p.paginas[0]
        return [
            Candidato(TipoFato.DATA_PUBLICACAO_SENTENCA, "2016-03-17", pagina, 10, 10, 0.9),
            Candidato(TipoFato.DATA_PUBLICACAO_SENTENCA, "2016-03-17", pagina, 10, 14, 0.9),
        ]

    monkeypatch.setitem(modulo_fatos.EXTRATORES, TipoPeca.CERTIDAO, _extrator_fixo(candidatos))
    resultado = extrair_fatos(uuid4(), [peca])
    assert resultado.fatos == []
    assert resultado.sem_trecho == 2
    assert resultado.candidatos == 2


def test_data_que_nao_existe_literalmente_e_rejeitada_e_logada_sem_conteudo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reconferência independente recusa a data e o log leva só tipo, regra e página (4F.4)."""
    texto = "Certifico que a sentença foi publicada em cartório em 17/03/2016."
    peca = _peca(TipoPeca.CERTIDAO, texto)

    def candidatos(p: PecaTexto) -> list[Candidato]:
        pagina = p.paginas[0]
        return [
            Candidato(
                TipoFato.DATA_PUBLICACAO_SENTENCA,
                "2016-03-18",
                pagina,
                14,
                len(texto) - 1,
                0.95,
                data=date(2016, 3, 18),
                regra="teste",
            )
        ]

    monkeypatch.setitem(modulo_fatos.EXTRATORES, TipoPeca.CERTIDAO, _extrator_fixo(candidatos))
    with capture_logs() as logs:
        resultado = extrair_fatos(uuid4(), [peca])
    assert resultado.fatos == []
    assert resultado.datas_rejeitadas == Counter({"data_publicacao_sentenca": 1})
    rejeicoes = [e for e in logs if e["event"] == "data_rejeitada"]
    assert len(rejeicoes) == 1
    assert set(rejeicoes[0]) == {"event", "log_level", "tipo", "regra", "pagina_id"}
    assert "17/03/2016" not in json.dumps(logs)


def test_conflito_entre_pecas_gera_os_dois_fatos_com_confianca_reduzida() -> None:
    """Duas publicações diferentes: dois fatos, confiança pela metade, motor em verificar."""
    pecas = [
        _peca(
            TipoPeca.CERTIDAO, "Certifico que a sentença foi publicada em cartório em 17/03/2016."
        ),
        _peca(
            TipoPeca.CERTIDAO, "Certifico que a sentença foi publicada em cartório em 18/03/2016."
        ),
        _peca(
            TipoPeca.DENUNCIA,
            "no dia 28/04/2014, por volta das 10 horas, cuja pena é de "
            "reclusão, de 1 (um) a 4 (quatro) anos",
        ),
        _peca(TipoPeca.RECEBIMENTO, "Assim, recebo a denúncia em 08/08/2014."),
    ]
    resultado = extrair_fatos(uuid4(), pecas)
    publicacoes = [f for f in resultado.fatos if f.tipo is TipoFato.DATA_PUBLICACAO_SENTENCA]
    assert sorted(valor_de(f) for f in publicacoes) == ["2016-03-17", "2016-03-18"]
    assert all(f.confianca == pytest.approx(0.95 * 0.5) for f in publicacoes)
    assert resultado.conflitos == ["data_publicacao_sentenca", "data_publicacao_sentenca"]
    achados = executar_catalogo(para_modelo(resultado.fatos), "criminal", date(2017, 1, 1))
    prescricao = next(a for a in achados if a.validacao == "prescricao_abstrata")
    assert prescricao.resultado == "verificar"
    assert prescricao.valores["conflitos"][0]["tipo"] == "data_publicacao_sentenca"


def test_mesmo_valor_em_duas_paginas_vira_um_fato_com_duas_evidencias() -> None:
    """Fato repetido não duplica: as evidências se somam."""
    pecas = [
        _peca(
            TipoPeca.RECEBIMENTO,
            "Assim, recebo a denúncia em 08/08/2014.",
            "Recebo a denúncia " "em 8 de agosto de 2014.",
        ),
    ]
    resultado = extrair_fatos(uuid4(), pecas)
    assert len(resultado.fatos) == 1
    assert len(resultado.fatos[0].evidencias) == 2
    assert resultado.conflitos == []


def test_ids_derivados_da_chave_natural_sao_estaveis() -> None:
    """Mesma extração, mesmos ids de fato e de evidência (base da idempotência da 4F.6)."""
    processo_id = uuid4()
    peca = _peca(TipoPeca.RECEBIMENTO, "Assim, recebo a denúncia em 08/08/2014.")
    primeira = extrair_fatos(processo_id, [peca])
    segunda = extrair_fatos(processo_id, [peca])
    assert [f.id for f in primeira.fatos] == [f.id for f in segunda.fatos]
    assert [f.evidencias[0].id for f in primeira.fatos] == [
        f.evidencias[0].id for f in segunda.fatos
    ]


DENUNCIA_DOIS_REUS = (
    "DENÚNCIA\n"
    "O MINISTÉRIO PÚBLICO vem oferecer DENÚNCIA em desfavor de Teodoro Quintanilha Brandão, "
    "brasileiro, inscrito no CPF sob o nº 123.456.789-09, nascido em 02/04/1985, e de "
    "MARIANA DOS SANTOS VILELA, brasileira, inscrita no CPF sob o nº 987.654.321-00, nascida em "
    "15 de agosto de 2001, pelos fatos a seguir narrados."
)


def test_reus_qualificados_recebem_pseudonimo_e_fatos_por_reu() -> None:
    """Dois réus: pseudônimos em ordem, CPF na identidade, nascimento de cada um com reu_id."""
    denuncia = _peca(TipoPeca.DENUNCIA, DENUNCIA_DOIS_REUS, origem=OrigemPeca.MP)
    certidao = _peca(
        TipoPeca.CERTIDAO,
        "Certifico que intimei pessoalmente o réu Teodoro Quintanilha Brandão em 07/04/2016.",
    )
    reus = identificar_reus([denuncia, certidao])
    assert [(r.pseudonimo, r.nome, r.documento) for r in reus] == [
        ("REU-01", "Teodoro Quintanilha Brandão", "123.456.789-09"),
        ("REU-02", "MARIANA DOS SANTOS VILELA", "987.654.321-00"),
    ]
    ids = {r.pseudonimo: uuid4() for r in reus}
    resultado = extrair_fatos(uuid4(), [denuncia, certidao], reus, ids)
    nascimentos = {
        f.valor["reu_id"]: f.valor["valor"]
        for f in resultado.fatos
        if f.tipo is TipoFato.DATA_NASCIMENTO_REU
    }
    assert nascimentos == {str(ids["REU-01"]): "1985-04-02", str(ids["REU-02"]): "2001-08-15"}
    intimacao = next(f for f in resultado.fatos if f.tipo is TipoFato.DATA_INTIMACAO_REU)
    assert intimacao.valor == {"valor": "2016-04-07", "reu_id": str(ids["REU-01"])}
    assert intimacao.evidencias[0].trecho == "em 07/04/2016"
    serializado = json.dumps([f.model_dump(mode="json") for f in resultado.fatos])
    for termo in ("Teodoro", "Quintanilha", "MARIANA", "VILELA", "123.456.789-09"):
        assert termo not in serializado


def test_sem_nomes_recorta_o_trecho_depois_do_nome() -> None:
    """O trecho começa depois do último termo sensível; sem termo, fica igual."""
    texto = "decreto a prisão preventiva de Fulano de Tal Silva, nesta data, 15/05/2014"
    novo = sem_nomes(texto, 0, len(texto), ["Fulano de Tal Silva"])
    assert texto[novo:] == "nesta data, 15/05/2014"
    assert sem_nomes(texto, 0, len(texto), ["Beltrano"]) == 0
    assert sem_nomes("Fulano", 0, 6, ["Fulano"]) == 6


def test_pena_maxima_pelo_texto_pela_tabela_e_divergente() -> None:
    """Pena transcrita vale; sem ela, a tabela pelo artigo; divergência reduz a confiança."""
    padroes = padroes_padrao()
    transcrita = _peca(
        TipoPeca.DENUNCIA,
        "incorreu nas sanções do art. 155, caput, do Código "
        "Penal, cuja pena é de reclusão, de 1 (um) a 4 (quatro) anos, e multa.",
    )
    so_artigo = _peca(
        TipoPeca.DENUNCIA, "incorreu nas sanções do art. 157, caput, do Código Penal."
    )
    lei = _peca(TipoPeca.DENUNCIA, "como incurso no art. 33, caput, da Lei 11.343/06.")
    divergente = _peca(
        TipoPeca.DENUNCIA,
        "incorreu nas sanções do art. 147 do Código Penal, cuja "
        "pena é de detenção, de 3 (três) meses a 1 (um) ano",
    )
    meses = _peca(TipoPeca.DENUNCIA, "cuja pena é de detenção, de 1 (um) a 6 (seis) meses")
    assert [(c.valor, c.confianca) for c in pena_maxima(transcrita, padroes)] == [(48, 0.9)]
    assert [(c.valor, c.confianca) for c in pena_maxima(so_artigo, padroes)] == [(120, 0.6)]
    assert [c.valor for c in pena_maxima(lei, padroes)] == [180]
    assert [(c.valor, c.confianca) for c in pena_maxima(divergente, padroes)] == [(12, 0.5)]
    assert [c.valor for c in pena_maxima(meses, padroes)] == [6]
    assert pena_maxima(_peca(TipoPeca.DENUNCIA, "sem pena citada"), padroes) == []


def test_pena_da_sentenca_so_vale_sem_pena_da_denuncia() -> None:
    """A pena pelo artigo citado na sentença é reserva."""
    sentenca = _peca(TipoPeca.SENTENCA, "CONDENAR o réu como incurso no art. 157 do Código Penal.")
    denuncia = _peca(TipoPeca.DENUNCIA, "cuja pena é de reclusão, de 1 (um) a 4 (quatro) anos")
    so_sentenca = extrair_fatos(uuid4(), [sentenca])
    assert [valor_de(f) for f in so_sentenca.fatos] == [120]
    ambos = extrair_fatos(uuid4(), [denuncia, sentenca])
    assert [valor_de(f) for f in ambos.fatos if f.tipo is TipoFato.PENA_MAXIMA_ABSTRATA] == [48]


def test_decretacao_e_revisao_sao_distinguidas_pelo_texto() -> None:
    """Decretação e revisão na mesma peça geram os dois fatos, distinguidos pelo verbo."""
    peca = _peca(
        TipoPeca.DECISAO_PRISAO,
        "Ante o exposto, decreto a prisão preventiva de Fulano, nesta data, 15 de maio de 2014.",
        "Por tais razões, mantenho a prisão preventiva em 07/10/2014.",
    )
    tipos = {(f.tipo, valor_de(f)) for f in extrair_fatos(uuid4(), [peca]).fatos}
    assert tipos == {
        (TipoFato.DATA_DECRETACAO_PREVENTIVA, "2014-05-15"),
        (TipoFato.DATA_REVISAO_PREVENTIVA, "2014-10-07"),
    }


def test_recurso_especie_e_recorrente() -> None:
    """Espécie normalizada; recorrente pelo texto e, sem pista, pela origem da peça."""
    assert especie("recurso em sentido estrito") == "rese"
    assert especie("embargos de declaracao") == "embargos_declaracao"
    assert especie("recurso de apelacao") == "apelacao"
    mp = _peca(
        TipoPeca.RECURSO,
        "O MINISTÉRIO PÚBLICO vem interpor RECURSO EM SENTIDO ESTRITO. "
        "Petição protocolada em 10/10/2016.",
    )
    pela_origem = _peca(
        TipoPeca.RECURSO, "Vem opor embargos de declaração.", origem=OrigemPeca.DEFESA
    )
    sem_pista = _peca(TipoPeca.RECURSO, "Vem interpor apelação.", origem=OrigemPeca.DESCONHECIDA)
    assert recorrente(mp) == "mp"
    assert recorrente(pela_origem) == "defesa"
    assert recorrente(sem_pista) is None
    assert recorrente(PecaTexto(TipoPeca.RECURSO, OrigemPeca.MP, ())) == "mp"
    valores = {str(f.tipo): valor_de(f) for f in extrair_fatos(uuid4(), [mp]).fatos}
    assert valores == {
        "tipo_recurso": {"tipo": "rese", "recorrente": "mp"},
        "data_interposicao_recurso": "2016-10-10",
    }
    assert extrair_fatos(uuid4(), [sem_pista]).fatos == []


def test_peca_outros_so_passa_pelas_regras_que_a_admitem() -> None:
    """Certidão classificada como `outros` ainda dá a publicação; denúncia não dá data_fato."""
    certidao = _peca(TipoPeca.OUTROS, "a sentença foi publicada em cartório em 17/03/2016")
    denuncia = _peca(TipoPeca.OUTROS, "no dia 28/04/2014, por volta das 10 horas")
    tipos = {f.tipo for f in extrair_fatos(uuid4(), [certidao, denuncia]).fatos}
    assert tipos == {TipoFato.DATA_PUBLICACAO_SENTENCA}


def test_ano_de_dois_digitos_reduz_a_confianca() -> None:
    """A regra multiplica a confiança por 0,8 quando o ano tem dois dígitos."""
    regra = next(r for r in padroes_padrao().regras if r.tipo is TipoFato.DATA_RECEBIMENTO_DENUNCIA)
    peca = _peca(TipoPeca.RECEBIMENTO, "recebo a denúncia em 08/08/14")
    (candidato,) = aplicar_regra(regra, peca)
    assert candidato.valor == "2014-08-08"
    assert candidato.confianca == pytest.approx(regra.confianca * 0.8)


def test_padroes_versionados_e_regra_ultima() -> None:
    """A versão do extrator junta eventos e tipos penais; `ultima` pega a última ocorrência."""
    eventos = {
        "versao": "x",
        "regras": [
            {
                "tipo": "data_denuncia",
                "pecas": ["denuncia"],
                "gatilhos": ["(?m)^cidade,\\s*"],
                "janela": 2,
                "ultima": True,
                "confianca": 0.5,
            }
        ],
    }
    tipos = {"versao": "9", "tipos": []}
    padroes = padroes_de(eventos, tipos)
    assert padroes.versao_extrator == "x+tp9"
    assert padroes.pena_do_artigo("155") is None
    peca = _peca(TipoPeca.DENUNCIA, "Cidade, 01/01/2014.\nCidade, 02/01/2014.")
    (ultima,) = aplicar_regra(padroes.regras[0], peca)
    assert ultima.valor == "2014-01-02"


def test_eventos_saida_usa_pagina_de_origem_e_valor_sem_reu() -> None:
    """Conversão para o harness: arquivo e página de origem, valor desembrulhado."""
    from lupa.ingestao.eventos.saida import eventos_saida

    pagina = PaginaTexto(uuid4(), 7, "Assim, recebo a denúncia em 08/08/2014.", "peca.pdf", 2)
    peca = PecaTexto(TipoPeca.RECEBIMENTO, OrigemPeca.JUIZO, (pagina,))
    (evento,) = eventos_saida(extrair_fatos(uuid4(), [peca]).fatos, {pagina.id: pagina})
    assert (evento.ref.arquivo, evento.ref.pagina, evento.valor) == ("peca.pdf", 2, "2014-08-08")
