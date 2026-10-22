"""Definição do gabinete corrente para a Row Level Security do PostgreSQL."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

VARIAVEL_GABINETE = "lupa.gabinete_id"
VARIAVEL_PAPEL = "lupa.papel"
PAPEL_APLICACAO = "lupa_app"


def definir_gabinete(session: Session, gabinete_id: UUID) -> None:
    """Define `lupa.gabinete_id` só para a transação corrente (equivale a `SET LOCAL`).

    A camada de API chama esta função no início de cada requisição autenticada, dentro da
    transação da requisição; ao fim da transação a variável deixa de valer.

    Args:
        session: Sessão SQLAlchemy com transação aberta.
        gabinete_id: Gabinete do usuário autenticado.
    """
    session.execute(
        text("SELECT set_config(:nome, :valor, true)"),
        {"nome": VARIAVEL_GABINETE, "valor": str(gabinete_id)},
    )


def assumir_papel_aplicacao(session: Session) -> None:
    """Troca, só na transação corrente, para o papel sem privilégios sujeito à RLS.

    Args:
        session: Sessão SQLAlchemy com transação aberta.
    """
    session.execute(text(f"SET LOCAL ROLE {PAPEL_APLICACAO}"))


def definir_papel(session: Session, papel: str) -> None:
    """Define `lupa.papel` só para a transação corrente.

    A política `<tabela>_administrador` da migração 0002 libera todas as linhas quando o
    valor é `administrador`; para os demais papéis vale só a política por gabinete.

    Args:
        session: Sessão SQLAlchemy com transação aberta.
        papel: Papel do usuário autenticado (valor de `PapelUsuario`).
    """
    session.execute(
        text("SELECT set_config(:nome, :valor, true)"),
        {"nome": VARIAVEL_PAPEL, "valor": papel},
    )
