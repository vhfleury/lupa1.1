"""Formatos de cifra da aplicação com a chave de dados (DEK) do processo.

Campo do banco (texto, versão 1)::

    lupa1:<base64( processo_id[16] | nonce[12] | AES-256-GCM(texto) + tag[16] )>

O AAD é `lupa1|<rotulo>|<processo_id>`: um valor copiado para outra coluna ou atribuído a
outro processo não decifra. O id do processo no cabeçalho só diz qual DEK usar.

Objeto do storage (binário, versão 1), cifrado em blocos para não exigir o arquivo inteiro em
memória na gravação::

    cabeçalho = "LUPAOBJ" | versao[1] = 0x01 | tamanho_bloco[4, big-endian] | sal[16]
    subchave  = HKDF-SHA256(DEK, sal, info="lupa/objeto/v1")
    bloco i   = AES-256-GCM(subchave, nonce = i[12, big-endian], AAD = cabeçalho | i[8] | final[1])

Todo bloco tem `tamanho_bloco` bytes em claro, exceto o último (que pode ter de 0 até
`tamanho_bloco`); cada bloco cifrado tem 16 bytes a mais (tag). O sal aleatório por objeto
gera uma subchave nova por objeto, então o contador começa em zero sem repetir nonce. A marca
`final` no AAD impede truncar o objeto em fronteira de bloco.
"""

import base64
import io
import os
from collections.abc import Iterator
from typing import BinaryIO
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

TAMANHO_DEK = 32
TAMANHO_NONCE = 12
TAMANHO_TAG = 16
PREFIXO_CAMPO = "lupa1:"
MAGICO_OBJETO = b"LUPAOBJ"
VERSAO_OBJETO = 1
TAMANHO_SAL = 16
TAMANHO_BLOCO = 64 * 1024
TAMANHO_CABECALHO = len(MAGICO_OBJETO) + 1 + 4 + TAMANHO_SAL
INFO_OBJETO = b"lupa/objeto/v1"


class CifraInvalidaError(ValueError):
    """Conteúdo cifrado malformado, adulterado ou aberto com a chave errada."""


def gerar_dek() -> bytes:
    """Gera uma chave de dados de 256 bits.

    Returns:
        32 bytes aleatórios.
    """
    return AESGCM.generate_key(bit_length=256)


def campo_cifrado(valor: object) -> bool:
    """Diz se o valor vindo do banco está no formato de campo cifrado.

    Args:
        valor: Valor da coluna.

    Returns:
        Verdadeiro se for texto com o prefixo `lupa1:`.
    """
    return isinstance(valor, str) and valor.startswith(PREFIXO_CAMPO)


def _aad_campo(rotulo: str, processo_id: UUID) -> bytes:
    return f"lupa1|{rotulo}|{processo_id}".encode()


def cifrar_campo(dek: bytes, processo_id: UUID, rotulo: str, texto: str) -> str:
    """Cifra um texto para gravar em coluna.

    Args:
        dek: Chave de dados do processo.
        processo_id: Processo dono.
        rotulo: Coluna (`pagina.texto`...), entra no AAD.
        texto: Texto em claro.

    Returns:
        `lupa1:<base64>`.
    """
    nonce = os.urandom(TAMANHO_NONCE)
    cifrado = AESGCM(dek).encrypt(nonce, texto.encode(), _aad_campo(rotulo, processo_id))
    return PREFIXO_CAMPO + base64.b64encode(processo_id.bytes + nonce + cifrado).decode()


def _bruto(valor: str) -> bytes:
    try:
        bruto = base64.b64decode(valor.removeprefix(PREFIXO_CAMPO), validate=True)
    except ValueError:
        raise CifraInvalidaError("base64 inválido") from None
    if len(bruto) < 16 + TAMANHO_NONCE + TAMANHO_TAG:
        raise CifraInvalidaError("campo curto demais")
    return bruto


def processo_do_campo(valor: str) -> UUID:
    """Processo cuja DEK abre o campo.

    Args:
        valor: Campo `lupa1:...`.

    Returns:
        Id do processo do cabeçalho.
    """
    return UUID(bytes=_bruto(valor)[:16])


def decifrar_campo(dek: bytes, valor: str, rotulo: str) -> str:
    """Decifra um campo.

    Args:
        dek: Chave de dados do processo.
        valor: Campo `lupa1:...`.
        rotulo: Coluna, conferida pelo AAD.

    Returns:
        Texto em claro.

    Raises:
        CifraInvalidaError: Chave errada, coluna errada ou conteúdo adulterado.
    """
    bruto = _bruto(valor)
    processo_id = UUID(bytes=bruto[:16])
    nonce, cifrado = bruto[16 : 16 + TAMANHO_NONCE], bruto[16 + TAMANHO_NONCE :]
    try:
        claro = AESGCM(dek).decrypt(nonce, cifrado, _aad_campo(rotulo, processo_id))
    except InvalidTag:
        raise CifraInvalidaError("tag inválida") from None
    return claro.decode()


def _subchave(dek: bytes, sal: bytes) -> AESGCM:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=TAMANHO_DEK, salt=sal, info=INFO_OBJETO)
    return AESGCM(hkdf.derive(dek))


def _aad_bloco(cabecalho: bytes, indice: int, final: bool) -> bytes:
    return cabecalho + indice.to_bytes(8, "big") + (b"\x01" if final else b"\x00")


def _nonce(indice: int) -> bytes:
    return indice.to_bytes(TAMANHO_NONCE, "big")


def cifrar_stream(
    dek: bytes, origem: BinaryIO, tamanho_bloco: int = TAMANHO_BLOCO
) -> Iterator[bytes]:
    """Cifra `origem` em blocos, lendo um bloco à frente para marcar o último.

    Args:
        dek: Chave de dados do processo.
        origem: Arquivo binário lido até o fim.
        tamanho_bloco: Bytes em claro por bloco.

    Yields:
        Cabeçalho e depois cada bloco cifrado.
    """
    sal = os.urandom(TAMANHO_SAL)
    cabecalho = MAGICO_OBJETO + bytes([VERSAO_OBJETO]) + tamanho_bloco.to_bytes(4, "big") + sal
    aead = _subchave(dek, sal)
    yield cabecalho
    atual = origem.read(tamanho_bloco)
    indice = 0
    while True:
        proximo = origem.read(tamanho_bloco) if len(atual) == tamanho_bloco else b""
        final = not proximo
        yield aead.encrypt(_nonce(indice), atual, _aad_bloco(cabecalho, indice, final))
        if final:
            return
        atual, indice = proximo, indice + 1


class LeitorCifrado(io.RawIOBase):
    """Arquivo somente leitura que entrega o conteúdo de `origem` já cifrado (para upload)."""

    def __init__(self, dek: bytes, origem: BinaryIO) -> None:
        """Cria o leitor.

        Args:
            dek: Chave de dados do processo.
            origem: Conteúdo em claro.
        """
        super().__init__()
        self._partes = cifrar_stream(dek, origem)
        self._sobra = b""

    def readable(self) -> bool:
        """Sempre legível.

        Returns:
            Verdadeiro.
        """
        return True

    def readinto(self, destino: bytearray | memoryview) -> int:  # type: ignore[override]
        """Preenche `destino` com o próximo trecho cifrado.

        Args:
            destino: Buffer.

        Returns:
            Bytes escritos (0 no fim).
        """
        while not self._sobra:
            try:
                self._sobra = next(self._partes)
            except StopIteration:
                return 0
        quantidade = min(len(destino), len(self._sobra))
        destino[:quantidade] = self._sobra[:quantidade]
        self._sobra = self._sobra[quantidade:]
        return quantidade


def objeto_cifrado(dados: bytes) -> bool:
    """Diz se os bytes começam com o cabeçalho de objeto cifrado.

    Args:
        dados: Início do objeto.

    Returns:
        Verdadeiro se começar com `LUPAOBJ`.
    """
    return dados.startswith(MAGICO_OBJETO)


def decifrar_objeto(dek: bytes, dados: bytes) -> bytes:
    """Decifra um objeto inteiro.

    Args:
        dek: Chave de dados do processo.
        dados: Objeto cifrado (cabeçalho + blocos).

    Returns:
        Conteúdo em claro.

    Raises:
        CifraInvalidaError: Cabeçalho desconhecido, truncado, adulterado ou chave errada.
    """
    if len(dados) < TAMANHO_CABECALHO or not objeto_cifrado(dados):
        raise CifraInvalidaError("cabeçalho ausente")
    cabecalho = dados[:TAMANHO_CABECALHO]
    if cabecalho[len(MAGICO_OBJETO)] != VERSAO_OBJETO:
        raise CifraInvalidaError("versão desconhecida")
    inicio_bloco = len(MAGICO_OBJETO) + 1
    tamanho_bloco = int.from_bytes(cabecalho[inicio_bloco : inicio_bloco + 4], "big")
    aead = _subchave(dek, cabecalho[-TAMANHO_SAL:])
    corpo = memoryview(dados)[TAMANHO_CABECALHO:]
    passo = tamanho_bloco + TAMANHO_TAG
    saida = io.BytesIO()
    indice, posicao = 0, 0
    try:
        while True:
            bloco = corpo[posicao : posicao + passo]
            final = posicao + passo >= len(corpo)
            if len(bloco) < TAMANHO_TAG:
                raise CifraInvalidaError("bloco truncado")
            saida.write(
                aead.decrypt(_nonce(indice), bytes(bloco), _aad_bloco(cabecalho, indice, final))
            )
            if final:
                return saida.getvalue()
            posicao, indice = posicao + passo, indice + 1
    except InvalidTag:
        raise CifraInvalidaError("tag inválida") from None
