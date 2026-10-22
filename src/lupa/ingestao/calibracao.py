"""Execução local da pipeline sobre um arquivo e relatório para conferência manual (4F.9, 4F.10).

Usado por ``scripts/calibrar.py`` (processo real do Projudi, quando existir) e por
``scripts/ponta_a_ponta.py`` (processos de referência). O arquivo é lacrado no storage
configurado e processado pelo mesmo código do worker (``processar_job``), até os achados. O
relatório reúne diagnóstico, qualidade por página, índice de peças, fatos com evidência e
achados, em Markdown, para o assessor conferir lado a lado com os autos.

O relatório contém trechos dos autos (as evidências): é material de conferência, fica dentro
do contêiner e nunca entra no repositório nem em log.
"""

import hashlib
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lupa.dominio.cnj import calcular_digito_verificador
from lupa.dominio.enums import EstadoJob, Materia, PapelUsuario, StatusProcesso
from lupa.dominio.repositorios import listar_fatos_por_processo
from lupa.dominio.tabelas import (
    GabineteTabela,
    PaginaTabela,
    ProcessoTabela,
    ReuTabela,
    UsuarioTabela,
)
from lupa.ingestao import repositorio, repositorio_eventos, repositorio_pecas
from lupa.ingestao.recepcao import ArquivoRecebido, TipoArquivo, detectar_tipo, lacrar
from lupa.ingestao.worker import Dependencias, processar_job
from lupa.validacoes.modelo import valor_de

ESTADOS_FINAIS = frozenset(
    {EstadoJob.CONCLUIDO, EstadoJob.PARCIAL, EstadoJob.FALHO, EstadoJob.QUARENTENA}
)
MAX_RODADAS = 200
TAMANHO_BLOCO = 1 << 20


@dataclass(frozen=True)
class Execucao:
    """Resultado de uma execução da pipeline sobre um arquivo.

    Attributes:
        gabinete_id: Gabinete.
        processo_id: Processo criado.
        arquivo_id: Arquivo lacrado.
        job_id: Job.
        estado: Estado final do job.
        segundos: Tempo de parede do processamento (sem a recepção).
    """

    gabinete_id: UUID
    processo_id: UUID
    arquivo_id: UUID
    job_id: UUID
    estado: EstadoJob | None
    segundos: float


def numero_cnj(sequencial: int) -> str:
    """Número CNJ sintético válido para o processo de calibração.

    Args:
        sequencial: Sequencial (até 7 dígitos).

    Returns:
        Número formatado com dígito verificador.
    """
    seq, ano, justica, tribunal, origem = (
        f"{sequencial % 10_000_000:07d}",
        "2026",
        "8",
        "09",
        "0001",
    )
    digito = calcular_digito_verificador(seq, ano, justica, tribunal, origem)
    return f"{seq}-{digito}.{ano}.{justica}.{tribunal}.{origem}"


def semear_gabinete(session: Session, rotulo: str) -> tuple[UUID, UUID]:
    """Cria um gabinete e um assessor sem senha utilizável, só para a execução local.

    Args:
        session: Sessão do dono das tabelas (sem RLS).
        rotulo: Rótulo do gabinete (sem dado real).

    Returns:
        Ids do gabinete e do usuário.
    """
    gabinete_id, usuario_id = uuid4(), uuid4()
    session.add(GabineteTabela(id=gabinete_id, nome=f"{rotulo} {gabinete_id.hex[:6]}"))
    session.flush()
    session.add(
        UsuarioTabela(
            id=usuario_id, gabinete_id=gabinete_id, nome_usuario=f"local_{usuario_id.hex[:10]}",
            papel=PapelUsuario.ASSESSOR.value, senha_hash="!", ativo=False,
        )
    )  # fmt: skip
    session.flush()
    return gabinete_id, usuario_id


def novo_processo(
    session: Session, gabinete_id: UUID, usuario_id: UUID, materia: Materia = Materia.CRIMINAL
) -> UUID:
    """Cria um processo vazio no gabinete.

    Args:
        session: Sessão do dono das tabelas.
        gabinete_id: Gabinete.
        usuario_id: Autor.
        materia: Matéria.

    Returns:
        Id do processo.
    """
    processo_id = uuid4()
    session.add(
        ProcessoTabela(
            id=processo_id, gabinete_id=gabinete_id, numero_cnj=numero_cnj(processo_id.int),
            classe="Calibração", materia=materia.value, sigiloso=False,
            status=StatusProcesso.CRIADO.value, criado_por=usuario_id,
        )
    )  # fmt: skip
    session.flush()
    return processo_id


def sha256_arquivo(caminho: Path) -> str:
    """SHA-256 do arquivo lido em blocos.

    Args:
        caminho: Arquivo.

    Returns:
        Hash hexadecimal.
    """
    resumo = hashlib.sha256()
    with caminho.open("rb") as entrada:
        while bloco := entrada.read(TAMANHO_BLOCO):
            resumo.update(bloco)
    return resumo.hexdigest()


def enviar_e_processar(
    deps: Dependencias,
    dono: sessionmaker[Session],
    gabinete_id: UUID,
    usuario_id: UUID,
    caminho: Path,
) -> Execucao:
    """Lacra o arquivo num processo novo e roda o worker até um estado final.

    Args:
        deps: Dependências do worker (use ``fila=None`` para não fatiar).
        dono: Fábrica de sessões do dono das tabelas (para semear sem RLS).
        gabinete_id: Gabinete.
        usuario_id: Usuário que envia.
        caminho: PDF ou ZIP.

    Returns:
        Execução com ids, estado final e tempo.

    Raises:
        ValueError: Se o arquivo não é PDF nem ZIP.
    """
    with caminho.open("rb") as entrada:
        tipo = detectar_tipo(entrada.read(8))
    if tipo is None:
        raise ValueError("arquivo não é PDF nem ZIP")
    recebido = ArquivoRecebido(
        caminho, sha256_arquivo(caminho), caminho.stat().st_size, TipoArquivo(tipo)
    )
    with dono() as session, session.begin():
        processo_id = novo_processo(session, gabinete_id, usuario_id)
        lacre = lacrar(
            session, deps.storage, recebido, gabinete_id=gabinete_id, processo_id=processo_id,
            enviado_por=usuario_id, nome_original=caminho.name,
        )  # fmt: skip
    inicio = time.perf_counter()
    estado: EstadoJob | None = None
    for _ in range(MAX_RODADAS):
        estado = processar_job(deps, lacre.job_id, gabinete_id)
        if estado in ESTADOS_FINAIS:
            break
    return Execucao(
        gabinete_id, processo_id, lacre.arquivo_id, lacre.job_id, estado,
        time.perf_counter() - inicio,
    )  # fmt: skip


def _paginas(session: Session, arquivo_id: UUID) -> dict[UUID, dict[str, Any]]:
    consulta = select(
        PaginaTabela.id, PaginaTabela.numero, PaginaTabela.tipo, PaginaTabela.origem_arquivo,
        PaginaTabela.pagina_origem, PaginaTabela.flags,
    ).where(PaginaTabela.arquivo_id == arquivo_id)  # fmt: skip
    chaves = ("id", "numero", "tipo", "origem_arquivo", "pagina_origem", "flags")
    return {linha[0]: dict(zip(chaves, linha, strict=True)) for linha in session.execute(consulta)}


def _fatos(session: Session, processo_id: UUID, paginas: dict[UUID, dict[str, Any]]) -> list[Any]:
    saida = []
    for fato in listar_fatos_por_processo(session, processo_id):
        evidencia = fato.evidencias[0]
        pagina = paginas.get(evidencia.pagina_id, {})
        saida.append(
            {
                "tipo": str(fato.tipo),
                "valor": valor_de(fato),
                "por_reu": isinstance(fato.valor, dict) and "reu_id" in fato.valor,
                "confianca": fato.confianca,
                "pagina": pagina.get("numero"),
                "arquivo": pagina.get("origem_arquivo"),
                "pagina_origem": pagina.get("pagina_origem"),
                "trecho": evidencia.trecho,
                "evidencias": len(fato.evidencias),
                "versao_extrator": fato.versao_extrator,
            }
        )
    return sorted(saida, key=lambda f: (f["pagina"] or 0, f["tipo"]))


def coletar(session: Session, processo_id: UUID, arquivo_id: UUID) -> dict[str, Any]:
    """Junta o que a pipeline produziu para o arquivo e o processo.

    Args:
        session: Sessão com transação aberta (RLS do gabinete).
        processo_id: Processo.
        arquivo_id: Arquivo.

    Returns:
        Diagnóstico, relatório do job, páginas por tipo, índice, réus, fatos e achados.
    """
    diagnostico = repositorio.obter_diagnostico(session, arquivo_id)
    paginas = _paginas(session, arquivo_id)
    pseudonimos = session.scalars(
        select(ReuTabela.pseudonimo).where(ReuTabela.processo_id == processo_id)
    )
    return {
        "diagnostico": diagnostico.model_dump(mode="json") if diagnostico else None,
        "job": repositorio.obter_relatorio(session, arquivo_id),
        "paginas_por_tipo": dict(Counter(p["tipo"] for p in paginas.values())),
        "paginas_com_flag": sum(1 for p in paginas.values() if any(p["flags"].values())),
        "indice": repositorio_pecas.indice_processo(session, processo_id),
        "reus": sorted(pseudonimos),
        "fatos": _fatos(session, processo_id, paginas),
        "achados": [
            a.model_dump(mode="json")
            for a in repositorio_eventos.achados_vigentes(session, processo_id)
        ],
    }


def _celula(valor: Any) -> str:
    texto = " ".join(str(valor).split())
    return texto.replace("|", "\\|")


def _secao_diagnostico(dados: dict[str, Any]) -> list[str]:
    diagnostico = dados["diagnostico"] or {}
    job = dados["job"] or {}
    relatorio = job.get("relatorio") or {}
    tempo = relatorio.get("tempo") or {}
    return [
        "## 1. Diagnóstico e páginas",
        "",
        "| Item | Valor |",
        "| --- | --- |",
        f"| Cenário diagnosticado | {diagnostico.get('cenario')} |",
        f"| Total de páginas | {diagnostico.get('total_paginas')} |",
        f"| Fronteiras vindas da origem | {len(diagnostico.get('fronteiras_origem') or [])} |",
        f"| Estado do job | {job.get('estado')} |",
        f"| Páginas por tipo | {_celula(dados['paginas_por_tipo'])} |",
        f"| Páginas abstidas (OCR integral) | {relatorio.get('abstidas')} |",
        f"| CER estimado | {relatorio.get('cer_estimado')} |",
        f"| Páginas com flag de saneamento | {dados['paginas_com_flag']} |",
        f"| Tempo de extração (s) | {tempo.get('parede_segundos')} |",
        f"| Tempo por mil páginas (s) | {tempo.get('por_mil_paginas')} |",
        "",
    ]


def _secao_pecas(dados: dict[str, Any]) -> list[str]:
    linhas = [
        "## 2. Peças (índice)",
        "",
        "Conferir: a peça começa nessa página? O tipo e a origem estão certos? A data é a da peça?",
        "",
        "| # | Páginas | Tipo | Origem | Data | Tipo da data | Confiança | Marcas | Confere? |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for peca in dados["indice"]:
        marcas = ", ".join(peca["resumo_flags"]["peca"]) or "-"
        linhas.append(
            f"| {peca['ordem']} | {peca['pagina_inicial']}-{peca['pagina_final']} | {peca['tipo']} "
            f"| {peca['origem']} | {peca['data'] or '-'} | {peca['tipo_data'] or '-'} "
            f"| {peca['confianca']:.2f} | {marcas} | |"
        )
    return [*linhas, ""]


def _secao_fatos(dados: dict[str, Any]) -> list[str]:
    linhas = [
        "## 3. Eventos (fatos) com evidência",
        "",
        f"Réus: {', '.join(dados['reus']) or 'nenhum'} (nomes só em `reu_identidade`).",
        "",
        "| Página | Tipo | Valor | Confiança | Trecho | Confere? |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for fato in dados["fatos"]:
        linhas.append(
            f"| {fato['pagina']} | {fato['tipo']} | {_celula(fato['valor'])} "
            f"| {fato['confianca']:.2f} | {_celula(fato['trecho'])} | |"
        )
    return [*linhas, ""]


def _secao_achados(dados: dict[str, Any]) -> list[str]:
    linhas = ["## 4. Achados", ""]
    for achado in dados["achados"]:
        linhas += [
            f"### {achado['validacao']}: {achado['resultado']}",
            "",
            _celula(achado["explicacao"]),
            "",
        ]
    return linhas


def para_markdown(dados: dict[str, Any], titulo: str) -> str:
    """Relatório de diagnóstico em Markdown, com colunas "Confere?" para o assessor.

    Args:
        dados: Saída de ``coletar``.
        titulo: Título (sem nome de parte).

    Returns:
        Markdown.
    """
    linhas = [f"# Calibração: {titulo}", ""]
    linhas += _secao_diagnostico(dados)
    linhas += _secao_pecas(dados)
    linhas += _secao_fatos(dados)
    linhas += _secao_achados(dados)
    return "\n".join(linhas) + "\n"
