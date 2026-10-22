"""Testes do logging estruturado."""

import json

import pytest

from lupa.logging import (
    CAMPOS_PROIBIDOS,
    CampoProibidoError,
    configurar_logging,
    get_logger,
)


@pytest.mark.parametrize("campo", sorted(CAMPOS_PROIBIDOS))
def test_logger_rejeita_chave_proibida_em_modo_estrito(campo: str) -> None:
    """Em teste, qualquer campo proibido lança erro."""
    configurar_logging(estrito=True)
    with pytest.raises(CampoProibidoError):
        get_logger("teste").info("evento", **{campo: "valor ficticio"})


def test_logger_remove_chave_proibida_em_producao(capsys: pytest.CaptureFixture[str]) -> None:
    """Em produção, campo proibido é removido e o evento segue."""
    configurar_logging(estrito=False)
    get_logger("teste").info("evento", **{"senha": "x", "Token": "y"}, processo_id=7)
    registro = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "senha" not in registro
    assert "Token" not in registro
    assert registro["processo_id"] == 7


def test_logger_emite_json_com_campos_fixos(capsys: pytest.CaptureFixture[str]) -> None:
    """Todo evento tem timestamp, level, event e request_id."""
    configurar_logging(estrito=True)
    get_logger("teste").info("evento_qualquer")
    registro = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert {"timestamp", "level", "event", "request_id"} <= registro.keys()
    assert registro["event"] == "evento_qualquer"
