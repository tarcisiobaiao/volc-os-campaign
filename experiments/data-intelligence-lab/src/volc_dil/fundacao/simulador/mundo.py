"""Processo VERDADEIRO do Simulator Lab: campanhas Google Ads → site → monetização, por hora local.

O mundo é a verdade. Nenhum consumidor (replay, shadow, Model Lab, observabilidade) deve
ler este objeto como entrada; ele existe para o OBSERVADOR (``observador.py``) emitir o que
cada fonte entregaria e para o AVALIADOR medir erro. Equações em 07-SIMULATOR-LAB.md §2.

Determinismo e números aleatórios comuns (CRN, mesma ideia do ``volc_dil.swarm.simulador``):
cada fluxo aleatório tem nome e é derivado de ``SeedSequence([seed, crc32(nome)])``. Fluxos
de cenário (bots, picos de RPM, quebras, mudanças de orçamento) têm nomes próprios; por isso
dois cenários com o mesmo tamanho e a mesma seed compartilham a MESMA base (mundos pareados)
e diferem só pelo que o cenário injeta. Contagens e receita são tiradas por CDF inversa de
uniformes fixos, então re-simular com outro orçamento (``orcamento_diario_micros``) muda o
resultado de forma coerente com o mesmo acaso (contrafactual pareado).

Dinheiro: custo e receita por hora são ``np.int64`` em micros, moeda explícita por campanha
(custo BRL; receita BRL ou USD nativa). Valores esperados (float) são internos.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
from scipy import special, stats

from .parametros import DISPOSITIVOS, PAISES, ParametrosMundo

MICROS = 1_000_000
_EPS = 1e-12


def rng_nomeado(seed: int, nome: str, *extra: int) -> np.random.Generator:
    s = int(seed)
    ss = np.random.SeedSequence([s & 0xFFFFFFFF, (s >> 32) & 0xFFFFFFFF, zlib.crc32(nome.encode()), *extra])
    return np.random.default_rng(ss)


def id_campanha(c: int) -> str:
    """Id sintético com a forma de um campaign.id do Google Ads (numérico, 11 dígitos)."""
    return f"9{c + 1:010d}"


def id_conta(k: int) -> str:
    return f"sint-conta-{k + 1:02d}"


@dataclass(frozen=True)
class Campanha:
    """Atributos latentes de uma campanha (verdade; nunca entram em registro de observação)."""

    idx: int
    id: str
    conta: str
    pais: str
    nova: bool
    inicio_h: int  # hora global (0 = 00:00 local do 1º dia) do lançamento; < 0 = madura
    moeda_receita: str
    impressoes_dia: float
    ctr: float
    cpc_brl: float
    rpm_brl: float
    continuacao: float
    aterrissagem: float
    roas_alvo: float
    orcamento_base_micros: int

    def como_dict(self) -> dict:
        return {
            "idx": self.idx, "id": self.id, "conta": self.conta, "pais": self.pais, "nova": self.nova,
            "inicio_h": self.inicio_h, "moeda_receita": self.moeda_receita,
            "impressoes_dia": round(self.impressoes_dia, 6), "ctr": round(self.ctr, 8),
            "cpc_brl": round(self.cpc_brl, 8), "rpm_brl": round(self.rpm_brl, 6),
            "continuacao": round(self.continuacao, 8), "aterrissagem": round(self.aterrissagem, 8),
            "roas_alvo": round(self.roas_alvo, 8), "orcamento_base_micros": self.orcamento_base_micros,
        }


METRICAS_HORARIAS = (
    "impressoes", "cliques", "cliques_invalidos", "cliques_bot", "cliques_bot_detectados",
    "custo_bruto_micros", "credito_micros", "custo_final_micros", "sessoes", "sessoes_bot",
    "pageviews", "pageviews_bot", "destino", "receita_micros",
)


class Mundo:
    """Verdade horária (C campanhas × T horas × K dispositivos). Construa com ``gerar_mundo``."""

    def __init__(self, params: ParametrosMundo, seed: int, campanhas: list[Campanha], dias: list[date],
                 arrays: dict[str, np.ndarray], flags: dict[str, np.ndarray], tz: ZoneInfo):
        self.params = params
        self.seed = int(seed)
        self.campanhas = campanhas
        self.dias = dias
        self.tz = tz
        self._a = arrays
        self.flags = flags
        self.C = len(campanhas)
        self.D = len(dias)
        self.T = self.D * 24
        self.K = len(DISPOSITIVOS)

    # ── acesso ───────────────────────────────────────────────────────────
    def horario(self, metrica: str) -> np.ndarray:
        """(C, T, K) int64."""
        return self._a[metrica]

    def por_hora(self, metrica: str) -> np.ndarray:
        """(C, T) somado nos dispositivos."""
        return self._a[metrica].sum(axis=2)

    def por_dia_hora(self, metrica: str) -> np.ndarray:
        """(C, D, 24) somado nos dispositivos."""
        return self.por_hora(metrica).reshape(self.C, self.D, 24)

    def diario(self, metrica: str) -> np.ndarray:
        """(C, D) total do dia civil local."""
        return self.por_dia_hora(metrica).sum(axis=2)

    def existe_dia(self) -> np.ndarray:
        """(C, D) campanha já existia em algum momento do dia (lançada até o fim do dia)."""
        return self.flags["existe"].reshape(self.C, self.D, 24).any(axis=2)

    def pausada_dia(self) -> np.ndarray:
        return self.flags["pausada_dia"]

    def instante_local(self, dia_idx: int, hora: int | float = 0) -> datetime:
        """Instante (aware, tz local) de ``dia_idx`` + ``hora`` horas (hora pode passar de 24)."""
        # soma em UTC para não depender de DST (São Paulo não tem DST desde 2019, mas o código é geral)
        d = self.dias[0] + timedelta(days=dia_idx)
        meia_noite = datetime(d.year, d.month, d.day, tzinfo=self.tz)
        return (meia_noite.astimezone(timezone.utc) + timedelta(hours=hora)).astimezone(self.tz)

    # ── tabelas de verdade (para avaliação; nunca entrada de consumidor) ─────
    def tabela_campanhas(self) -> list[dict]:
        return [c.como_dict() for c in self.campanhas]

    def tabela_diaria(self) -> list[dict]:
        existe = self.existe_dia()
        pausada = self.pausada_dia()
        tot = {m: self.diario(m) for m in METRICAS_HORARIAS}
        orc = self.flags["orcamento_hora_micros"].reshape(self.C, self.D, 24)
        linhas = []
        for c, camp in enumerate(self.campanhas):
            for i, d in enumerate(self.dias):
                if not existe[c, i]:
                    continue
                linha = {"campanha_id": camp.id, "conta": camp.conta, "dia_local": d.isoformat(),
                         "timezone": self.params.timezone, "pausada": bool(pausada[c, i]),
                         "moeda_custo": self.params.moeda_custo, "moeda_receita": camp.moeda_receita,
                         "orcamento_00h_micros": int(orc[c, i, 0]), "orcamento_23h_micros": int(orc[c, i, 23])}
                for m in METRICAS_HORARIAS:
                    linha[m] = int(tot[m][c, i])
                linhas.append(linha)
        return linhas

    def tabela_horaria(self) -> list[dict]:
        existe = self.flags["existe"]
        tot = {m: self.por_hora(m) for m in METRICAS_HORARIAS}
        theta = self.flags["theta"]
        bot = self.flags["bot_hora"]
        pico = self.flags["pico_rpm_hora"]
        orc = self.flags["orcamento_hora_micros"]
        ativo = self.flags["ativo"]
        inicio_utc = [self.instante_local(0, t).astimezone(timezone.utc).isoformat() for t in range(self.T)]
        linhas = []
        for c, camp in enumerate(self.campanhas):
            for t in range(self.T):
                if not existe[c, t]:
                    continue
                i, h = divmod(t, 24)
                linha = {"campanha_id": camp.id, "dia_local": self.dias[i].isoformat(), "hora_local": h,
                         "inicio_utc": inicio_utc[t], "ativo": bool(ativo[c, t]),
                         "orcamento_diario_micros": int(orc[c, t]), "theta_ppm": int(round(theta[c, t] * 1e6)),
                         "bot_hora": bool(bot[c, t]), "pico_rpm": bool(pico[c, t])}
                for m in METRICAS_HORARIAS:
                    linha[m] = int(tot[m][c, t])
                linhas.append(linha)
        return linhas


def _ppf_poisson(u: np.ndarray, lam: np.ndarray) -> np.ndarray:
    out = np.zeros(lam.shape, dtype=np.int64)
    m = lam > 0
    if m.any():
        out[m] = stats.poisson.ppf(u[m], lam[m]).astype(np.int64)
    return out


def _ppf_binom(u: np.ndarray, n: np.ndarray, p: np.ndarray | float) -> np.ndarray:
    out = np.zeros(n.shape, dtype=np.int64)
    p = np.broadcast_to(np.asarray(p, dtype=float), n.shape)
    m = (n > 0) & (p > 0)
    if m.any():
        out[m] = stats.binom.ppf(u[m], n[m], np.minimum(p[m], 1.0)).astype(np.int64)
    return np.minimum(out, n)


def _uniformes(seed: int, nome: str, shape: tuple[int, ...]) -> np.ndarray:
    return np.clip(rng_nomeado(seed, nome).random(shape), _EPS, 1 - _EPS)


def _selecionar(seed: int, nome: str, C: int, frac: float) -> np.ndarray:
    perm = rng_nomeado(seed, nome).permutation(C)
    n = int(np.ceil(frac * C - 1e-9))
    m = np.zeros(C, dtype=bool)
    m[perm[:n]] = True
    return m


def _hora_global(p: ParametrosMundo, em_frac: float, hora: int) -> int:
    dia = min(p.n_dias - 1, max(0, int(np.floor(em_frac * p.n_dias + 1e-9))))
    return dia * 24 + int(hora)


def perfil_diario(p: ParametrosMundo) -> np.ndarray:
    h = np.arange(24, dtype=float)
    s = (1 + p.amp_diaria * np.cos(2 * np.pi * (h - p.hora_pico) / 24)
         + p.amp_diaria2 * np.cos(4 * np.pi * (h - p.hora_pico2) / 24))
    s = np.maximum(s, 0.05)
    return s / s.mean()


def share_dispositivos(p: ParametrosMundo) -> np.ndarray:
    """(24, K): mobile cresce à noite; os demais repartem o resto na proporção base."""
    h = np.arange(24, dtype=float)
    base = np.asarray(p.share_dispositivo, dtype=float)
    mob = np.clip(base[0] + p.amp_share_mobile_noite * np.cos(2 * np.pi * (h - 23) / 24), 0.01, 0.99)
    resto = base[1:] / base[1:].sum()
    return np.column_stack([mob, (1 - mob)[:, None] * resto[None, :]])


def gerar_mundo(params: ParametrosMundo, seed: int,
                orcamento_diario_micros: np.ndarray | None = None) -> Mundo:
    """Gera a verdade. Mesma (params, seed, orçamento) → mesmo mundo, bit a bit.

    ``orcamento_diario_micros`` (C, D) int64, opcional: substitui o cronograma de orçamento do
    cenário (inclusive as mudanças intradiárias) — é o gancho para malha fechada/contrafactual.
    """
    p = params
    C, D, K = p.n_campanhas, p.n_dias, len(DISPOSITIVOS)
    T = D * 24
    tz = ZoneInfo(p.timezone)
    inicio = date.fromisoformat(p.data_inicio)
    dias = [inicio + timedelta(days=i) for i in range(D)]
    dow = np.array([d.weekday() for d in dias])
    fds = dow >= 5

    # ── atributos das campanhas ──────────────────────────────────────────
    r = rng_nomeado(seed, "campanhas")
    u = r.random((C, 8))
    z = r.standard_normal((C, 4))
    mu, kap = p.ctr_media, p.ctr_concentracao
    ctr_c = r.beta(mu * kap, (1 - mu) * kap, size=C)
    pais_idx = np.searchsorted(np.cumsum(p.prob_pais), u[:, 0], side="right").clip(0, len(PAISES) - 1)
    nova = u[:, 1] < p.frac_novas
    inicio_nova = (np.floor(u[:, 2] * p.novas_inicio_max_frac * D) * 24 + np.floor(u[:, 3] * 24)).astype(np.int64)
    idade_mad = p.idade_madura_dias_min + u[:, 4] * (p.idade_madura_dias_max - p.idade_madura_dias_min)
    inicio_h = np.where(nova, inicio_nova, -np.round(idade_mad * 24).astype(np.int64))
    usd = u[:, 5] < p.frac_campanhas_receita_usd
    q_c = p.continuacao_min + u[:, 6] * (p.continuacao_max - p.continuacao_min)
    land_c = p.taxa_aterrissagem_min + u[:, 7] * (p.taxa_aterrissagem_max - p.taxa_aterrissagem_min)
    imp_dia = p.impressoes_dia_mediana * np.exp(p.impressoes_dia_sigma * z[:, 0])
    rpm_c = p.rpm_mediana_brl * np.asarray(p.mult_rpm_pais)[pais_idx] * np.exp(p.rpm_sigma * z[:, 1])
    roas_c = p.roas_mediana * np.exp(p.roas_sigma * z[:, 2])
    razao_orc = rng_nomeado(seed, "orcamento_base").uniform(p.orcamento_razao_min, p.orcamento_razao_max, C)

    share_base = np.asarray(p.share_dispositivo)
    m_ctr = np.asarray(p.mult_ctr_dispositivo)
    m_cpc = np.asarray(p.mult_cpc_dispositivo)
    m_rpm = np.asarray(p.mult_rpm_dispositivo)
    peso_clique = share_base * m_ctr
    mix_rpm = (peso_clique * m_rpm).sum() / peso_clique.sum()
    mix_cpc = (peso_clique * m_cpc).sum() / peso_clique.sum()
    L = p.funil_passos
    pv_sessao = (1 - q_c ** L) / (1 - q_c)
    rpc_humano = land_c * pv_sessao * rpm_c * mix_rpm / 1000.0
    iota = p.taxa_cliques_invalidos
    cpc_c = (1 - iota) * rpc_humano / (roas_c * mix_cpc)
    custo_dia_esperado = imp_dia * ctr_c * peso_clique.sum() * cpc_c * mix_cpc
    orc_base = (np.round(razao_orc * custo_dia_esperado * 100).astype(np.int64)) * 10_000  # centavos

    contas = [id_conta(k) for k in range(p.n_contas)]
    campanhas = [
        Campanha(idx=c, id=id_campanha(c), conta=contas[c % p.n_contas], pais=PAISES[pais_idx[c]],
                 nova=bool(nova[c]), inicio_h=int(inicio_h[c]),
                 moeda_receita="USD" if usd[c] else p.moeda_receita, impressoes_dia=float(imp_dia[c]),
                 ctr=float(ctr_c[c]), cpc_brl=float(cpc_c[c]), rpm_brl=float(rpm_c[c]),
                 continuacao=float(q_c[c]), aterrissagem=float(land_c[c]), roas_alvo=float(roas_c[c]),
                 orcamento_base_micros=int(orc_base[c]))
        for c in range(C)
    ]

    # ── calendário horário e ciclo de vida ───────────────────────────────
    t = np.arange(T)
    hora = t % 24
    dia = t // 24
    idade = t[None, :] - inicio_h[:, None]  # (C, T) horas desde o lançamento
    existe = idade >= 0
    pausada_dia = rng_nomeado(seed, "pausas").random((C, D)) < p.p_pausa_dia
    ativo = existe & ~np.repeat(pausada_dia, 24, axis=1)
    idade_pos = np.maximum(idade, 0).astype(float)
    mult_vol = 1 - (1 - p.volume_inicial) * np.exp(-idade_pos / p.tau_volume_h)
    exp_apr = np.exp(-idade_pos / p.tau_aprendizado_h)
    mult_cpc_apr = 1 + p.amp_cpc_aprendizado * exp_apr
    mult_ctr_apr = 1 - p.amp_ctr_aprendizado * exp_apr
    mult_ruido = 1 + p.amp_ruido_aprendizado * exp_apr

    # ── choques diários (AR(1) em log) e ruído de CTR ────────────────────
    rc = rng_nomeado(seed, "choques")
    eps = rc.standard_normal((C, D))
    zeta = rc.standard_normal((C, D))
    zd = np.zeros((C, D))
    phi = p.choque_dia_ar
    zd[:, 0] = p.choque_dia_sigma * eps[:, 0]
    for i in range(1, D):
        zd[:, i] = phi * zd[:, i - 1] + np.sqrt(1 - phi ** 2) * p.choque_dia_sigma * eps[:, i]
    sig_h = p.choque_dia_sigma * mult_ruido
    choque = np.exp(zd[:, dia] * mult_ruido - 0.5 * sig_h ** 2)  # (C, T)
    ctr_ruido = np.exp(p.ctr_sigma_dia * zeta[:, dia] * mult_ruido - 0.5 * (p.ctr_sigma_dia * mult_ruido) ** 2)

    # ── quebras de regime (change points) ────────────────────────────────
    fator_rpm = np.ones((C, T))
    fator_cpc = np.ones((C, T))
    for j, q in enumerate(p.quebras):
        sel = _selecionar(seed, f"quebra_{j}_{q.alvo}", C, q.frac_campanhas)
        t0 = _hora_global(p, q.em_frac_periodo, q.hora_local)
        alvo = fator_rpm if q.alvo == "rpm" else fator_cpc
        alvo[np.ix_(sel, t >= t0)] *= q.fator

    # ── intensidades esperadas ───────────────────────────────────────────
    s_dia = perfil_diario(p)
    share = share_dispositivos(p)  # (24, K)
    fds_vol = np.where(fds, p.fator_fds_volume, 1.0)
    lam = (imp_dia[:, None, None] / 24.0 * s_dia[hora][None, :, None] * fds_vol[dia][None, :, None]
           * share[hora][None, :, :] * (mult_vol * choque * ativo)[:, :, None])
    ctr = np.clip(ctr_c[:, None, None] * m_ctr[None, None, :] * (mult_ctr_apr * ctr_ruido)[:, :, None], 1e-6, 0.5)
    cpc_med = cpc_c[:, None, None] * m_cpc[None, None, :] * (mult_cpc_apr * fator_cpc)[:, :, None]
    c0 = (lam * ctr * cpc_med).sum(axis=2)  # custo esperado irrestrito (BRL), (C, T)

    # ── orçamento e pacing (saturação) ───────────────────────────────────
    if orcamento_diario_micros is not None:
        ob = np.asarray(orcamento_diario_micros)
        if ob.shape != (C, D) or ob.dtype.kind not in "iu":
            raise TypeError("orcamento_diario_micros precisa ser inteiro (C, D) em micros")
        orc_hora = np.repeat(ob.astype(np.int64), 24, axis=1)
    else:
        orc_hora = np.repeat(orc_base[:, None], T, axis=1).astype(np.int64)
        for j, mo in enumerate(p.mudancas_orcamento):
            sel = _selecionar(seed, f"mudanca_orcamento_{j}", C, mo.frac_campanhas)
            t0 = _hora_global(p, mo.em_frac_periodo, mo.hora_local)
            bloco = orc_hora[np.ix_(sel, t >= t0)]
            orc_hora[np.ix_(sel, t >= t0)] = (np.round(bloco * mo.fator / 10_000).astype(np.int64)) * 10_000
    c0_dia = c0.reshape(C, D, 24)
    tot_dia = c0_dia.sum(axis=2, keepdims=True)
    w = np.divide(c0_dia, tot_dia, out=np.zeros_like(c0_dia), where=tot_dia > 0).reshape(C, T)
    cap = p.overdelivery * (orc_hora / MICROS) * w
    eta = p.elasticidade_cpc
    razao = np.divide(cap, c0, out=np.ones_like(c0), where=c0 > 0)
    theta = np.minimum(1.0, np.power(np.maximum(razao, 0.0), 1.0 / (1.0 + eta)))

    # ── realizações (CRN por CDF inversa) ────────────────────────────────
    shp = (C, T, K)
    od = rng_nomeado(seed, "sobredispersao").standard_gamma(1.0 / p.sobredispersao, shp) * p.sobredispersao
    imp = _ppf_poisson(_uniformes(seed, "u_impressoes", shp), lam * theta[:, :, None] * od)
    cliq_h = _ppf_binom(_uniformes(seed, "u_cliques", shp), imp, ctr)
    inval = _ppf_binom(_uniformes(seed, "u_invalidos", shp), cliq_h, iota)
    n_cpc = rng_nomeado(seed, "cpc_hora").standard_normal(shp)
    sig_cpc = p.cpc_sigma_hora * mult_ruido[:, :, None]
    cpc_t = cpc_med * np.power(theta, eta)[:, :, None] * np.exp(sig_cpc * n_cpc - 0.5 * sig_cpc ** 2)

    # bots (tráfego inválido em rajada): cobrados no ato, parcialmente creditados depois
    bot_hora = (_uniformes(seed, "u_bot_hora", (C, T)) < p.p_bot_hora) & ativo
    esperado_cliques_h = (lam * theta[:, :, None] * ctr).sum(axis=2)
    lam_bot = np.where(bot_hora, p.bot_mult * esperado_cliques_h + p.bot_cliques_min, 0.0)
    n_bot = _ppf_poisson(_uniformes(seed, "u_bot_cliques", (C, T)), lam_bot)
    share_bot = np.array([(1 - p.bot_share_desktop) * 0.85, p.bot_share_desktop, (1 - p.bot_share_desktop) * 0.15])
    bot_k = np.floor(n_bot[:, :, None] * share_bot[None, None, :]).astype(np.int64)
    bot_k[:, :, 1] += n_bot - bot_k.sum(axis=2)
    bot_det = _ppf_binom(_uniformes(seed, "u_bot_deteccao", shp), bot_k, p.bot_deteccao)

    # corte rígido do limite diário (Google: até 2× o orçamento diário num dia): a partir da hora em
    # que o gasto acumulado do dia passaria do limite, a campanha para de servir no resto do dia.
    bruto_h = np.rint((cliq_h + bot_k) * cpc_t * MICROS).sum(axis=2).reshape(C, D, 24)
    limite = p.limite_diario_x_orcamento * orc_hora.reshape(C, D, 24).max(axis=2)
    serve = (np.cumsum(bruto_h, axis=2) <= limite[:, :, None]).reshape(C, T)
    corte = ~serve & ativo
    m3 = serve[:, :, None]
    imp, cliq_h, inval, bot_k, bot_det = imp * m3, cliq_h * m3, inval * m3, bot_k * m3, bot_det * m3

    cliques = cliq_h + bot_k
    custo_bruto = np.rint(cliques * cpc_t * MICROS).astype(np.int64)
    credito = np.rint((inval + bot_det) * cpc_t * MICROS).astype(np.int64)
    custo_final = custo_bruto - credito

    # site: aterrissagem e funil (entrada → páginas → destino)
    sess = _ppf_binom(_uniformes(seed, "u_sessoes", shp), cliq_h - inval, land_c[:, None, None])
    S = sess
    pv = sess.copy()
    qb = np.broadcast_to(q_c[:, None, None], shp)
    for j in range(2, L + 1):
        S = _ppf_binom(_uniformes(seed, f"u_funil_{j}", shp), S, qb)
        pv += S
    destino = S
    sess_bot = _ppf_binom(_uniformes(seed, "u_sessoes_bot", shp), bot_k, p.bot_aterrissagem)
    pv_bot = sess_bot + _ppf_binom(_uniformes(seed, "u_pv_bot", shp), sess_bot, p.bot_continuacao)

    # monetização: RPM por pageview com país/dispositivo/hora/fim de semana/regime/picos
    rpm_hora = 1 + p.amp_rpm_hora * np.cos(2 * np.pi * (np.arange(24) - p.hora_pico_rpm) / 24)
    fds_rpm = np.where(fds, p.fator_fds_rpm, 1.0)
    rp = rng_nomeado(seed, "picos_rpm")
    u_pico = rp.random((C, T))
    fator_pico_val = rp.uniform(p.pico_rpm_fator_min, p.pico_rpm_fator_max, (C, T))
    pico = (u_pico < p.p_pico_rpm_hora) & ativo
    fator_pico = np.where(pico, fator_pico_val, 1.0)
    rpm_t = (rpm_c[:, None, None] * m_rpm[None, None, :]
             * (rpm_hora[hora][None, :] * fds_rpm[dia][None, :] * fator_rpm * fator_pico)[:, :, None])
    media_rec = (pv + pv_bot * p.bot_rpm_fator) * rpm_t / 1000.0
    forma = pv / p.dispersao_receita
    u_rec = _uniformes(seed, "u_receita", shp)
    g = np.ones(shp)
    m = forma > 0
    g[m] = special.gammaincinv(forma[m], u_rec[m]) / forma[m]
    rec_brl = pv * rpm_t / 1000.0 * g + pv_bot * p.bot_rpm_fator * rpm_t / 1000.0
    del media_rec
    conv = np.where(usd, 1.0 / p.cambio_brl_por_usd, 1.0)
    receita = np.rint(rec_brl * conv[:, None, None] * MICROS).astype(np.int64)

    arrays = {
        "impressoes": imp, "cliques": cliques, "cliques_invalidos": inval, "cliques_bot": bot_k,
        "cliques_bot_detectados": bot_det, "custo_bruto_micros": custo_bruto, "credito_micros": credito,
        "custo_final_micros": custo_final, "sessoes": sess + sess_bot, "sessoes_bot": sess_bot,
        "pageviews": pv + pv_bot, "pageviews_bot": pv_bot, "destino": destino, "receita_micros": receita,
    }
    flags = {"existe": existe, "ativo": ativo, "pausada_dia": pausada_dia & existe.reshape(C, D, 24).any(axis=2),
             "theta": theta, "corte_limite_diario": corte, "bot_hora": bot_hora, "pico_rpm_hora": pico, "orcamento_hora_micros": orc_hora,
             "fator_rpm": fator_rpm, "fator_cpc": fator_cpc}
    return Mundo(p, seed, campanhas, dias, arrays, flags, tz)
