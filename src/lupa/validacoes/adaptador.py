"""Ponte entre as validações e o domínio: fatos do domínio entram, achados do domínio saem.

As validações já consomem ``lupa.dominio.esquemas.Fato`` diretamente; este módulo só monta o
``ModeloProcesso`` e vincula o ``AchadoValidacao`` a um processo, produzindo o ``Achado`` do
domínio. Não importa tabelas, repositórios nem sessão: quem lê e grava no banco é o chamador.
"""

from collections.abc import Iterable
from uuid import UUID

from lupa.dominio.esquemas import Achado, Fato
from lupa.validacoes.modelo import AchadoValidacao, ModeloProcesso


def para_modelo(fatos: Iterable[Fato]) -> ModeloProcesso:
    """Indexa fatos do domínio (por exemplo, lidos do banco) para o motor.

    Args:
        fatos: Fatos de um processo.

    Returns:
        Modelo pronto para ``executar_catalogo``.
    """
    return ModeloProcesso(fatos)


def para_dominio(achado_validacao: AchadoValidacao, processo_id: UUID) -> Achado:
    """Converte o resultado de uma validação no ``Achado`` do domínio.

    Args:
        achado_validacao: Saída do motor.
        processo_id: Processo a que o achado pertence.

    Returns:
        Achado do domínio, com ``id`` e ``criado_em`` novos.
    """
    return Achado(
        processo_id=processo_id,
        validacao=achado_validacao.validacao,
        versao_catalogo=achado_validacao.versao_catalogo,
        resultado=achado_validacao.resultado,
        fatos_usados=achado_validacao.fatos_usados,
        valores=achado_validacao.valores,
        explicacao=achado_validacao.explicacao,
    )
