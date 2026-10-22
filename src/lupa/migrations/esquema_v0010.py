"""Revisão 0010, escrita à mão: criptografia em repouso (Etapa 7.3 a 7.7).

- `processo.chave_dados_cifrada`: DEK do processo cifrada pela chave Transit do gabinete.
- `processo.status` aceita `descartado` (tombstone da exclusão criptográfica).
- `pagina.trechos_ocultos` e `trechos_suspeitos` passam de JSONB a texto (cifrado).
- `lupa_chave_processo(uuid)`: devolve gabinete e DEK cifrada (SECURITY DEFINER), para o
  contexto de cifra abrir a DEK de um processo cujo conteúdo a sessão já leu sob RLS.
- `lupa_descartar_processo(uuid)`: apaga o conteúdo do processo (inclusive tabelas sem DELETE
  para `lupa_app`), zera a DEK e deixa o tombstone; confere gabinete/papel da transação.
- Dados existentes: cada processo ganha DEK; textos, trechos e mensagens são cifrados em lote e
  identidades dos réus vão para o Transit. Idempotente: valor já cifrado é pulado.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection

PAPEL_APLICACAO = "lupa_app"
CHECK_STATUS = "ck_processo_status_valido"
STATUS_ANTIGOS = ("criado", "em_ingestao", "pronto", "bloqueado", "arquivado", "em_revisao")
STATUS_NOVOS = (*STATUS_ANTIGOS, "descartado")
LOTE = 500

# (tabela, coluna, rótulo, consulta que liga a linha ao processo)
COLUNAS_CIFRADAS: tuple[tuple[str, str, str, str], ...] = (
    ("pagina", "texto", "pagina.texto", "pagina"),
    ("pagina", "texto_nativo", "pagina.texto_nativo", "pagina"),
    ("pagina", "texto_ocr", "pagina.texto_ocr", "pagina"),
    ("pagina", "texto_normalizado", "pagina.texto_normalizado", "pagina"),
    ("pagina", "trechos_ocultos", "pagina.trechos_ocultos", "pagina"),
    ("pagina", "trechos_suspeitos", "pagina.trechos_suspeitos", "pagina"),
    ("evidencia", "trecho", "evidencia.trecho", "evidencia"),
    ("mensagem", "texto", "mensagem.texto", "mensagem"),
)

PROCESSO_DA_LINHA = {
    "pagina": "SELECT t.id, a.processo_id FROM pagina t JOIN arquivo a ON a.id = t.arquivo_id",
    "evidencia": (
        "SELECT t.id, a.processo_id FROM evidencia t JOIN pagina p ON p.id = t.pagina_id"
        " JOIN arquivo a ON a.id = p.arquivo_id"
    ),
    "mensagem": (
        "SELECT t.id, c.processo_id FROM mensagem t JOIN conversa c ON c.id = t.conversa_id"
    ),
}

SQL_FUNCOES = """
CREATE FUNCTION lupa_chave_processo(p_processo uuid)
RETURNS TABLE (gabinete_id uuid, chave text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT p.gabinete_id, p.chave_dados_cifrada FROM public.processo p WHERE p.id = p_processo
$$;

CREATE FUNCTION lupa_descartar_processo(p_processo uuid)
RETURNS text
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    v_gabinete uuid;
    v_chave text;
BEGIN
    SELECT p.gabinete_id, p.chave_dados_cifrada INTO v_gabinete, v_chave
      FROM public.processo p WHERE p.id = p_processo FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'processo inexistente' USING ERRCODE = 'no_data_found';
    END IF;
    IF coalesce(current_setting('lupa.papel', true), '') <> 'administrador'
       AND v_gabinete IS DISTINCT FROM
           NULLIF(current_setting('lupa.gabinete_id', true), '')::uuid THEN
        RAISE EXCEPTION 'processo de outro gabinete' USING ERRCODE = 'insufficient_privilege';
    END IF;
    DELETE FROM public.mensagem m USING public.conversa c
     WHERE m.conversa_id = c.id AND c.processo_id = p_processo;
    DELETE FROM public.chamada_modelo WHERE processo_id = p_processo;
    DELETE FROM public.conversa WHERE processo_id = p_processo;
    DELETE FROM public.revisao_processo WHERE processo_id = p_processo;
    DELETE FROM public.anotacao n USING public.achado a
     WHERE n.achado_id = a.id AND a.processo_id = p_processo;
    DELETE FROM public.anotacao n USING public.fato f
     WHERE n.fato_id = f.id AND f.processo_id = p_processo;
    DELETE FROM public.achado WHERE processo_id = p_processo;
    DELETE FROM public.fato WHERE processo_id = p_processo;
    DELETE FROM public.reu WHERE processo_id = p_processo;
    UPDATE public.peca pc SET data_evidencia_id = NULL FROM public.arquivo a
     WHERE pc.arquivo_id = a.id AND a.processo_id = p_processo
       AND pc.data_evidencia_id IS NOT NULL;
    DELETE FROM public.peca pc USING public.arquivo a
     WHERE pc.arquivo_id = a.id AND a.processo_id = p_processo AND pc.substitui_peca_id IS NOT NULL;
    DELETE FROM public.peca pc USING public.arquivo a
     WHERE pc.arquivo_id = a.id AND a.processo_id = p_processo;
    DELETE FROM public.diagnostico_arquivo d USING public.arquivo a
     WHERE d.arquivo_id = a.id AND a.processo_id = p_processo;
    DELETE FROM public.lote_ingestao l USING public.job_ingestao j
     WHERE l.job_id = j.id AND j.processo_id = p_processo;
    DELETE FROM public.job_ingestao WHERE processo_id = p_processo;
    DELETE FROM public.arquivo WHERE processo_id = p_processo;
    UPDATE public.processo SET chave_dados_cifrada = NULL, status = 'descartado'
     WHERE id = p_processo;
    RETURN v_chave;
END;
$$;

REVOKE ALL ON FUNCTION lupa_chave_processo(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION lupa_descartar_processo(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION lupa_chave_processo(uuid) TO lupa_app;
GRANT EXECUTE ON FUNCTION lupa_descartar_processo(uuid) TO lupa_app;
"""


def _check_status(valores: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{v}'" for v in valores)
    op.execute(f"ALTER TABLE processo DROP CONSTRAINT {CHECK_STATUS}")
    op.execute(f"ALTER TABLE processo ADD CONSTRAINT {CHECK_STATUS} CHECK (status IN ({lista}))")


def _trechos_para_texto() -> None:
    for coluna in ("trechos_ocultos", "trechos_suspeitos"):
        op.execute(f"ALTER TABLE pagina ALTER COLUMN {coluna} DROP DEFAULT")
        op.execute(f"ALTER TABLE pagina ALTER COLUMN {coluna} TYPE text USING {coluna}::text")
        op.execute(f"ALTER TABLE pagina ALTER COLUMN {coluna} SET DEFAULT '[]'")


def _trechos_para_jsonb() -> None:
    for coluna in ("trechos_ocultos", "trechos_suspeitos"):
        op.execute(f"ALTER TABLE pagina ALTER COLUMN {coluna} DROP DEFAULT")
        # Linha ainda cifrada (chave destruída) não tem como voltar: vira lista vazia.
        op.execute(
            f"ALTER TABLE pagina ALTER COLUMN {coluna} TYPE jsonb USING"
            f" CASE WHEN {coluna} LIKE 'lupa1:%' THEN '[]'::jsonb ELSE {coluna}::jsonb END"
        )
        op.execute(f"ALTER TABLE pagina ALTER COLUMN {coluna} SET DEFAULT '[]'::jsonb")


def _deks(conexao: Connection) -> dict[UUID, bytes]:
    from lupa.seguranca.cofre import ChaveAusenteError, TokenInvalidoError
    from lupa.seguranca.contexto import abrir_dek, nova_dek, obter_cofre

    cofre = obter_cofre()
    deks: dict[UUID, bytes] = {}
    for processo_id, gabinete_id, chave in conexao.execute(
        text(
            "SELECT id, gabinete_id, chave_dados_cifrada FROM processo WHERE status <> 'descartado'"
        )
    ).all():
        if chave is None:
            dek, chave = nova_dek(cofre, gabinete_id)
            conexao.execute(
                text("UPDATE processo SET chave_dados_cifrada = :c WHERE id = :id"),
                {"c": chave, "id": processo_id},
            )
        else:
            try:
                dek = abrir_dek(cofre, gabinete_id, chave)
            except (ChaveAusenteError, TokenInvalidoError):
                continue  # chave do gabinete destruída: conteúdo já ilegível, fica como está
        deks[processo_id] = dek
    return deks


def _converter(
    conexao: Connection,
    deks: dict[UUID, bytes],
    transformar: Callable[[bytes, UUID, str, str], str | None],
) -> None:
    for tabela, coluna, rotulo, base in COLUNAS_CIFRADAS:
        linhas = conexao.execute(
            text(
                f"SELECT q.id, q.processo_id, t.{coluna} FROM ({PROCESSO_DA_LINHA[base]}) q"  # noqa: S608
                f" JOIN {tabela} t ON t.id = q.id WHERE t.{coluna} IS NOT NULL"
            )
        ).all()
        mudancas: list[dict[str, Any]] = []
        for linha_id, processo_id, valor in linhas:
            dono = _dono_do_campo(valor) or processo_id
            dek = deks.get(dono)
            novo = transformar(dek, dono, rotulo, valor) if dek else None
            if novo is not None:
                mudancas.append({"id": linha_id, "v": novo})
            if len(mudancas) >= LOTE:
                _gravar(conexao, tabela, coluna, mudancas)
                mudancas = []
        if mudancas:
            _gravar(conexao, tabela, coluna, mudancas)


def _gravar(conexao: Connection, tabela: str, coluna: str, mudancas: list[dict[str, Any]]) -> None:
    conexao.execute(
        text(f"UPDATE {tabela} SET {coluna} = :v WHERE id = :id"),  # noqa: S608
        mudancas,
    )


def _cifrar(dek: bytes, processo_id: UUID, rotulo: str, valor: str) -> str | None:
    from lupa.seguranca.envelope import campo_cifrado, cifrar_campo

    if campo_cifrado(valor):
        return None
    return cifrar_campo(dek, processo_id, rotulo, valor)


def _dono_do_campo(valor: str) -> UUID | None:
    """Processo do cabeçalho de um campo já cifrado (é a DEK dele que abre o campo)."""
    from lupa.seguranca.envelope import CifraInvalidaError, campo_cifrado, processo_do_campo

    if not campo_cifrado(valor):
        return None
    try:
        return processo_do_campo(valor)
    except CifraInvalidaError:
        return None


def _decifrar(dek: bytes, _processo_id: UUID, rotulo: str, valor: str) -> str | None:
    from lupa.seguranca.envelope import CifraInvalidaError, campo_cifrado, decifrar_campo

    if not campo_cifrado(valor):
        return None
    try:
        return decifrar_campo(dek, valor, rotulo)
    except CifraInvalidaError:
        return None  # ilegível (chave destruída ou adulterado): fica como está


def _identidades(conexao: Connection, *, cifrar: bool) -> None:
    from lupa.seguranca.chaves import cifrar_identidade, decifrar_identidade
    from lupa.seguranca.cofre import ChaveAusenteError, TokenInvalidoError
    from lupa.seguranca.contexto import obter_cofre

    linhas = conexao.execute(
        text("SELECT reu_id, gabinete_id, nome, documento FROM reu_identidade")
    ).all()
    if not linhas:
        return
    cofre = obter_cofre()
    funcao = cifrar_identidade if cifrar else decifrar_identidade
    for reu_id, gabinete_id, nome, documento in linhas:
        try:
            valores = {
                "id": reu_id,
                "n": funcao(cofre, gabinete_id, nome),
                "d": funcao(cofre, gabinete_id, documento),
            }
        except (ChaveAusenteError, TokenInvalidoError):
            continue  # chave de identidades destruída: fica ilegível
        conexao.execute(
            text("UPDATE reu_identidade SET nome = :n, documento = :d WHERE reu_id = :id"),
            valores,
        )


def _tem_dados(conexao: Connection) -> bool:
    return bool(conexao.execute(text("SELECT EXISTS (SELECT 1 FROM processo)")).scalar())


def upgrade() -> None:
    """Cria a coluna da DEK, as funções e cifra os dados existentes."""
    op.execute("ALTER TABLE processo ADD COLUMN chave_dados_cifrada text")
    _check_status(STATUS_NOVOS)
    _trechos_para_texto()
    op.execute(SQL_FUNCOES)
    conexao = op.get_bind()
    if _tem_dados(conexao):
        deks = _deks(conexao)
        _converter(conexao, deks, _cifrar)
        _identidades(conexao, cifrar=True)
        deks.clear()


def downgrade() -> None:
    """Decifra os dados (processos descartados ficam como estão) e desfaz o esquema."""
    conexao = op.get_bind()
    if _tem_dados(conexao):
        deks = _deks(conexao)
        _converter(conexao, deks, _decifrar)
        _identidades(conexao, cifrar=False)
        deks.clear()
    op.execute("DROP FUNCTION lupa_descartar_processo(uuid)")
    op.execute("DROP FUNCTION lupa_chave_processo(uuid)")
    _trechos_para_jsonb()
    op.execute("UPDATE processo SET status = 'arquivado' WHERE status = 'descartado'")
    _check_status(STATUS_ANTIGOS)
    op.execute("ALTER TABLE processo DROP COLUMN chave_dados_cifrada")


__all__ = ["downgrade", "upgrade"]
