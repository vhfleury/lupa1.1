"""Inventário e extração segura de ZIP: manifesto ordenado por nome com hash por entrada.

Antes de extrair, cada entrada é conferida: caminho relativo sem `..`, sem link simbólico, sem
criptografia, quantidade de entradas, razão de compressão e tamanho total descomprimido. Na
extração, o limite de tamanho é imposto sobre os bytes efetivamente lidos (o cabeçalho do ZIP
pode mentir). Diretórios são ignorados.
"""

import hashlib
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from lupa.dominio.enums import MotivoQuarentena
from lupa.dominio.esquemas import EntradaManifesto

BLOCO = 1024 * 1024
FLAG_CRIPTOGRAFIA = 0x1


@dataclass(frozen=True)
class LimitesZip:
    """Limites do inventário.

    Attributes:
        max_entradas: Quantidade máxima de arquivos.
        max_razao: Razão máxima `descomprimido / comprimido` por entrada.
        max_descomprimido_bytes: Soma máxima dos tamanhos descomprimidos.
    """

    max_entradas: int = 2000
    max_razao: float = 100.0
    max_descomprimido_bytes: int = 4 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class EntradaExtraida:
    """Entrada extraída para o disco.

    Attributes:
        manifesto: Ordem, nome, tamanho e hash.
        caminho: Arquivo extraído (nome interno opaco, não o nome da entrada).
    """

    manifesto: EntradaManifesto
    caminho: Path


class ZipRecusadoError(ValueError):
    """ZIP recusado; `motivo` vai para a quarentena e `detalhe` é legível, sem conteúdo."""

    def __init__(self, motivo: MotivoQuarentena, detalhe: str) -> None:
        """Cria o erro.

        Args:
            motivo: Motivo de quarentena.
            detalhe: Explicação curta (regra violada).
        """
        super().__init__(f"{motivo}: {detalhe}")
        self.motivo = motivo
        self.detalhe = detalhe


def _malicioso(detalhe: str) -> ZipRecusadoError:
    return ZipRecusadoError(MotivoQuarentena.ZIP_MALICIOSO, detalhe)


def caminho_seguro(nome: str) -> bool:
    """Diz se o nome da entrada é um caminho relativo sem subida de diretório.

    Args:
        nome: Nome da entrada no ZIP.

    Returns:
        Falso para caminhos absolutos, com unidade, com `..` ou com barra invertida.
    """
    if not nome or "\\" in nome or "\x00" in nome:
        return False
    caminho = PurePosixPath(nome)
    if caminho.is_absolute() or ":" in caminho.parts[0]:
        return False
    return ".." not in caminho.parts


def _eh_link(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def _conferir_entrada(info: zipfile.ZipInfo, limites: LimitesZip) -> None:
    if not caminho_seguro(info.filename):
        raise _malicioso("caminho fora do diretório de extração")
    if _eh_link(info):
        raise _malicioso("link simbólico")
    if info.flag_bits & FLAG_CRIPTOGRAFIA:
        raise ZipRecusadoError(MotivoQuarentena.SENHA, "entrada protegida por senha")
    razao = info.file_size / max(info.compress_size, 1)
    if razao > limites.max_razao:
        raise _malicioso("razão de compressão acima do limite")


def conferir(arquivo: zipfile.ZipFile, limites: LimitesZip) -> list[zipfile.ZipInfo]:
    """Confere todas as entradas pelo diretório central, sem extrair.

    Args:
        arquivo: ZIP aberto.
        limites: Limites do inventário.

    Returns:
        Entradas de arquivo (sem diretórios), ordenadas por nome.

    Raises:
        ZipRecusadoError: Na primeira regra violada.
    """
    entradas = [info for info in arquivo.infolist() if not info.is_dir()]
    if not entradas:
        raise ZipRecusadoError(MotivoQuarentena.TIPO_INVALIDO, "ZIP sem arquivos")
    if len(entradas) > limites.max_entradas:
        raise _malicioso("quantidade de entradas acima do limite")
    nomes = [info.filename for info in entradas]
    if len(set(nomes)) != len(nomes):
        raise _malicioso("nomes de entrada repetidos")
    for info in entradas:
        _conferir_entrada(info, limites)
    if sum(info.file_size for info in entradas) > limites.max_descomprimido_bytes:
        raise _malicioso("tamanho descomprimido acima do limite")
    return sorted(entradas, key=lambda info: info.filename)


def _extrair(
    arquivo: zipfile.ZipFile, info: zipfile.ZipInfo, destino: Path, restante: int
) -> tuple[int, str]:
    resumo = hashlib.sha256()
    lidos = 0
    with arquivo.open(info) as origem, destino.open("wb") as saida:
        while bloco := origem.read(BLOCO):
            lidos += len(bloco)
            if lidos > restante:
                raise _malicioso("tamanho descomprimido acima do limite")
            resumo.update(bloco)
            saida.write(bloco)
    return lidos, resumo.hexdigest()


def inventariar(caminho: Path, diretorio: Path, limites: LimitesZip) -> list[EntradaExtraida]:
    """Confere e extrai o ZIP, devolvendo o manifesto ordenado por nome.

    Args:
        caminho: ZIP de origem.
        diretorio: Diretório vazio onde as entradas são gravadas com nomes opacos.
        limites: Limites do inventário.

    Returns:
        Entradas extraídas, na ordem do manifesto.

    Raises:
        ZipRecusadoError: ZIP malicioso, protegido por senha ou corrompido.
    """
    try:
        with zipfile.ZipFile(caminho) as arquivo:
            entradas = conferir(arquivo, limites)
            restante = limites.max_descomprimido_bytes
            extraidas: list[EntradaExtraida] = []
            for ordem, info in enumerate(entradas, start=1):
                destino = diretorio / f"entrada-{ordem:05d}"
                tamanho, sha256 = _extrair(arquivo, info, destino, restante)
                restante -= tamanho
                manifesto = EntradaManifesto(
                    ordem=ordem, nome=info.filename, tamanho_bytes=tamanho, sha256=sha256
                )
                extraidas.append(EntradaExtraida(manifesto, destino))
            return extraidas
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError) as erro:
        raise ZipRecusadoError(MotivoQuarentena.CORROMPIDO, "ZIP ilegível") from erro
    except NotImplementedError as erro:
        raise ZipRecusadoError(MotivoQuarentena.CORROMPIDO, "compressão não suportada") from erro
