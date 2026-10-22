"""Recifra objetos legados em claro no storage com a DEK do processo (Etapa 7.10).

Objetos gravados antes da 7.4 (originais, entradas de ZIP, cache do visualizador) ficaram em
claro no bucket; a leitura ainda os aceita, com aviso `objeto_legado_em_claro`. Este script
percorre o bucket, e cada objeto que não começa com o cabeçalho `LUPAOBJ` é cifrado em stream com
a DEK do processo dono (tirado da chave `gabinete/<id>/processo/<id>/...`), regravado na mesma
chave e conferido (decifra e compara com o claro lido) antes de seguir.

Uso (no contêiner da API, com o Vault destravado):

    python scripts/recifrar_objetos_legado.py            # simulação: só conta
    python scripts/recifrar_objetos_legado.py --executar # recifra de fato

Idempotente: objeto já cifrado é pulado; rodar de novo não muda nada. Objeto de processo sem DEK
(descartado ou inexistente no banco) não é tocado e entra na contagem `sem_dek`: o conteúdo de
processo descartado deveria ter sido apagado; apague-o à mão depois de conferir. Saída: só
contagens, nunca chaves de objeto nem conteúdo.
"""

import io
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lupa.config import get_settings
from lupa.ingestao.storage import (
    ArmazenamentoS3,
    ChaveSemProcessoError,
    ObjectStorage,
    StorageCifrado,
    criar_cliente_s3,
    processo_da_chave,
)
from lupa.seguranca.chaves import carregador_sql
from lupa.seguranca.contexto import (
    Carregador,
    ChaveIndisponivelError,
    contexto_cifra,
    dek_de,
)
from lupa.seguranca.envelope import decifrar_objeto, objeto_cifrado

PREFIXO = "gabinete/"


class ConferenciaError(RuntimeError):
    """O objeto regravado não decifra para o mesmo conteúdo."""


@dataclass
class Resultado:
    """Contagens da recifragem.

    Attributes:
        executado: Se regravou (`--executar`) ou só simulou.
        total: Objetos examinados.
        ja_cifrados: Já tinham o cabeçalho `LUPAOBJ` (pulados).
        recifrados: Em claro e cifrados (ou que seriam, na simulação).
        sem_dek: Em claro, mas o processo não tem DEK (não tocados).
        sem_processo: Chave fora do padrão `processo/<id>/` (não tocados).
        bytes_recifrados: Soma do tamanho em claro dos recifrados.
        processos: Processos com objeto recifrado.
    """

    executado: bool
    total: int = 0
    ja_cifrados: int = 0
    recifrados: int = 0
    sem_dek: int = 0
    sem_processo: int = 0
    bytes_recifrados: int = 0
    processos: set[str] = field(default_factory=set)


def _recifrar_um(interno: ObjectStorage, chave: str, dados: bytes, dek: bytes) -> None:
    StorageCifrado(interno).gravar(chave, io.BytesIO(dados))
    if decifrar_objeto(dek, interno.ler(chave)) != dados:
        raise ConferenciaError("objeto regravado nao confere")


def recifrar(
    interno: ObjectStorage,
    carregador: Carregador,
    *,
    executar: bool,
    prefixo: str = PREFIXO,
) -> Resultado:
    """Percorre o storage e cifra os objetos ainda em claro.

    Args:
        interno: Storage cru (sem o embrulho `StorageCifrado`), para ver os bytes gravados.
        carregador: `processo_id -> (gabinete_id, dek_cifrada)` (ver `carregador_sql`).
        executar: Regrava; sem isso só conta.
        prefixo: Prefixo das chaves examinadas.

    Returns:
        Contagens.

    Raises:
        ConferenciaError: Objeto regravado que não decifra para o claro original (para tudo).
    """
    resultado = Resultado(executado=executar)
    with contexto_cifra(carregador):
        for chave in interno.listar(prefixo):
            resultado.total += 1
            dados = interno.ler(chave)
            if objeto_cifrado(dados):
                resultado.ja_cifrados += 1
                continue
            try:
                processo_id = processo_da_chave(chave)
                dek = dek_de(processo_id)
            except ChaveSemProcessoError:
                resultado.sem_processo += 1
                continue
            except ChaveIndisponivelError:
                resultado.sem_dek += 1
                continue
            if executar:
                _recifrar_um(interno, chave, dados, dek)
            resultado.recifrados += 1
            resultado.bytes_recifrados += len(dados)
            resultado.processos.add(str(processo_id))
    return resultado


def main(argumentos: Sequence[str]) -> int:
    """Ponto de entrada.

    Args:
        argumentos: Argumentos da linha de comando (sem o nome do programa).

    Returns:
        Código de saída (0 ok).
    """
    settings = get_settings()
    executar = "--executar" in argumentos
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        interno = ArmazenamentoS3(criar_cliente_s3(settings), settings.minio_bucket)
        resultado = recifrar(interno, carregador_sql(sessionmaker(engine)), executar=executar)
    finally:
        engine.dispose()
    verbo = "recifrados" if executar else "seriam recifrados (use --executar)"
    sys.stdout.write(f"objetos examinados: {resultado.total}\n")
    sys.stdout.write(f"ja cifrados (pulados): {resultado.ja_cifrados}\n")
    sys.stdout.write(f"objetos {verbo}: {resultado.recifrados}\n")
    sys.stdout.write(f"  bytes: {resultado.bytes_recifrados}\n")
    sys.stdout.write(f"  processos: {len(resultado.processos)}\n")
    sys.stdout.write(f"em claro sem DEK (nao tocados): {resultado.sem_dek}\n")
    sys.stdout.write(f"chave fora do padrao (nao tocados): {resultado.sem_processo}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
