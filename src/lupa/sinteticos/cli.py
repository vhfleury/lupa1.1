"""Linha de comando dos autos sintéticos (usada por ``scripts/gerar_autos.py`` e ``medir.py``).

Os arquivos gerados vão para ``LUPA_SINTETICOS_DIR`` ou, sem ela, para ``.sinteticos/`` na raiz
do repositório (ignorada pelo git). Logs são JSON, sem texto dos autos.
"""

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from lupa.dominio.enums import TipoPeca
from lupa.logging import configurar_logging, get_logger
from lupa.sinteticos.gabarito import TODOS_VETORES, Cenario, Gabarito, VetorInjecao
from lupa.sinteticos.medicao import medir, para_markdown
from lupa.sinteticos.referencia import (
    REFERENCIAS,
    ResumoGeracao,
    configuracoes_injecao,
    gerar_processo,
    mistura,
)
from lupa.sinteticos.roteiro import Configuracao
from lupa.sinteticos.saida_pipeline import SaidaPipeline

_LOG = get_logger("lupa.sinteticos")


def destino_padrao() -> Path:
    """Pasta padrão dos autos gerados.

    Returns:
        ``LUPA_SINTETICOS_DIR`` ou ``<repositório>/.sinteticos``.
    """
    configurado = os.environ.get("LUPA_SINTETICOS_DIR")
    return Path(configurado) if configurado else Path(__file__).resolve().parents[3] / ".sinteticos"


def _registrar(resumos: list[ResumoGeracao], arquivo: Path) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(
        json.dumps([asdict(r) for r in resumos], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for resumo in resumos:
        _LOG.info("processo_sintetico_gerado", **asdict(resumo))


def _gerar(args: argparse.Namespace) -> int:
    injecoes = TODOS_VETORES if args.injecoes == "todas" else tuple(
        VetorInjecao(v) for v in args.injecoes.split(",") if v
    )  # fmt: skip
    config = Configuracao(
        semente=args.semente, paginas_alvo=args.paginas, mistura=mistura(args.digitalizada),
        injecoes=injecoes,
        duas_colunas=tuple(TipoPeca(t) for t in args.duas_colunas.split(",") if t),
    )  # fmt: skip
    cenarios = tuple(Cenario(c) for c in args.cenarios.split(","))
    resumo = gerar_processo(args.nome or f"processo_{args.semente}", config, args.destino, cenarios)
    _registrar([resumo], args.destino / f"resumo_{resumo.nome}.json")
    return 0


def _referencia(args: argparse.Namespace) -> int:
    nomes = args.somente.split(",") if args.somente else list(REFERENCIAS)
    resumos = [gerar_processo(n, REFERENCIAS[n], args.destino / "referencia") for n in nomes]
    _registrar(resumos, args.destino / "referencia" / "resumo.json")
    return 0


def _injecao(args: argparse.Namespace) -> int:
    variantes = configuracoes_injecao(args.paginas)
    resumos = [
        gerar_processo(nome, config, args.destino / "injecao", (Cenario.PDF_LISO,))
        for nome, config in variantes.items()
    ]
    _registrar(resumos, args.destino / "injecao" / "resumo.json")
    return 0


def _medir(args: argparse.Namespace) -> int:
    gabarito = Gabarito.model_validate_json(args.gabarito.read_text(encoding="utf-8"))
    saida = SaidaPipeline.model_validate_json(args.saida.read_text(encoding="utf-8"))
    relatorio = medir(gabarito, saida)
    args.json.write_text(relatorio.model_dump_json(indent=2), encoding="utf-8")
    args.markdown.write_text(para_markdown(relatorio), encoding="utf-8")
    _LOG.info("medicao_concluida", processo=relatorio.processo, cenario=relatorio.cenario)
    return 0


def _parser_gerar() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gerar_autos.py", description=__doc__)
    parser.add_argument("--destino", type=Path, default=destino_padrao())
    sub = parser.add_subparsers(dest="comando", required=True)
    um = sub.add_parser("processo", help="gera um processo nos três cenários")
    um.add_argument("--semente", type=int, required=True)
    um.add_argument("--paginas", type=int, default=40)
    um.add_argument("--digitalizada", type=float, default=0.25)
    um.add_argument("--cenarios", default=",".join(c.value for c in Cenario))
    um.add_argument("--injecoes", default="", help="'todas' ou vetores separados por vírgula")
    um.add_argument("--nome", default=None)
    um.add_argument("--duas-colunas", default="", help="tipos de peça em duas colunas: laudo,...")
    um.set_defaults(funcao=_gerar)
    ref = sub.add_parser("referencia", help="gera os dez processos de referência")
    ref.add_argument("--somente", default=None, help="ex.: semente_01,semente_02")
    ref.set_defaults(funcao=_referencia)
    inj = sub.add_parser("injecao", help="gera o corpus de injeção")
    inj.add_argument("--paginas", type=int, default=30)
    inj.set_defaults(funcao=_injecao)
    return parser


def main_gerar(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada de ``scripts/gerar_autos.py``.

    Args:
        argv: Argumentos (padrão: os da linha de comando).

    Returns:
        Código de saída.
    """
    configurar_logging()
    args = _parser_gerar().parse_args(argv)
    return int(args.funcao(args))


def main_medir(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada de ``scripts/medir.py``.

    Args:
        argv: Argumentos (padrão: os da linha de comando).

    Returns:
        Código de saída.
    """
    configurar_logging()
    parser = argparse.ArgumentParser(prog="medir.py", description="compara saída e gabarito")
    parser.add_argument("--gabarito", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    return _medir(parser.parse_args(argv))
