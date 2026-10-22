"""Conversão dos fatos extraídos para a saída medida pelo harness (``scripts/medir.py``)."""

from collections.abc import Iterable, Mapping
from uuid import UUID

from lupa.dominio.esquemas import Fato
from lupa.ingestao.eventos.modelo import PaginaTexto
from lupa.sinteticos.saida_pipeline import EventoSaida, RefPagina
from lupa.validacoes.modelo import valor_de


def eventos_saida(
    fatos: Iterable[Fato], paginas: Mapping[UUID, PaginaTexto], arquivo_padrao: str = "autos.pdf"
) -> tuple[EventoSaida, ...]:
    """Um evento por fato, na página da primeira evidência, com o valor sem ``reu_id``.

    Args:
        fatos: Fatos extraídos.
        paginas: Páginas por id (com arquivo e página de origem).
        arquivo_padrao: Nome do arquivo quando a página não traz a origem.

    Returns:
        Eventos no formato de ``lupa.sinteticos.saida_pipeline``.
    """
    eventos = []
    for fato in fatos:
        pagina = paginas[fato.evidencias[0].pagina_id]
        ref = RefPagina(
            arquivo=pagina.origem_arquivo or arquivo_padrao,
            pagina=pagina.pagina_origem or pagina.numero,
        )
        eventos.append(
            EventoSaida(
                tipo=fato.tipo, valor=valor_de(fato), ref=ref, trecho=fato.evidencias[0].trecho
            )
        )
    return tuple(eventos)
