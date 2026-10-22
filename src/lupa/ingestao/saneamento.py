"""Normalização Unicode com mapa de offsets e hash por trecho (Etapas 4D.3 e 4D.9).

`normalizar` produz o texto de análise a partir do texto original da página: NFKC por
aglomerado (caractere base mais marcas combinantes), remoção de caracteres de controle e de
formatação (marcas de direção, espaços de largura zero, hífen suave) e troca de homóglifos
pelo equivalente latino (`dados/homoglifos.yaml`). Quebras de linha e tabulações ficam.

Cada caractere do normalizado guarda o intervalo do original que o produziu, então qualquer
trecho do normalizado resolve para o trecho original exato: a evidência aponta para o original,
o que vai ao modelo é o derivado. O mapa é recalculável a qualquer momento a partir de
`pagina.texto` (a função é determinística para a mesma versão), por isso não é gravado.
"""

import unicodedata
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files

import yaml

from lupa.dominio.esquemas import calcular_hash

MANTIDOS = frozenset("\n\t")
CATEGORIAS_REMOVIDAS = frozenset({"Cc", "Cf", "Co", "Cs"})


@dataclass(frozen=True)
class MapaHomoglifos:
    """Mapa de homóglifos versionado.

    Attributes:
        versao: Versão do YAML.
        mapa: Caractere confundível para o equivalente latino.
    """

    versao: str
    mapa: dict[str, str]


@cache
def homoglifos_padrao() -> MapaHomoglifos:
    """Mapa de `dados/homoglifos.yaml`, lido uma vez.

    Returns:
        Mapa versionado.
    """
    texto = files("lupa.ingestao").joinpath("dados").joinpath("homoglifos.yaml").read_text("utf-8")
    dados = yaml.safe_load(texto)
    return MapaHomoglifos(str(dados["versao"]), {str(k): str(v) for k, v in dados["mapa"].items()})


@dataclass
class TextoNormalizado:
    """Texto normalizado e o mapa de volta ao original.

    Attributes:
        texto: Texto normalizado.
        inicios: Para cada caractere do normalizado, o início do trecho original que o gerou.
        fins: Para cada caractere do normalizado, o fim (exclusivo) desse trecho original.
        tamanho_original: Tamanho do texto original.
        homoglifos: Quantos caracteres foram trocados pelo mapa de homóglifos.
        removidos: Quantos caracteres de controle ou de direção foram removidos.
    """

    texto: str
    inicios: list[int] = field(default_factory=list)
    fins: list[int] = field(default_factory=list)
    tamanho_original: int = 0
    homoglifos: int = 0
    removidos: int = 0

    def para_original(self, inicio: int, fim: int) -> tuple[int, int]:
        """Converte um intervalo do normalizado para o intervalo do original.

        Args:
            inicio: Início no normalizado.
            fim: Fim (exclusivo) no normalizado.

        Returns:
            `(inicio, fim)` no original; intervalo vazio vira posição vazia no original.

        Raises:
            ValueError: Se o intervalo estiver fora do normalizado.
        """
        if not 0 <= inicio <= fim <= len(self.texto):
            raise ValueError("intervalo fora do texto normalizado")
        if inicio == fim:
            posicao = self.inicios[inicio] if inicio < len(self.inicios) else self.tamanho_original
            return posicao, posicao
        return self.inicios[inicio], self.fins[fim - 1]

    def substituir(self, inicio: int, fim: int, novo: str) -> None:
        """Troca um intervalo do normalizado por outro texto, mantendo o mapa.

        Os caracteres novos apontam para o intervalo original inteiro do trecho trocado.

        Args:
            inicio: Início no normalizado.
            fim: Fim (exclusivo) no normalizado.
            novo: Texto que entra no lugar.
        """
        origem_inicio, origem_fim = self.para_original(inicio, fim)
        self.texto = self.texto[:inicio] + novo + self.texto[fim:]
        self.inicios[inicio:fim] = [origem_inicio] * len(novo)
        self.fins[inicio:fim] = [origem_fim] * len(novo)


def _aglomerados(texto: str) -> list[tuple[int, int]]:
    limites: list[tuple[int, int]] = []
    inicio = 0
    for posicao in range(1, len(texto) + 1):
        if posicao == len(texto) or not unicodedata.combining(texto[posicao]):
            limites.append((inicio, posicao))
            inicio = posicao
    return limites if texto else []


def _removido(caractere: str) -> bool:
    return caractere not in MANTIDOS and unicodedata.category(caractere) in CATEGORIAS_REMOVIDAS


def normalizar(texto: str, mapa: MapaHomoglifos | None = None) -> TextoNormalizado:
    """Normaliza o texto de uma página para análise.

    Args:
        texto: Texto original.
        mapa: Mapa de homóglifos (padrão: o do YAML versionado).

    Returns:
        Texto normalizado com o mapa de offsets.
    """
    trocas = (mapa or homoglifos_padrao()).mapa
    saida = TextoNormalizado("", tamanho_original=len(texto))
    partes: list[str] = []
    for inicio, fim in _aglomerados(texto):
        for caractere in unicodedata.normalize("NFKC", texto[inicio:fim]):
            if _removido(caractere):
                saida.removidos += 1
                continue
            latino = trocas.get(caractere)
            if latino is not None:
                saida.homoglifos += 1
                caractere = latino
            partes.append(caractere)
            saida.inicios.append(inicio)
            saida.fins.append(fim)
    saida.texto = "".join(partes)
    return saida


def hash_trecho(texto_original: str, inicio: int, fim: int) -> str:
    """Hash do trecho original, igual ao `Evidencia.hash_trecho` do domínio.

    Args:
        texto_original: Texto original da página (`pagina.texto`).
        inicio: Início do trecho.
        fim: Fim (exclusivo) do trecho.

    Returns:
        SHA-256 hexadecimal de `texto_original[inicio:fim]`.

    Raises:
        ValueError: Se o intervalo for vazio ou estiver fora do texto.
    """
    if not 0 <= inicio < fim <= len(texto_original):
        raise ValueError("intervalo inválido para o trecho")
    return calcular_hash(texto_original[inicio:fim])


def hash_trecho_normalizado(texto_original: str, inicio: int, fim: int) -> tuple[int, int, str]:
    """Resolve um trecho do normalizado para o original e calcula o hash do original.

    Args:
        texto_original: Texto original da página.
        inicio: Início no normalizado.
        fim: Fim (exclusivo) no normalizado.

    Returns:
        `(inicio, fim, hash)` no original.
    """
    origem_inicio, origem_fim = normalizar(texto_original).para_original(inicio, fim)
    return origem_inicio, origem_fim, hash_trecho(texto_original, origem_inicio, origem_fim)
