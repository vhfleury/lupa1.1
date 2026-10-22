"""Detectores de saneamento sobre o texto da página (Etapas 4D.4 a 4D.7).

Tudo é determinístico e nada bloqueia o processamento: cada detector devolve trechos e flags.

- Blocos codificados (4D.4): base64 (40 ou mais caracteres do alfabeto, padding plausível),
  hexadecimal (40 ou mais) e URL-encoded (10 ou mais sequências `%XX`); no texto de OCR, o
  bloco costuma sair partido em pedaços separados por espaço, então uma sequência de dois ou
  mais tokens do alfabeto base64 com troca interna de caixa ou de letra/algarismo, somando 40
  ou mais caracteres, também é bloco (`fragmentado`). O bloco sai do texto
  normalizado (vira `[bloco codificado removido]`) e fica no original. Exceção de rodapé:
  bloco que não decodifica para texto legível, com tamanho de resumo criptográfico (hex de 32,
  40, 56, 64, 96 ou 128, com tolerância de 3 caracteres e aceitando as letras que o OCR troca
  em algarismos, desde que o bloco tenha uma só caixa; base64 de 24, 28, 44, 64 ou 88) e
  precedido, a até 60 caracteres, de
  uma palavra de autenticação ("autenticação", "verificação", "hash", "assinatura", "chave",
  "código", "protocolo", "certificado") é código de autenticação legítimo e fica intacto.
  Bloco que decodifica para texto legível nunca é tratado como rodapé, e o texto decodificado
  passa pelos padrões de instrução.
- Padrões de instrução (4D.5): `dados/padroes_instrucao.yaml`, sobre o normalizado em
  minúsculas e sem acentos.
- Idioma inesperado (4D.6): por frase, contagem de palavras funcionais (`dados/idiomas.yaml`).
- Densidade anômala (4D.7): caracteres por página acima do limite do tipo
  (`dados/densidade.yaml`).
"""

import base64
import binascii
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

import yaml

MARCADOR_BLOCO = "[bloco codificado removido]"
CATEGORIA_BLOCO = "bloco_codificado"
CATEGORIA_IDIOMA = "idioma"
MIN_BASE64 = 40
MIN_HEX = 40
MIN_URL = 10
MIN_DECODIFICADO = 8
MIN_IMPRIMIVEIS = 0.9
JANELA_RODAPE = 60
TAMANHOS_HEX_RODAPE = frozenset({32, 40, 56, 64, 96, 128})
TAMANHOS_B64_RODAPE = frozenset({24, 28, 44, 64, 88})
TOLERANCIA_OCR = 3
PADRAO_HEX_OCR = re.compile(r"[0-9A-Z]+|[0-9a-f]+")
PALAVRAS_RODAPE = re.compile(
    r"autentica|verifica|hash|assinatura|chave|codigo|protocolo|certificado|sha|md5"
)
PADRAO_HEX = re.compile(rf"(?<![0-9A-Za-z])[0-9A-Fa-f]{{{MIN_HEX},}}(?![0-9A-Za-z])")
PADRAO_BASE64 = re.compile(
    rf"(?<![0-9A-Za-z+/])[A-Za-z0-9+/]{{{MIN_BASE64},}}={{0,2}}(?![0-9A-Za-z+/=])"
)
PADRAO_URL = re.compile(rf"(?:[^\s%]*%[0-9A-Fa-f]{{2}}){{{MIN_URL},}}[^\s%]*")
_FRAGMENTO = r"[A-Za-z0-9+/]*(?:[a-z][A-Z]|[A-Za-z][0-9]|[0-9][A-Za-z])[A-Za-z0-9+/]*={0,2}"
PADRAO_FRAGMENTADO = re.compile(rf"(?<!\S){_FRAGMENTO}(?:[ 	]+{_FRAGMENTO})+(?!\S)")
PADRAO_PALAVRA = re.compile(r"[a-z]+")
PADRAO_FRASE = re.compile(r"[^.!?]+[.!?]*")


def _ler_yaml(nome: str) -> dict[str, Any]:
    texto = files("lupa.ingestao").joinpath("dados").joinpath(nome).read_text("utf-8")
    dados: dict[str, Any] = yaml.safe_load(texto)
    return dados


def dobrar(texto: str) -> str:
    """Minúsculas sem acentos, com o mesmo tamanho do texto (offsets preservados).

    Args:
        texto: Texto (normalizado).

    Returns:
        Texto dobrado, caractere a caractere.
    """
    return "".join(unicodedata.normalize("NFD", c)[0].lower()[:1] or c for c in texto)


@dataclass(frozen=True)
class Ocorrencia:
    """Trecho detectado no texto normalizado.

    Attributes:
        inicio: Início no normalizado.
        fim: Fim (exclusivo) no normalizado.
        categoria: Categoria do detector.
        padrao: Identificador do padrão.
    """

    inicio: int
    fim: int
    categoria: str
    padrao: str


@dataclass(frozen=True)
class Padroes:
    """Padrões de instrução compilados.

    Attributes:
        versao: Versão do YAML.
        regras: `(categoria, id, regex)`.
    """

    versao: str
    regras: tuple[tuple[str, str, re.Pattern[str]], ...]


@cache
def padroes_padrao() -> Padroes:
    """Padrões de `dados/padroes_instrucao.yaml`, lidos uma vez.

    Returns:
        Padrões compilados.
    """
    dados = _ler_yaml("padroes_instrucao.yaml")
    regras = tuple(
        (str(categoria), str(item["id"]), re.compile(str(item["regex"])))
        for categoria, itens in dados["categorias"].items()
        for item in itens
    )
    return Padroes(str(dados["versao"]), regras)


def encontrar_padroes(texto: str, padroes: Padroes | None = None) -> list[Ocorrencia]:
    """Ocorrências de padrões de instrução.

    Args:
        texto: Texto normalizado.
        padroes: Padrões (padrão: os do YAML versionado).

    Returns:
        Ocorrências em ordem de posição.
    """
    dobrado = dobrar(texto)
    achados = [
        Ocorrencia(m.start(), m.end(), categoria, ident)
        for categoria, ident, regex in (padroes or padroes_padrao()).regras
        for m in regex.finditer(dobrado)
        if m.end() > m.start()
    ]
    return sorted(achados, key=lambda o: (o.inicio, o.fim, o.padrao))


@dataclass(frozen=True)
class BlocoCodificado:
    """Bloco codificado encontrado.

    Attributes:
        inicio: Início no texto analisado.
        fim: Fim (exclusivo).
        codificacao: `base64`, `hex`, `url` ou `fragmentado`.
        decodificado: Texto legível decodificado, ou None.
        rodape: Se é código de autenticação de rodapé (fica intacto).
    """

    inicio: int
    fim: int
    codificacao: str
    decodificado: str | None
    rodape: bool


def _legivel(dados: bytes) -> str | None:
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if len(texto) < MIN_DECODIFICADO or " " not in texto:
        return None
    imprimiveis = sum(1 for c in texto if c.isprintable())
    return texto if imprimiveis / len(texto) >= MIN_IMPRIMIVEIS else None


def _decodificar(trecho: str, codificacao: str) -> str | None:
    if codificacao == "fragmentado":
        compacto = "".join(trecho.split())
        tipo = "hex" if all(c in "0123456789abcdefABCDEF" for c in compacto) else "base64"
        return _decodificar(compacto, tipo)
    try:
        if codificacao == "hex":
            return _legivel(bytes.fromhex(trecho[: len(trecho) // 2 * 2]))
        if codificacao == "base64":
            preenchido = trecho + "=" * (-len(trecho) % 4)
            return _legivel(base64.b64decode(preenchido, validate=True))
    except (ValueError, binascii.Error):
        return None
    return _legivel(urllib.parse.unquote_to_bytes(trecho))


def _base64_plausivel(trecho: str) -> bool:
    corpo = trecho.rstrip("=")
    if len(corpo) % 4 == 1 or (trecho.endswith("=") and len(trecho) % 4):
        return False
    variado = any(c.isdigit() or c in "+/" for c in corpo)
    return variado or (any(c.isupper() for c in corpo) and any(c.islower() for c in corpo))


def _rodape(texto: str, inicio: int, trecho: str, codificacao: str) -> bool:
    compacto = "".join(trecho.split())
    if codificacao == "url":
        return False
    if PADRAO_HEX_OCR.fullmatch(compacto):
        tamanho_ok = any(abs(len(compacto) - n) <= TOLERANCIA_OCR for n in TAMANHOS_HEX_RODAPE)
    else:
        tamanho_ok = len(compacto) in TAMANHOS_B64_RODAPE
    if not tamanho_ok:
        return False
    antes = dobrar(texto[max(0, inicio - JANELA_RODAPE) : inicio])
    return PALAVRAS_RODAPE.search(antes) is not None


def _candidatos(texto: str) -> list[tuple[int, int, str]]:
    achados: list[tuple[int, int, str]] = []
    ocupado: set[int] = set()
    for codificacao, regex in (("hex", PADRAO_HEX), ("base64", PADRAO_BASE64), ("url", PADRAO_URL)):
        for m in regex.finditer(texto):
            if ocupado.intersection(range(m.start(), m.end())):
                continue
            if codificacao == "base64" and not _base64_plausivel(m.group()):
                continue
            achados.append((m.start(), m.end(), codificacao))
            ocupado.update(range(m.start(), m.end()))
    for m in PADRAO_FRAGMENTADO.finditer(texto):
        compacto = "".join(m.group().split())
        if len(compacto) >= MIN_BASE64 and not ocupado.intersection(range(m.start(), m.end())):
            achados.append((m.start(), m.end(), "fragmentado"))
    return sorted(achados)


def detectar_blocos(texto: str) -> list[BlocoCodificado]:
    """Blocos codificados no texto.

    Args:
        texto: Texto normalizado.

    Returns:
        Blocos em ordem de posição.
    """
    blocos = []
    for inicio, fim, codificacao in _candidatos(texto):
        trecho = texto[inicio:fim]
        decodificado = _decodificar(trecho, codificacao)
        rodape = decodificado is None and _rodape(texto, inicio, trecho, codificacao)
        blocos.append(BlocoCodificado(inicio, fim, codificacao, decodificado, rodape))
    return blocos


@dataclass(frozen=True)
class Idiomas:
    """Parâmetros da detecção de idioma.

    Attributes:
        versao: Versão do YAML.
        esperado: Idioma esperado.
        min_palavras: Palavras mínimas para avaliar um segmento.
        min_funcionais: Palavras funcionais mínimas do idioma estrangeiro.
        vantagem: Múltiplo mínimo sobre as funcionais do esperado.
        min_proporcao: Fração mínima de funcionais estrangeiras sobre as palavras do segmento.
        stopwords: Palavras funcionais por idioma.
    """

    versao: str
    esperado: str
    min_palavras: int
    min_funcionais: int
    vantagem: float
    min_proporcao: float
    stopwords: dict[str, frozenset[str]]


@cache
def idiomas_padrao() -> Idiomas:
    """Parâmetros de `dados/idiomas.yaml`, lidos uma vez.

    Returns:
        Parâmetros versionados.
    """
    dados = _ler_yaml("idiomas.yaml")
    return Idiomas(
        versao=str(dados["versao"]),
        esperado=str(dados["esperado"]),
        min_palavras=int(dados["min_palavras"]),
        min_funcionais=int(dados["min_funcionais"]),
        vantagem=float(dados["vantagem"]),
        min_proporcao=float(dados["min_proporcao"]),
        stopwords={str(k): frozenset(map(str, v)) for k, v in dados["stopwords"].items()},
    )


def idioma_do_segmento(segmento: str, idiomas: Idiomas | None = None) -> str | None:
    """Idioma estrangeiro de um segmento, se houver evidência suficiente.

    Args:
        segmento: Texto dobrado (minúsculas, sem acentos).
        idiomas: Parâmetros (padrão: os do YAML).

    Returns:
        Código do idioma estrangeiro, ou None (esperado ou indeterminado).
    """
    cfg = idiomas or idiomas_padrao()
    palavras = PADRAO_PALAVRA.findall(segmento)
    if len(palavras) < cfg.min_palavras:
        return None
    contagem = {
        lingua: sum(p in lista for p in palavras) for lingua, lista in cfg.stopwords.items()
    }
    esperado = contagem.get(cfg.esperado, 0)
    for lingua, total in sorted(contagem.items(), key=lambda par: -par[1]):
        if lingua == cfg.esperado:
            return None
        suficiente = total >= cfg.min_funcionais and total >= cfg.min_proporcao * len(palavras)
        if suficiente and total >= cfg.vantagem * max(1, esperado):
            return lingua
    return None


def detectar_idioma(texto: str, idiomas: Idiomas | None = None) -> list[Ocorrencia]:
    """Frases em idioma inesperado.

    Args:
        texto: Texto normalizado.
        idiomas: Parâmetros (padrão: os do YAML).

    Returns:
        Ocorrências com categoria `idioma` e padrão `idioma_<código>`.
    """
    dobrado = dobrar(texto)
    achados = []
    for m in PADRAO_FRASE.finditer(dobrado):
        lingua = idioma_do_segmento(m.group(), idiomas)
        if lingua is None:
            continue
        inicio = m.start() + len(m.group()) - len(m.group().lstrip())
        achados.append(Ocorrencia(inicio, m.end(), CATEGORIA_IDIOMA, f"idioma_{lingua}"))
    return achados


@dataclass(frozen=True)
class Densidade:
    """Limites de densidade.

    Attributes:
        versao: Versão do YAML.
        max_caracteres: Limite por tipo de página.
    """

    versao: str
    max_caracteres: dict[str, int]


@cache
def densidade_padrao() -> Densidade:
    """Limites de `dados/densidade.yaml`, lidos uma vez.

    Returns:
        Limites versionados.
    """
    dados = _ler_yaml("densidade.yaml")
    return Densidade(
        str(dados["versao"]), {str(k): int(v) for k, v in dados["max_caracteres"].items()}
    )


def densidade_anomala(texto: str, tipo: str, densidade: Densidade | None = None) -> bool:
    """Se a página tem mais caracteres do que o limite do seu tipo.

    Args:
        texto: Texto original da página.
        tipo: Tipo da página.
        densidade: Limites (padrão: os do YAML).

    Returns:
        True quando acima do limite (tipo sem limite nunca dispara).
    """
    limite = (densidade or densidade_padrao()).max_caracteres.get(tipo)
    return limite is not None and len(texto) > limite
