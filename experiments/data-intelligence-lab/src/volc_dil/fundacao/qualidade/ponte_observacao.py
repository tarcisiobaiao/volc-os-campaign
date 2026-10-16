"""Ponte com o contrato real do worker A (`volc_dil.fundacao.observacao`) e checagens sobre `dil_obs`.

Mapeamento `Observacao` (A: UMA métrica por linha) -> `ObservacaoDQ` (G: uma LEITURA com várias
métricas):

| A (`Observacao`)                                   | G (`ObservacaoDQ`)                          |
|----------------------------------------------------|---------------------------------------------|
| fonte, conta, grao (tupla)                         | fonte, conta, grao = "_".join(grao)         |
| entidade.id                                        | entidade                                    |
| (fonte, conta, entidade, grao, dimensoes, janela)  | chave (sem a métrica: agrupa a leitura)     |
| metrica=cost / impressions / clicks / revenue …    | metricas["cost_micros" / "impressions" …]   |
| valor (None se status sem valor)                   | valor da métrica (None nunca vira 0)        |
| status (pior status entre as métricas da leitura)  | status                                      |
| motivo                                             | atributos["motivo"]                         |
| observed_at / available_at / ingested_at           | idem (max entre as métricas)                |
| run_id, lote_id, payload_sha256                    | idem                                        |
| coletor.nome / coletor.versao                      | coletor / versao_coletor                    |
| janela_inicio (no fuso da observação)              | metric_date                                 |

Zero sintetizado com o contrato A: `zero_confirmed` conta como zero com prova; `observed` exige
valor ≠ 0 no contrato A, logo o caso "zero sem prova" do v21 legado chega aqui como `missing` (se o
adaptador de A provar ausência) ou não chega — ver HANDOFF-G.

Checagens novas a partir dos insumos sugeridos por A: latência `ingested_at − available_at`,
taxa de `dead_letter` por run e distribuição de status/motivo.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from .modelo import Achado, ObservacaoDQ, RunDQ, Severidade, StatusDado, iso, para_datetime

NOME_METRICA = {"cost": "cost_micros", "revenue": "revenue_micros"}
_PIOR = ("invalid", "unavailable", "missing", "late", "partial", "unsupported", "observed", "zero_confirmed")
STATUS_RUN_DIL = {"succeeded": "completed", "running": "running", "failed": "failed", "partial": "partial"}

LIMIAR_LATENCIA_P95_S = 3600.0  # disponível -> ingerido em mais de 1 h no p95: aviso
LIMIAR_DEAD_LETTER = 0.05  # > 5% das linhas lidas em dead letter: alto


def de_observacoes(observacoes: Iterable[Any]) -> list[ObservacaoDQ]:
    """Agrupa `Observacao` de A (uma métrica por linha) em leituras `ObservacaoDQ`."""
    grupos: dict[tuple, list[Any]] = defaultdict(list)
    for o in observacoes:
        k = (o.fonte, o.conta, o.entidade.tipo, o.entidade.id, tuple(o.grao), tuple(o.dimensoes),
             o.janela_inicio, o.janela_fim, o.run_id, o.lote_id, o.payload_sha256, o.observed_at)
        grupos[k].append(o)
    saida = []
    for k, obs in grupos.items():
        fonte, conta, tipo, ent, grao, dims, ji, jf, run, lote, sha, obs_at = k
        status_vals = [o.status.value if hasattr(o.status, "value") else str(o.status) for o in obs]
        pior = min(status_vals, key=_PIOR.index)
        metricas = {NOME_METRICA.get(_m(o), _m(o)): o.valor for o in obs}
        motivos = sorted({o.motivo for o in obs if o.motivo})
        moedas = sorted({o.moeda for o in obs if o.moeda})
        saida.append(ObservacaoDQ(
            fonte=fonte, grao="_".join(grao), run_id=run, lote_id=lote, payload_sha256=sha,
            chave="|".join([fonte, conta, f"{tipo}:{ent}", "_".join(grao),
                            ",".join(f"{a}={b}" for a, b in dims), ji.isoformat(), jf.isoformat()]),
            status=StatusDado(pior), coletor=obs[0].coletor.nome, versao_coletor=obs[0].coletor.versao,
            entidade=ent, conta=conta, metric_date=ji.astimezone(ZoneInfo(obs[0].timezone)).date(),
            observed_at=para_datetime(obs_at), available_at=max(para_datetime(o.available_at) for o in obs),
            ingested_at=max(para_datetime(o.ingested_at) for o in obs), metricas=metricas,
            atributos={"motivo": motivos[0] if len(motivos) == 1 else (motivos or None),
                       "schema_version": obs[0].schema_version},
            moeda=moedas[0] if len(moedas) == 1 else None,
        ))
    return sorted(saida, key=lambda x: (x.fonte, x.chave, x.observed_at or datetime.min))


def _m(o: Any) -> str:
    return o.metrica.value if hasattr(o.metrica, "value") else str(o.metrica)


def runs_de_run_coleta(linhas: Iterable[Mapping[str, Any]]) -> list[RunDQ]:
    """`dil_obs.run_coleta` -> `RunDQ` (`succeeded` vira `completed`; `n_inseridas` = linhas escritas)."""
    return [RunDQ.de_dict({
        "run_id": r["run_id"], "fonte": r["fonte"], "coletor": r["coletor_nome"],
        "status": STATUS_RUN_DIL[r["status"]], "started_at": r["iniciado_em"],
        "finished_at": r.get("finalizado_em"), "linhas_escritas": r.get("n_inseridas"),
        "versao_coletor": r.get("coletor_versao"), "ultimo_sinal": r.get("ultimo_sinal"),
    }) for r in linhas]


def _quantil(valores: list[float], q: float) -> float:
    """Quantil contínuo (interpolação linear), igual a `percentile_cont` do PostgreSQL."""
    v = sorted(valores)
    pos = (len(v) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def checar_latencia_ingestao(
    observacoes: Iterable[ObservacaoDQ],
    limiar_p95_s: float = LIMIAR_LATENCIA_P95_S,
) -> list[Achado]:
    """p95 de `ingested_at − available_at` por fonte × coletor. Relógio ausente não conta como 0."""
    grupos: dict[tuple[str, str | None], list[float]] = defaultdict(list)
    sem_relogio: dict[tuple[str, str | None], int] = defaultdict(int)
    for o in observacoes:
        k = (o.fonte, o.coletor)
        if o.ingested_at is None or o.available_at is None:
            sem_relogio[k] += 1
            continue
        grupos[k].append((o.ingested_at - o.available_at).total_seconds())
    achados = []
    for k in sorted(set(grupos) | set(sem_relogio), key=lambda t: (t[0], t[1] or "")):
        vals = grupos.get(k, [])
        p95 = _quantil(vals, 0.95) if vals else None
        if (p95 is not None and p95 > limiar_p95_s) or sem_relogio.get(k):
            achados.append(Achado(
                regra="latencia_ingestao_p95" if p95 is not None and p95 > limiar_p95_s else "latencia_sem_relogio",
                severidade=Severidade.AVISO, fonte=k[0], grao="leitura", janela=(None, None), chave=k[1],
                evidencia={"n": len(vals), "p95_s": None if p95 is None else round(p95, 1),
                           "limiar_s": limiar_p95_s, "sem_relogio": sem_relogio.get(k, 0)},
                mensagem=f"{k[0]}/{k[1]}: p95 disponível→ingerido = {p95} s (limiar {limiar_p95_s} s)",
            ))
    return achados


def checar_dead_letter(
    runs_coleta: Iterable[Mapping[str, Any]],
    limiar: float = LIMIAR_DEAD_LETTER,
) -> list[Achado]:
    """Taxa `n_dead_letter / n_lidas` por run finalizado. `n_lidas` nulo/0 não gera razão."""
    achados = []
    for r in sorted(runs_coleta, key=lambda x: x["run_id"]):
        lidas, dl = r.get("n_lidas"), r.get("n_dead_letter")
        if r.get("status") == "running" or lidas in (None, 0) or dl is None:
            continue
        taxa = dl / lidas
        if taxa > limiar:
            achados.append(Achado(
                regra="dead_letter_taxa", severidade=Severidade.ALTO, fonte=r["fonte"], grao="run",
                janela=(iso(para_datetime(r["iniciado_em"])), iso(para_datetime(r.get("finalizado_em")))),
                chave=r["run_id"], evidencia={"n_lidas": lidas, "n_dead_letter": dl, "taxa": round(taxa, 4),
                                              "limiar": limiar, "coletor": r.get("coletor_nome")},
                mensagem=f"run {r['run_id']}: {dl}/{lidas} linhas em dead letter ({taxa:.1%})",
            ))
    return achados
