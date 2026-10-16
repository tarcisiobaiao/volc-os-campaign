"""Leitura mínima de expressões cron de 5 campos (minuto hora dia mês dia-da-semana).

Só o necessário para o modelo de capacidade: quantas execuções por dia uma agenda produz e
em que minutos do dia elas caem (para calcular o intervalo entre leituras). Dia do mês, mês e
dia da semana precisam ser `*` — agendas que dependem do calendário são recusadas em vez de
aproximadas em silêncio.
"""
from __future__ import annotations

from dataclasses import dataclass


class CronInvalido(ValueError):
    """Expressão fora do subconjunto suportado (ou malformada)."""


def _campo(texto: str, minimo: int, maximo: int) -> tuple[int, ...]:
    valores: set[int] = set()
    for parte in texto.split(","):
        if not parte:
            raise CronInvalido(f"lista vazia em {texto!r}")
        passo = 1
        if "/" in parte:
            base, passo_txt = parte.split("/", 1)
            if not passo_txt.isdigit() or int(passo_txt) <= 0:
                raise CronInvalido(f"passo inválido em {parte!r}")
            passo = int(passo_txt)
        else:
            base = parte
        if base == "*":
            ini, fim = minimo, maximo
        elif "-" in base:
            a, b = base.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise CronInvalido(f"faixa inválida em {parte!r}")
            ini, fim = int(a), int(b)
        elif base.isdigit():
            ini = int(base)
            fim = maximo if "/" in parte else ini
        else:
            raise CronInvalido(f"campo inválido {parte!r}")
        if not (minimo <= ini <= maximo and minimo <= fim <= maximo and ini <= fim):
            raise CronInvalido(f"fora do intervalo [{minimo},{maximo}]: {parte!r}")
        valores.update(range(ini, fim + 1, passo))
    return tuple(sorted(valores))


@dataclass(frozen=True)
class Agenda:
    expressao: str
    minutos: tuple[int, ...]
    horas: tuple[int, ...]

    @property
    def execucoes_por_dia(self) -> int:
        return len(self.minutos) * len(self.horas)

    def instantes_do_dia(self) -> tuple[int, ...]:
        """Minutos desde 00:00 de cada execução, ordenados."""
        return tuple(sorted(h * 60 + m for h in self.horas for m in self.minutos))

    def intervalos_min(self) -> tuple[int, ...]:
        """Intervalo (min) desde a leitura anterior, para cada execução, contando a virada do dia."""
        t = self.instantes_do_dia()
        if len(t) == 1:
            return (1440,)
        return tuple([t[0] + 1440 - t[-1]] + [t[i] - t[i - 1] for i in range(1, len(t))])

    def janela_coberta_h(self) -> tuple[int, int]:
        """(primeira hora, última hora) com execução — para discutir cobertura 06–23 × 24 h."""
        return (self.horas[0], self.horas[-1])


def ler(expressao: str) -> Agenda:
    partes = expressao.split()
    if len(partes) != 5:
        raise CronInvalido(f"esperados 5 campos: {expressao!r}")
    minuto, hora, dia, mes, dow = partes
    if (dia, mes, dow) != ("*", "*", "*"):
        raise CronInvalido("só agendas diárias (dia, mês e dia-da-semana = '*') são suportadas")
    return Agenda(expressao=expressao, minutos=_campo(minuto, 0, 59), horas=_campo(hora, 0, 23))


def a_cada(minutos: int) -> str:
    """Expressão cron de uma agenda de N minutos (N divide 60) ou N horas (múltiplo de 60 que divide 1440)."""
    if minutos <= 0:
        raise CronInvalido("intervalo deve ser positivo")
    if minutos < 60:
        if 60 % minutos:
            raise CronInvalido("intervalo em minutos precisa dividir 60")
        return f"*/{minutos} * * * *" if minutos > 1 else "* * * * *"
    if minutos % 60 or 1440 % minutos:
        raise CronInvalido("intervalo em horas precisa dividir 24 h")
    h = minutos // 60
    return f"0 */{h} * * *" if h > 1 else "0 * * * *"
