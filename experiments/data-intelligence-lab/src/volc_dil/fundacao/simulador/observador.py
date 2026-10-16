"""Processo de OBSERVAÇÃO: o que cada fonte entregaria do mundo verdadeiro, e QUANDO.

Separação essencial: o mundo (``mundo.py``) sabe a verdade; o observador decide o que cada
fonte devolve em cada coleta agendada — com atraso, parcialidade intradiária, estimativa que
muda até fechar, restatement, quantização, falhas, ausência, dimensão não suportada, payload
inválido, troca silenciosa de chave, duplicação, coleta atrasada, run preso em ``running`` e
(cenários adversariais) zero falso, zero sintetizado, carimbo retrodatado, campanha descartada
pelo sensor, dedup por segundo e o gatilho legado da JoinAds. Cadências e atrasos default
espelham a FORMA documentada das fontes reais (``calibracao.py``); os números são parâmetros.

Fontes simuladas (contas sintéticas):

- ``google_ads`` — custo (micros BRL), cliques e impressões por campanha × dia. D0 em passadas
  intradiárias (``partial``, inclui cliques inválidos ainda não creditados), D-1 (preliminar,
  parte do crédito aplicada) e backfill em D+n (final = custo faturado verdadeiro).
- ``joinads`` — receita (micros, moeda da campanha, 2 casas) e pageviews por
  ``custom_key=utm_campaign`` × dia. Intradiária estimada, releituras D-1..D-n com estimativa
  que converge; a última releitura fecha no valor verdadeiro quantizado.
- ``site_analytics`` — sessões (inclui bots), pageviews do sensor e chegadas ao destino, D-1.
- ``legado_daily_metrics`` (só com ``emitir_legado_daily_metrics``) — o que o gatilho legado
  JoinAds→``daily_campaign_metrics`` deixa na tabela: receita do ÚLTIMO domínio processado e
  custo 0 na linha recém-criada até a sincronização de custo (R5).

Além dos registros, o observador devolve o livro de execuções (``Leituras.execucoes``): um run
por coleta, com status ``completed``/``failed``/``running`` (preso, sem reaper).

Determinismo: todo sorteio do observador vem de fluxos nomeados (``rng_nomeado``) com forma
fixa (contas × dias × slots ou campanhas × dias × slots), então a mesma (mundo, parâmetros,
seed) produz os mesmos registros byte a byte, e a ordem final é por relógio de conhecimento.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import numpy as np
from scipy import stats

from volc_dil.contracts.fingerprint import json_canonico

from .mundo import Mundo, id_campanha, rng_nomeado
from .parametros import ParametrosObservador
from .registro import Gabarito, RegistroObservacao

UTC = timezone.utc
GRAO_CAMPANHA_DIA = ("campaign", "day")
GRAO_POST_DIA = ("day", "url")
GRAO_CONTA_DIA = ("account", "day")
GRAO_CONTA_DIA_DISP = ("account", "day", "device")
DIM_SENSOR_SEM_CAMPANHA = (("utm_medium", "cpc"), ("utm_source", "google"), ("utm_term", "*"))
MOTIVOS_INVALIDO = ("payload inválido: JSON truncado", "payload inválido: custo negativo",
                    "payload inválido: tipo string em campo numérico", "payload inválido: data fora da janela pedida")


def iso(dt: datetime) -> str:
    """Instante canônico: UTC, resolução de segundo, formato fixo (ordenável como texto)."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _sha(obj: object) -> str:
    return hashlib.sha256(json_canonico(obj).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Slot:
    fonte: str
    tipo: str          # intradia | d1 | releitura | backfill
    desloc_dias: int   # dia da leitura = dia de referência + desloc
    hora: int          # hora local agendada
    corte_h: int       # horas do dia de referência cobertas ([0, corte))
    final: bool
    maturidade: str
    idade_h: float     # horas entre o fim da janela e a leitura (negativo se intradiária)
    minuto: int = 0


@dataclass(frozen=True)
class _Alvo:
    """Quem a linha descreve: campanha real, campanha listada sem métrica ou agregado do sensor."""

    id: Optional[str]
    conta: str
    moeda_receita: str
    idx: int = -1


def slots(po: ParametrosObservador) -> dict[str, list[Slot]]:
    g = [Slot("google_ads", "intradia", 0, h, max(0, h - po.gads_lag_d0_h), False, "intradiaria", h - 24.0)
         for h in po.gads_horas_d0]
    g.append(Slot("google_ads", "d1", 1, po.gads_d1_hora, 24, False, "preliminar", float(po.gads_d1_hora)))
    g.append(Slot("google_ads", "backfill", po.gads_backfill_dias, po.gads_backfill_hora, 24, True, "final",
                  24.0 * (po.gads_backfill_dias - 1) + po.gads_backfill_hora))
    j = [Slot("joinads", "intradia", 0, h, max(0, h - po.join_lag_intradia_h), False, "intradiaria", h - 24.0)
         for h in po.join_horas_intradia]
    for r in range(1, po.join_releituras + 1):
        fim = r == po.join_releituras
        j.append(Slot("joinads", "d1" if r == 1 else "releitura", r, po.join_d1_hora, 24, fim,
                      "final" if fim else "preliminar", 24.0 * (r - 1) + po.join_d1_hora))
    s = [Slot("site_analytics", "d1", 1, po.site_d1_hora, 24, True, "final", float(po.site_d1_hora))]
    out = {"google_ads": g, "joinads": j, "site_analytics": s}
    if po.emitir_legado_daily_metrics:
        out["legado_daily_metrics"] = [Slot("legado_daily_metrics", x.tipo, x.desloc_dias, x.hora, x.corte_h, x.final,
                                            x.maturidade, x.idade_h, po.legado_atraso_min) for x in j]
    return out


@dataclass
class Leituras:
    """Saída do observador: registros (o que consumidores veem), gabarito (só avaliação) e runs."""

    registros: list[RegistroObservacao]
    gabarito: dict[str, Gabarito]
    execucoes: list[dict]

    def contagem_status(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.registros:
            out[r.status] = out.get(r.status, 0) + 1
        return dict(sorted(out.items()))

    def com_armadilha(self, nome: str) -> list[RegistroObservacao]:
        return [r for r in self.registros if nome in self.gabarito[r.obs_id].armadilhas]


class _Fluxos:
    """Uniformes por fonte com forma fixa: (contas|campanhas, dias, slots)."""

    def __init__(self, seed: int, fonte: str, n_contas: int, C: int, D: int, S: int):
        def u(nome: str, n: int) -> np.ndarray:
            return rng_nomeado(seed, f"obs:{fonte}:{nome}").random((n, D, S))
        self.exec_falha = u("exec_falha", n_contas)
        self.presa = u("presa", n_contas)
        self.atraso = u("atraso", n_contas)
        self.atraso_h = u("atraso_h", n_contas)
        self.duracao = u("duracao", n_contas)
        self.ingestao = u("ingestao", n_contas)
        self.retro = u("retro", n_contas)
        self.ausente = u("ausente", C)
        self.invalido = u("invalido", C)
        self.motivo = u("motivo", C)
        self.zero_falso = u("zero_falso", C)
        self.dup = u("dup", C)
        self.dup_lag = u("dup_lag", C)
        self.recup = u("recup", C)
        self.troca = u("troca", C)
        self.troca_val = u("troca_val", C)
        self.post = u("post", C)
        self.preservada = u("preservada", C)
        self.colisao_h = u("colisao_h", C)
        self.colisao_b = u("colisao_b", C)
        self.z = rng_nomeado(seed, f"obs:{fonte}:estimativa").standard_normal((C, D, S))


def observar(mundo: Mundo, po: ParametrosObservador, *, cenario: str = "ad_hoc") -> Leituras:
    """Emite os registros de todas as coletas agendadas para todos os dias do mundo.

    Coletas que caem depois do fim do período também são emitidas (o mundo inteiro acaba
    observado); o consumidor corta por ``available_at`` (nunca por ``observed_at``)."""
    return _Emissor(mundo, po, cenario).executar()


class _Emissor:
    def __init__(self, mundo: Mundo, po: ParametrosObservador, cenario: str):
        self.m = mundo
        self.po = po
        self.cenario = cenario
        self.tz = mundo.params.timezone
        C, D = mundo.C, mundo.D
        self.slots = slots(po)
        self.fluxos = {f: _Fluxos(mundo.seed, f, mundo.params.n_contas, C, D, len(s))
                       for f, s in self.slots.items()}
        self._brutos: list[tuple[tuple, dict, dict]] = []
        self._runs: dict[str, dict] = {}
        cum = lambda nome: np.cumsum(mundo.por_dia_hora(nome), axis=2)  # noqa: E731
        self.cum = {k: cum(k) for k in ("custo_bruto_micros", "cliques", "impressoes", "receita_micros", "pageviews")}
        self.dia = {k: mundo.diario(k) for k in ("custo_bruto_micros", "credito_micros", "custo_final_micros",
                                                   "cliques", "cliques_invalidos", "cliques_bot_detectados",
                                                   "impressoes", "receita_micros", "pageviews", "pageviews_bot",
                                                   "sessoes", "sessoes_bot", "destino")}
        self.cliques_credito = self.dia["cliques_invalidos"] + self.dia["cliques_bot_detectados"]
        self.existe_dia = mundo.existe_dia()
        self.inicio_h = np.array([c.inicio_h for c in mundo.campanhas])
        contas = sorted({c.conta for c in mundo.campanhas})
        self.contas = contas
        self.por_conta = {k: [c for c in mundo.campanhas if c.conta == k] for k in contas}
        rec = self.dia["receita_micros"]
        self.receita_media_conta = {k: float(np.mean([rec[c.idx][self.existe_dia[c.idx]].mean()
                                                      if self.existe_dia[c.idx].any() else 0.0
                                                      for c in self.por_conta[k]]))
                                    for k in contas}
        # R3: campanhas listadas na conta sem nenhuma linha de métrica (ids fora do intervalo real)
        self.sem_metrica: dict[str, list[_Alvo]] = {}
        base = C
        for k in contas:
            n = int(round(po.gads_razao_campanhas_sem_metrica * len(self.por_conta[k])))
            self.sem_metrica[k] = [_Alvo(id_campanha(base + j), k, mundo.params.moeda_receita) for j in range(n)]
            base += n
        # R5: partilha da receita por domínio JoinAds (o gatilho legado guarda só o último)
        nd = max(1, po.legado_dominios_por_campanha)
        self.share_ultimo_dominio = rng_nomeado(mundo.seed, "obs:legado:dominios").dirichlet(np.full(nd, 2.0), C)[:, -1]
        self._cache_inst: dict[tuple[int, float], datetime] = {}
        self.janelas_fora = [(j.fonte, self.inst(int(np.floor(j.inicio_frac_periodo * D + 1e-9)), j.hora_local),
                              j.duracao_h) for j in po.janelas_fora_do_ar]

    # ── utilidades ───────────────────────────────────────────────────────
    def inst(self, dia_idx: int, hora: float) -> datetime:
        k = (dia_idx, hora)
        v = self._cache_inst.get(k)
        if v is None:
            v = self.m.instante_local(dia_idx, hora).astimezone(UTC)
            self._cache_inst[k] = v
        return v

    def fora_do_ar(self, fonte: str, t: datetime) -> Optional[datetime]:
        for f, ini, dur in self.janelas_fora:
            fim = ini + timedelta(hours=dur)
            if f == fonte and ini <= t < fim:
                return fim
        return None

    def _quant(self, x: float) -> int:
        q = self.po.join_quantum_micros
        return int(np.rint(max(x, 0.0) / q)) * q

    def _run(self, run_id: str, **campos) -> None:
        if run_id not in self._runs:
            self._runs[run_id] = dict(run_id=run_id, n_registros=0, **campos)

    # ── laço principal ───────────────────────────────────────────────────
    def executar(self) -> Leituras:
        D = self.m.D
        for fonte, lista in self.slots.items():
            fl = self.fluxos[fonte]
            for ki, conta in enumerate(self.contas):
                for i in range(D):
                    for si, sl in enumerate(lista):
                        self._coleta(fonte, fl, ki, conta, i, si, sl)
                    if fonte == "joinads" and self.po.join_consulta_dispositivo:
                        self._dimensao_nao_suportada(conta, i)
        return self._finalizar()

    def _coleta(self, fonte: str, fl: _Fluxos, ki: int, conta: str, i: int, si: int, sl: Slot) -> None:
        po = self.po
        agendado = self.inst(i + sl.desloc_dias, sl.hora) + timedelta(minutes=sl.minuto)
        dur = timedelta(seconds=int(po.duracao_execucao_s_min
                                    + fl.duracao[ki, i, si] * (po.duracao_execucao_s_max - po.duracao_execucao_s_min)))
        disp_prev = agendado + dur
        fim_fora = self.fora_do_ar(fonte, agendado)
        falhou = fim_fora is not None or fl.exec_falha[ki, i, si] < po.p_execucao_indisponivel
        presa = (not falhou) and fl.presa[ki, i, si] < po.p_execucao_presa
        intradia = sl.tipo == "intradia"
        atrasada = (not intradia) and (not falhou) and (not presa) and fl.atraso[ki, i, si] < po.p_atraso
        disponivel = disp_prev
        if atrasada:
            disponivel = disp_prev + timedelta(seconds=int(3600 * (po.atraso_min_h + fl.atraso_h[ki, i, si]
                                                                     * (po.atraso_max_h - po.atraso_min_h))))
        ingest = disponivel + timedelta(seconds=int(po.ingestao_lag_s_min + fl.ingestao[ki, i, si]
                                                    * (po.ingestao_lag_s_max - po.ingestao_lag_s_min)))
        janela_ini = self.inst(i, 0)
        janela_fim = self.inst(i + 1, 0)
        retro = (not intradia) and fl.retro[ki, i, si] < po.p_retrodatar
        observado = janela_fim if retro else agendado
        run_id = "run-" + hashlib.sha256(f"{self.m.seed}|{fonte}|{conta}|{sl.tipo}|{iso(agendado)}|ref={i}".encode()).hexdigest()[:16]
        # um run por (fonte, conta, slot, dia de referência): releituras de dias diferentes no mesmo
        # horário são runs distintos (simplificação declarada; a JoinAds real relê 3 dias numa chamada)
        status_run = "failed" if falhou else "running" if presa else "completed"
        self._run(run_id, fonte=fonte, conta=conta, tipo_leitura=sl.tipo, dia_referencia=self.m.dias[i].isoformat(),
                  agendado_em=iso(agendado), concluido_em=None if presa else iso(disponivel), status=status_run,
                  motivo=("fonte fora do ar (HTTP 503)" if fim_fora is not None else "execução da coleta falhou (timeout)")
                  if falhou else ("run preso em running, sem reaper" if presa else None), recuperacao=False)
        ctx = dict(fonte=fonte, conta=conta, i=i, si=si, sl=sl, agendado=agendado, disp_prev=disp_prev,
                   disponivel=disponivel, ingest=ingest, observado=observado, janela_ini=janela_ini,
                   janela_fim=janela_fim, run_id=run_id, falhou=falhou, fim_fora=fim_fora, atrasada=atrasada,
                   retro=retro, presa=presa)
        t_ag_h = i * 24 + sl.desloc_dias * 24 + sl.hora
        agregado_sensor: dict[str, int] = {}
        verdade_sensor: dict[str, int] = {}
        for camp in self.por_conta[conta]:
            c = camp.idx
            if not self.existe_dia[c, i]:
                continue
            if intradia and self.inicio_h[c] >= t_ag_h:
                continue  # campanha ainda não existia no instante da leitura
            if (fonte == "site_analytics" and po.site_descarta_utm_campaign_numerica
                    and fl.preservada[c, i, si] >= po.site_p_campanha_preservada):
                emit, final, _ = self._valores(fonte, sl, c, i, si, fl)
                for k, v in emit.items():
                    agregado_sensor[k] = agregado_sensor.get(k, 0) + v
                    verdade_sensor[k] = verdade_sensor.get(k, 0) + final[k]
                continue
            self._linha(ctx, fl, camp)
        if agregado_sensor and not presa:
            self._linha_sensor_sem_campanha(ctx, conta, agregado_sensor, verdade_sensor)
        if fonte == "google_ads" and not presa:
            for alvo in self.sem_metrica.get(conta, ()):
                self._linha_sem_metrica(ctx, alvo)

    # ── valores verdadeiros por fonte/slot ───────────────────────────────
    def _valores(self, fonte: str, sl: Slot, c: int, i: int, si: int, fl: _Fluxos) -> tuple[dict, dict, dict]:
        """(emitido, verdade_final, verdade_cobertura) por métrica."""
        k = sl.corte_h

        def acum(nome: str) -> int:
            return int(self.cum[nome][c, i, k - 1]) if k >= 1 else 0

        d = self.dia
        po = self.po
        if fonte == "google_ads":
            final = {"cost": int(d["custo_final_micros"][c, i]),
                     "clicks": int(d["cliques"][c, i] - self.cliques_credito[c, i]),
                     "impressions": int(d["impressoes"][c, i])}
            if sl.tipo == "intradia":
                emit = {"cost": acum("custo_bruto_micros"), "clicks": acum("cliques"), "impressions": acum("impressoes")}
                cob = dict(emit)
            elif sl.final:
                emit, cob = dict(final), dict(final)
            else:
                f = po.gads_frac_credito_d1
                emit = {"cost": int(d["custo_bruto_micros"][c, i] - round(f * int(d["credito_micros"][c, i]))),
                        "clicks": int(d["cliques"][c, i] - round(f * int(self.cliques_credito[c, i]))),
                        "impressions": int(d["impressoes"][c, i])}
                cob = dict(final)
            return emit, final, cob
        if fonte == "joinads":
            rf = int(d["receita_micros"][c, i])
            final = {"revenue": rf, "pageviews": int(d["pageviews"][c, i])}
            z = float(fl.z[c, i, si])
            if sl.tipo == "intradia":
                parcial = acum("receita_micros")
                s = po.join_sigma_estimativa
                emit = {"revenue": self._quant(parcial * po.join_f0 * np.exp(s * z - 0.5 * s * s)),
                        "pageviews": acum("pageviews")}
                cob = {"revenue": parcial, "pageviews": acum("pageviews")}
            elif sl.final:
                emit = {"revenue": self._quant(rf), "pageviews": final["pageviews"]}
                cob = dict(final)
            else:
                f = 1 - (1 - po.join_f0) * np.exp(-max(sl.idade_h, 0.0) / po.join_tau_maturacao_h)
                s = po.join_sigma_estimativa * (1 - f) / (1 - po.join_f0)
                emit = {"revenue": self._quant(rf * f * np.exp(s * z - 0.5 * s * s)), "pageviews": final["pageviews"]}
                cob = dict(final)
            return emit, final, cob
        if fonte == "legado_daily_metrics":
            jsl = self.slots["joinads"][si]
            jemit, jfinal, _ = self._valores("joinads", jsl, c, i, si, self.fluxos["joinads"])
            rev = self._quant(jemit["revenue"] * float(self.share_ultimo_dominio[c]))
            sync = self.inst(i + 1, po.gads_d1_hora) + timedelta(hours=1)
            agendado = self.inst(i + jsl.desloc_dias, jsl.hora) + timedelta(minutes=po.legado_atraso_min)
            if agendado < sync:
                custo = 0
            else:
                gsl = next(s for s in self.slots["google_ads"] if s.tipo == "d1")
                custo = self._valores("google_ads", gsl, c, i, 0, self.fluxos["google_ads"])[0]["cost"]
            final = {"revenue": jfinal["revenue"], "cost": int(d["custo_final_micros"][c, i])}
            return {"revenue": rev, "cost": custo}, final, dict(final)
        pv = int(d["pageviews"][c, i])
        final = {"sessions": int(d["sessoes"][c, i]), "pageviews": pv, "destino": int(d["destino"][c, i])}
        emit = dict(final)
        if po.site_dedup_por_segundo:
            pvb, sb = int(d["pageviews_bot"][c, i]), int(d["sessoes_bot"][c, i])
            ext_h = max(0, (pv - pvb) - (final["sessions"] - sb))
            ext_b = max(0, pvb - sb)
            col = 0
            if ext_h:
                col += int(stats.binom.ppf(fl.colisao_h[c, i, si], ext_h, po.site_p_colisao_humano))
            if ext_b:
                col += int(stats.binom.ppf(fl.colisao_b[c, i, si], ext_b, po.site_p_colisao_bot))
            emit["pageviews"] = pv - col
        return emit, final, dict(final)

    # ── uma linha (campanha) de uma coleta ───────────────────────────────
    def _linha(self, ctx: dict, fl: _Fluxos, camp) -> None:
        po = self.po
        fonte, sl, i, si = ctx["fonte"], ctx["sl"], ctx["i"], ctx["si"]
        c = camp.idx
        emit, final, cob = self._valores(fonte, sl, c, i, si, fl)
        intradia = sl.tipo == "intradia"
        armadilhas: list[str] = []
        entidade, entidade_tipo, grao = camp.id, "campaign", GRAO_CAMPANHA_DIA
        ck_sol = ck_ef = "utm_campaign" if fonte == "joinads" else None
        motivo: Optional[str] = None
        valores: dict[str, Optional[int]] = dict(emit)
        if ctx["presa"]:
            status = "running"  # nada é entregue; só decide a recuperação abaixo
        elif ctx["falhou"]:
            status = "unavailable"
            motivo = ("fonte fora do ar (HTTP 503)" if ctx["fim_fora"] is not None
                      else "execução da coleta falhou (timeout)")
            valores = {m: None for m in emit}
        elif fl.ausente[c, i, si] < po.p_ausente:
            status, motivo = "missing", "linha da entidade ausente no payload"
            valores = {m: None for m in emit}
        elif fl.invalido[c, i, si] < po.p_payload_invalido:
            status = "invalid"
            motivo = MOTIVOS_INVALIDO[int(fl.motivo[c, i, si] * len(MOTIVOS_INVALIDO))]
            valores = {m: None for m in emit}
        else:
            status = "partial" if intradia else ("late" if ctx["atrasada"] else "observed")
        # JoinAds troca a custom_key calada quando não há dado (forma documentada da API real)
        if fonte == "joinads" and status in ("observed", "partial", "late"):
            sem_dado = cob["revenue"] == 0
            p_troca = po.join_p_troca_chave_sem_dado if sem_dado else po.join_p_troca_chave_com_dado
            if fl.troca[c, i, si] < p_troca:
                entidade_tipo, grao, ck_ef = "post", GRAO_POST_DIA, "id_post_wp"
                if po.join_ids_post_colidem and self.m.C > 1:
                    outro = (c + 1 + int(fl.post[c, i, si] * (self.m.C - 1))) % self.m.C
                    entidade = id_campanha(outro)
                    armadilhas.append("id_colide_com_campanha")
                else:
                    entidade = f"wp-{1000 + int(fl.post[c, i, si] * 9000)}"
                frac = (sl.corte_h / 24.0) if intradia else 1.0
                base = max(self.receita_media_conta[camp.conta], 1e6) * frac
                rv = self._quant(base * (0.2 + 0.8 * fl.troca_val[c, i, si]))
                valores = {"revenue": rv, "pageviews": int(rv // 50_000)}
                armadilhas.append("custom_key_trocada")
        # R3: o coletor VOLC grava 0 para campanha sem linha de métrica → zero indistinguível do confirmado
        if fonte == "google_ads" and po.gads_zero_sintetizado and status == "missing":
            status = "partial" if intradia else "observed"
            motivo = None
            valores = {m: 0 for m in emit}
            armadilhas.append("zero_sintetizado")
        # zero falso: a fonte devolve 0 onde não há dado (forma do Google Ads MCP 0.0.4)
        if status in ("missing", "unavailable") and fl.zero_falso[c, i, si] < po.p_zero_falso:
            status = "partial" if intradia else "observed"
            motivo = None
            valores = {m: 0 for m in emit}
            armadilhas.append("zero_falso")
        if fonte == "legado_daily_metrics" and status in ("observed", "partial", "late"):
            armadilhas.append("ultimo_dominio_vence")
        recuperar = sl.final and status in ("missing", "unavailable", "invalid", "running")
        if ctx["retro"]:
            armadilhas.append("retrodatado")
        if ctx["atrasada"]:
            armadilhas.append("coleta_atrasada")
        if status != "running":
            self._registros_da_linha(ctx, camp, entidade, entidade_tipo, grao, ck_sol, ck_ef, valores, status, motivo,
                                     final, cob, armadilhas, fl.dup[c, i, si] < po.p_duplicata, fl.dup_lag[c, i, si])
        if recuperar:
            base_t = ctx["fim_fora"] if ctx["fim_fora"] is not None else ctx["agendado"]
            t_rec = base_t + timedelta(seconds=int(3600 * (1 + po.atraso_min_h + fl.recup[c, i, si]
                                                             * (po.atraso_max_h - po.atraso_min_h))))
            disp = t_rec + timedelta(seconds=120)
            rid = "run-" + hashlib.sha256(f"{ctx['run_id']}|recuperacao|{camp.id}".encode()).hexdigest()[:16]
            self._run(rid, fonte=fonte, conta=camp.conta, tipo_leitura=sl.tipo,
                      dia_referencia=self.m.dias[i].isoformat(), agendado_em=iso(t_rec), concluido_em=iso(disp),
                      status="completed", motivo="recuperação após falha da leitura final", recuperacao=True)
            rctx = dict(ctx, agendado=t_rec, disponivel=disp, ingest=disp + timedelta(seconds=60),
                        observado=t_rec, retro=False, atrasada=True, run_id=rid)
            rem, _, _ = self._valores(fonte, sl, c, i, si, fl)
            arm_rec = ["recuperacao_tardia"] + (["ultimo_dominio_vence"] if fonte == "legado_daily_metrics" else [])
            self._registros_da_linha(rctx, camp, camp.id, "campaign", GRAO_CAMPANHA_DIA, ck_sol, ck_sol, rem,
                                     "late", "recuperação após falha da leitura final", final, cob, arm_rec, False, 0.0)

    def _linha_sensor_sem_campanha(self, ctx: dict, conta: str, valores: dict, verdade: dict) -> None:
        """R2: sessões pagas chegam com source/medium/term mas sem utm_campaign (numérico anulado)."""
        alvo = _Alvo(None, conta, self.m.params.moeda_receita)
        status = "late" if ctx["atrasada"] else "observed"
        motivo = None
        if ctx["falhou"]:
            status, motivo = "unavailable", "fonte fora do ar (HTTP 503)" if ctx["fim_fora"] else "execução da coleta falhou (timeout)"
            valores = {k: None for k in valores}
        arm = ["campanha_descartada_sensor"] + (["coleta_atrasada"] if ctx["atrasada"] else [])
        self._registros_da_linha(ctx, alvo, "google/cpc", "utm_source_medium", GRAO_CONTA_DIA, None, None, dict(valores),
                                 status, motivo, dict(verdade), dict(verdade), arm, False, 0.0,
                                 dimensoes=DIM_SENSOR_SEM_CAMPANHA)

    def _linha_sem_metrica(self, ctx: dict, alvo: _Alvo) -> None:
        """R3: campanha listada sem linha de métrica; o coletor grava 0 como se fosse medido."""
        if ctx["falhou"]:
            return
        intradia = ctx["sl"].tipo == "intradia"
        valores = {"cost": 0, "clicks": 0, "impressions": 0}
        vazio = {"cost": None, "clicks": None, "impressions": None}
        status = "partial" if intradia else ("late" if ctx["atrasada"] else "observed")
        self._registros_da_linha(ctx, alvo, alvo.id, "campaign", GRAO_CAMPANHA_DIA, None, None, valores, status, None,
                                 vazio, vazio, ["zero_sintetizado", "campanha_sem_linha"], False, 0.0)

    def _registros_da_linha(self, ctx, camp, entidade, entidade_tipo, grao, ck_sol, ck_ef, valores, status, motivo,
                            final, cob, armadilhas, dup, dup_lag, dimensoes=()) -> None:
        fonte, sl = ctx["fonte"], ctx["sl"]
        ja_ini, ja_fim = iso(ctx["janela_ini"]), iso(ctx["janela_fim"])
        cobertura_ate = iso(self.inst(ctx["i"], sl.corte_h)) if sl.tipo == "intradia" else ja_fim
        if status == "unavailable":
            payload = {"run_id": ctx["run_id"], "erro": motivo}
        elif status == "missing":
            payload = {"run_id": ctx["run_id"], "ausente": entidade}
        elif status == "invalid":
            payload = {"run_id": ctx["run_id"], "bruto_corrompido": f"{entidade}:{motivo}"}
        else:
            payload = {"run_id": ctx["run_id"], "fonte": fonte, "conta": camp.conta, "entidade": entidade,
                       "custom_key": ck_ef, "janela": [ja_ini, ja_fim], "metricas": valores,
                       "dimensoes": [list(x) for x in dimensoes]}
        psha = _sha(payload)
        disfarcado = {"zero_falso", "zero_sintetizado"} & set(armadilhas)
        for metrica, valor in valores.items():
            monet = metrica in ("cost", "revenue")
            moeda = (self.m.params.moeda_custo if metrica == "cost" else camp.moeda_receita) if monet else None
            st = status
            if valor == 0 and st in ("observed", "late") and (not disfarcado or "zero_sintetizado" in armadilhas):
                st = "zero_confirmed"  # R3: o zero sintetizado sai idêntico ao confirmado
            arm = list(armadilhas)
            if monet and moeda != "BRL":
                arm.append("moeda_nao_brl")
            if fonte == "legado_daily_metrics" and metrica == "cost" and valor == 0 and final.get("cost"):
                arm.append("custo_zero_inserido")
            leitura_id = hashlib.sha256(f"{ctx['run_id']}|{entidade}|{metrica}|{ja_ini}".encode()).hexdigest()[:20]
            vf = final.get(metrica)
            if (self.po.site_dedup_por_segundo and fonte == "site_analytics" and metrica == "pageviews" and valor is not None and vf is not None and valor < vf and "zero_falso" not in arm):
                arm.append("dedup_por_segundo")
            rest = (valor - vf) if (valor is not None and vf is not None and metrica in ("cost", "clicks")
                                    and fonte == "google_ads" and sl.tipo != "intradia") else None
            campos = dict(
                fonte=fonte, conta=camp.conta, entidade=entidade, grao=grao, metrica=metrica, valor=valor, moeda=moeda,
                janela_inicio=ja_ini, janela_fim=ja_fim, timezone=self.tz, observed_at=iso(ctx["observado"]),
                available_at=iso(ctx["disponivel"]), ingested_at=iso(ctx["ingest"]), run_id=ctx["run_id"],
                payload_sha256=psha, status=st, motivo=motivo, leitura_id=leitura_id,
                unidade="micros" if monet else "contagem", tipo_leitura=sl.tipo, maturidade=sl.maturidade,
                cobertura_ate=cobertura_ate, entidade_tipo=entidade_tipo, custom_key_solicitada=ck_sol,
                custom_key_efetiva=ck_ef, dimensoes=tuple(dimensoes),
                available_previsto=iso(ctx["disp_prev"]) if ctx["atrasada"] and st in ("late", "zero_confirmed") else None,
                cenario=self.cenario)
            gab = dict(campanha_pedida=camp.id, valor_verdade_final=vf, valor_verdade_cobertura=cob.get(metrica),
                       restatement_pendente=rest, armadilhas=tuple(arm))
            chave = (campos["available_at"], campos["ingested_at"], fonte, camp.conta, entidade, metrica, ja_ini, sl.tipo)
            self._brutos.append((chave + (0,), campos, gab))
            self._runs[ctx["run_id"]]["n_registros"] += 1
            if dup:
                lag = timedelta(seconds=int(60 + dup_lag * 7140))
                c2 = dict(campos, ingested_at=iso(ctx["ingest"] + lag))
                g2 = dict(gab, armadilhas=tuple(arm + ["duplicata"]))
                self._brutos.append(((c2["available_at"], c2["ingested_at"]) + chave[2:] + (1,), c2, g2))
                self._runs[ctx["run_id"]]["n_registros"] += 1

    def _dimensao_nao_suportada(self, conta: str, i: int) -> None:
        sl = next(s for s in self.slots["joinads"] if s.tipo == "d1")
        ag = self.inst(i + 1, sl.hora)
        disp = ag + timedelta(seconds=45)
        run_id = "run-" + hashlib.sha256(f"{self.m.seed}|joinads|{conta}|dimensao|{iso(ag)}".encode()).hexdigest()[:16]
        motivo = "JoinAds não segmenta receita por dispositivo (dimensão não suportada)"
        self._run(run_id, fonte="joinads", conta=conta, tipo_leitura="dimensao", dia_referencia=self.m.dias[i].isoformat(),
                  agendado_em=iso(ag), concluido_em=iso(disp), status="completed", motivo=motivo, recuperacao=False)
        self._runs[run_id]["n_registros"] += 1
        ja_ini, ja_fim = iso(self.inst(i, 0)), iso(self.inst(i + 1, 0))
        campos = dict(
            fonte="joinads", conta=conta, entidade=conta, grao=GRAO_CONTA_DIA_DISP, metrica="revenue", valor=None,
            moeda=None, janela_inicio=ja_ini, janela_fim=ja_fim, timezone=self.tz, observed_at=iso(ag),
            available_at=iso(disp), ingested_at=iso(disp + timedelta(seconds=30)), run_id=run_id,
            payload_sha256=_sha({"run_id": run_id, "erro": motivo}), status="unsupported", motivo=motivo,
            leitura_id=hashlib.sha256(f"{run_id}|{conta}|revenue|{ja_ini}".encode()).hexdigest()[:20],
            unidade="micros", tipo_leitura="dimensao", maturidade="nao_aplicavel", cobertura_ate=None,
            entidade_tipo="account", custom_key_solicitada=None, custom_key_efetiva=None,
            dimensoes=(("dispositivo", "*"),), available_previsto=None, cenario=self.cenario)
        gab = dict(campanha_pedida=None, valor_verdade_final=None, valor_verdade_cobertura=None,
                   restatement_pendente=None, armadilhas=())
        self._brutos.append(((campos["available_at"], campos["ingested_at"], "joinads", conta, conta, "revenue", ja_ini,
                              "dimensao", 0), campos, gab))

    def _finalizar(self) -> Leituras:
        self._brutos.sort(key=lambda x: x[0])
        regs: list[RegistroObservacao] = []
        gabs: dict[str, Gabarito] = {}
        for n, (_, campos, gab) in enumerate(self._brutos):
            oid = f"obs-{n:08d}"
            regs.append(RegistroObservacao(obs_id=oid, **campos))
            gabs[oid] = Gabarito(obs_id=oid, **gab)
        execs = sorted(self._runs.values(), key=lambda r: (r["agendado_em"], r["fonte"], r["conta"], r["run_id"]))
        return Leituras(regs, gabs, execs)


def registros_contrato(registros: Iterable[RegistroObservacao]) -> list[dict]:
    """Projeção nos 17 campos do contrato da missão (para o adaptador do integrador)."""
    return [r.contrato() for r in registros]
