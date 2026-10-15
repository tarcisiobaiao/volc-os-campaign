"""Contrato de uma família de coleta Google Ads → banco.

Uma família é um módulo em `volc_ads/coleta/familias/` que exporta `FAMILIA`,
um objeto com:

- `nome`: str — a família na RPC (`hora_dispositivo`, `url`, `geo`,
  `placement`, `termo`, `keyword`, `asset`, `mudanca`, `estado`) ou
  `campanha_dia` (que usa a RPC da v12_04);
- `rpc`: str — `volc_registrar_gads_fatos` (padrão) ou outra;
- `gaql(ctx) -> str | list[str]`: consulta(s) da janela do contexto. Toda GAQL
  passa por `gads.catalogo.exigir_valida` antes de sair;
- `normalizar(row, ctx) -> dict | None`: uma `GoogleAdsRow` → uma linha do
  documento da RPC (None descarta, com motivo contado pelo executor);
- opcional `documento(ctx, linhas, *, lote, execucao_chave, iniciada) -> dict`:
  monta o documento quando a RPC não é a dos fatos granulares;
- opcional `consolidar(linhas) -> list[dict]`: soma linhas que a RPC trataria
  como o MESMO fato (views por grupo ou por anúncio);
- opcional `fechamento(ctx, *, execucao_chave, lotes, iniciada) -> dict`: o lote
  de fechamento (ordinal 0) que a saúde da coleta e o deadman enxergam;
- opcional `limite: int`: o LIMIT da GAQL; ler exatamente isso = janela cortada.

Regras que todo normalizador segue (são as invariantes do banco):
- número da API vai como número JSON (int/float), NUNCA string;
- métrica ausente vai como `None`, nunca 0;
- dinheiro fica em micros; taxas ficam 0..1, como a API manda;
- enum vira o `.name` (string), e `UNKNOWN` passa como está.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class Contexto:
    customer_id: str
    login_customer_id: str
    origem_janela: str            # D0 | D-1 | backfill
    data_inicio: date
    data_fim: date
    fuso: str                     # customer.time_zone
    moeda: str                    # customer.currency_code
    api_versao: str = "v25"
    colhida_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # campaign_id → volc_campaign_id (de trafego_inventario_campanha). Sem ele a
    # RPC da v12_04 sobrescreveria o vínculo que o inventário já gravou com NULL.
    mapa_volc: Mapping[str, str] = field(default_factory=dict)
    # Execução recorrente: `disparo='agenda'` exige o PASSO da agenda (ex.: "06",
    # "12"), que entra na `execucao_chave` — as passadas do dia são leituras
    # distintas (v12_04), e é pelo passo que o agendador sabe se já rodou.
    disparo: str = "manual"
    passo: str | None = None
    # Projeção na tabela legada `daily_campaign_metrics` (só o campanha-dia a
    # pede). A recoleta desliga: ver `__main__`.
    projetar_compat: bool = True

    def __post_init__(self) -> None:
        if self.disparo not in ("manual", "agenda"):
            raise ValueError(f"disparo inválido: {self.disparo} (CHECK do ledger: agenda | manual)")
        if self.disparo == "agenda" and not self.passo:
            raise ValueError("disparo='agenda' exige o passo da agenda")
        if self.passo is not None and not re.fullmatch(r"[0-9a-z]{1,8}", self.passo):
            raise ValueError(f"passo inválido: {self.passo!r}")
        if self.origem_janela not in ("D0", "D-1", "backfill"):
            raise ValueError(f"origem_janela inválida: {self.origem_janela}")
        if self.data_fim < self.data_inicio:
            raise ValueError("janela invertida")
        if self.origem_janela != "backfill" and self.data_inicio != self.data_fim:
            raise ValueError("D0 e D-1 são de um dia só (CHECK do ledger)")

    @property
    def janela_gaql(self) -> str:
        return f"segments.date BETWEEN '{self.data_inicio.isoformat()}' AND '{self.data_fim.isoformat()}'"

    @property
    def colhida_iso(self) -> str:
        return self.colhida_em.isoformat()


RECOLETA_DIAS_MAXIMO = 90


def janela_recoleta(hoje: date, dias: int) -> tuple[date, date]:
    """Os `dias` dias FECHADOS anteriores ao D-1, no fuso da conta.

    O Google ajusta custo (cliques inválidos) e conversões depois do dia fechar;
    D-1 é uma leitura só. A recoleta relê a janela [hoje-1-dias, hoje-2] como
    `backfill` (precedência 3 na v12_04), então a leitura mais nova de cada
    (conta, campanha, data) substitui a anterior pelo `colhida_em`. O D-1 fica
    fora de propósito: ele tem job, passo e saúde próprios e não é duplicado.
    """
    if not isinstance(dias, int) or isinstance(dias, bool) or not 1 <= dias <= RECOLETA_DIAS_MAXIMO:
        raise ValueError(f"recoleta exige 1..{RECOLETA_DIAS_MAXIMO} dias, veio {dias!r}")
    return hoje - timedelta(days=1 + dias), hoje - timedelta(days=2)


class Familia(Protocol):
    nome: str
    rpc: str

    def gaql(self, ctx: Contexto) -> str | list[str]: ...

    def normalizar(self, row: Any, ctx: Contexto) -> dict | None: ...


# ── utilitários para os normalizadores ─────────────────────────────────────

def enum_nome(valor: Any) -> str | None:
    """`.name` de um enum proto-plus; None se ausente."""
    if valor is None:
        return None
    nome = getattr(valor, "name", None)
    return nome if nome is not None else str(valor)


def inteiro(valor: Any) -> int | None:
    """Métrica int64 da API. proto-plus devolve 0 para campo não preenchido em
    escalares sem presença — por isso quem chama decide se a métrica foi pedida
    (estava no SELECT). Aqui só se garante o TIPO."""
    return None if valor is None else int(valor)


def numero(valor: Any) -> float | None:
    return None if valor is None else float(valor)


def medida(mensagem: Any, campo: str, tipo: type = int) -> int | float | None:
    """Métrica com PRESENÇA: None quando a API não mandou, o número quando mandou.

    ⚠️ Em proto-plus, campo escalar ausente lê como 0. Ler `row.metrics.clicks`
    direto transformaria "não medido" em "zero medido" — exatamente o que o
    banco recusa. As métricas da v25 são `optional`, então `campo in mensagem`
    distingue. Todo normalizador usa ESTA função para métrica.
    """
    if mensagem is None:
        return None
    try:
        presente = campo in mensagem
    except TypeError:
        presente = getattr(mensagem, campo, None) is not None
    if not presente:
        return None
    return tipo(getattr(mensagem, campo))
