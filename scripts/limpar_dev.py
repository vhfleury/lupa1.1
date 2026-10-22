"""Remove gabinetes SINTÉTICOS do banco de desenvolvimento (Etapa 6.10; revisão 6.4-6.9, item 3).

Uso (no contêiner da API):

    python scripts/limpar_dev.py          # só mostra o que seria removido
    python scripts/limpar_dev.py --sim    # remove de fato

RecusaError rodar fora de `LUPA_AMBIENTE=desenvolvimento`/`teste`. Seleciona os gabinetes cujo nome
começa (sem diferenciar maiúsculas) por um dos prefixos de `PREFIXOS` (calibração, ponta a
ponta, carga, E2E) e remove, numa única transação:

1. os eventos de auditoria desses gabinetes (a cadeia inteira de cada um some junto; a trava
   append-only de `evento_auditoria` é desligada só dentro da transação e religada antes do
   commit, e só o dono das tabelas consegue fazer isso);
2. todas as linhas com `gabinete_id` desses gabinetes, das tabelas filhas para as mães
   (ordem topológica dos metadados), e por fim os próprios gabinetes.

Se algum evento da cadeia global (sem gabinete) apontar para um usuário desses gabinetes, o
script recusa: apagá-lo quebraria a verificação da cadeia global. Saída: contagens, nunca
conteúdo.

Etapa 7.7: antes de apagar as linhas, cada processo desses gabinetes passa pelo mesmo caminho do
`POST /processos/{id}/descartar` (`lupa_descartar_processo`: conteúdo e DEK cifrada). Com
`--sim`, depois do commit, os objetos do processo são apagados do storage e as chaves Transit
do gabinete são destruídas no cofre (exclusão criptográfica completa).
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import BindParameter, Engine, bindparam, create_engine, text

from lupa.config import get_settings
from lupa.dominio.tabelas import Base
from lupa.ingestao.storage import ObjectStorage, criar_storage
from lupa.seguranca.cofre import Cofre, criar_cofre, nome_chave_gabinete, nome_chave_identidades
from lupa.seguranca.descarte import objetos_do_processo

AMBIENTES_PERMITIDOS = frozenset({"desenvolvimento", "teste"})
PREFIXOS: tuple[str, ...] = (
    "Gabinete ponta a ponta",
    "Gabinete de calibração",
    "Gabinete E2E",
    "Gabinete Processos E2E",
    "carga",
    "e2e",
)
TRAVA = "evento_auditoria_append_only"


class RecusaError(RuntimeError):
    """Limpeza recusada (ambiente ou integridade da cadeia global)."""


@dataclass(frozen=True)
class Resultado:
    """Contagens da limpeza.

    Attributes:
        gabinetes: Gabinetes sintéticos encontrados (removidos se `executado`).
        eventos: Eventos de auditoria desses gabinetes (inclusive os da carga de 1 milhão).
        linhas: Demais linhas removidas, por tabela.
        executado: Se a remoção foi feita (`--sim`) ou só simulada.
    """

    gabinetes: int
    eventos: int
    linhas: dict[str, int]
    executado: bool
    processos_descartados: int = 0
    objetos_apagados: int = 0


def _filtro_prefixos(prefixos: Sequence[str]) -> tuple[str, dict[str, str]]:
    condicoes = " OR ".join(f"lower(nome) LIKE :p{i}" for i in range(len(prefixos)))
    parametros = {
        f"p{i}": p.lower().replace("%", r"\%").replace("_", r"\_") + "%"
        for i, p in enumerate(prefixos)
    }
    return condicoes, parametros


def _descartar_processos(
    conexao: Any, ids: list[UUID], por_id: BindParameter[list[UUID]]
) -> list[tuple[UUID, UUID]]:
    processos = [
        (linha[0], linha[1])
        for linha in conexao.execute(
            text("SELECT id, gabinete_id FROM processo WHERE gabinete_id IN :ids").bindparams(
                por_id
            ),
            {"ids": ids},
        )
    ]
    conexao.execute(text("SELECT set_config('lupa.papel', 'administrador', true)"))
    for processo_id, _ in processos:
        conexao.execute(text("SELECT lupa_descartar_processo(:id)"), {"id": processo_id})
    return processos


def _apagar_fora_do_banco(
    processos: list[tuple[UUID, UUID]],
    ids: list[UUID],
    storage: ObjectStorage | None,
    cofre: Cofre | None,
) -> int:
    apagados = 0
    if storage is not None:
        for processo_id, gabinete_id in processos:
            for chave in objetos_do_processo(storage, gabinete_id, processo_id):
                storage.apagar(chave)
                apagados += 1
    if cofre is not None:
        for gabinete_id in ids:
            cofre.destruir_chave(nome_chave_gabinete(gabinete_id))
            cofre.destruir_chave(nome_chave_identidades(gabinete_id))
    return apagados


def limpar(
    engine: Engine,
    *,
    executar: bool,
    prefixos: Sequence[str] = PREFIXOS,
    ambiente: str,
    storage: ObjectStorage | None = None,
    cofre: Cofre | None = None,
) -> Resultado:
    """Encontra e (com `executar`) remove os gabinetes sintéticos e seus dados.

    Args:
        engine: Engine com o dono das tabelas (`LUPA_DATABASE_URL`).
        executar: Remove de fato; sem isso só conta e desfaz.
        prefixos: Prefixos de nome dos gabinetes sintéticos.
        ambiente: `LUPA_AMBIENTE` corrente.
        storage: Storage dos objetos (apagados só com `executar`).
        cofre: Cofre (chaves do gabinete destruídas só com `executar`).

    Returns:
        Contagens.

    Raises:
        RecusaError: Fora de desenvolvimento/teste, ou evento global ligado a esses usuários.
    """
    if ambiente not in AMBIENTES_PERMITIDOS:
        raise RecusaError("recusado fora de desenvolvimento/teste")
    condicoes, parametros = _filtro_prefixos(prefixos)
    por_id: BindParameter[list[UUID]] = bindparam("ids", expanding=True)
    linhas: dict[str, int] = {}
    processos: list[tuple[UUID, UUID]] = []
    with engine.connect() as conexao:
        transacao = conexao.begin()
        try:
            consulta = text(f"SELECT id FROM gabinete WHERE {condicoes}")  # noqa: S608
            ids: list[UUID] = list(conexao.execute(consulta, parametros).scalars())
            eventos = 0
            if ids:
                globais = conexao.execute(
                    text(
                        "SELECT count(*) FROM evento_auditoria e "
                        "JOIN usuario u ON u.id = e.usuario_id "
                        "WHERE e.gabinete_id IS NULL AND u.gabinete_id IN :ids"
                    ).bindparams(por_id),
                    {"ids": ids},
                ).scalar_one()
                if globais:
                    raise RecusaError(
                        f"{globais} evento(s) da cadeia global apontam para esses usuarios"
                    )
            conexao.execute(text(f"ALTER TABLE evento_auditoria DISABLE TRIGGER {TRAVA}"))
            if ids:
                eventos += conexao.execute(
                    text("DELETE FROM evento_auditoria WHERE gabinete_id IN :ids").bindparams(
                        por_id
                    ),
                    {"ids": ids},
                ).rowcount
            conexao.execute(text(f"ALTER TABLE evento_auditoria ENABLE TRIGGER {TRAVA}"))
            if ids:
                processos = _descartar_processos(conexao, ids, por_id)
                for tabela in reversed(Base.metadata.sorted_tables):
                    if tabela.name in {"evento_auditoria", "gabinete"}:
                        continue
                    if "gabinete_id" not in tabela.c:
                        continue
                    apagar = text(f"DELETE FROM {tabela.name} WHERE gabinete_id IN :ids")  # noqa: S608
                    total = conexao.execute(apagar.bindparams(por_id), {"ids": ids}).rowcount
                    if total:
                        linhas[tabela.name] = total
                conexao.execute(
                    text("DELETE FROM gabinete WHERE id IN :ids").bindparams(por_id), {"ids": ids}
                )
            if executar:
                transacao.commit()
            else:
                transacao.rollback()
        except BaseException:
            if transacao.is_active:
                transacao.rollback()
            raise
    apagados = _apagar_fora_do_banco(processos, ids, storage, cofre) if executar else 0
    return Resultado(len(ids), eventos, linhas, executar, len(processos), apagados)


def main(argumentos: Sequence[str]) -> int:
    """Ponto de entrada.

    Args:
        argumentos: Argumentos da linha de comando (sem o nome do programa).

    Returns:
        Código de saída (0 ok, 2 recusado).
    """
    settings = get_settings()
    executar = "--sim" in argumentos
    if settings.ambiente not in AMBIENTES_PERMITIDOS:
        sys.stderr.write("limpar_dev: recusado fora de desenvolvimento/teste\n")
        return 2
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        resultado = limpar(
            engine,
            executar=executar,
            ambiente=settings.ambiente,
            storage=criar_storage(settings),
            cofre=criar_cofre(settings),
        )
    except RecusaError as erro:
        sys.stderr.write(f"limpar_dev: {erro}\n")
        return 2
    finally:
        engine.dispose()
    verbo = "removidos" if resultado.executado else "seriam removidos (use --sim para remover)"
    sys.stdout.write(f"gabinetes {verbo}: {resultado.gabinetes}\n")
    sys.stdout.write(f"eventos de auditoria {verbo}: {resultado.eventos}\n")
    sys.stdout.write(f"processos descartados: {resultado.processos_descartados}\n")
    sys.stdout.write(f"objetos apagados do storage: {resultado.objetos_apagados}\n")
    for tabela, total in sorted(resultado.linhas.items()):
        sys.stdout.write(f"  {tabela}: {total}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
