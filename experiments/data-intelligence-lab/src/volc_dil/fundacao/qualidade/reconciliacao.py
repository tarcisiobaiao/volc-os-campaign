"""Reconciliação: receita JoinAds (soma kv por campanha × earnings de domínio) e custo D0 × D-1.

Receita por domínio × dia, só no universo com earnings válido E kv (R2-G8, mesma regra da junção da
thread C, R1-F19). Equivalentes SQL: `dq_reconciliacao_joinads` (sobre a view real `joinads_observation_latest`) e
`dq_reconciliacao_custo_d0_d1`. Referência de produção (recibo L5, 16/10): a soma kv por campanha
com `custom_value` numérico foi 97–100% do earnings de domínio em 08–16/10.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from .agenda import LIMIARES_PADRAO, TZ_PADRAO
from .modelo import SUCESSO, Achado, ObservacaoDQ, RunDQ, Severidade, iso, numero

ENDPOINT_EARNINGS = "earnings"
ENDPOINT_KV_CAMPANHA = "key_value_campaign_adunit"
COLETOR_D0 = "n8n-google-ads-d0"
COLETOR_D1 = "n8n-google-ads-d1"


def _hoje_local(agora: datetime, tz: str = TZ_PADRAO) -> date:
    return agora.astimezone(ZoneInfo(tz)).date()


def _soma(valores: list) -> float | None:
    """SUM do SQL: ignora nulos; sem nenhum valor numérico devolve None (não zero)."""
    nums = [numero(v) for v in valores]
    nums = [v for v in nums if v is not None]
    return float(sum(nums)) if nums else None


# --------------------------------------------------------------------------- receita JoinAds


@dataclass(frozen=True)
class LinhaReceitaDia:
    """Um domínio × dia (R2-G8: a reconciliação compara universos iguais, como a junção da thread C).

    `tem_earnings`/`tem_kv` dizem se o endpoint tem linha no domínio × dia; `earnings_valido` é falso se
    alguma linha de earnings não tem valor (status sem valor ou receita nula). `None` em `tem_*` = inferir
    do valor (compatibilidade com linhas montadas à mão)."""

    metric_date: date
    earnings: float | None
    receita_kv_campanha: float | None
    receita_kv_sem_campanha: float | None = None
    n_campanhas: int = 0
    n_moedas: int = 1
    dominio: str | None = None
    tem_earnings: bool | None = None
    earnings_valido: bool = True
    tem_kv: bool | None = None

    @property
    def com_earnings(self) -> bool:
        return self.earnings is not None if self.tem_earnings is None else self.tem_earnings

    @property
    def com_kv(self) -> bool:
        if self.tem_kv is not None:
            return self.tem_kv
        return self.receita_kv_campanha is not None or self.receita_kv_sem_campanha is not None

    @classmethod
    def de_dict(cls, d: Mapping) -> "LinhaReceitaDia":
        from .modelo import para_date

        f = lambda k: None if d.get(k) in (None, "") else float(d[k])  # noqa: E731
        b = lambda k: None if d.get(k) is None else bool(d[k])  # noqa: E731
        return cls(para_date(d["metric_date"]), f("earnings"), f("receita_kv_campanha"),
                   f("receita_kv_sem_campanha"), int(d.get("n_campanhas") or 0), int(d.get("n_moedas") or 1),
                   d.get("dominio"), b("tem_earnings"), bool(d.get("earnings_valido", True)), b("tem_kv"))

    def como_dict(self) -> dict:
        return {"metric_date": self.metric_date.isoformat(), "dominio": self.dominio, "earnings": self.earnings,
                "receita_kv_campanha": self.receita_kv_campanha,
                "receita_kv_sem_campanha": self.receita_kv_sem_campanha, "n_campanhas": self.n_campanhas,
                "n_moedas": self.n_moedas, "tem_earnings": self.tem_earnings,
                "earnings_valido": self.earnings_valido, "tem_kv": self.tem_kv}


_COM_VALOR = frozenset({"observed", "zero_confirmed"})


def joinads_latest(observacoes: Iterable[ObservacaoDQ], runs: Iterable[RunDQ]) -> list[ObservacaoDQ]:
    """Réplica pura de `joinads_observation_latest` (192bc065:…20261015170000…): só runs
    completed|partial da MAIOR versão bem-sucedida do coletor físico; por chave natural, a leitura de
    maior `observed_at` (desempate por `observation_key` desc)."""
    runs = list(runs)
    elegiveis_por_coletor: dict[str, list[RunDQ]] = defaultdict(list)
    for r in runs:
        if r.status in SUCESSO:
            elegiveis_por_coletor[r.coletor.split(":")[0]].append(r)
    elegiveis: set[str] = set()
    for lista in elegiveis_por_coletor.values():
        vmax = max(int(r.versao_coletor or 0) for r in lista)
        elegiveis.update(r.run_id for r in lista if int(r.versao_coletor or 0) == vmax)
    melhor: dict[str, ObservacaoDQ] = {}
    for o in observacoes:
        if o.fonte != "joinads" or o.run_id not in elegiveis:
            continue
        atual = melhor.get(o.chave)
        chave_ord = (o.observed_at, str(o.atributos.get("observation_key", "")))
        if atual is None or chave_ord > (atual.observed_at, str(atual.atributos.get("observation_key", ""))):
            melhor[o.chave] = o
    return list(melhor.values())


def agregar_receita_joinads(
    observacoes: Iterable[ObservacaoDQ],
    runs: Iterable[RunDQ],
    agora: datetime,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[LinhaReceitaDia]:
    """Por domínio × dia (domínio = `ObservacaoDQ.conta`, como no adaptador JoinAds), só earnings e kv."""
    inicio = _hoje_local(agora) - timedelta(days=int(limiares["janela_reconciliacao_dias"]))
    grupos: dict[tuple[date, str | None], list[ObservacaoDQ]] = defaultdict(list)
    for o in joinads_latest(observacoes, runs):
        if o.metric_date is None or not o.metric_date > inicio:
            continue
        if o.atributos.get("endpoint") in (ENDPOINT_EARNINGS, ENDPOINT_KV_CAMPANHA):
            grupos[(o.metric_date, o.conta)].append(o)
    linhas = []
    for (dia, dominio), obs in sorted(grupos.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        ep = lambda o: o.atributos.get("endpoint")  # noqa: E731
        earn = [o for o in obs if ep(o) == ENDPOINT_EARNINGS]
        valido = lambda o: o.status.value in _COM_VALOR and numero(o.metricas.get("revenue_client")) is not None  # noqa: E731
        kv = [o for o in obs if ep(o) == ENDPOINT_KV_CAMPANHA]
        linhas.append(
            LinhaReceitaDia(
                metric_date=dia,
                dominio=dominio,
                earnings=_soma([o.metricas.get("revenue_client") for o in earn if valido(o)]),
                receita_kv_campanha=_soma([o.metricas.get("revenue_client") for o in kv if o.entidade]),
                receita_kv_sem_campanha=_soma([o.metricas.get("revenue_client") for o in kv if not o.entidade]),
                n_campanhas=len({o.entidade for o in kv if o.entidade}),
                n_moedas=len({o.moeda for o in obs if o.moeda}),
                tem_earnings=bool(earn),
                earnings_valido=all(valido(o) for o in earn),
                tem_kv=bool(kv),
            )
        )
    return linhas


@dataclass(frozen=True)
class EstadoReceita:
    metric_date: date
    cobertura: float | None
    # ok | sem_base | earnings_indisponivel | kv_sem_earnings | earnings_sem_kv | cobertura_baixa | excesso | moeda_mista
    estado: str
    severidade: str
    linha: LinhaReceitaDia


def avaliar_reconciliacao_receita(
    linhas: Iterable[LinhaReceitaDia],
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[EstadoReceita]:
    """Cobertura = kv por campanha / earnings, SÓ no domínio × dia com earnings válido E kv (R2-G8).
    Domínio × dia fora desse universo vira estado próprio, nunca entra no numerador nem no denominador de
    outro domínio — assim um domínio a 60% não é mascarado pelo kv de um domínio sem earnings."""
    lo, hi, crit = (float(limiares[k]) for k in
                    ("receita_cobertura_min", "receita_cobertura_max", "receita_cobertura_critica"))
    saida = []
    for ln in sorted(linhas, key=lambda x: (x.metric_date, x.dominio or "")):
        cob = None
        comparavel = ln.com_earnings and ln.earnings_valido and ln.earnings is not None and ln.earnings > 0 and ln.com_kv
        if comparavel:
            cob = round((ln.receita_kv_campanha or 0.0) / ln.earnings, 4)
        if ln.n_moedas > 1:
            estado, sev = "moeda_mista", "alto"
        elif ln.com_earnings and not ln.earnings_valido:
            estado, sev = "earnings_indisponivel", "aviso"
        elif not ln.com_earnings and ln.com_kv:
            estado, sev = "kv_sem_earnings", "aviso"
        elif not ln.com_earnings or ln.earnings is None or ln.earnings <= 0:
            estado, sev = "sem_base", "info"
        elif not ln.com_kv:
            estado, sev = "earnings_sem_kv", "alto"
        elif cob < crit:
            estado, sev = "cobertura_baixa", "alto"
        elif cob < lo:
            estado, sev = "cobertura_baixa", "aviso"
        elif cob > hi:
            estado, sev = "excesso", "alto"
        else:
            estado, sev = "ok", "ok"
        saida.append(EstadoReceita(ln.metric_date, cob, estado, sev, ln))
    return saida


def checar_reconciliacao_receita(
    linhas: Iterable[LinhaReceitaDia],
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[Achado]:
    achados = []
    for e in avaliar_reconciliacao_receita(linhas, limiares):
        if e.severidade == "ok":
            continue
        dia = iso(e.metric_date)
        achados.append(
            Achado(
                regra=f"reconciliacao_receita_{e.estado}",
                severidade=Severidade(e.severidade),
                fonte="joinads",
                grao="domain_day×campaign_adunit_day",
                janela=(dia, dia),
                chave=e.linha.dominio,
                evidencia={"cobertura": e.cobertura, "n_campanhas": e.linha.n_campanhas,
                           "n_moedas": e.linha.n_moedas, "tem_earnings": e.linha.com_earnings,
                           "earnings_valido": e.linha.earnings_valido, "tem_kv": e.linha.com_kv},
                mensagem=f"receita {e.linha.dominio} {dia}: {e.estado} (cobertura kv/earnings = {e.cobertura})",
            )
        )
    return achados


# --------------------------------------------------------------------------- custo D0 × D-1


@dataclass(frozen=True)
class EstadoCusto:
    conta: str | None
    campanha: str | None
    metric_date: date
    custo_d0: float | None
    custo_d1: float | None
    diferenca_relativa: float | None
    estado: str  # ok | aguardando_d1 | sem_d1 | sem_d0 | valor_nulo | divergente
    severidade: str


def avaliar_reconciliacao_custo(
    observacoes: Iterable[ObservacaoDQ],
    runs: Iterable[RunDQ],
    agora: datetime,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
    metrica: str = "cost_micros",
    tz: str = TZ_PADRAO,
) -> list[EstadoCusto]:
    """Último D0 bem-sucedido × D-1 fechado (lido em dia local > metric_date), por campanha-dia."""
    status = {r.run_id: r.status for r in runs}
    hoje = _hoje_local(agora, tz)
    inicio = hoje - timedelta(days=int(limiares["janela_reconciliacao_dias"]))
    zona = ZoneInfo(tz)
    d0: dict[tuple, ObservacaoDQ] = {}
    d1: dict[tuple, ObservacaoDQ] = {}
    for o in observacoes:
        if o.fonte != "google_ads" or o.grao != "campaign_day" or o.metric_date is None:
            continue
        if status.get(o.run_id) not in SUCESSO or not (o.metric_date > inicio) or o.observed_at is None:
            continue
        if o.observed_at > agora:
            continue
        k = (o.conta, o.entidade, o.metric_date)
        if o.coletor == COLETOR_D0:
            alvo = d0
        elif o.coletor == COLETOR_D1 and o.observed_at.astimezone(zona).date() > o.metric_date:
            alvo = d1
        else:
            continue
        if k not in alvo or o.observed_at > alvo[k].observed_at:
            alvo[k] = o
    tol, alto = float(limiares["custo_d0_d1_tol"]), float(limiares["custo_d0_d1_alto"])
    saida = []
    for k in sorted(set(d0) | set(d1), key=lambda t: (t[0] or "", t[1] or "", t[2])):
        conta, camp, dia = k
        v0 = numero(d0[k].metricas.get(metrica)) if k in d0 else None
        v1 = numero(d1[k].metricas.get(metrica)) if k in d1 else None
        diff = None
        if k not in d1:
            estado, sev = ("aguardando_d1", "ok") if dia >= hoje else ("sem_d1", "info")
        elif k not in d0:
            estado, sev = "sem_d0", "info"
        elif v0 is None or v1 is None:
            estado, sev = "valor_nulo", "aviso"
        else:
            diff = 0.0 if v1 == 0 and v0 == 0 else (float("inf") if v1 == 0 else round(abs(v1 - v0) / abs(v1), 4))
            if diff <= tol:
                estado, sev = "ok", "ok"
            elif diff <= alto:
                estado, sev = "divergente", "aviso"
            else:
                estado, sev = "divergente", "alto"
        saida.append(EstadoCusto(conta, camp, dia, v0, v1, diff, estado, sev))
    return saida


def checar_reconciliacao_custo(
    observacoes: Iterable[ObservacaoDQ],
    runs: Iterable[RunDQ],
    agora: datetime,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[Achado]:
    achados = []
    sem_d1: dict[date, int] = defaultdict(int)
    for e in avaliar_reconciliacao_custo(observacoes, runs, agora, limiares):
        if e.severidade == "ok":
            continue
        if e.estado in ("sem_d1", "sem_d0"):
            sem_d1[e.metric_date] += 1
            continue
        dia = iso(e.metric_date)
        achados.append(
            Achado(
                regra=f"reconciliacao_custo_{e.estado}",
                severidade=Severidade(e.severidade),
                fonte="google_ads",
                grao="campaign_day",
                janela=(dia, dia),
                chave=f"{e.conta}:{e.campanha}",
                evidencia={"diferenca_relativa": None if e.diferenca_relativa in (None, float("inf"))
                           else e.diferenca_relativa, "d1_zero_d0_nao": e.diferenca_relativa == float("inf")},
                mensagem=f"custo {e.conta}:{e.campanha} {dia}: {e.estado} (dif. relativa {e.diferenca_relativa})",
            )
        )
    for dia, n in sorted(sem_d1.items()):
        achados.append(
            Achado(
                regra="reconciliacao_custo_sem_par",
                severidade=Severidade.INFO,
                fonte="google_ads",
                grao="campaign_day",
                janela=(iso(dia), iso(dia)),
                evidencia={"campanhas": n},
                mensagem=f"{n} campanha(s) sem par D0/D-1 em {dia}",
            )
        )
    return achados
