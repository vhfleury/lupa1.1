"""Funções de apoio comuns às validações: leitura de datas, referências e templates."""

from collections.abc import Iterable
from datetime import date, datetime
from importlib.resources import files
from typing import Any
from uuid import UUID

from lupa.validacoes.modelo import (
    AchadoValidacao,
    ConflitoDeFatosError,
    Fato,
    ModeloProcesso,
    ResultadoAchado,
    valor_de,
)
from lupa.validacoes.versao import VERSAO_CATALOGO

NENHUM = "nenhum"


def data_de(fato: Fato) -> date:
    """Lê a data de um fato.

    Fatos lidos do banco trazem a data como string ISO ``AAAA-MM-DD`` (o ``valor`` é JSONB);
    fatos montados em código Python podem trazer um ``datetime.date``. Os dois são aceitos.
    ``datetime`` não é aceito, para não truncar hora silenciosamente.

    Args:
        fato: Fato cujo valor é uma data ISO ou ``date``.

    Returns:
        A data.

    Raises:
        ValueError: Se o valor não for uma data ISO.
    """
    valor = valor_de(fato)
    if isinstance(valor, str):
        return date.fromisoformat(valor)
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    raise ValueError(f"fato {fato.id} ({fato.tipo}) não contém data ISO")


def rastrear(fato: Fato) -> dict[str, Any]:
    """Monta a referência rastreável de uma data: valor, fato e evidências.

    Args:
        fato: Fato de data.

    Returns:
        Dicionário com ``data``, ``tipo``, ``fato_id``, ``evidencia_id`` e ``evidencia_ids``.
    """
    return {
        "data": data_de(fato).isoformat(),
        "tipo": str(fato.tipo),
        "fato_id": str(fato.id),
        "evidencia_id": str(fato.evidencias[0].id),
        "evidencia_ids": [str(e.id) for e in fato.evidencias],
    }


def formatar_data(dia: date | str) -> str:
    """Formata data como ``dd/mm/aaaa``.

    Args:
        dia: Data ou string ISO.

    Returns:
        Data formatada.
    """
    valor = date.fromisoformat(dia) if isinstance(dia, str) else dia
    return valor.strftime("%d/%m/%Y")


def listar(itens: Iterable[str]) -> str:
    """Junta itens com vírgula, ou devolve ``nenhum``.

    Args:
        itens: Textos.

    Returns:
        Texto único.
    """
    lista = list(itens)
    return "; ".join(lista) if lista else NENHUM


def renderizar(nome: str, **campos: object) -> str:
    """Monta a explicação a partir de ``templates/<nome>.txt`` com ``str.format``.

    Args:
        nome: Nome do template sem extensão.
        **campos: Valores do template.

    Returns:
        Texto da explicação.
    """
    modelo = files("lupa.validacoes").joinpath("templates").joinpath(f"{nome}.txt")
    return modelo.read_text(encoding="utf-8").strip().format(**campos)


class Coleta:
    """Busca fatos únicos no modelo anotando os faltantes e os conflitos."""

    def __init__(self, modelo: ModeloProcesso) -> None:
        """Cria a coleta.

        Args:
            modelo: Modelo do processo.
        """
        self._modelo = modelo
        self.faltantes: list[str] = []
        self.conflitos: list[dict[str, Any]] = []
        self.usados: list[UUID] = []

    def unico(self, tipo: str, *, obrigatorio: bool = True) -> Fato | None:
        """Busca o fato único de um tipo.

        Args:
            tipo: Tipo de fato.
            obrigatorio: Se verdadeiro, ausência entra em ``faltantes``.

        Returns:
            O fato, ou ``None`` se ausente ou em conflito.
        """
        try:
            fato = self._modelo.fato(tipo)
        except ConflitoDeFatosError as erro:
            self.conflitos.append({"tipo": erro.tipo, "fato_ids": erro.fato_ids})
            return None
        if fato is None:
            if obrigatorio:
                self.faltantes.append(tipo)
            return None
        self.usados.append(fato.id)
        return fato

    @property
    def pendente(self) -> bool:
        """Verdadeiro se há fato faltante ou em conflito."""
        return bool(self.faltantes or self.conflitos)

    def verificar(
        self, validacao: str, motivo: str, extras: dict[str, Any] | None = None
    ) -> AchadoValidacao:
        """Gera achado ``verificar`` com faltantes, conflitos e motivo.

        Args:
            validacao: Nome da validação (também nome base do template).
            motivo: Frase curta do motivo.
            extras: Valores adicionais.

        Returns:
            AchadoValidacao ``verificar``.
        """
        valores: dict[str, Any] = {
            "motivo": motivo,
            "faltantes": list(self.faltantes),
            "conflitos": list(self.conflitos),
            **(extras or {}),
        }
        explicacao = renderizar(
            f"{validacao}_verificar",
            motivo=motivo,
            faltantes=listar(self.faltantes),
            conflitos=listar(c["tipo"] for c in self.conflitos),
        )
        return criar_achado(validacao, "verificar", self.usados, valores, explicacao)


def motivo_pendencia(coleta: Coleta) -> str:
    """Descreve por que a coleta ficou pendente.

    Args:
        coleta: Coleta com faltantes ou conflitos.

    Returns:
        Motivo em uma frase.
    """
    if coleta.conflitos:
        return "há fatos com valores divergentes."
    return "faltam fatos necessários."


def criar_achado(
    validacao: str,
    resultado: ResultadoAchado,
    fatos_usados: Iterable[UUID],
    valores: dict[str, Any],
    explicacao: str,
) -> AchadoValidacao:
    """Cria o achado com a versão do catálogo.

    Args:
        validacao: Nome da validação.
        resultado: Resultado.
        fatos_usados: Ids de fatos.
        valores: Valores para conferência.
        explicacao: Texto gerado por template.

    Returns:
        AchadoValidacao.
    """
    return AchadoValidacao(
        validacao=validacao,
        versao_catalogo=VERSAO_CATALOGO,
        resultado=resultado,
        fatos_usados=tuple(sorted(set(fatos_usados))),
        valores=valores,
        explicacao=explicacao,
    )
