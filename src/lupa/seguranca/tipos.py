"""Tipos de coluna cifrados com a DEK do processo (`TextoCifrado`, `JsonCifrado`).

Na gravação o valor é cifrado com a DEK do processo ativo do contexto (`dek_para_gravar`); na
leitura o processo vem do cabeçalho do campo. O rótulo (`tabela.coluna`) entra no AAD. Valor
legado ainda em claro (antes da migração 0010) é devolvido como está.
"""

import json
from typing import Any

from sqlalchemy import Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from lupa.seguranca.contexto import dek_de, dek_para_gravar
from lupa.seguranca.envelope import (
    campo_cifrado,
    cifrar_campo,
    decifrar_campo,
    processo_do_campo,
)


def cifrar_valor(rotulo: str, texto: str) -> str:
    """Cifra um texto com a DEK do processo ativo.

    Args:
        rotulo: Coluna (`pagina.texto`...).
        texto: Texto em claro.

    Returns:
        Campo `lupa1:...`.
    """
    processo_id, dek = dek_para_gravar()
    return cifrar_campo(dek, processo_id, rotulo, texto)


def decifrar_valor(rotulo: str, valor: str) -> str:
    """Decifra um campo com a DEK do processo do cabeçalho.

    Args:
        rotulo: Coluna.
        valor: Campo `lupa1:...`.

    Returns:
        Texto em claro.
    """
    return decifrar_campo(dek_de(processo_do_campo(valor)), valor, rotulo)


class TextoCifrado(TypeDecorator[str]):
    """Texto guardado como `lupa1:<base64>`."""

    impl = Text
    cache_ok = True

    def __init__(self, rotulo: str) -> None:
        """Cria o tipo.

        Args:
            rotulo: Coluna (`tabela.coluna`), parte do AAD.
        """
        super().__init__()
        self.rotulo = rotulo

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        """Cifra na gravação.

        Args:
            value: Texto em claro.
            dialect: Dialeto (não usado).

        Returns:
            Campo cifrado.
        """
        if value is None or campo_cifrado(value):
            return value
        return cifrar_valor(self.rotulo, value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        """Decifra na leitura.

        Args:
            value: Campo do banco.
            dialect: Dialeto (não usado).

        Returns:
            Texto em claro.
        """
        if value is None or not campo_cifrado(value):
            return value
        return decifrar_valor(self.rotulo, value)


class JsonCifrado(TypeDecorator[Any]):
    """JSON serializado e guardado como `lupa1:<base64>`."""

    impl = Text
    cache_ok = True

    def __init__(self, rotulo: str) -> None:
        """Cria o tipo.

        Args:
            rotulo: Coluna (`tabela.coluna`), parte do AAD.
        """
        super().__init__()
        self.rotulo = rotulo

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """Serializa e cifra.

        Args:
            value: Valor JSON.
            dialect: Dialeto (não usado).

        Returns:
            Campo cifrado.
        """
        if value is None:
            return None
        if campo_cifrado(value):
            return str(value)
        return cifrar_valor(self.rotulo, json.dumps(value, ensure_ascii=False))

    def process_result_value(self, value: str | None, dialect: Dialect) -> Any:
        """Decifra e desserializa.

        Args:
            value: Campo do banco.
            dialect: Dialeto (não usado).

        Returns:
            Valor JSON.
        """
        if value is None:
            return None
        if campo_cifrado(value):
            return json.loads(decifrar_valor(self.rotulo, value))
        return json.loads(value) if isinstance(value, str) else value
