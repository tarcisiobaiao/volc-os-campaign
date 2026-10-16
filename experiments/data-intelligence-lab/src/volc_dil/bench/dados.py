"""Gerador SINTÉTICO determinístico de observações planas para a bancada.

Esquema plano (uma linha = uma versão de uma observação; espelha `Observacao`):

    conta, entidade_id, device, dia, metrica, fonte, value_kind,
    disponivel_em_us, micros, moeda, estado, maturidade, cobertura

- `tipo_entidade="campaign"`, grão `(campaign, day, device)`, timezone `America/Sao_Paulo`
  e janela [dia 00:00, dia+1 00:00) são constantes do gerador (não viram coluna).
- `micros`/`moeda` são NULL quando o estado não tem valor (null != 0).
- chave lógica = (conta, entidade_id, device, dia, metrica, fonte, value_kind).
- armadilhas incluídas de propósito: lacunas (`nao_coletado`, `falha`), zero confirmado,
  restatement (preliminar -> revisada), backfill de custo, unidades em USD, unidade-dia com
  um device reportando receita em moeda diferente, e receita reportada sob OUTRA conta com o
  mesmo `entidade_id` (identidade trocada).
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

COLUNAS = (
    "conta", "entidade_id", "device", "dia", "metrica", "fonte", "value_kind",
    "disponivel_em_us", "micros", "moeda", "estado", "maturidade", "cobertura",
)
CHAVE_LOGICA = COLUNAS[:7]
(I_CONTA, I_ENT, I_DEV, I_DIA, I_MET, I_FONTE, I_VK, I_DISP, I_MICROS, I_MOEDA, I_ESTADO, I_MAT, I_COB) = range(13)

DEVICES = ("desktop", "mobile", "tablet")
DIAS = 30
INICIO = date(2026, 8, 1)
OFFSET_SP = timedelta(hours=-3)  # America/Sao_Paulo sem horário de verão desde 2019
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
LINHAS_POR_UNIDADE_DIA = 9.05  # ~3 devices × (custo ~1,02 + receita 2)


def instante_us(dia: date, horas: int) -> int:
    """Instante (epoch µs UTC) de `dia` 00:00 em São Paulo + `horas`."""
    dt = datetime(dia.year, dia.month, dia.day, tzinfo=timezone(OFFSET_SP)) + timedelta(hours=horas)
    return (dt - EPOCH) // timedelta(microseconds=1)


def as_of_padrao_us() -> int:
    """Corte no fim do penúltimo dia: deixa preliminares, revisões futuras e backfills de fora."""
    return instante_us(INICIO + timedelta(days=DIAS - 2), 12)


def n_unidades_para(n_alvo: int) -> int:
    return max(1, round(n_alvo / (LINHAS_POR_UNIDADE_DIA * DIAS)))


def gerar(n_alvo: int, seed: int) -> list[tuple]:
    r = random.Random(seed)
    linhas: list[tuple] = []
    n_u = n_unidades_para(n_alvo)
    for u in range(n_u):
        ent = f"cmp-{u:06d}"
        moeda_u = "USD" if r.random() < 0.05 else "BRL"
        conta_custo = "acc-A"
        troca = r.random() < 0.01
        conta_receita = "acc-B" if (troca or u == 1) else "acc-A"  # identidade trocada (u=1 sempre)
        for d in range(DIAS):
            dia = INICIO + timedelta(days=d)
            sdia = dia.isoformat()
            moeda_errada = r.random() < 0.005 or (u == 0 and d == 5)  # um device reporta receita em outra moeda
            for k, dev in enumerate(DEVICES):
                # custo
                t1 = instante_us(dia, 24 + 3)
                if r.random() < 0.03:
                    linhas.append((conta_custo, ent, dev, sdia, "cost", "google_ads", None, t1, None, None,
                                   "nao_coletado", "preliminary", "unknown"))
                    if r.random() < 0.5:
                        v = r.randint(0, 50_000_000)
                        linhas.append((conta_custo, ent, dev, sdia, "cost", "google_ads", None, t1 + 86_400_000_000, v,
                                       moeda_u, "zero_confirmado" if v == 0 else "medido", "mature", "complete"))
                else:
                    v = 0 if r.random() < 0.02 else r.randint(1, 50_000_000)
                    linhas.append((conta_custo, ent, dev, sdia, "cost", "google_ads", None, t1, v, moeda_u,
                                   "zero_confirmado" if v == 0 else "medido", "mature", "complete"))
                # receita: preliminar (d+1 06h) e revisada (d+3 06h)
                tp = instante_us(dia, 24 + 6)
                tr = instante_us(dia, 72 + 6)
                moeda_r = ("USD" if moeda_u == "BRL" else "BRL") if (moeda_errada and k == 0) else moeda_u
                rv = 0 if r.random() < 0.02 else r.randint(1, 80_000_000)
                if r.random() < 0.02:
                    for t in (tp, tr):
                        linhas.append((conta_receita, ent, dev, sdia, "revenue", "publisher", "reported_revenue", t,
                                       None, None, "nao_coletado", "preliminary", "unknown"))
                    continue
                if r.random() < 0.05:
                    linhas.append((conta_receita, ent, dev, sdia, "revenue", "publisher", "reported_revenue", tp,
                                   None, None, "falha", "preliminary", "unknown"))
                else:
                    pv = rv * r.randint(60, 105) // 100
                    linhas.append((conta_receita, ent, dev, sdia, "revenue", "publisher", "reported_revenue", tp,
                                   pv, moeda_r, "zero_confirmado" if pv == 0 else "medido", "preliminary", "partial"))
                linhas.append((conta_receita, ent, dev, sdia, "revenue", "publisher", "reported_revenue", tr,
                               rv, moeda_r, "zero_confirmado" if rv == 0 else "medido", "revised", "complete"))
    r.shuffle(linhas)  # ordem de chegada não pode importar
    return linhas


def esquema_polars():
    import polars as pl

    return {
        "conta": pl.Utf8, "entidade_id": pl.Utf8, "device": pl.Utf8, "dia": pl.Utf8, "metrica": pl.Utf8,
        "fonte": pl.Utf8, "value_kind": pl.Utf8, "disponivel_em_us": pl.Int64, "micros": pl.Int64,
        "moeda": pl.Utf8, "estado": pl.Utf8, "maturidade": pl.Utf8, "cobertura": pl.Utf8,
    }


def para_polars(linhas: list[tuple]):
    import polars as pl

    return pl.DataFrame(linhas, schema=esquema_polars(), orient="row")
