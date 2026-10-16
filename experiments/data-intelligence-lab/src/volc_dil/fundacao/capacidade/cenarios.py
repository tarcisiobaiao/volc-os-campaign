"""Cenários do modelo de capacidade: escala medida, jobs atuais/propostos, cadências e políticas.

Cada número carrega a origem. Abreviações de evidência (todas lidas por `git show`, só leitura):
- J  = ref `wip/historico-joinads-20261015` (192bc065)
- P  = `.claude-ads/runs/google-ads-recovery-20261015T125729-0300`
- MS = ref `wip/historico-measurement-20261015`
"""
from __future__ import annotations

from .cron import a_cada
from .volume import Escala, Job, Politica

# ----------------------------------------------------------------- calibração com dado real

# Fatia de impressões por hora do dia (em 1/100.000), D30 16/09–15/10/2026, campanha ativa da conta A
# (America/Sao_Paulo). Fonte: J:P/receipts/d-live-campaign-audit.json:667-1020 (bloco "hour"), extraída e
# reduzida a fatias por `scripts/fundacao_capacidade_horas.py`. IDs e valores absolutos omitidos (R1 F25).
FATIA_IMPRESSOES_POR_HORA_D30 = (1957, 954, 609, 425, 417, 650, 1484, 3729, 4956, 5621, 6600, 6993, 7442, 6792, 6929, 6047, 6014, 6415, 6038, 6648, 5686, 3929, 2406, 1259)
_media = sum(FATIA_IMPRESSOES_POR_HORA_D30) / 24
PERFIL_HORARIO_GADS = tuple(x / _media for x in FATIA_IMPRESSOES_POR_HORA_D30)
LAMBDA_CAMPANHA_ATIVA_H = 17.32  # impressões/h médias da campanha ativa no D30 (horas_campanha_d30.json)

ESCALA_ATUAL = Escala(
    contas=1,  # J:P/account-snapshot.json:6-9; gaql-catalog.json:10 (customer_client = 1)
    campanhas_por_conta=5,  # J:P/gaql-catalog.json:11; D0 canário 58046 = 5 observações
    grupos_por_campanha=0.2,  # 1 ad group na conta: J:P/gaql-catalog.json:16
    anuncios_por_grupo=2,  # 2 RSAs: J:P/gaql-catalog.json:17
    keywords_por_conta=4,  # keyword_view 4: J:P/gaql-catalog.json:21 (14 keyword-dia em 7 d → 2 ativas)
    termos_dia_por_campanha=2228 / 7 / 5,  # 2.228 termo-dia em 7 d: J:docs/audits/GOOGLE-ADS-COLETA-CANONICA-2026-10-15.md:93-100
    dispositivos=3,
    geos_por_campanha_dia=10,  # premissa (não medido)
    horas_por_dia=24,
    linhas_joinads_dia_por_conta=209 / 7,  # D1 58097: 209 linhas em 7 d: J:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:77-85
    origem="medido (conta A, 15/10/2026)",
)

FATORES_CRESCIMENTO = (1, 10, 100, 1000)

# p de revisão de termo-dia fechado entre leituras. A 1ª versão usava 0,02 (premissa). O recibo de
# leituras (2ª/4ª rodadas) mostra 2.525 versões distintas para ≈2.546 termo-dias lidos por 13 runs:
# nenhuma revisão detectável. 0,005 é o limite superior compatível (≈ 5% de folga / ~10 releituras).
P_REVISAO_TERMOS = 0.005

# ----------------------------------------------------------------- jobs

CONF_REPO = "confirmado no repo (ref+caminho+linha)"


def jobs_atuais() -> list[Job]:
    """Os coletores canônicos em shadow, com a agenda confirmada no repositório."""
    return [
        Job(nome="gads_campanha_d0", fonte="google_ads", base="campanha", cron="7 6-23 * * *", janela=(0, 0),
            metricas_por_linha=8, lambda_mudanca_h=LAMBDA_CAMPANHA_ATIVA_H, fracao_ativa=1.0, fracao_mutavel=0.2,
            perfil_horario=PERFIL_HORARIO_GADS, consultas_por_execucao=4, consultas_fixas_por_execucao=1,
            lotes_por_execucao=1,
            confirmacao=f"{CONF_REPO}: J:P/collector-inventory.json:102,109,111-117 (customer_client + 4 GAQL "
                        "por conta: campaign, conversion_goal_campaign_config, campaign_budget, métricas D0); "
                        "J:scripts/instalar_coleta_canonica_google_ads_n8n.py:262"),
        Job(nome="gads_campanha_d1", fonte="google_ads", base="campanha", cron="17 6,14 * * *", janela=(1, 1),
            metricas_por_linha=8, fracao_mutavel=0.2, p_revisao_fechado=0.3, consultas_por_execucao=4,
            consultas_fixas_por_execucao=1, lotes_por_execucao=1,
            confirmacao=f"{CONF_REPO}: J:P/collector-inventory.json:127,134,136-142 (customer_client + 4 GAQL por conta)"),
        Job(nome="gads_termos", fonte="google_ads", base="termo_dia", cron="23 */4 * * *", janela=(1, 7),
            metricas_por_linha=5, p_revisao_fechado=P_REVISAO_TERMOS, tipo_payload="termo", consultas_fixas_por_execucao=1,
            confirmacao=f"{CONF_REPO}: J:scripts/instalar_coleta_termos_keywords_n8n.py:166-167,193; listagem de contas "
                        "inferida de J:P/collector-inventory.json:168 (retry.account_query)"),
        Job(nome="gads_keywords", fonte="google_ads", base="keyword", cron="23 */4 * * *", janela=(1, 7),
            metricas_por_linha=5, fracao_ativa=0.5, p_revisao_fechado=P_REVISAO_TERMOS,
            confirmacao=f"{CONF_REPO}: mesmo workflow TFlmThr4930oPneE (2º lote)"),
        Job(nome="joinads_intraday", fonte="joinads", base="joinads_linha", cron="15 6-22/2 * * *", janela=(0, 0),
            metricas_por_linha=6, lambda_mudanca_h=2.0, fracao_mutavel=0.5, consultas_por_execucao=9,
            tipo_payload="campanha",
            confirmacao=f"{CONF_REPO}: J:n8n/joinads_v2_intraday.json:10; λ e consultas/execução são premissas"),
        Job(nome="joinads_d1", fonte="joinads", base="joinads_linha", cron="20 6 * * *", janela=(1, 7),
            metricas_por_linha=6, p_revisao_fechado=0.05, consultas_por_execucao=64, tipo_payload="campanha",
            confirmacao=f"{CONF_REPO}: J:n8n/joinads_v2_d1.json:10; 64 lotes/run: J:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:80"),
    ]


def jobs_vertical_completa() -> list[Job]:
    """Atuais + granularidades que faltam (ad group, anúncio, hora, dispositivo, geo) — PROPOSTA.

    Segue J:P/canonical-collection-plan.json:25 ("device/network/hour/geography: D-1 daily, hourly
    dimension once daily"). Ad group D0 segue a cadência do D0 de campanha.
    """
    novos = [
        Job(nome="gads_grupo_d0", fonte="google_ads", base="grupo", cron="7 6-23 * * *", janela=(0, 0),
            metricas_por_linha=8, lambda_mudanca_h=LAMBDA_CAMPANHA_ATIVA_H, fracao_mutavel=0.2,
            perfil_horario=PERFIL_HORARIO_GADS, confirmacao="proposta"),
        Job(nome="gads_grupo_d1", fonte="google_ads", base="grupo", cron="17 6,14 * * *", janela=(1, 1),
            metricas_por_linha=8, p_revisao_fechado=0.3, confirmacao="proposta"),
        Job(nome="gads_anuncio_d1", fonte="google_ads", base="anuncio", cron="17 6,14 * * *", janela=(1, 1),
            metricas_por_linha=8, p_revisao_fechado=0.3, confirmacao="proposta"),
        Job(nome="gads_campanha_hora_d1", fonte="google_ads", base="campanha_hora", cron="37 6 * * *", janela=(1, 1),
            metricas_por_linha=8, fracao_ativa=0.2 * 21 / 24, confirmacao="proposta (só horas com entrega voltam)"),
        Job(nome="gads_campanha_dispositivo_d1", fonte="google_ads", base="campanha_dispositivo", cron="37 6 * * *",
            janela=(1, 1), metricas_por_linha=8, fracao_ativa=0.2, confirmacao="proposta"),
        Job(nome="gads_campanha_geo_d1", fonte="google_ads", base="campanha_geo", cron="37 6 * * *", janela=(1, 1),
            metricas_por_linha=8, fracao_ativa=0.2, confirmacao="proposta; geos por campanha é premissa"),
    ]
    return jobs_atuais() + novos


INTRADAY = ("gads_campanha_d0", "gads_grupo_d0", "joinads_intraday")

CADENCIAS = {
    "atual": None,  # agenda documentada de cada job
    "horaria_24h": a_cada(60),
    "15min": a_cada(15),
    "10min": a_cada(10),
}


def aplicar_cadencia(jobs: list[Job], cadencia: str) -> list[Job]:
    """A cadência só muda os jobs INTRADAY: dia fechado não fica mais fresco com leitura frequente."""
    cron = CADENCIAS[cadencia]
    if cron is None:
        return list(jobs)
    return [j.com_cron(cron) if j.nome in INTRADAY else j for j in jobs]


def termos_uma_vez_ao_dia(jobs: list[Job]) -> list[Job]:
    return [j.com_cron("23 7 * * *") if j.nome in ("gads_termos", "gads_keywords") else j for j in jobs]


# ----------------------------------------------------------------- políticas de gravação

POLITICAS = {
    # como está em v21: 1 linha por entidade por run (UNIQUE (run_id, observation_key)), lote bruto por run
    "v21_atual": Politica(dedup_observacao=False, dedup_payload="nenhum", rotulo="réplica v21 (sem dedup)"),
    "compacto_sem_dedup": Politica(dedup_observacao=False, dedup_payload="nenhum", rotulo="tipado, sem dedup"),
    "compacto_dedup_lote": Politica(dedup_observacao=True, dedup_payload="lote", rotulo="tipado, dedup obs + lote"),
    "compacto_dedup_linha": Politica(dedup_observacao=True, dedup_payload="linha", rotulo="tipado, dedup obs + linha"),
    "compacto_dedup_sem_indices": Politica(dedup_observacao=True, dedup_payload="linha_em_lote", com_indices=False,
                                           rotulo="tipado, dedup, sem índices (piso teórico)"),
    "compacto_dedup_linha_em_lote": Politica(dedup_observacao=True, dedup_payload="linha_em_lote",
                                             rotulo="tipado, dedup obs + linha gravada em lote"),
    # regra D2 da frente A (observed_at na chave da leitura): toda releitura vira versão; o payload bruto
    # continua deduplicado por conteúdo (hash por linha)
    "registro_d2": Politica(dedup_observacao=False, dedup_payload="linha_em_lote",
                            rotulo="regra D2 da frente A: toda releitura é versão; payload por linha em lote"),
    "recomendada": Politica(dedup_observacao=True, dedup_payload="linha_em_lote", particao_mensal=True,
                            retencao_bruto_dias=396, rollup_diario=True,
                            rotulo="tipado largo, dedup obs + linha em lote, partição mensal, bruto 13 m + rollup"),
}


def com_escala(escala: Escala, fator: float) -> Escala:
    return escala if fator == 1 else escala.crescer(fator)


def premissas() -> dict:
    """O que NÃO é medido e entra no modelo — para o relatório publicar."""
    return {
        "lambda_campanha_ativa_h": {"valor": LAMBDA_CAMPANHA_ATIVA_H, "origem": "calibrado: impressões D30/720 h"},
        "fracao_mutavel_gads": {"valor": 0.2, "origem": "1 de 5 campanhas com entrega (account-snapshot/D0 canário)"},
        "p_revisao_d1": {"valor": 0.3, "origem": "PREMISSA: atraso de conversão não medido (J:P/reconciliation.json:1013)"},
        "p_revisao_termos": {"valor": P_REVISAO_TERMOS,
                             "origem": "limite superior compatível com o recibo (2.525 distintas ≈ 2.546 termo-dias); era 0,02"},
        "p_revisao_joinads_d1": {"valor": 0.05, "origem": "PREMISSA"},
        "joinads_lambda_h": {"valor": 2.0, "origem": "PREMISSA"},
        "joinads_consultas_intraday": {"valor": 9, "origem": "PREMISSA: 64 lotes / 7 dias do D1"},
        "geos_por_campanha_dia": {"valor": ESCALA_ATUAL.geos_por_campanha_dia, "origem": "PREMISSA"},
        "crescimento": "mais contas com a mesma estrutura por conta (portfólio de sites)",
    }

