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

Zero sintetizado com o contrato A: o adaptador v21 de A só deixa passar 0 com prova de linha de
métrica (vira `zero_confirmed`/`partial` com valor 0 -> aqui `linha_metrica_presente=True`); o 0 sem
prova chega como `missing` + motivo `zero_sem_linha_de_metrica` (-> `sintetizado`) ou
`zero_sem_prova_de_linha` (-> `ambiguo`), via `atributos["motivos_por_metrica"]`. Teste de
equivalência: caminho direto (linhas v21) × caminho A (`adaptar_google_ads_v21` + esta ponte).

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
        zero_da_fonte = any(o.valor == 0 for o in obs)  # contrato A: 0 só sobrevive com prova da fonte
        saida.append(ObservacaoDQ(
            fonte=fonte, grao="_".join(grao), run_id=run, lote_id=lote, payload_sha256=sha,
            chave="|".join([fonte, conta, f"{tipo}:{ent}", "_".join(grao),
                            ",".join(f"{a}={b}" for a, b in dims), ji.isoformat(), jf.isoformat()]),
            status=StatusDado(pior), coletor=obs[0].coletor.nome, versao_coletor=obs[0].coletor.versao,
            entidade=ent, conta=conta, metric_date=ji.astimezone(ZoneInfo(obs[0].timezone)).date(),
            observed_at=para_datetime(obs_at), available_at=max(para_datetime(o.available_at) for o in obs),
            ingested_at=max(para_datetime(o.ingested_at) for o in obs), metricas=metricas,
            atributos={"motivo": motivos[0] if len(motivos) == 1 else (motivos or None),
                       "motivos_por_metrica": {NOME_METRICA.get(_m(o), _m(o)): o.motivo for o in obs if o.motivo},
                       "linha_metrica_presente": True if zero_da_fonte else None,
                       "schema_version": obs[0].schema_version},
            moeda=moedas[0] if len(moedas) == 1 else None,
        ))
    return sorted(saida, key=lambda x: (x.fonte, x.chave, x.observed_at or datetime.min))


def _m(o: Any) -> str:
    return o.metrica.value if hasattr(o.metrica, "value") else str(o.metrica)


def runs_de_run_coleta(linhas: Iterable[Mapping[str, Any]]) -> list[RunDQ]:
    """`dil_obs.run_coleta` -> `RunDQ` (`succeeded` vira `completed`).

    Linhas escritas = `n_inseridas + n_confirmadas` (R2-G23): no D2' da thread A uma releitura do mesmo
    estado vira CONFIRMAÇÃO, não versão; um run só de confirmações leu e gravou dado — não é "0 linhas".
    `n_confirmadas` ausente (schema anterior ao D2') conta 0; `n_inseridas` nulo continua desconhecido."""
    saida = []
    for r in linhas:
        ins = r.get("n_inseridas")
        escritas = None if ins is None else ins + (r.get("n_confirmadas") or 0)
        saida.append(RunDQ.de_dict({
            "run_id": r["run_id"], "fonte": r["fonte"], "coletor": r["coletor_nome"],
            "status": STATUS_RUN_DIL[r["status"]], "started_at": r["iniciado_em"],
            "finished_at": r.get("finalizado_em"), "linhas_escritas": escritas,
            "versao_coletor": r.get("coletor_versao"), "ultimo_sinal": r.get("ultimo_sinal"),
        }))
    return saida


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
    """Por run finalizado (R2-G6), mesma regra de `dq_obs_dead_letter`:
    - dead letters registrados (`dead_letter_registrados`, contagem real da tabela) > `n_dead_letter` do
      fechamento -> `dead_letter_apos_fechamento` (alto);
    - dead letters com `n_lidas` 0 ou nulo -> `dead_letter_sem_linhas_lidas` (alto: taxa indefinida não é ok);
    - `dl / n_lidas > limiar` -> `dead_letter_taxa` (alto)."""
    achados = []
    for r in sorted(runs_coleta, key=lambda x: x["run_id"]):
        if r.get("status") == "running":
            continue
        lidas, decl, reg = r.get("n_lidas"), r.get("n_dead_letter"), r.get("dead_letter_registrados")
        dl = max(decl or 0, reg or 0)
        taxa = dl / lidas if lidas else None
        if reg is not None and reg > (decl or 0):
            regra = "dead_letter_apos_fechamento"
        elif dl > 0 and not lidas:
            regra = "dead_letter_sem_linhas_lidas"
        elif taxa is not None and taxa > limiar:
            regra = "dead_letter_taxa"
        else:
            continue
        achados.append(Achado(
            regra=regra, severidade=Severidade.ALTO, fonte=r["fonte"], grao="run",
            janela=(iso(para_datetime(r["iniciado_em"])), iso(para_datetime(r.get("finalizado_em")))),
            chave=r["run_id"], evidencia={"n_lidas": lidas, "n_dead_letter": decl, "dead_letter_registrados": reg,
                                          "taxa": None if taxa is None else round(taxa, 4), "limiar": limiar,
                                          "coletor": r.get("coletor_nome")},
            mensagem=f"run {r['run_id']}: {regra} ({dl} dead letter(s), {lidas} lida(s))",
        ))
    return achados
