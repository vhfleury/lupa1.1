"""Reconhecimento de datas em texto de autos, com offsets no texto original (Etapa 4F.1).

Formatos aceitos:

- numérico: ``dd/mm/aaaa``, ``dd.mm.aaaa`` e ``dd-mm-aaaa`` (dia e mês com um ou dois dígitos);
- numérico com ano de dois dígitos (``15/05/14``): aceito com cautela. O século vem de um pivô
  fixo (``ANO_PIVO``): ``00`` a ``49`` viram 2000 a 2049; ``50`` a ``99`` viram 1950 a 1999. A
  ocorrência sai marcada com ``ano_dois_digitos`` para quem a usa reduzir a confiança;
- por extenso: ``15 de maio de 2014``, ``1º de maio de 2014``, ``quinze de maio de dois mil e
  catorze`` (dia e ano em algarismos ou por extenso, em qualquer combinação);
- abreviado: ``15/mai/2014``, ``15-mai-2014``, ``15 mai. 2014``, ``15 de mai. de 2014``.

Com ou sem dia da semana antes (``quinta-feira, 15 de maio de 2014``): o dia da semana não entra
no literal. Datas impossíveis (31/02, mês 13) e anos fora de 1900 a 2100 são descartadas.

A busca acontece sobre o texto normalizado (``lupa.ingestao.saneamento.normalizar``: NFKC,
homóglifos, sem caracteres de controle) "dobrado" caractere a caractere (minúsculas, sem
acento), que tem o mesmo comprimento do normalizado; os offsets voltam ao original pelo mapa do
normalizado. ``reconferir`` é a conferência independente da 4F.4: em vez de interpretar o
trecho, escreve a data em todas as formas aceitas e procura alguma delas literalmente no trecho.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from lupa.ingestao.saneamento import TextoNormalizado, normalizar

ANO_MINIMO = 1900
ANO_MAXIMO = 2100
ANO_PIVO = 50
MESES = (
    "janeiro",
    "fevereiro",
    "marco",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)
ABREVIADOS = tuple(m[:3] for m in MESES)
UNIDADES = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "catorze": 14,
    "quatorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezasseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
    "cem": 100,
    "cento": 100,
    "duzentos": 200,
    "trezentos": 300,
    "quatrocentos": 400,
    "quinhentos": 500,
    "seiscentos": 600,
    "setecentos": 700,
    "oitocentos": 800,
    "novecentos": 900,
    "primeiro": 1,
}
_PALAVRA_NUMERO = "|".join(sorted(UNIDADES, key=len, reverse=True))
_NUMERO_EXTENSO = rf"(?:(?:{_PALAVRA_NUMERO})(?:\s+e\s+(?:{_PALAVRA_NUMERO}))*)"
_ANO_EXTENSO = rf"(?:(?:dois\s+mil|mil)(?:\s+(?:e\s+)?{_NUMERO_EXTENSO})?)"
_DIA = rf"(?P<dia>\d{{1,2}}o?|{_NUMERO_EXTENSO})"
_MES = rf"(?P<mes>{'|'.join(MESES)})"
_ABREV = rf"(?P<abrev>{'|'.join(ABREVIADOS)})\.?"
_ANO = rf"(?P<ano>\d{{4}}|{_ANO_EXTENSO})"
PADROES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "numerico",
        re.compile(
            r"(?<![\d/.\-])(?P<d>\d{1,2})(?P<sep>[/.\-])(?P<m>\d{1,2})(?P=sep)"
            r"(?P<a>\d{4}|\d{2})(?![\d/])"
        ),
    ),
    (
        "numerico",
        re.compile(
            r"(?<![\d/.\-])(?P<d>\d{1,2}) ?(?P<sep>/) ?(?P<m>\d{1,2}) ?/ ?" r"(?P<a>\d{4})(?![\d/])"
        ),
    ),
    ("extenso", re.compile(rf"(?<![\w]){_DIA}\s+de\s+{_MES}\s+de\s+{_ANO}(?![\w])")),
    (
        "abreviado",
        re.compile(
            rf"(?<![\w]){_DIA}\s*(?:[/\-]|\s|\s+de\s+)\s*{_ABREV}"
            rf"\s*(?:[/\-]|\s|\s+de\s+)\s*{_ANO}(?![\w])"
        ),
    ),
)


@dataclass(frozen=True)
class OcorrenciaData:
    """Data reconhecida num texto.

    Attributes:
        data: Data normalizada.
        inicio: Offset inicial do literal no texto de busca.
        fim: Offset final (exclusivo).
        literal: Literal como está no texto.
        formato: ``numerico``, ``extenso`` ou ``abreviado``.
        ano_dois_digitos: Se o ano foi escrito com dois dígitos (século pelo pivô).
    """

    data: date
    inicio: int
    fim: int
    literal: str
    formato: str
    ano_dois_digitos: bool = False

    @property
    def iso(self) -> str:
        """A data em ISO ``AAAA-MM-DD``."""
        return self.data.isoformat()


def dobrar(texto: str) -> str:
    """Minúsculas sem acento, preservando o comprimento (um caractere por caractere).

    Args:
        texto: Texto (normalmente o normalizado).

    Returns:
        Texto dobrado do mesmo tamanho.
    """
    return "".join(_dobrar_caractere(c) for c in texto)


def _dobrar_caractere(caractere: str) -> str:
    base = unicodedata.normalize("NFD", caractere)[:1] or caractere
    minuscula = base.lower()
    return minuscula if len(minuscula) == 1 else base


def numero_por_extenso(palavras: str) -> int | None:
    """Interpreta um número escrito por extenso (de 1 a 2999).

    Args:
        palavras: Texto dobrado, por exemplo ``dois mil e catorze``.

    Returns:
        O número, ou None se alguma palavra não for numeral.
    """
    total = 0
    parcial = 0
    for palavra in palavras.split():
        if palavra == "e":
            continue
        if palavra == "mil":
            total += (parcial or 1) * 1000
            parcial = 0
        elif palavra in UNIDADES:
            parcial += UNIDADES[palavra]
        else:
            return None
    return total + parcial or None


def _inteiro(texto: str) -> int | None:
    limpo = texto.strip().rstrip("o")
    if limpo.isdigit():
        return int(limpo)
    return numero_por_extenso(texto)


def _ano_numerico(texto: str) -> tuple[int, bool]:
    if len(texto) == 2:
        valor = int(texto)
        return (2000 + valor if valor < ANO_PIVO else 1900 + valor), True
    return int(texto), False


def construir_data(ano: int, mes: int, dia: int) -> date | None:
    """Monta a data se ela existir e o ano estiver entre 1900 e 2100.

    Args:
        ano: Ano.
        mes: Mês.
        dia: Dia.

    Returns:
        Data, ou None se impossível (31/02, mês 13) ou fora da faixa.
    """
    if not ANO_MINIMO <= ano <= ANO_MAXIMO:
        return None
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _interpretar(formato: str, achado: re.Match[str]) -> tuple[date | None, bool]:
    if formato == "numerico":
        ano, dois = _ano_numerico(achado.group("a"))
        return construir_data(ano, int(achado.group("m")), int(achado.group("d"))), dois
    dia = _inteiro(achado.group("dia"))
    ano_valor = _inteiro(achado.group("ano"))
    if formato == "extenso":
        mes = MESES.index(achado.group("mes")) + 1
    else:
        mes = ABREVIADOS.index(achado.group("abrev")[:3]) + 1
    if dia is None or ano_valor is None:
        return None, False
    return construir_data(ano_valor, mes, dia), False


def _sem_sobreposicao(ocorrencias: list[OcorrenciaData]) -> list[OcorrenciaData]:
    escolhidas: list[OcorrenciaData] = []
    for ocorrencia in sorted(ocorrencias, key=lambda o: (o.inicio, -(o.fim - o.inicio))):
        if escolhidas and ocorrencia.inicio < escolhidas[-1].fim:
            continue
        escolhidas.append(ocorrencia)
    return escolhidas


def datas_no_dobrado(dobrado: str, texto: str | None = None) -> list[OcorrenciaData]:
    """Datas de um texto já dobrado, com offsets nesse mesmo texto.

    Args:
        dobrado: Texto dobrado (``dobrar``).
        texto: Texto com o mesmo comprimento de onde sai o literal (padrão: o dobrado).

    Returns:
        Ocorrências em ordem, sem sobreposição (a mais longa vence).
    """
    fonte = dobrado if texto is None else texto
    ocorrencias: list[OcorrenciaData] = []
    for formato, padrao in PADROES:
        for achado in padrao.finditer(dobrado):
            valor, dois = _interpretar(formato, achado)
            if valor is None:
                continue
            inicio, fim = achado.span()
            ocorrencias.append(OcorrenciaData(valor, inicio, fim, fonte[inicio:fim], formato, dois))
    return _sem_sobreposicao(ocorrencias)


@dataclass(frozen=True)
class TextoAnalise:
    """Texto original de uma página com o normalizado e o dobrado usados nas buscas.

    Attributes:
        original: Texto original (``pagina.texto``).
        normalizado: Normalizado com o mapa de offsets.
        dobrado: Normalizado dobrado (mesmo comprimento do normalizado).
    """

    original: str
    normalizado: TextoNormalizado
    dobrado: str

    @classmethod
    def de(cls, original: str) -> "TextoAnalise":
        """Prepara o texto para busca.

        Args:
            original: Texto original da página.

        Returns:
            Texto de análise.
        """
        normalizado = normalizar(original)
        return cls(original, normalizado, dobrar(normalizado.texto))

    def para_original(self, inicio: int, fim: int) -> tuple[int, int]:
        """Converte um intervalo do dobrado/normalizado para o original.

        Args:
            inicio: Início no dobrado.
            fim: Fim no dobrado.

        Returns:
            Intervalo no original.
        """
        return self.normalizado.para_original(inicio, fim)

    def datas(self) -> list[OcorrenciaData]:
        """Datas do texto com offsets no dobrado (literal do normalizado)."""
        return datas_no_dobrado(self.dobrado, self.normalizado.texto)


def encontrar_datas(texto: str) -> list[OcorrenciaData]:
    """Todas as datas do texto original, com offsets e literal no original.

    Args:
        texto: Texto original (por exemplo, ``pagina.texto``).

    Returns:
        Ocorrências em ordem de posição.
    """
    analise = TextoAnalise.de(texto)
    saida = []
    for ocorrencia in analise.datas():
        inicio, fim = analise.para_original(ocorrencia.inicio, ocorrencia.fim)
        saida.append(
            OcorrenciaData(
                ocorrencia.data,
                inicio,
                fim,
                texto[inicio:fim],
                ocorrencia.formato,
                ocorrencia.ano_dois_digitos,
            )
        )
    return saida


_EXTENSO_UNIDADES = (
    "",
    "um",
    "dois",
    "tres",
    "quatro",
    "cinco",
    "seis",
    "sete",
    "oito",
    "nove",
    "dez",
    "onze",
    "doze",
    "treze",
    "catorze",
    "quinze",
    "dezesseis",
    "dezessete",
    "dezoito",
    "dezenove",
)
_EXTENSO_DEZENAS = (
    "",
    "",
    "vinte",
    "trinta",
    "quarenta",
    "cinquenta",
    "sessenta",
    "setenta",
    "oitenta",
    "noventa",
)
_EXTENSO_CENTENAS = (
    "",
    "cento",
    "duzentos",
    "trezentos",
    "quatrocentos",
    "quinhentos",
    "seiscentos",
    "setecentos",
    "oitocentos",
    "novecentos",
)


def _ate_cem(numero: int) -> str:
    if numero < len(_EXTENSO_UNIDADES):
        return _EXTENSO_UNIDADES[numero]
    dezena, unidade = divmod(numero, 10)
    return _EXTENSO_DEZENAS[dezena] + (f" e {_EXTENSO_UNIDADES[unidade]}" if unidade else "")


def escrever_por_extenso(numero: int) -> str:
    """Escreve de 1 a 2999 por extenso (sem acento), forma usada em datas.

    Args:
        numero: Número.

    Returns:
        Por extenso, por exemplo ``dois mil e catorze``.
    """
    milhar, resto = divmod(numero, 1000)
    partes = [] if milhar == 0 else ["mil" if milhar == 1 else f"{_ate_cem(milhar)} mil"]
    if resto:
        centena, dezena = divmod(resto, 100)
        if resto == 100:
            texto = "cem"
        elif centena:
            texto = _EXTENSO_CENTENAS[centena] + (f" e {_ate_cem(dezena)}" if dezena else "")
        else:
            texto = _ate_cem(dezena)
        partes.append(texto)
    conjuncao = " e " if resto < 100 or resto % 100 == 0 else " "
    return conjuncao.join(partes)


def _variantes_extenso(numero: int) -> set[str]:
    base = escrever_por_extenso(numero)
    variantes = {base, base.replace("catorze", "quatorze")}
    if numero >= 1000 and numero % 1000:
        variantes |= {v.replace("mil e ", "mil ", 1) for v in set(variantes)}
        variantes |= {v.replace("mil ", "mil e ", 1) for v in set(variantes) if "mil e " not in v}
    return variantes


def escritas(dia: date) -> set[str]:
    """Todas as formas aceitas de escrever a data, já dobradas.

    Args:
        dia: Data.

    Returns:
        Conjunto de literais possíveis.
    """
    d, m, a = dia.day, dia.month, dia.year
    dias = {str(d), f"{d:02d}"}
    anos_num = {str(a)}
    if 1900 + ANO_PIVO <= a < 2000 + ANO_PIVO:
        anos_num.add(f"{a % 100:02d}")
    meses_num = {str(m), f"{m:02d}"}
    formas = {
        f"{dd}{sep}{mm}{sep}{aa}"
        for dd in dias
        for mm in meses_num
        for aa in anos_num
        for sep in "/.-"
    }
    dias_texto = dias | _variantes_extenso(d)
    if d == 1:
        dias_texto |= {"1o", "01o", "primeiro"}
    anos_texto = {str(a)} | _variantes_extenso(a)
    mes_nome = MESES[m - 1]
    abrev = ABREVIADOS[m - 1]
    for dd in dias_texto:
        for aa in anos_texto:
            formas.add(f"{dd} de {mes_nome} de {aa}")
            for sep in ("/", "-", " ", " de "):
                formas |= {f"{dd}{sep}{abrev}{p}{sep}{aa}" for p in ("", ".")}
                formas.add(f"{dd}{sep}{abrev}. {aa}")
    return formas


def _compactar(texto: str) -> str:
    compacto = re.sub(r"\s+", " ", dobrar(normalizar(texto).texto)).strip()
    return re.sub(r" ?/ ?", "/", compacto)


def reconferir(trecho: str, dia: date) -> bool:
    """Conferência independente: a data está escrita literalmente no trecho?

    Não reaproveita as expressões de busca: escreve a data em todas as formas aceitas e procura
    cada uma no trecho dobrado (espaços compactados), com fronteira de número nas pontas.

    Args:
        trecho: Trecho original da evidência.
        dia: Data devolvida pelo extrator.

    Returns:
        Verdadeiro se alguma escrita da data aparece no trecho.
    """
    alvo = _compactar(trecho)
    for forma in escritas(dia):
        for achado in re.finditer(re.escape(forma), alvo):
            antes = alvo[achado.start() - 1] if achado.start() else " "
            depois = alvo[achado.end()] if achado.end() < len(alvo) else " "
            if not (antes.isalnum() or depois.isalnum()):
                return True
    return False
