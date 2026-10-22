"""Contagem de prazos em dias corridos e úteis, com feriados e suspensões vindos de dados."""

import calendar
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

_UM_DIA = timedelta(days=1)
_SABADO = 5
_DOMINGO = 6
_MESES_NO_ANO = 12


@dataclass(frozen=True)
class Periodo:
    """Período de suspensão de prazos, inclusivo nas duas pontas."""

    inicio: date
    fim: date
    descricao: str

    def contem(self, dia: date) -> bool:
        """Diz se o dia está no período.

        Args:
            dia: Dia a testar.

        Returns:
            Verdadeiro se ``inicio <= dia <= fim``.
        """
        return self.inicio <= dia <= self.fim


@dataclass(frozen=True)
class Calendario:
    """Feriados e suspensões usados na contagem."""

    feriados: Mapping[date, str] = field(default_factory=dict)
    suspensoes: Sequence[Periodo] = ()


@dataclass(frozen=True)
class DiaDesconsiderado:
    """Dia pulado ou que deslocou o vencimento, com o motivo."""

    data: date
    motivo: str


@dataclass(frozen=True)
class ResultadoPrazo:
    """Resultado de uma contagem de prazo."""

    data_base: date
    dias: int
    vencimento_nominal: date
    vencimento: date
    deslocamentos: tuple[DiaDesconsiderado, ...]
    dias_suspensos: tuple[DiaDesconsiderado, ...]


def motivo_suspensao(dia: date, suspensoes: Sequence[Periodo]) -> str | None:
    """Retorna a descrição da suspensão que cobre o dia, se houver.

    Args:
        dia: Dia a testar.
        suspensoes: Períodos de suspensão.

    Returns:
        Descrição prefixada ou ``None``.
    """
    for periodo in suspensoes:
        if periodo.contem(dia):
            return f"suspensão: {periodo.descricao}"
    return None


def motivo_sem_expediente(
    dia: date, feriados: Mapping[date, str], suspensoes: Sequence[Periodo]
) -> str | None:
    """Diz por que o dia não tem expediente forense, ou ``None`` se tem.

    Args:
        dia: Dia a testar.
        feriados: Feriados por data.
        suspensoes: Períodos de suspensão.

    Returns:
        Motivo (feriado, suspensão, sábado, domingo) ou ``None``.
    """
    if dia in feriados:
        return f"feriado: {feriados[dia]}"
    suspenso = motivo_suspensao(dia, suspensoes)
    if suspenso is not None:
        return suspenso
    if dia.weekday() == _SABADO:
        return "sábado"
    if dia.weekday() == _DOMINGO:
        return "domingo"
    return None


def _prorrogar(
    dia: date, feriados: Mapping[date, str], suspensoes: Sequence[Periodo]
) -> tuple[date, tuple[DiaDesconsiderado, ...]]:
    deslocamentos: list[DiaDesconsiderado] = []
    while (motivo := motivo_sem_expediente(dia, feriados, suspensoes)) is not None:
        deslocamentos.append(DiaDesconsiderado(dia, motivo))
        dia += _UM_DIA
    return dia, tuple(deslocamentos)


def contar_prazo_corrido(
    data_base: date, dias: int, feriados: Mapping[date, str], suspensoes: Sequence[Periodo]
) -> ResultadoPrazo:
    """Conta prazo em dias corridos (art. 798 CPP).

    Exclui o dia do começo e inclui o do vencimento. Dias em período de suspensão não são
    contados. Vencimento em dia sem expediente prorroga para o próximo dia útil (art. 798, §3º).

    Args:
        data_base: Dia do começo (ex.: data da intimação).
        dias: Tamanho do prazo.
        feriados: Feriados por data.
        suspensoes: Períodos de suspensão.

    Returns:
        Vencimento nominal, vencimento efetivo e os dias que interferiram.
    """
    atual = data_base
    contados = 0
    suspensos: list[DiaDesconsiderado] = []
    while contados < dias:
        atual += _UM_DIA
        motivo = motivo_suspensao(atual, suspensoes)
        if motivo is not None:
            suspensos.append(DiaDesconsiderado(atual, motivo))
            continue
        contados += 1
    vencimento, deslocamentos = _prorrogar(atual, feriados, suspensoes)
    return ResultadoPrazo(data_base, dias, atual, vencimento, deslocamentos, tuple(suspensos))


def contar_prazo_util(
    data_base: date, dias: int, feriados: Mapping[date, str], suspensoes: Sequence[Periodo]
) -> ResultadoPrazo:
    """Conta prazo em dias úteis (para o módulo cível), excluindo o dia do começo.

    Args:
        data_base: Dia do começo.
        dias: Quantidade de dias úteis.
        feriados: Feriados por data.
        suspensoes: Períodos de suspensão.

    Returns:
        Resultado com os dias não úteis pulados em ``dias_suspensos``.
    """
    atual = data_base
    contados = 0
    pulados: list[DiaDesconsiderado] = []
    while contados < dias:
        atual += _UM_DIA
        motivo = motivo_sem_expediente(atual, feriados, suspensoes)
        if motivo is not None:
            pulados.append(DiaDesconsiderado(atual, motivo))
            continue
        contados += 1
    return ResultadoPrazo(data_base, dias, atual, atual, (), tuple(pulados))


def somar_meses(dia: date, meses: int) -> date:
    """Soma meses de calendário, ajustando para o último dia quando o mês é mais curto.

    Args:
        dia: Data inicial.
        meses: Meses a somar.

    Returns:
        Data resultante.
    """
    anos, mes_indice = divmod(dia.month - 1 + meses, _MESES_NO_ANO)
    ano = dia.year + anos
    mes = mes_indice + 1
    return date(ano, mes, min(dia.day, calendar.monthrange(ano, mes)[1]))


def idade_em(nascimento: date, dia: date) -> int:
    """Calcula a idade em anos completos.

    Args:
        nascimento: Data de nascimento.
        dia: Data em que a idade é medida.

    Returns:
        Anos completos.
    """
    aniversario_passou = (dia.month, dia.day) >= (nascimento.month, nascimento.day)
    return dia.year - nascimento.year - (0 if aniversario_passou else 1)
