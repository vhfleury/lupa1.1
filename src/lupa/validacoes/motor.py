"""Motor que executa o catálogo de uma matéria sobre o modelo de um processo."""

from datetime import date

from lupa.logging import get_logger
from lupa.validacoes.apoio import criar_achado, renderizar
from lupa.validacoes.catalogo import Validacao, validacoes_de
from lupa.validacoes.modelo import AchadoValidacao, ModeloProcesso

_log = get_logger("lupa.validacoes.motor")


def _executar_protegido(
    validacao: Validacao, modelo: ModeloProcesso, referencia: date
) -> AchadoValidacao:
    try:
        return validacao.executar(modelo, referencia)
    except Exception as erro:  # noqa: BLE001 - uma validação não pode derrubar as demais
        _log.warning("validacao_falhou", validacao=validacao.nome, erro_tipo=type(erro).__name__)
        valores = {"erro_tipo": type(erro).__name__, "mensagem": str(erro), "faltantes": []}
        explicacao = renderizar(
            "motor_erro", validacao=validacao.nome, erro_tipo=type(erro).__name__, mensagem=erro
        )
        return criar_achado(validacao.nome, "verificar", [], valores, explicacao)


def executar_catalogo(
    modelo: ModeloProcesso, materia: str, referencia: date
) -> list[AchadoValidacao]:
    """Executa todas as validações da matéria, isolando falhas.

    Args:
        modelo: Fatos do processo.
        materia: ``criminal`` ou ``civel``.
        referencia: Data de referência ("hoje").

    Returns:
        Um achado por validação, na ordem do catálogo.
    """
    return [_executar_protegido(v, modelo, referencia) for v in validacoes_de(materia)]
