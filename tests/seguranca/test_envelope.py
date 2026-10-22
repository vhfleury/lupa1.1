"""Formatos de cifra: campo `lupa1:` e objeto `LUPAOBJ` (Etapa 7.3 a 7.5)."""

import io
from uuid import uuid4

import pytest

from lupa.seguranca.envelope import (
    TAMANHO_BLOCO,
    CifraInvalidaError,
    LeitorCifrado,
    campo_cifrado,
    cifrar_campo,
    cifrar_stream,
    decifrar_campo,
    decifrar_objeto,
    gerar_dek,
    objeto_cifrado,
    processo_do_campo,
)


def test_campo_ida_e_volta_e_cabecalho() -> None:
    """O campo decifra com a DEK e o rótulo certos e carrega o processo no cabeçalho."""
    dek, processo = gerar_dek(), uuid4()
    campo = cifrar_campo(dek, processo, "pagina.texto", "Certidão de intimação")
    assert campo_cifrado(campo) and "Certidão" not in campo
    assert processo_do_campo(campo) == processo
    assert decifrar_campo(dek, campo, "pagina.texto") == "Certidão de intimação"


def test_campo_recusa_chave_rotulo_ou_adulteracao() -> None:
    """DEK de outro processo, outra coluna ou um byte trocado: recusado."""
    dek, processo = gerar_dek(), uuid4()
    campo = cifrar_campo(dek, processo, "pagina.texto", "texto")
    with pytest.raises(CifraInvalidaError):
        decifrar_campo(gerar_dek(), campo, "pagina.texto")
    with pytest.raises(CifraInvalidaError):
        decifrar_campo(dek, campo, "mensagem.texto")
    adulterado = campo[:-4] + ("AAAA" if not campo.endswith("AAAA") else "BBBB")
    with pytest.raises(CifraInvalidaError):
        decifrar_campo(dek, adulterado, "pagina.texto")
    with pytest.raises(CifraInvalidaError):
        decifrar_campo(dek, "lupa1:@@@", "pagina.texto")
    with pytest.raises(CifraInvalidaError):
        decifrar_campo(dek, "lupa1:AAAA", "pagina.texto")


@pytest.mark.parametrize(
    "tamanho", [0, 1, 100, TAMANHO_BLOCO - 1, TAMANHO_BLOCO, TAMANHO_BLOCO + 1, 3 * TAMANHO_BLOCO]
)
def test_objeto_ida_e_volta(tamanho: int) -> None:
    """Objeto de qualquer tamanho (inclusive fronteira de bloco) volta igual."""
    dek = gerar_dek()
    claro = bytes(i % 251 for i in range(tamanho))
    cifrado = b"".join(cifrar_stream(dek, io.BytesIO(claro)))
    assert objeto_cifrado(cifrado)
    assert decifrar_objeto(dek, cifrado) == claro
    assert io.BufferedReader(LeitorCifrado(dek, io.BytesIO(claro))).read()[:7] == b"LUPAOBJ"


def test_objeto_recusa_truncado_chave_errada_e_versao() -> None:
    """Truncar no limite de bloco, outra DEK, cabeçalho desconhecido: recusado."""
    dek = gerar_dek()
    claro = b"%PDF-" + b"x" * (2 * TAMANHO_BLOCO)
    cifrado = b"".join(cifrar_stream(dek, io.BytesIO(claro)))
    cabecalho = 7 + 1 + 4 + 16
    with pytest.raises(CifraInvalidaError):
        decifrar_objeto(dek, cifrado[: cabecalho + TAMANHO_BLOCO + 16])
    with pytest.raises(CifraInvalidaError):
        decifrar_objeto(gerar_dek(), cifrado)
    with pytest.raises(CifraInvalidaError):
        decifrar_objeto(dek, cifrado[:7] + b"\x09" + cifrado[8:])
    with pytest.raises(CifraInvalidaError):
        decifrar_objeto(dek, b"%PDF-1.7")
    with pytest.raises(CifraInvalidaError):
        decifrar_objeto(dek, cifrado[:cabecalho] + b"curto")
