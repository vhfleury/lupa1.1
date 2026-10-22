"""CLI de conferência: ``python -m lupa.validacoes --fatos fatos.json --materia criminal``."""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import TypeAdapter

from lupa.dominio.esquemas import Fato
from lupa.validacoes.adaptador import para_modelo
from lupa.validacoes.motor import executar_catalogo

_FATOS = TypeAdapter(list[Fato])


def main(argv: Sequence[str] | None = None) -> int:
    """Lê fatos do domínio de um JSON, executa o catálogo e imprime os achados em JSON.

    Args:
        argv: Argumentos (padrão: os da linha de comando).

    Returns:
        Código de saída.
    """
    parser = argparse.ArgumentParser(prog="python -m lupa.validacoes")
    parser.add_argument("--fatos", type=Path, required=True, help="arquivo JSON com lista de fatos")
    parser.add_argument("--materia", default="criminal", choices=["criminal", "civel"])
    parser.add_argument("--referencia", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)
    fatos = _FATOS.validate_json(args.fatos.read_text(encoding="utf-8"))
    referencia = args.referencia or date.today()
    achados = executar_catalogo(para_modelo(fatos), args.materia, referencia)
    saida = [a.model_dump(mode="json") for a in achados]
    sys.stdout.write(json.dumps(saida, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
