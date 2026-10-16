"""A MESMA operação do replay em quatro implementações, com resultado canônico comparável.

Operação (spec):
1. corte as_of: `disponivel_em_us <= as_of`;
2. última versão por chave lógica (maior `disponivel_em_us`); `n_empates` = chaves cuja versão
   máxima aparece mais de uma vez (deve ser 0 — o contrato chama isso de `VersaoAmbigua`);
3. agregação por (conta, entidade_id, dia, metrica) somando devices, com semântica do
   `agregar` do contrato: membro sem valor anula o total (pior estado vence: falha >
   nao_coletado > ausente > nao_atribuivel > nao_aplicavel); mais de uma moeda no grupo ->
   total NULL e estado `moedas_misturadas` (nunca soma); total 0 -> `zero_confirmado`;
4. join custo × receita por identidade EXATA (conta, entidade_id, dia), full outer;
   contribuição = receita − custo só com ambos com valor e mesma moeda; senão NULL + motivo
   (`sem_custo`, `sem_receita`, `sem_valor`, `moedas_diferentes`).

Linha canônica de saída (ordenada por conta, entidade_id, dia):
    (conta, entidade_id, dia,
     c_total, c_estado, c_moeda, c_n, c_n_sem,
     r_total, r_estado, r_moeda, r_n, r_n_sem,
     contribuicao, motivo)
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .dados import (
    I_CONTA, I_COB, I_DEV, I_DIA, I_DISP, I_ESTADO, I_ENT, I_FONTE, I_MAT, I_MET, I_MICROS, I_MOEDA, I_VK,
    OFFSET_SP,
)

GRAVIDADE = ("falha", "nao_coletado", "ausente", "nao_atribuivel", "nao_aplicavel")
RANK = {e: i for i, e in enumerate(GRAVIDADE)}


class EmpateDeVersao(RuntimeError):
    pass


def hash_resultado(linhas: list[tuple], n_empates: int) -> str:
    corpo = json.dumps({"n_empates": n_empates, "linhas": sorted(linhas, key=lambda x: (x[0], x[1], x[2]))},
                       separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(corpo.encode()).hexdigest()


def _agregado(grupo: list[tuple]) -> tuple:
    n = len(grupo)
    sem = [g for g in grupo if g[I_MICROS] is None]
    moedas = {g[I_MOEDA] for g in grupo if g[I_MOEDA] is not None}
    if len(moedas) > 1:
        return (None, "moedas_misturadas", None, n, len(sem))
    moeda = next(iter(moedas)) if moedas else None
    if sem:
        pior = min((g[I_ESTADO] for g in sem), key=RANK.__getitem__)
        return (None, pior, moeda, n, len(sem))
    total = sum(g[I_MICROS] for g in grupo)
    return (total, "zero_confirmado" if total == 0 else "medido", moeda, n, 0)


def _juntar(chave: tuple, c: tuple | None, r: tuple | None) -> tuple:
    vazio = (None, None, None, None, None)
    cc, rr = c or vazio, r or vazio
    if c is None:
        contrib, motivo = None, "sem_custo"
    elif r is None:
        contrib, motivo = None, "sem_receita"
    elif c[0] is None or r[0] is None:
        contrib, motivo = None, "sem_valor"
    elif c[2] != r[2]:
        contrib, motivo = None, "moedas_diferentes"
    else:
        contrib, motivo = r[0] - c[0], None
    return (*chave, *cc, *rr, contrib, motivo)


# ── (i) Python puro, linhas planas (estilo atual do VOLC) ─────────────────

def op_python(linhas: list[tuple], as_of_us: int) -> tuple[list[tuple], int]:
    ultimo: dict[tuple, list] = {}
    for x in linhas:
        t = x[I_DISP]
        if t > as_of_us:
            continue
        k = x[:7]
        cur = ultimo.get(k)
        if cur is None or t > cur[0][I_DISP]:
            ultimo[k] = [x, 1]
        elif t == cur[0][I_DISP]:
            cur[1] += 1
    n_empates = sum(1 for v in ultimo.values() if v[1] > 1)
    grupos: dict[tuple, list[tuple]] = {}
    for x, _ in ultimo.values():
        grupos.setdefault((x[I_CONTA], x[I_ENT], x[I_DIA], x[I_MET]), []).append(x)
    custo: dict[tuple, tuple] = {}
    receita: dict[tuple, tuple] = {}
    for (conta, ent, dia, met), g in grupos.items():
        (custo if met == "cost" else receita)[(conta, ent, dia)] = _agregado(g)
    saida = [_juntar(k, custo.get(k), receita.get(k)) for k in sorted(custo.keys() | receita.keys())]
    return saida, n_empates


# ── (0) caminho do CONTRATO (Observacao + Snapshot + agregar) ──────────────

def para_observacoes(linhas: list[tuple]):
    """Converte linhas planas em objetos do contrato (custo de conversão medido à parte)."""
    from volc_dil.contracts import (
        ChaveUnidade, Cobertura, Dinheiro, EstadoMedida, Maturidade, Metrica, MetodoAtribuicao, Observacao, ValueKind,
    )

    tz = timezone(OFFSET_SP)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    chaves: dict[tuple, Any] = {}
    janelas: dict[str, tuple] = {}
    instantes: dict[int, datetime] = {}
    saida = []
    for x in linhas:
        kc = (x[I_CONTA], x[I_ENT], x[I_DEV])
        u = chaves.get(kc)
        if u is None:
            u = chaves[kc] = ChaveUnidade(x[I_CONTA], "campaign", x[I_ENT], ("campaign", "day", "device"),
                                          (("device", x[I_DEV]),))
        jan = janelas.get(x[I_DIA])
        if jan is None:
            d = date.fromisoformat(x[I_DIA])
            ini = datetime(d.year, d.month, d.day, tzinfo=tz)
            jan = janelas[x[I_DIA]] = (ini, ini + timedelta(days=1))
        t = instantes.get(x[I_DISP])
        if t is None:
            t = instantes[x[I_DISP]] = (epoch + timedelta(microseconds=x[I_DISP])).astimezone(tz)
        custo = x[I_MET] == "cost"
        saida.append(Observacao(
            unidade=u, metrica=Metrica.CUSTO if custo else Metrica.RECEITA,
            valor=None if x[I_MICROS] is None else Dinheiro(x[I_MICROS], x[I_MOEDA]),
            estado=EstadoMedida(x[I_ESTADO]), janela_inicio=jan[0], janela_fim=jan[1], timezone="America/Sao_Paulo",
            observado_em=t, disponivel_em=t, fonte=x[I_FONTE], versao_fonte="bench-v0",
            coleta_id=f"{x[I_ENT]}:{x[I_DEV]}:{x[I_DIA]}:{x[I_MET]}:{x[I_DISP]}",
            cobertura=Cobertura(x[I_COB]), maturidade=Maturidade(x[I_MAT]),
            metodo=MetodoAtribuicao.NAO_APLICAVEL if custo else MetodoAtribuicao.AGGREGATE_CAMPAIGN_DATE,
            value_kind=None if x[I_VK] is None else ValueKind(x[I_VK]),
            motivo=None if x[I_MICROS] is not None else f"sem valor: {x[I_ESTADO]}",
        ))
    return saida


def op_contrato(observacoes: list, as_of_us: int) -> tuple[list[tuple], int]:
    from volc_dil.contracts import MoedasDiferentes, Snapshot, VersaoAmbigua, agregar

    as_of = (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=as_of_us)).astimezone(timezone(OFFSET_SP))
    try:
        snap = Snapshot.construir(observacoes, as_of)
    except VersaoAmbigua as exc:  # o contrato recusa; a bancada só conta
        raise EmpateDeVersao(str(exc)) from exc
    grupos: dict[tuple, list] = {}
    for o in snap.observacoes:
        dia = o.janela_inicio.date().isoformat()
        grupos.setdefault((o.unidade.conta, o.unidade.entidade_id, dia, o.metrica.value), []).append(o)
    custo: dict[tuple, tuple] = {}
    receita: dict[tuple, tuple] = {}
    for (conta, ent, dia, met), g in grupos.items():
        try:
            a = agregar(g)
            ag = (a.valor.micros if a.valor is not None else None, a.estado.value, a.moeda, a.n, a.n_sem_valor)
        except MoedasDiferentes:
            ag = (None, "moedas_misturadas", None, len(g), sum(1 for o in g if o.valor is None))
        (custo if met == "cost" else receita)[(conta, ent, dia)] = ag
    saida = [_juntar(k, custo.get(k), receita.get(k)) for k in sorted(custo.keys() | receita.keys())]
    return saida, 0


# ── (ii) DuckDB ────────────────────────────────────────────────────────────

CONFIG_DUCKDB = {"autoinstall_known_extensions": False, "autoload_known_extensions": False}

_SQL_CORPO = """
WITH corte AS (SELECT * FROM obs WHERE disponivel_em_us <= {as_of}),
marcado AS (
  SELECT *,
    max(disponivel_em_us) OVER w AS mx,
    count(*) OVER (PARTITION BY conta, entidade_id, device, dia, metrica, fonte, value_kind, disponivel_em_us) AS n_mesmo
  FROM corte
  WINDOW w AS (PARTITION BY conta, entidade_id, device, dia, metrica, fonte, value_kind)
),
ultimo AS (SELECT * FROM marcado WHERE disponivel_em_us = mx),
agg AS (
  SELECT conta, entidade_id, dia, metrica,
    count(*) AS n,
    count(*) - count(micros) AS n_sem,
    count(DISTINCT moeda) AS n_moedas,
    min(moeda) AS moeda_min,
    sum(micros) AS soma,
    min(CASE estado WHEN 'falha' THEN 0 WHEN 'nao_coletado' THEN 1 WHEN 'ausente' THEN 2
                    WHEN 'nao_atribuivel' THEN 3 WHEN 'nao_aplicavel' THEN 4 END) FILTER (WHERE micros IS NULL) AS pior
  FROM ultimo GROUP BY conta, entidade_id, dia, metrica
),
fim AS (
  SELECT conta, entidade_id, dia, metrica, n, n_sem,
    {total} AS total,
    {estado} AS estado,
    CASE WHEN n_moedas > 1 THEN NULL ELSE moeda_min END AS moeda
  FROM agg
),
c AS (SELECT * FROM fim WHERE metrica = 'cost'),
r AS (SELECT * FROM fim WHERE metrica = 'revenue')
SELECT coalesce(c.conta, r.conta) AS conta, coalesce(c.entidade_id, r.entidade_id) AS entidade_id,
       coalesce(c.dia, r.dia) AS dia,
       c.total::BIGINT AS c_total, c.estado AS c_estado, c.moeda AS c_moeda, c.n AS c_n, c.n_sem AS c_n_sem,
       r.total::BIGINT AS r_total, r.estado AS r_estado, r.moeda AS r_moeda, r.n AS r_n, r.n_sem AS r_n_sem,
       CASE WHEN c.conta IS NULL OR r.conta IS NULL OR c.total IS NULL OR r.total IS NULL OR c.moeda <> r.moeda
            THEN NULL ELSE (r.total - c.total)::BIGINT END AS contribuicao,
       CASE WHEN c.conta IS NULL THEN 'sem_custo' WHEN r.conta IS NULL THEN 'sem_receita'
            WHEN c.total IS NULL OR r.total IS NULL THEN 'sem_valor'
            WHEN c.moeda <> r.moeda THEN 'moedas_diferentes' END AS motivo
FROM c FULL OUTER JOIN r ON c.conta = r.conta AND c.entidade_id = r.entidade_id AND c.dia = r.dia
"""

_TOTAL_CERTO = "CASE WHEN n_moedas > 1 OR n_sem > 0 THEN NULL ELSE soma END"
_ESTADO_CERTO = ("CASE WHEN n_moedas > 1 THEN 'moedas_misturadas' "
                 "WHEN n_sem > 0 THEN ['falha','nao_coletado','ausente','nao_atribuivel','nao_aplicavel'][pior + 1] "
                 "WHEN soma = 0 THEN 'zero_confirmado' ELSE 'medido' END")
# Versão ingênua (SUM ignora NULL): existe só para provar que a equivalência pega o erro.
_TOTAL_INGENUO = "soma"
_ESTADO_INGENUO = "CASE WHEN soma = 0 THEN 'zero_confirmado' ELSE 'medido' END"

def conectar_duckdb(threads: int):
    import duckdb

    return duckdb.connect(config={**CONFIG_DUCKDB, "threads": threads})


def sql_duckdb(as_of_us: int, *, ingenuo: bool = False) -> str:
    return _SQL_CORPO.format(as_of=int(as_of_us), total=_TOTAL_INGENUO if ingenuo else _TOTAL_CERTO,
                             estado=_ESTADO_INGENUO if ingenuo else _ESTADO_CERTO)


def sql_empates_duckdb(as_of_us: int) -> str:
    return f"""
    SELECT count(*) FROM (
      SELECT conta, entidade_id, device, dia, metrica, fonte, value_kind, disponivel_em_us, count(*) AS c,
             max(disponivel_em_us) OVER (PARTITION BY conta, entidade_id, device, dia, metrica, fonte, value_kind) AS mx
      FROM obs WHERE disponivel_em_us <= {int(as_of_us)}
      GROUP BY conta, entidade_id, device, dia, metrica, fonte, value_kind, disponivel_em_us
    ) WHERE disponivel_em_us = mx AND c > 1
    """


def op_duckdb(con, as_of_us: int, *, ingenuo: bool = False) -> int:
    """Materializa o resultado numa tabela temporária (nativo) e devolve n_empates."""
    con.execute("CREATE OR REPLACE TEMP TABLE resultado AS " + sql_duckdb(as_of_us, ingenuo=ingenuo))
    return con.execute(sql_empates_duckdb(as_of_us)).fetchone()[0]


def exportar_duckdb(con) -> list[tuple]:
    return con.execute("SELECT * FROM resultado ORDER BY conta, entidade_id, dia").fetchall()


# ── (iii) Polars lazy ──────────────────────────────────────────────────────

CHAVE = ["conta", "entidade_id", "device", "dia", "metrica", "fonte", "value_kind"]


def plano_polars(lf, as_of_us: int, *, ingenuo: bool = False):
    import polars as pl

    corte = lf.filter(pl.col("disponivel_em_us") <= as_of_us)
    marcado = corte.with_columns(
        pl.col("disponivel_em_us").max().over(CHAVE).alias("mx"),
        pl.len().over(CHAVE + ["disponivel_em_us"]).alias("n_mesmo"),
    )
    ultimo = marcado.filter(pl.col("disponivel_em_us") == pl.col("mx"))
    rank = (pl.when(pl.col("estado") == "falha").then(0)
            .when(pl.col("estado") == "nao_coletado").then(1)
            .when(pl.col("estado") == "ausente").then(2)
            .when(pl.col("estado") == "nao_atribuivel").then(3)
            .when(pl.col("estado") == "nao_aplicavel").then(4))
    agg = ultimo.group_by(["conta", "entidade_id", "dia", "metrica"]).agg(
        pl.len().alias("n"),
        pl.col("micros").null_count().alias("n_sem"),
        pl.col("moeda").drop_nulls().n_unique().alias("n_moedas"),
        pl.col("moeda").min().alias("moeda_min"),
        pl.col("micros").sum().alias("soma"),
        rank.filter(pl.col("micros").is_null()).min().alias("pior"),
    )
    nomes = pl.Series(GRAVIDADE)
    if ingenuo:
        total = pl.col("soma")
        estado = pl.when(pl.col("soma") == 0).then(pl.lit("zero_confirmado")).otherwise(pl.lit("medido"))
    else:
        total = pl.when((pl.col("n_moedas") > 1) | (pl.col("n_sem") > 0)).then(None).otherwise(pl.col("soma"))
        estado = (pl.when(pl.col("n_moedas") > 1).then(pl.lit("moedas_misturadas"))
                  .when(pl.col("n_sem") > 0).then(pl.col("pior").replace_strict(list(range(5)), list(nomes), default=None))
                  .when(pl.col("soma") == 0).then(pl.lit("zero_confirmado"))
                  .otherwise(pl.lit("medido")))
    fim = agg.select(
        "conta", "entidade_id", "dia", "metrica",
        total.cast(pl.Int64).alias("total"), estado.alias("estado"),
        pl.when(pl.col("n_moedas") > 1).then(None).otherwise(pl.col("moeda_min")).alias("moeda"),
        pl.col("n").cast(pl.Int64), pl.col("n_sem").cast(pl.Int64),
    )
    lado = ["total", "estado", "moeda", "n", "n_sem"]
    c = fim.filter(pl.col("metrica") == "cost").select(
        "conta", "entidade_id", "dia", *[pl.col(x).alias("c_" + x) for x in lado], pl.lit(True).alias("c_existe"))
    r = fim.filter(pl.col("metrica") == "revenue").select(
        "conta", "entidade_id", "dia", *[pl.col(x).alias("r_" + x) for x in lado], pl.lit(True).alias("r_existe"))
    j = c.join(r, on=["conta", "entidade_id", "dia"], how="full", coalesce=True, nulls_equal=False)
    sem_c = pl.col("c_existe").is_null()
    sem_r = pl.col("r_existe").is_null()
    sem_v = pl.col("c_total").is_null() | pl.col("r_total").is_null()
    moeda_dif = pl.col("c_moeda") != pl.col("r_moeda")
    resultado = j.select(
        "conta", "entidade_id", "dia",
        *["c_" + x for x in lado], *["r_" + x for x in lado],
        pl.when(sem_c | sem_r | sem_v | moeda_dif).then(None)
          .otherwise(pl.col("r_total") - pl.col("c_total")).cast(pl.Int64).alias("contribuicao"),
        pl.when(sem_c).then(pl.lit("sem_custo")).when(sem_r).then(pl.lit("sem_receita"))
          .when(sem_v).then(pl.lit("sem_valor")).when(moeda_dif).then(pl.lit("moedas_diferentes"))
          .otherwise(None).alias("motivo"),
    )
    empates = ultimo.filter(pl.col("n_mesmo") > 1).select(CHAVE).unique().select(pl.len())
    return resultado, empates


def op_polars(lf, as_of_us: int, *, ingenuo: bool = False):
    import polars as pl

    resultado, empates = plano_polars(lf, as_of_us, ingenuo=ingenuo)
    res, emp = pl.collect_all([resultado, empates])
    return res, int(emp.item())


def exportar_polars(df) -> list[tuple]:
    return df.sort(["conta", "entidade_id", "dia"]).rows()
