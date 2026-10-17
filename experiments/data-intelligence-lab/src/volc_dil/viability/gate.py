"""Gate pré-campanha: SÓ análise. Combina evidência de custo, receita, maturação, moeda,
qualidade, fronteira, tolerância do owner e simulação numa recomendação tipada.

O gate não aprova campanha e não emite ação externa. Toda recomendação diz por que chegou ali
(`reasons`) e o que a faria mudar (`missing_evidence`, `next_read_only_actions`).
"""
from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, field
from datetime import timedelta
from fractions import Fraction
from typing import Any, Optional

from volc_dil.contracts import Dinheiro

from . import VERSAO_KERNEL
from .contrato import REALIZADA, EntradaViabilidade, Evidencia, hash_entrada, json_canonico
from .economia import Cenario, Envelope, Fronteira, Indisponivel, envelope_conservador, estresse, fronteira
from .simulacao import CurvaIndisponivel, analisar_simulacao
from .teto import MIN_CLIQUES_MADUROS, MIN_DIAS_MADUROS, MATURITY_WAIT_DIAS, TetoExperimento, calcular_teto

CLIQUES_CONFIANCA_ALTA = 500
DIAS_CONFIANCA_ALTA = 7
COBERTURA_COMPLETA_PPM = 1_000_000
FRESHNESS_SLA_DIAS_PADRAO = 7
# Evidência de custo/cliques/receita que NUNCA sustenta veredito positivo nem confiança alta.
EVIDENCIA_NAO_DECISIVA = frozenset({Evidencia.PROJECTED, Evidencia.ESTIMATED, Evidencia.IMMATURE})


class Veredito(str, enum.Enum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    # Inviável SOB OS CENÁRIOS DECLARADOS (estresse enumerado); não é prova de inviabilidade estrutural.
    UNVIABLE_UNDER_DECLARED_SCENARIOS = "unviable_under_declared_scenarios"
    TEST_WITH_CAP = "test_with_cap"
    VIABLE_CANDIDATE = "viable_candidate"
    ALREADY_PROFITABLE = "already_profitable"
    # Alias de compatibilidade (mesmo membro) para código V1 ainda não migrado; remover na integração.

    @staticmethod
    def ordem(v: "Veredito") -> int:
        """Permissividade (quanto gasto o veredito admite). Inviável e insuficiente não admitem gasto."""
        return {Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS: 0, Veredito.INSUFFICIENT_EVIDENCE: 0, Veredito.TEST_WITH_CAP: 1,
                Veredito.VIABLE_CANDIDATE: 2, Veredito.ALREADY_PROFITABLE: 3}[v]


class Confianca(str, enum.Enum):
    INSUFFICIENT = "insufficient"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    def ordem(self) -> int:
        return {Confianca.INSUFFICIENT: 0, Confianca.LOW: 1, Confianca.MEDIUM: 2, Confianca.HIGH: 3}[self]


class Recomendacao(str, enum.Enum):
    REJEITAR_TESE_ECONOMICA = "rejeitar_tese_economica"
    COLETAR_EVIDENCIA = "coletar_evidencia"
    PREPARAR_CAMPANHA_PAUSADA = "preparar_campanha_pausada"
    PROPOR_TESTE_LIMITADO = "propor_teste_limitado"
    CONTINUAR_CAMPANHA_EXISTENTE = "continuar_campanha_existente"
    PARAR_POR_STOP_LOSS = "parar_por_stop_loss"
    AGUARDAR_MATURACAO = "aguardar_maturacao"


@dataclass(frozen=True)
class Motivo:
    codigo: str
    detalhe: str
    severidade: str = "info"  # info | aviso | bloqueante

    def para_json(self) -> dict:
        return {"codigo": self.codigo, "detalhe": self.detalhe, "severidade": self.severidade}


PROHIBITED_ACTIONS = (
    "criar, ativar, pausar ou alterar campanha no Google Ads",
    "enviar valor de conversão ao Google Ads",
    "publicar GTM ou WordPress",
    "alterar banco, n8n ou qualquer sistema externo",
    "derivar tolerância financeira do owner",
    "tratar ausência como zero, projeção como realizado ou moeda atestada como provada",
)


def _fr(v: Optional[Fraction]) -> Optional[str]:
    return None if v is None else str(v)


def _din(v: Optional[Dinheiro]) -> Optional[dict]:
    return None if v is None else v.para_json()


@dataclass(frozen=True)
class ResultadoViabilidade:
    kernel_version: str
    candidato_id: str
    as_of: str
    verdict: Veredito
    confidence_class: Confianca
    recomendacao: Recomendacao
    break_even_cpc: Optional[Fraction]
    conservative_affordable_cpc: Optional[Fraction]
    observed_cpc: Optional[Fraction]
    observed_rpc: Optional[Fraction]
    required_rpc: Optional[Fraction]
    required_rpc_multiplier: Optional[Fraction]
    contribution_observed: Optional[Dinheiro]
    contribution_conservative: Optional[Dinheiro]
    break_even_interval: Optional[dict]
    max_experiment_spend: Optional[Dinheiro]
    max_experiment_clicks: Optional[int]
    max_experiment_days: Optional[int]
    stop_loss: Optional[Dinheiro]
    maturity_wait: Optional[int]
    missing_evidence: tuple[str, ...]
    invalid_evidence: tuple[str, ...]
    assumptions: tuple[str, ...]
    reasons: tuple[Motivo, ...]
    next_read_only_actions: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    stress: tuple[dict, ...]
    simulacao: Optional[dict]
    teto: Optional[dict]
    input_hash: str
    trace: tuple[dict, ...]
    result_hash: str = ""
    observed_rpc_per_visit: Optional[Fraction] = None          # só reportado; o break-even é por clique
    observed_rpc_per_visit_unavailable: Optional[str] = None   # "visitas_ausente" | "visitas_zero"
    max_loss: Optional[Dinheiro] = None                        # tolerância do owner (perda_maxima.valor); nunca é teto de gasto
    spend_cap: Optional[Dinheiro] = None                       # teto de gasto do experimento (== max_experiment_spend)
    net_loss_observed: Optional[Dinheiro] = None               # max(0, custo − receita líquida) observado/maduro
    net_loss_conservative: Optional[Dinheiro] = None           # max(0, custo_cons − receita_cons) sob as premissas

    def para_json(self, com_hash: bool = True) -> dict:
        d = {
            "kernel_version": self.kernel_version, "candidato_id": self.candidato_id, "as_of": self.as_of,
            "verdict": self.verdict.value, "confidence_class": self.confidence_class.value, "recomendacao": self.recomendacao.value,
            "break_even_cpc_micros": _fr(self.break_even_cpc), "conservative_affordable_cpc_micros": _fr(self.conservative_affordable_cpc),
            "observed_cpc_micros": _fr(self.observed_cpc), "observed_rpc_micros": _fr(self.observed_rpc),
            "observed_rpc_grain": "click", "observed_rpc_per_visit_micros": _fr(self.observed_rpc_per_visit),
            "observed_rpc_per_visit_unavailable": self.observed_rpc_per_visit_unavailable,
            "required_rpc_micros": _fr(self.required_rpc), "required_rpc_multiplier": _fr(self.required_rpc_multiplier),
            "contribution_observed": _din(self.contribution_observed), "contribution_conservative": _din(self.contribution_conservative),
            "break_even_interval": self.break_even_interval, "probability_of_break_even": None,
            "max_experiment_spend": _din(self.max_experiment_spend), "max_experiment_clicks": self.max_experiment_clicks,
            "max_experiment_days": self.max_experiment_days, "stop_loss": _din(self.stop_loss), "maturity_wait_days": self.maturity_wait,
            "max_loss": _din(self.max_loss), "spend_cap": _din(self.spend_cap),
            "net_loss_observed": _din(self.net_loss_observed), "net_loss_conservative": _din(self.net_loss_conservative),
            "missing_evidence": list(self.missing_evidence), "invalid_evidence": list(self.invalid_evidence),
            "assumptions": list(self.assumptions), "reasons": [m.para_json() for m in self.reasons],
            "next_read_only_actions": list(self.next_read_only_actions), "prohibited_actions": list(self.prohibited_actions),
            "stress": list(self.stress), "simulacao": self.simulacao, "teto": self.teto, "input_hash": self.input_hash,
            "trace": list(self.trace), "external_actions": 0,
        }
        if com_hash:
            d["result_hash"] = self.result_hash
        return d


def _hash_resultado(d: dict) -> str:
    return hashlib.sha256(json_canonico(d).encode("utf-8")).hexdigest()


def _cenarios_json(cs: list[Cenario]) -> list[dict]:
    return [{"nome": c.nome, "contribuicao": c.contribuicao.para_json(), "rpc_micros": str(c.rpc), "premissas": list(c.premissas)} for c in cs]


def _teto_json(t: TetoExperimento) -> dict:
    return {"spend_cap": t.spend_cap.para_json(), "click_cap": t.click_cap, "day_cap": t.day_cap, "maturity_wait_dias": t.maturity_wait_dias,
            "cpc_conservador_micros": str(t.cpc_conservador), "rpc_conservador_micros": str(t.rpc_conservador),
            "perda_por_clique_micros": str(t.perda_por_clique_conservadora),
            "parada": list(t.parada.gatilhos), "continuidade": list(t.continuidade.gatilhos), "inconclusao": list(t.inconclusao.gatilhos),
            "premissas": list(t.premissas)}


@dataclass(frozen=True)
class Governanca:
    """Governança de evidência lida do contrato (V1 ou V2, via getattr): o que impede veredito positivo
    (viable_candidate/already_profitable) e confiança alta, independentemente dos números."""
    evidencia_fraca: tuple[str, ...]      # "custo_projected", "cliques_estimated", "receita_immature"...
    stale: tuple[str, ...]                # medidas com observado_em < as_of − freshness_sla_dias
    invalidas: tuple[str, ...]            # "receita:invalid_schema"
    cobertura_receita_ppm: Optional[int]  # None = desconhecida (≠ completa)
    dias_custo_sem_receita: int
    freshness_sla_dias: int

    @property
    def cobertura_completa(self) -> bool:
        return self.cobertura_receita_ppm is not None and self.cobertura_receita_ppm >= COBERTURA_COMPLETA_PPM

    def bloqueia_positivo(self) -> bool:
        return bool(self.evidencia_fraca or self.stale or self.invalidas) or not self.cobertura_completa

    def impede_alta(self) -> bool:
        return self.bloqueia_positivo()


def _governanca(e: EntradaViabilidade) -> Governanca:
    sla = getattr(e, "freshness_sla_dias", FRESHNESS_SLA_DIAS_PADRAO)
    if not isinstance(sla, int) or isinstance(sla, bool) or sla <= 0:
        sla = FRESHNESS_SLA_DIAS_PADRAO
    limite = e.as_of - timedelta(days=sla)
    fraca: list[str] = []
    stale: list[str] = []
    invalidas: list[str] = []
    for nome in ("custo", "cliques", "receita", "visitas"):
        m = getattr(e, nome)
        if m is None:
            continue
        if nome != "visitas" and m.evidencia in EVIDENCIA_NAO_DECISIVA:
            fraca.append(f"{nome}_{m.evidencia.value}")
        obs = getattr(m, "observado_em", None)
        if obs is not None and obs < limite:
            stale.append(nome)
        for flag in getattr(m, "flags_qualidade", ()) or ():
            if str(flag).startswith("invalid"):
                invalidas.append(f"{nome}:{flag}")
    for flag in e.flags_qualidade:
        if str(flag).startswith("invalid"):
            invalidas.append(f"entrada:{flag}")
    cobertura = getattr(e.janela, "cobertura_receita_ppm", None)
    if cobertura is not None and (not isinstance(cobertura, int) or isinstance(cobertura, bool) or cobertura < 0):
        cobertura = None
    dias_sem = getattr(e.janela, "dias_custo_sem_receita", 0)
    if not isinstance(dias_sem, int) or isinstance(dias_sem, bool) or dias_sem < 0:
        dias_sem = 0
    return Governanca(tuple(fraca), tuple(stale), tuple(invalidas), cobertura, dias_sem, sla)


def _menor(a: Confianca, b: Confianca) -> Confianca:
    return a if a.ordem() <= b.ordem() else b


def _confianca(env: Envelope, e: EntradaViabilidade, gov: Governanca) -> Confianca:
    """Classe de confiança. Evidência de custo e cliques entra junto com a de receita/moeda/câmbio;
    governança (stale, flags inválidas, cobertura incompleta, evidência não decisiva) nunca permite `high`."""
    c = Confianca.HIGH
    if (env.economia.moeda_evidencia is not Evidencia.OBSERVED or e.custo.moeda_evidencia is not Evidencia.OBSERVED
            or (env.economia.cambio_evidencia not in (None, Evidencia.OBSERVED))):
        c = _menor(c, Confianca.MEDIUM)
    for m in (e.custo, e.cliques):
        if m.evidencia in EVIDENCIA_NAO_DECISIVA:
            c = _menor(c, Confianca.LOW)
        elif m.evidencia not in REALIZADA:
            c = _menor(c, Confianca.MEDIUM)
    if env.economia.cliques < MIN_CLIQUES_MADUROS or e.janela.dias_maduros < DIAS_CONFIANCA_ALTA:
        c = _menor(c, Confianca.LOW)
    elif env.economia.cliques < CLIQUES_CONFIANCA_ALTA:
        c = _menor(c, Confianca.MEDIUM)
    if not env.receita_realizada:
        c = _menor(c, Confianca.LOW)
    if gov.impede_alta():
        c = _menor(c, Confianca.MEDIUM)
    return c


def avaliar(e: EntradaViabilidade) -> ResultadoViabilidade:
    trace: list[dict] = []
    reasons: list[Motivo] = []
    missing: list[str] = []
    invalid: list[str] = []
    assumptions: list[str] = []
    next_actions: list[str] = []
    ih = hash_entrada(e)
    trace.append({"passo": "entrada", "input_hash": ih, "as_of": e.as_of.isoformat()})

    teto = calcular_teto(e)
    teto_json: Optional[dict] = None
    if isinstance(teto, Indisponivel):
        missing.append(teto.motivo)
        trace.append({"passo": "teto", "resultado": teto.motivo})
        teto_ok: Optional[TetoExperimento] = None
    else:
        teto_ok = teto
        teto_json = _teto_json(teto)
        assumptions.extend(teto.premissas)
        trace.append({"passo": "teto", "spend_cap_micros": teto.spend_cap.micros, "click_cap": teto.click_cap})

    env = envelope_conservador(e)
    if e.receita.moeda_evidencia is Evidencia.UNKNOWN and e.receita.valor is not None:
        missing.append("receita_moeda_unknown")
    if e.receita.moeda_evidencia is Evidencia.INVALID:
        invalid.append("receita_moeda_invalid")

    def _resultado(verdict: Veredito, conf: Confianca, rec: Recomendacao, **kw: Any) -> ResultadoViabilidade:
        base = dict(
            kernel_version=VERSAO_KERNEL, candidato_id=e.candidato_id, as_of=e.as_of.isoformat(), verdict=verdict,
            confidence_class=conf, recomendacao=rec, break_even_cpc=None, conservative_affordable_cpc=None, observed_cpc=None,
            observed_rpc=None, required_rpc=None, required_rpc_multiplier=None, contribution_observed=None,
            contribution_conservative=None, break_even_interval=None, max_experiment_spend=None, max_experiment_clicks=None,
            max_experiment_days=None, stop_loss=None, maturity_wait=None, missing_evidence=tuple(dict.fromkeys(missing)),
            invalid_evidence=tuple(dict.fromkeys(invalid)), assumptions=tuple(dict.fromkeys(assumptions)), reasons=tuple(reasons),
            next_read_only_actions=tuple(dict.fromkeys(next_actions)), prohibited_actions=PROHIBITED_ACTIONS, stress=(),
            simulacao=None, teto=teto_json, input_hash=ih, trace=tuple(trace),
        )
        base.update(kw)
        r = ResultadoViabilidade(**base)
        return ResultadoViabilidade(**{**r.__dict__, "result_hash": _hash_resultado(r.para_json(com_hash=False))})

    # ---------------- sem economia observada
    if isinstance(env, Indisponivel):
        missing.append(env.motivo)
        if env.motivo.endswith("_invalid"):
            invalid.append(env.motivo)
        trace.append({"passo": "envelope", "resultado": env.motivo, "detalhe": env.detalhe})
        reasons.append(Motivo(env.motivo, f"economia observada indisponível: {env.detalhe or env.motivo}", "bloqueante"))
        next_actions.append("coletar custo, cliques e receita no grão campanha×dia pelo coletor canônico (read-only)")
        if e.receita.valor is not None and e.custo.valor is not None and e.receita.valor.moeda != e.custo.valor.moeda:
            next_actions.append("obter câmbio datado (PTAX) ou moeda observada no payload da fonte")
        sem_historico = e.custo.valor is None and e.receita.valor is None and e.cliques.valor is None
        if sem_historico and teto_ok is not None and e.cpc_intervalo is not None and e.rpc_intervalo is not None:
            reasons.append(Motivo("campanha_nova_sem_historico", "sem custo/receita observados; só CPC e RPC de pesquisa (nunca autorizam verba) e tolerância do owner", "aviso"))
            assumptions.append("cpc_rpc_de_pesquisa_sao_hipotese_nao_observacao")
            next_actions.append("preparar campanha PAUSADA com o teto; ativação é decisão humana")
            return _resultado(Veredito.TEST_WITH_CAP, Confianca.LOW, Recomendacao.PREPARAR_CAMPANHA_PAUSADA,
                              break_even_cpc=teto_ok.rpc_conservador, conservative_affordable_cpc=teto_ok.rpc_conservador,
                              max_experiment_spend=teto_ok.spend_cap, max_experiment_clicks=teto_ok.click_cap,
                              max_experiment_days=teto_ok.day_cap, stop_loss=teto_ok.perda_maxima, maturity_wait=teto_ok.maturity_wait_dias,
                              max_loss=teto_ok.perda_maxima, spend_cap=teto_ok.spend_cap)
        if sem_historico and (e.cpc_intervalo is None or e.rpc_intervalo is None):
            missing.extend(x for x, v in (("cpc_intervalo", e.cpc_intervalo), ("rpc_intervalo", e.rpc_intervalo)) if v is None)
        return _resultado(Veredito.INSUFFICIENT_EVIDENCE, Confianca.INSUFFICIENT, Recomendacao.COLETAR_EVIDENCIA)

    # ---------------- com economia observada
    eco = env.economia
    assumptions.extend(f"{n}={v}" for n, v in env.premissas)
    for lim in env.limitacoes:
        reasons.append(Motivo(lim, "limitação de evidência", "aviso"))
    trace.append({"passo": "envelope", "cpc_micros": str(eco.cpc), "rpc_micros": str(eco.rpc), "rpc_cons_micros": str(env.rpc_conservador),
                  "contribuicao_micros": eco.contribuicao.micros, "contribuicao_cons_micros": env.contribuicao_conservadora.micros,
                  "receita_realizada": env.receita_realizada})
    fr = fronteira(e)
    assert isinstance(fr, Fronteira)
    cs_ = estresse(e)
    cs: list[Cenario] = [] if isinstance(cs_, Indisponivel) else cs_
    trace.append({"passo": "estresse", "cenarios": {c.nome: c.contribuicao.micros for c in cs}})
    sim_json: Optional[dict] = None
    if e.simulacao is not None:
        fm = analisar_simulacao(e.simulacao, env.rpc_conservador, moeda=eco.moeda)
        sim_json = fm.para_json()
        if isinstance(fm, CurvaIndisponivel):
            reasons.append(Motivo(f"simulacao_{fm.motivo}", fm.detalhe or fm.motivo, "aviso"))
            missing.append(f"simulacao_{fm.motivo}")
        else:
            if fm.primeiro_ponto_destrutivo is not None:
                reasons.append(Motivo("expansao_marginal_destrutiva", f"a partir de modificação {fm.primeiro_ponto_destrutivo.modificacao_micros} micros o CPC marginal supera o RPC conservador", "aviso"))
            if fm.ultimo_ponto_sustentavel is not None:
                assumptions.append(f"expansao_aceitavel_ate_modificacao={fm.ultimo_ponto_sustentavel.modificacao_micros}")
        trace.append({"passo": "simulacao", "disponivel": sim_json.get("disponivel")})
    else:
        missing.append("simulacao_ausente")
        next_actions.append("ler campaign_simulation (GAQL, read-only) para a curva de custo marginal")

    comum = dict(
        break_even_cpc=eco.rpc, conservative_affordable_cpc=env.rpc_conservador, observed_cpc=eco.cpc, observed_rpc=eco.rpc,
        observed_rpc_per_visit=eco.rpc_por_visita, observed_rpc_per_visit_unavailable=eco.rpc_por_visita_indisponivel,
        required_rpc=fr.required_rpc, required_rpc_multiplier=fr.required_rpc_multiplier,
        contribution_observed=eco.contribuicao, contribution_conservative=env.contribuicao_conservadora,
        stress=tuple(_cenarios_json(cs)), simulacao=sim_json,
    )
    if eco.cliques >= MIN_CLIQUES_MADUROS and e.janela.dias_maduros >= MIN_DIAS_MADUROS:
        comum["break_even_interval"] = {"contribuicao_por_clique_micros": {"conservadora": str(env.rpc_conservador - env.cpc_conservador),
                                                                           "central": str(eco.rpc - eco.cpc), "otimista": str(env.rpc_otimista - eco.cpc)},
                                        "nota": "intervalo por premissas declaradas; não é probabilidade"}
    perda_liq_obs = Dinheiro(max(0, -eco.contribuicao.micros), eco.moeda)
    perda_liq_cons = env.perda_liquida_conservadora()
    comum.update(net_loss_observed=perda_liq_obs, net_loss_conservative=perda_liq_cons)
    if teto_ok is not None:
        comum.update(max_experiment_spend=teto_ok.spend_cap, max_experiment_clicks=teto_ok.click_cap,
                     max_experiment_days=teto_ok.day_cap, stop_loss=teto_ok.perda_maxima, maturity_wait=teto_ok.maturity_wait_dias,
                     max_loss=teto_ok.perda_maxima, spend_cap=teto_ok.spend_cap)

    gov = _governanca(e)
    for item in gov.evidencia_fraca:
        if not item.startswith("receita_"):   # receita não realizada já entra pelas limitações do envelope
            reasons.append(Motivo(item, "evidência projetada/estimada/imatura não decide viabilidade", "aviso"))
    for nome in gov.stale:
        obs = getattr(getattr(e, nome), "observado_em")
        reasons.append(Motivo("stale", f"{nome}: observado_em {obs.isoformat()} anterior a as_of − {gov.freshness_sla_dias} d", "bloqueante"))
        missing.append(f"{nome}_fresco")
    for item in gov.invalidas:
        reasons.append(Motivo("invalid_flag", item, "bloqueante"))
        invalid.append(item)
    if not gov.cobertura_completa:
        reasons.append(Motivo("cobertura_receita_incompleta", f"cobertura_receita_ppm={gov.cobertura_receita_ppm} (completa = {COBERTURA_COMPLETA_PPM}; None = desconhecida)", "aviso"))
        missing.append("cobertura_receita_completa")
    if gov.dias_custo_sem_receita > 0:
        reasons.append(Motivo(f"dias_custo_sem_receita={gov.dias_custo_sem_receita}", "dias com custo observado e sem receita correspondente na janela", "aviso"))
    trace.append({"passo": "governanca", "evidencia_fraca": list(gov.evidencia_fraca), "stale": list(gov.stale), "invalidas": list(gov.invalidas),
                  "cobertura_receita_ppm": gov.cobertura_receita_ppm, "dias_custo_sem_receita": gov.dias_custo_sem_receita, "freshness_sla_dias": gov.freshness_sla_dias})

    conf = _confianca(env, e, gov)
    imatura = eco.receita_evidencia is Evidencia.IMMATURE or e.janela.dias_maduros < MIN_DIAS_MADUROS
    if imatura:
        espera = max(MIN_DIAS_MADUROS, MATURITY_WAIT_DIAS - e.janela.dias_maduros)
        reasons.append(Motivo("receita_imatura", f"{e.janela.dias_maduros} dia(s) maduro(s); mínimo {MIN_DIAS_MADUROS}", "bloqueante"))
        missing.append("dias_maduros")
        next_actions.append("aguardar releituras D-1 (D-7..D-1) antes de decidir")
        comum.update(max_experiment_spend=None, max_experiment_clicks=None, max_experiment_days=None, stop_loss=None, maturity_wait=espera)
        return _resultado(Veredito.INSUFFICIENT_EVIDENCE, Confianca.INSUFFICIENT, Recomendacao.AGUARDAR_MATURACAO, **comum)

    # medidas inválidas ou velhas: nenhum veredito (nem rejeição) nasce delas
    if gov.invalidas or gov.stale:
        next_actions.append("recoletar as medidas marcadas (invalid/stale) pelo coletor canônico antes de decidir")
        comum.update(max_experiment_spend=None, max_experiment_clicks=None, max_experiment_days=None)
        return _resultado(Veredito.INSUFFICIENT_EVIDENCE, Confianca.INSUFFICIENT, Recomendacao.COLETAR_EVIDENCIA, **comum)

    realizada = env.receita_realizada and not gov.evidencia_fraca   # custo/cliques projetados ou estimados também não realizam
    moeda_custo_ev = e.custo.moeda_evidencia
    moeda_provada = (eco.moeda_evidencia is Evidencia.OBSERVED and moeda_custo_ev is Evidencia.OBSERVED
                     and eco.cambio_evidencia in (None, Evidencia.OBSERVED))
    if moeda_custo_ev is not Evidencia.OBSERVED:
        reasons.append(Motivo(f"moeda_custo_{moeda_custo_ev.value}", "moeda do custo não observada na fonte", "aviso"))
    poucos = eco.cliques < MIN_CLIQUES_MADUROS
    forte = eco.cliques >= CLIQUES_CONFIANCA_ALTA and e.janela.dias_maduros >= DIAS_CONFIANCA_ALTA
    if poucos:
        reasons.append(Motivo("poucos_cliques", f"{eco.cliques} cliques < {MIN_CLIQUES_MADUROS}", "aviso"))
        missing.append("cliques_minimos")

    todos_negativos = all(c.contribuicao.micros < 0 for c in cs)
    if not realizada:
        reasons.append(Motivo(f"receita_{eco.receita_evidencia.value}", "receita não realizada não decide viabilidade", "aviso"))
        missing.append("receita_realizada")

    # 1) inviável sob estresse (só com receita realizada e volume mínimo)
    if todos_negativos and realizada and not poucos:
        reasons.append(Motivo("inviavel_sob_estresse", "inviável sob os cenários declarados: nem receita×2, câmbio×1,5 e maturação×1,3 levam a contribuição >= 0", "bloqueante"))
        next_actions.append("comparar RPC JoinAds por país/ad unit e CPC de pesquisa da vertical antes de qualquer nova campanha")
        comum.update(max_experiment_spend=None, max_experiment_clicks=None, max_experiment_days=None)
        c2 = Confianca.HIGH if (moeda_provada and conf is Confianca.HIGH) else (Confianca.MEDIUM if conf.ordem() >= 2 else Confianca.MEDIUM)
        return _resultado(Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS, c2, Recomendacao.REJEITAR_TESE_ECONOMICA, **comum)

    # 2) stop-loss: a perda LÍQUIDA madura (custo − receita comparável) já excede a tolerância do owner.
    #    O gasto bruto nunca é comparado com a tolerância. A perda líquida sob as premissas conservadoras
    #    (custo_cons − receita_cons) acima da tolerância é aviso, não parada: ainda não aconteceu.
    if teto_ok is not None and realizada and perda_liq_obs.micros > teto_ok.perda_maxima.micros:
        reasons.append(Motivo("stop_loss", f"perda líquida madura {perda_liq_obs.micros} micros > tolerância {teto_ok.perda_maxima.micros} micros", "bloqueante"))
        return _resultado(Veredito.TEST_WITH_CAP if not todos_negativos else Veredito.UNVIABLE_UNDER_DECLARED_SCENARIOS, conf, Recomendacao.PARAR_POR_STOP_LOSS, **comum)
    if teto_ok is not None and realizada and perda_liq_cons.micros > teto_ok.perda_maxima.micros:
        reasons.append(Motivo("perda_conservadora_acima_da_tolerancia", f"perda líquida conservadora {perda_liq_cons.micros} micros > tolerância {teto_ok.perda_maxima.micros} micros (ainda não realizada)", "aviso"))

    # 3) lucrativa com evidência forte e governança limpa: já lucrativa (volume e maturação altos) ou candidata viável
    positivo_permitido = realizada and moeda_provada and not poucos and not gov.bloqueia_positivo()
    if env.contribuicao_conservadora.micros >= 0 and positivo_permitido:
        reasons.append(Motivo("contribuicao_conservadora_positiva", "receita conservadora cobre o custo conservador", "info"))
        next_actions.append("ler campaign_simulation antes de qualquer expansão; expandir só até o último ponto sustentável")
        if forte:
            return _resultado(Veredito.ALREADY_PROFITABLE, conf, Recomendacao.CONTINUAR_CAMPANHA_EXISTENTE, **comum)
        reasons.append(Motivo("volume_ou_maturacao_abaixo_do_limiar_alto", f"{eco.cliques} cliques / {e.janela.dias_maduros} dia(s) maduro(s); already_profitable exige >= {CLIQUES_CONFIANCA_ALTA} e >= {DIAS_CONFIANCA_ALTA}", "aviso"))
        next_actions.append("manter a coleta até >= 500 cliques e >= 7 dias maduros para promover a candidata")
        return _resultado(Veredito.VIABLE_CANDIDATE, _menor(conf, Confianca.MEDIUM), Recomendacao.PROPOR_TESTE_LIMITADO, **comum)

    # 4) favorável mas evidência fraca (moeda atestada, câmbio estimado, poucos cliques, não realizada, cobertura incompleta)
    if env.contribuicao_conservadora.micros >= 0:
        if not moeda_provada:
            next_actions.append("obter moeda observada no payload e câmbio PTAX datado para promover a evidência")
        if teto_ok is None:
            return _resultado(Veredito.INSUFFICIENT_EVIDENCE, Confianca.INSUFFICIENT, Recomendacao.COLETAR_EVIDENCIA, **comum)
        return _resultado(Veredito.TEST_WITH_CAP, Confianca.LOW if not realizada or poucos else Confianca.MEDIUM,
                          Recomendacao.PROPOR_TESTE_LIMITADO, **comum)

    # 5) contribuição conservadora negativa mas algum cenário favorável (perto do equilíbrio)
    reasons.append(Motivo("perto_do_equilibrio", "contribuição conservadora negativa; algum cenário de estresse favorável é >= 0", "aviso"))
    next_actions.append("replay pós-cutover com moeda original e PTAX antes de ampliar")
    if teto_ok is None:
        return _resultado(Veredito.INSUFFICIENT_EVIDENCE, Confianca.INSUFFICIENT, Recomendacao.COLETAR_EVIDENCIA, **comum)
    return _resultado(Veredito.TEST_WITH_CAP, Confianca.LOW if (poucos or not realizada) else Confianca.MEDIUM, Recomendacao.PROPOR_TESTE_LIMITADO, **comum)
