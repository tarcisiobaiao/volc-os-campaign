"""Health contracts por coletor: cadência esperada (agenda), tolerância e limiares.

Fonte das cadências (todas de código versionado, nenhuma de produção):
- Google Ads D0 `7 6-23 * * *`, D-1 `17 6,14 * * *`: `043c77f5:scripts/instalar_coleta_canonica_google_ads_n8n.py:261-262`.
- Google Ads termos/keywords `23 */4 * * *`: `043c77f5:scripts/instalar_coleta_termos_keywords_n8n.py:193`.
- JoinAds v2 intraday `15 6-22/2 * * *`, D-1 `20 6 * * *` (D-7..D-1): `192bc065:n8n/gerar_flows_joinads_v2.py:319-324`.

Os MESMOS valores estão na view `dil_qualidade.dq_parametros_sla` / `dq_parametros_limiares`
(`migrations_candidatas/views_qualidade/dq_01_views_qualidade.sql`); um teste compara os dois.

Semântica de slot (idêntica no SQL):
- slot = (dia local + hora:minuto da agenda) no fuso do coletor;
- o slot só é "vencido" quando `slot + tolerancia <= agora`; antes disso é `pendente`, nunca buraco;
- hora fora da agenda não gera slot — janela fora do horário de coleta não é buraco;
- só slots em (agora - 7 dias, agora] e a partir do primeiro run do coletor (menos a folga)
  contam: o coletor não é cobrado por horas anteriores à sua existência.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

TZ_PADRAO = "America/Sao_Paulo"
JANELA_AVALIACAO = timedelta(days=7)
TIMEOUT_RUNNING_PADRAO = timedelta(minutes=30)


def horas_de_cron(expr: str) -> tuple[int, tuple[int, ...]]:
    """`"7 6-23 * * *"` -> (7, (6..23)). Só o subconjunto diário usado pelos coletores VOLC."""
    partes = expr.split()
    if len(partes) != 5 or partes[2:] != ["*", "*", "*"]:
        raise ValueError(f"cron não suportado (só agenda diária): {expr!r}")
    minuto = int(partes[0])
    horas: set[int] = set()
    for item in partes[1].split(","):
        passo = 1
        if "/" in item:
            item, p = item.split("/")
            passo = int(p)
        if item == "*":
            ini, fim = 0, 23
        elif "-" in item:
            a, b = item.split("-")
            ini, fim = int(a), int(b)
        else:
            ini = fim = int(item)
        horas.update(range(ini, fim + 1, passo))
    if not 0 <= minuto <= 59 or not horas or min(horas) < 0 or max(horas) > 23:
        raise ValueError(f"cron fora de faixa: {expr!r}")
    return minuto, tuple(sorted(horas))


@dataclass(frozen=True)
class SLA:
    """Contrato de saúde de um coletor lógico."""

    fonte: str
    coletor: str
    grao: str
    cron: str
    tolerancia: timedelta
    timeout_running: timedelta
    min_linhas: int = 1
    folga: timedelta = timedelta(minutes=10)
    tz: str = TZ_PADRAO
    descricao: str = ""

    @property
    def minuto(self) -> int:
        return horas_de_cron(self.cron)[0]

    @property
    def horas(self) -> tuple[int, ...]:
        return horas_de_cron(self.cron)[1]

    def slots(self, agora: datetime, primeiro_run: datetime | None) -> list[datetime]:
        """Slots esperados em (agora - 7d, agora], a partir de `primeiro_run - folga` (se houver)."""
        zona = ZoneInfo(self.tz)
        hoje_local = agora.astimezone(zona).date()
        saida: list[datetime] = []
        for k in range(8, -1, -1):
            dia = hoje_local - timedelta(days=k)
            for h in self.horas:
                s = datetime.combine(dia, time(h, self.minuto), tzinfo=zona).astimezone(timezone.utc)
                if not (agora - JANELA_AVALIACAO < s <= agora):
                    continue
                if primeiro_run is not None and s < primeiro_run - self.folga:
                    continue
                saida.append(s)
        return sorted(saida)

    def dia_hora_local(self, instante: datetime) -> tuple[date, int]:
        local = instante.astimezone(ZoneInfo(self.tz))
        return local.date(), local.hour

    def como_dict(self) -> dict:
        return {
            "fonte": self.fonte,
            "coletor": self.coletor,
            "grao": self.grao,
            "cron": self.cron,
            "minuto": self.minuto,
            "horas": list(self.horas),
            "tolerancia_s": int(self.tolerancia.total_seconds()),
            "timeout_running_s": int(self.timeout_running.total_seconds()),
            "min_linhas": self.min_linhas,
            "folga_s": int(self.folga.total_seconds()),
            "tz": self.tz,
        }


_M = timedelta(minutes=1)

SLA_PADRAO: Mapping[str, SLA] = {
    s.coletor: s
    for s in (
        SLA("google_ads", "n8n-google-ads-d0", "campaign_day", "7 6-23 * * *", 30 * _M, 30 * _M,
            descricao="Google Ads D0 horário 06–23 (workflow Ps9yLfQkHeaAbyZZ)"),
        SLA("google_ads", "n8n-google-ads-d1", "campaign_day", "17 6,14 * * *", 60 * _M, 30 * _M,
            descricao="Google Ads D-1 2×/dia (workflow 7yxs1aOlzWkkkSf9)"),
        SLA("google_ads", "n8n-google-ads-terms-keywords", "search_term_day", "23 */4 * * *", 60 * _M, 60 * _M,
            descricao="Google Ads termos/keywords a cada 4 h, LAST_7_DAYS (workflow TFlmThr4930oPneE)"),
        SLA("joinads", "n8n_joinads_v2:intraday", "campaign_adunit_day", "15 6-22/2 * * *", 45 * _M, 30 * _M,
            descricao="JoinAds v2 intraday a cada 2 h 06–22 (workflow cpb6tNxt211UkAn2)"),
        SLA("joinads", "n8n_joinads_v2:d1", "campaign_adunit_day", "20 6 * * *", 120 * _M, 30 * _M,
            descricao="JoinAds v2 D-1 diário, relê D-7..D-1 (workflow jDX397ViVcRQft4A)"),
    )
}

# Limiares numéricos. Mesmos nomes e valores em `dil_qualidade.dq_parametros_limiares`.
LIMIARES_PADRAO: Mapping[str, float] = {
    "frescor_slots_parado": 3,  # >= 3 slots vencidos sem sucesso: parado (alto)
    "zero_sintetizado_alto": 0.5,  # proporção de zeros sem linha de métrica que vira alto
    "receita_cobertura_min": 0.90,  # soma kv campanha / earnings domínio abaixo disso: cobertura baixa
    "receita_cobertura_max": 1.02,  # acima disso: excesso (dupla contagem, moeda)
    "receita_cobertura_critica": 0.50,  # abaixo disso: alto (a ponte custo×receita quebrou)
    "custo_d0_d1_tol": 0.05,  # |D-1 fechado - último D0| / D-1 acima disso: divergente
    "custo_d0_d1_alto": 0.25,
    "sensor_cobertura_min": 0.90,  # pagas com utm_campaign / pagas
    "sensor_cobertura_alto": 0.50,
    "sensor_amostra_min": 10,  # abaixo disso a razão não é avaliada (info)
    "janela_leituras_dias": 14,  # janela de leituras para duplicação/zeros
    "janela_reconciliacao_dias": 14,
}


def primeiro_run_por_coletor(runs: Iterable, agora: datetime) -> dict[str, datetime]:
    saida: dict[str, datetime] = {}
    for r in runs:
        if r.started_at > agora:
            continue
        atual = saida.get(r.coletor)
        if atual is None or r.started_at < atual:
            saida[r.coletor] = r.started_at
    return saida
