"""Revisão 0004, escrita à mão: colunas da extração de páginas (Etapa 4C).

- `pagina`: sinais, coordenadas, dados da extração, textos nativo e OCR, versão do extrator e
  posição de origem (entrada do ZIP e página dentro dela).
- `job_ingestao`: relatório de qualidade e versão do extrator.
- `diagnostico_arquivo`: fronteiras candidatas vindas do índice, dos bookmarks ou do manifesto;
  o CHECK de `cenario` passa a aceitar `pdf_com_bookmarks_e_indice`.
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from lupa.dominio.enums import CenarioArquivo

CENARIOS_V0003 = ("zip_por_peca", "pdf_com_bookmarks", "pdf_com_indice", "pdf_liso")


def _json(nome: str, padrao: str) -> sa.Column[Any]:
    return sa.Column(nome, JSONB, server_default=padrao, nullable=False)


def _checar_cenario(valores: tuple[str, ...]) -> None:
    op.drop_constraint("cenario_valido", "diagnostico_arquivo", type_="check")
    lista = ", ".join(f"'{valor}'" for valor in valores)
    op.create_check_constraint("cenario_valido", "diagnostico_arquivo", f"cenario IN ({lista})")


def upgrade() -> None:
    """Acrescenta as colunas da extração de páginas e o novo cenário."""
    op.add_column("pagina", _json("sinais", "{}"))
    op.add_column("pagina", _json("coordenadas", "{}"))
    op.add_column("pagina", _json("extracao", "{}"))
    for coluna in ("texto_nativo", "texto_ocr", "versao_extrator", "origem_arquivo"):
        op.add_column("pagina", sa.Column(coluna, sa.Text(), nullable=True))
    op.add_column("pagina", sa.Column("pagina_origem", sa.Integer(), nullable=True))
    op.add_column("job_ingestao", sa.Column("relatorio", JSONB, nullable=True))
    op.add_column("job_ingestao", sa.Column("versao_extrator", sa.Text(), nullable=True))
    op.add_column("diagnostico_arquivo", _json("fronteiras_origem", "[]"))
    _checar_cenario(tuple(c.value for c in CenarioArquivo))


def downgrade() -> None:
    """Remove as colunas acrescentadas e restaura o CHECK de `cenario` da 0003."""
    op.execute("DELETE FROM diagnostico_arquivo WHERE cenario = 'pdf_com_bookmarks_e_indice'")
    _checar_cenario(CENARIOS_V0003)
    op.drop_column("diagnostico_arquivo", "fronteiras_origem")
    op.drop_column("job_ingestao", "versao_extrator")
    op.drop_column("job_ingestao", "relatorio")
    for coluna in (
        "pagina_origem", "origem_arquivo", "versao_extrator", "texto_ocr", "texto_nativo",
        "extracao", "coordenadas", "sinais",
    ):  # fmt: skip
        op.drop_column("pagina", coluna)
