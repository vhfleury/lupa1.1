"""Execução de parsers em subprocesso isolado, com limites de memória, CPU e tempo.

O filho roda com `python -I`, ambiente mínimo (sem variáveis `LUPA_*`, portanto sem URL nem
credenciais do banco, do storage ou do Redis), diretório de trabalho temporário, sockets
desabilitados no próprio filho e limites `setrlimit` de espaço de endereçamento, CPU, tamanho
de arquivo gravado e descritores. O resultado volta só por JSON em stdout; stderr é descartado
(nunca vai ao log). Isolamento de rede no nível do sistema vem do contêiner do worker, que fica
numa rede interna sem saída (ver `docs/ingestao.md`).
"""

import json
import os
import resource
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lupa
from lupa.dominio.enums import MotivoFalha
from lupa.ingestao.parser_pdf import EXIT_MEMORIA

MB = 1024 * 1024
MAX_DESCRITORES = 64
SINAIS_CPU = frozenset({-signal.SIGXCPU, -signal.SIGKILL})
MODULO_PARSER_PDF = "lupa.ingestao.parser_pdf"


@dataclass(frozen=True)
class LimitesSandbox:
    """Limites do processo filho.

    Attributes:
        memoria_mb: Espaço de endereçamento máximo (RLIMIT_AS).
        cpu_segundos: Tempo de CPU (RLIMIT_CPU).
        tempo_segundos: Tempo de parede, imposto pelo pai.
    """

    memoria_mb: int = 1024
    cpu_segundos: int = 60
    tempo_segundos: float = 120.0


@dataclass(frozen=True)
class ResultadoSandbox:
    """Resultado de uma execução no sandbox.

    Attributes:
        dados: Objeto JSON devolvido pelo filho (vazio em falha).
        motivo_falha: Motivo quando o filho não terminou normalmente.
    """

    dados: dict[str, Any] = field(default_factory=dict)
    motivo_falha: MotivoFalha | None = None

    @property
    def ok(self) -> bool:
        """Verdadeiro se o filho terminou e devolveu JSON."""
        return self.motivo_falha is None


def _aplicar_limites(limites: LimitesSandbox) -> Callable[[], None]:
    def _preexec() -> None:  # pragma: no cover (roda no processo filho)
        memoria = limites.memoria_mb * MB
        resource.setrlimit(resource.RLIMIT_AS, (memoria, memoria))
        resource.setrlimit(resource.RLIMIT_CPU, (limites.cpu_segundos, limites.cpu_segundos + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (MAX_DESCRITORES, MAX_DESCRITORES))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return _preexec


def _ambiente_minimo(diretorio: str) -> dict[str, str]:
    return {"PATH": os.defpath, "HOME": diretorio, "LANG": "C.UTF-8", "TMPDIR": diretorio}


def _comando(modulo: str, argumentos: list[str]) -> list[str]:
    raiz = str(Path(lupa.__file__).resolve().parents[1])
    codigo = f"import sys; sys.path.insert(0, {raiz!r}); from {modulo} import main; main()"
    return [sys.executable, "-I", "-c", codigo, *argumentos]


def _motivo_por_codigo(codigo: int) -> MotivoFalha:
    if codigo == EXIT_MEMORIA:
        return MotivoFalha.LIMITE_MEMORIA
    if codigo in SINAIS_CPU:
        return MotivoFalha.LIMITE_CPU
    return MotivoFalha.ERRO_PARSER


def executar(modulo: str, argumentos: list[str], limites: LimitesSandbox) -> ResultadoSandbox:
    """Executa `modulo.main()` num processo filho limitado e lê o JSON de stdout.

    Args:
        modulo: Módulo com função `main()` que escreve um objeto JSON em stdout.
        argumentos: Argumentos do filho (caminhos de arquivo).
        limites: Limites de recurso.

    Returns:
        Dados do filho, ou o motivo da falha (memória, CPU, tempo, erro).
    """
    with tempfile.TemporaryDirectory(prefix="lupa-sandbox-") as diretorio:
        try:
            processo = subprocess.run(  # noqa: S603
                _comando(modulo, argumentos),
                capture_output=True,
                timeout=limites.tempo_segundos,
                env=_ambiente_minimo(diretorio),
                cwd=diretorio,
                preexec_fn=_aplicar_limites(limites),  # noqa: PLW1509
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ResultadoSandbox(motivo_falha=MotivoFalha.TEMPO_ESGOTADO)
    if processo.returncode != 0:
        return ResultadoSandbox(motivo_falha=_motivo_por_codigo(processo.returncode))
    try:
        dados = json.loads(processo.stdout)
    except ValueError:
        return ResultadoSandbox(motivo_falha=MotivoFalha.ERRO_PARSER)
    if not isinstance(dados, dict):
        return ResultadoSandbox(motivo_falha=MotivoFalha.ERRO_PARSER)
    return ResultadoSandbox(dados=dados)


def inspecionar_pdf(caminho: Path, limites: LimitesSandbox) -> ResultadoSandbox:
    """Inspeciona um PDF no sandbox (ver `lupa.ingestao.parser_pdf`).

    Args:
        caminho: Arquivo PDF legível pelo filho.
        limites: Limites de recurso.

    Returns:
        Resultado da inspeção.
    """
    return executar(MODULO_PARSER_PDF, [str(caminho)], limites)


def inspecionar_pdfs(caminhos: Sequence[Path], limites: LimitesSandbox) -> list[ResultadoSandbox]:
    """Inspeciona vários PDFs num único filho do sandbox (entradas de um ZIP).

    A partida do filho (interpretador e PyMuPDF) custa perto de 0,8 s e domina a inspeção de
    peças pequenas. Se o filho do grupo falhar (memória, CPU, tempo), cada PDF é reinspecionado
    sozinho, para que o motivo da falha fique com a entrada que o causou.

    Args:
        caminhos: Arquivos PDF legíveis pelo filho, na ordem desejada.
        limites: Limites de recurso do grupo (e de cada reinspeção individual).

    Returns:
        Um resultado por caminho, na mesma ordem.
    """
    if len(caminhos) <= 1:
        return [inspecionar_pdf(c, limites) for c in caminhos]
    grupo = executar(MODULO_PARSER_PDF, [str(c) for c in caminhos], limites)
    itens = grupo.dados.get("itens") if grupo.ok else None
    if not isinstance(itens, list) or len(itens) != len(caminhos):
        return [inspecionar_pdf(c, limites) for c in caminhos]
    return [ResultadoSandbox(dados=dict(item)) for item in itens]
