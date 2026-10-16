"""Checagens sobre leituras (observações): duplicação, zero sintetizado e completude da grade.

Equivalentes SQL: `dq_duplicacao`, `dq_zero_sintetizado` (testados por equivalência).
A completude de grade (entidade × dia × hora esperada) é só Python: o conjunto esperado de
entidades não é conhecido pelo banco hoje.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Iterable, Mapping, Sequence

from volc_dil.contracts.fingerprint import sha256_de

from .agenda import LIMIARES_PADRAO
from .modelo import Achado, ObservacaoDQ, Severidade, StatusDado, iso, numero


def _na_janela(o: ObservacaoDQ, agora: datetime | None, dias: float) -> bool:
    if agora is None:
        return True
    if o.observed_at is None:
        return False
    return agora - timedelta(days=dias) < o.observed_at <= agora


def identidade_payload(o: ObservacaoDQ) -> str:
    """Identidade do conteúdo: `payload_sha256` se veio da fonte; senão sha256 das métricas."""
    return o.payload_sha256 or sha256_de(dict(o.metricas))


# --------------------------------------------------------------------------- duplicação

SEVERIDADE_DUPLICACAO = {
    "conflito_no_run": "critico",
    "duplicata_exata_no_run": "aviso",
    "reingestao_suspeita": "aviso",
    "releitura_identica": "info",
    "releitura_com_revisao": "info",
}


@dataclass(frozen=True)
class ClasseDuplicacao:
    fonte: str
    grao: str
    chave: str
    escopo: str  # no_run | entre_runs
    run_id: str | None
    classe: str
    n_leituras: int
    n_runs: int
    n_payloads: int

    @property
    def severidade(self) -> str:
        return SEVERIDADE_DUPLICACAO[self.classe]


def classificar_duplicacao(
    observacoes: Iterable[ObservacaoDQ],
    agora: datetime | None = None,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[ClasseDuplicacao]:
    """Regras (idênticas à view):

    - mesma chave, mesmo run, payloads diferentes -> `conflito_no_run` (crítico: a view latest
      escolhe um deles por desempate arbitrário);
    - mesma chave, mesmo run, payload idêntico repetido -> `duplicata_exata_no_run` (suspeito);
    - mesma chave em >= 2 runs com o MESMO `observed_at` -> `reingestao_suspeita` (a mesma leitura
      foi gravada sob outro run);
    - mesma chave em >= 2 runs, `observed_at` distintos, payload idêntico -> `releitura_identica`
      (esperado: D0 horário, D-1 relendo D-7..D-1, termos LAST_7_DAYS);
    - idem com payload diferente -> `releitura_com_revisao` (esperado: maturação).
    """
    dias = float(limiares["janela_leituras_dias"])
    leituras = [o for o in observacoes if _na_janela(o, agora, dias)]
    no_run: dict[tuple[str, str, str, str], list[ObservacaoDQ]] = defaultdict(list)
    por_chave: dict[tuple[str, str, str], list[ObservacaoDQ]] = defaultdict(list)
    for o in leituras:
        no_run[(o.fonte, o.grao, o.chave, o.run_id)].append(o)
        por_chave[(o.fonte, o.grao, o.chave)].append(o)
    saida: list[ClasseDuplicacao] = []
    for (fonte, grao, chave, run_id), grupo in no_run.items():
        if len(grupo) < 2:
            continue
        payloads = {identidade_payload(o) for o in grupo}
        classe = "conflito_no_run" if len(payloads) > 1 else "duplicata_exata_no_run"
        saida.append(ClasseDuplicacao(fonte, grao, chave, "no_run", run_id, classe, len(grupo), 1, len(payloads)))
    for (fonte, grao, chave), grupo in por_chave.items():
        runs = {o.run_id for o in grupo}
        if len(runs) < 2:
            continue
        payloads = {identidade_payload(o) for o in grupo}
        runs_por_coleta: dict[datetime | None, set[str]] = defaultdict(set)
        for o in grupo:
            runs_por_coleta[o.observed_at].add(o.run_id)
        if max(len(v) for v in runs_por_coleta.values()) >= 2:
            classe = "reingestao_suspeita"
        elif len(payloads) == 1:
            classe = "releitura_identica"
        else:
            classe = "releitura_com_revisao"
        saida.append(ClasseDuplicacao(fonte, grao, chave, "entre_runs", None, classe, len(grupo), len(runs), len(payloads)))
    return sorted(saida, key=lambda c: (c.fonte, c.grao, c.chave, c.escopo, c.run_id or ""))


def checar_duplicacao(
    observacoes: Iterable[ObservacaoDQ],
    agora: datetime | None = None,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[Achado]:
    """Anomalias viram um achado por chave; releituras esperadas viram UM achado `info` agregado
    por fonte × grão (contagem), para não inundar o recibo."""
    achados: list[Achado] = []
    esperadas: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in classificar_duplicacao(observacoes, agora, limiares):
        if c.severidade == "info":
            esperadas[(c.fonte, c.grao)][c.classe] += 1
            continue
        achados.append(
            Achado(
                regra=f"duplicacao_{c.classe}",
                severidade=Severidade(c.severidade),
                fonte=c.fonte,
                grao=c.grao,
                janela=(None, iso(agora)),
                chave=c.chave if c.run_id is None else f"{c.chave}@{c.run_id}",
                evidencia={"escopo": c.escopo, "run_id": c.run_id, "n_leituras": c.n_leituras,
                           "n_runs": c.n_runs, "n_payloads": c.n_payloads},
                mensagem=f"{c.classe}: chave {c.chave} ({c.n_leituras} leituras, {c.n_payloads} payloads)",
            )
        )
    for (fonte, grao), contagem in sorted(esperadas.items()):
        achados.append(
            Achado(
                regra="duplicacao_releituras_esperadas",
                severidade=Severidade.INFO,
                fonte=fonte,
                grao=grao,
                janela=(None, iso(agora)),
                evidencia=dict(sorted(contagem.items())),
                mensagem=f"releituras esperadas em {fonte}/{grao}: {dict(sorted(contagem.items()))}",
            )
        )
    return achados


# --------------------------------------------------------------------------- zero sintetizado

METRICAS_ZERO_PADRAO = ("cost_micros", "impressions")


def classificar_zero(o: ObservacaoDQ, metricas: Sequence[str] = METRICAS_ZERO_PADRAO) -> str:
    """`nulo` | `com_valor` | `zero_com_linha` | `sintetizado` | `ambiguo`.

    Zero só é prova quando há linha de métrica na resposta da API (ou status `zero_confirmed`).
    Zero sem linha de métrica é o zero sintetizado do Code node (risco R3). Valor ausente ou não
    numérico é `nulo` — nunca zero."""
    valores = [numero(o.metricas.get(m)) for m in metricas]
    if any(v is None for v in valores):
        return "nulo"
    if any(v != 0 for v in valores):
        return "com_valor"
    if o.status is StatusDado.ZERO_CONFIRMED:
        return "zero_com_linha"
    linha = o.atributos.get("linha_metrica_presente")
    if linha is True:
        return "zero_com_linha"
    if linha is False:
        return "sintetizado"
    return "ambiguo"


@dataclass(frozen=True)
class ResumoZero:
    fonte: str
    coletor: str | None
    grao: str
    metric_date: date | None
    total: int
    zeros: int
    sintetizados: int
    zeros_com_linha: int
    ambiguos: int
    nulos: int

    @property
    def proporcao_sintetizada(self) -> float:
        return round(self.sintetizados / self.total, 4) if self.total else 0.0

    def severidade(self, limiares: Mapping[str, float] = LIMIARES_PADRAO) -> str:
        if self.total and self.proporcao_sintetizada >= float(limiares["zero_sintetizado_alto"]):
            return "alto"
        if self.sintetizados:
            return "aviso"
        if self.ambiguos:
            return "info"
        return "ok"


def medir_zero_sintetizado(
    observacoes: Iterable[ObservacaoDQ],
    agora: datetime | None = None,
    grao: str = "campaign_day",
    metricas: Sequence[str] = METRICAS_ZERO_PADRAO,
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[ResumoZero]:
    dias = float(limiares["janela_leituras_dias"])
    grupos: dict[tuple[str, str | None, date | None], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for o in observacoes:
        if o.grao != grao or not _na_janela(o, agora, dias):
            continue
        grupos[(o.fonte, o.coletor, o.metric_date)][classificar_zero(o, metricas)] += 1
    saida = []
    for (fonte, coletor, dia), c in sorted(grupos.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][2] or date.min)):
        zeros = c["zero_com_linha"] + c["sintetizado"] + c["ambiguo"]
        saida.append(ResumoZero(fonte, coletor, grao, dia, sum(c.values()), zeros, c["sintetizado"],
                                c["zero_com_linha"], c["ambiguo"], c["nulo"]))
    return saida


def checar_zero_sintetizado(
    observacoes: Iterable[ObservacaoDQ],
    agora: datetime | None = None,
    grao: str = "campaign_day",
    limiares: Mapping[str, float] = LIMIARES_PADRAO,
) -> list[Achado]:
    achados = []
    for r in medir_zero_sintetizado(observacoes, agora, grao, limiares=limiares):
        sev = r.severidade(limiares)
        if sev == "ok":
            continue
        dia = iso(r.metric_date)
        achados.append(
            Achado(
                regra="zero_sintetizado",
                severidade=Severidade(sev),
                fonte=r.fonte,
                grao=r.grao,
                janela=(dia, dia),
                chave=r.coletor,
                evidencia={"total": r.total, "zeros": r.zeros, "sintetizados": r.sintetizados,
                           "zeros_com_linha": r.zeros_com_linha, "ambiguos": r.ambiguos, "nulos": r.nulos,
                           "proporcao_sintetizada": r.proporcao_sintetizada},
                mensagem=(f"{r.coletor} {dia}: {r.sintetizados}/{r.total} leituras com zero sem linha de métrica"
                          f" ({r.proporcao_sintetizada:.0%}); {r.ambiguos} zero(s) sem prova"),
            )
        )
    return achados


# --------------------------------------------------------------------------- completude de grade


@dataclass(frozen=True)
class CelulaEsperada:
    fonte: str
    grao: str
    chave: str
    metric_date: date | None = None
    metric_hour: int | None = None


SEVERIDADE_CELULA = {
    "observado": "ok",
    "zero_confirmado": "ok",
    "nao_suportado": "ok",
    "atrasado": "info",
    "parcial": "info",
    "observado_sem_valor": "aviso",
    "ausente_declarado": "aviso",
    "invalido": "alto",
    "ausente_silencioso": "alto",
}

_STATUS_PARA_CLASSE = {
    StatusDado.OBSERVED: "observado",
    StatusDado.ZERO_CONFIRMED: "zero_confirmado",
    StatusDado.UNSUPPORTED: "nao_suportado",
    StatusDado.LATE: "atrasado",
    StatusDado.PARTIAL: "parcial",
    StatusDado.MISSING: "ausente_declarado",
    StatusDado.UNAVAILABLE: "ausente_declarado",
    StatusDado.INVALID: "invalido",
}
_ORDEM_MELHOR = ("observado", "zero_confirmado", "nao_suportado", "parcial", "atrasado",
                 "observado_sem_valor", "ausente_declarado", "invalido")


def classificar_celula(
    leituras: Sequence[ObservacaoDQ],
    prazo: datetime | None = None,
) -> str:
    """Melhor estado entre as leituras de uma célula esperada.

    - nenhuma leitura -> `ausente_silencioso` (o pior: ninguém declarou nada);
    - `missing`/`unavailable` declarados -> `ausente_declarado` (a fonte disse que não tem);
    - `late`, ou `available_at` depois do `prazo` -> `atrasado` (chegou; atraso não é ausência);
    - `observed` com todas as métricas nulas -> `observado_sem_valor` (null não é zero)."""
    if not leituras:
        return "ausente_silencioso"
    classes = []
    for o in leituras:
        c = _STATUS_PARA_CLASSE[o.status]
        if c == "observado" and o.metricas and all(numero(v) is None for v in o.metricas.values()):
            c = "observado_sem_valor"
        if c in ("observado", "zero_confirmado") and prazo is not None and o.available_at is not None \
                and o.available_at > prazo:
            c = "atrasado"
        classes.append(c)
    return min(classes, key=_ORDEM_MELHOR.index)


def checar_completude_grade(
    observacoes: Iterable[ObservacaoDQ],
    esperadas: Iterable[CelulaEsperada],
    prazo: Callable[[CelulaEsperada], datetime | None] | None = None,
) -> list[Achado]:
    """Esperado × observado por célula. Um achado por fonte × grão × classe não-ok, com as chaves."""
    indice: dict[tuple, list[ObservacaoDQ]] = defaultdict(list)
    for o in observacoes:
        indice[(o.fonte, o.grao, o.chave, o.metric_date, o.metric_hour)].append(o)
    grupos: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for cel in esperadas:
        leituras = indice.get((cel.fonte, cel.grao, cel.chave, cel.metric_date, cel.metric_hour), [])
        classe = classificar_celula(leituras, prazo(cel) if prazo else None)
        if SEVERIDADE_CELULA[classe] == "ok":
            continue
        rotulo = cel.chave + ("" if cel.metric_date is None else f"@{cel.metric_date}") + \
            ("" if cel.metric_hour is None else f"h{cel.metric_hour:02d}")
        grupos[(cel.fonte, cel.grao, classe)].append(rotulo)
    achados = []
    for (fonte, grao, classe), chaves in sorted(grupos.items()):
        achados.append(
            Achado(
                regra=f"completude_{classe}",
                severidade=Severidade(SEVERIDADE_CELULA[classe]),
                fonte=fonte,
                grao=grao,
                janela=(None, None),
                evidencia={"n": len(chaves), "chaves": sorted(chaves)[:50]},
                mensagem=f"{len(chaves)} célula(s) {classe} em {fonte}/{grao}",
            )
        )
    return achados
