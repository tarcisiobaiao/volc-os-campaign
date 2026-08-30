"""Constantes de contrato. Qualquer mudança aqui é mudança de definição do alvo."""

from __future__ import annotations

VERSAO_CONTRATO = "orakul-predictive-core/v1"
FUSO_NEGOCIO = "America/Sao_Paulo"
MOEDA = "BRL"
UNIDADE_MONETARIA = "micros"
HORIZONTE_PADRAO_DIAS = 1
GRAIN = "campaign_day"

ALVO_SPEND = "spend"
ALVO_REVENUE = "revenue"
ALVO_ROAS = "roas"
ALVOS_PONTO = (ALVO_SPEND, ALVO_REVENUE)
ALVOS_DERIVADOS = (ALVO_ROAS,)
DEFINICOES_ALVO = {
    ALVO_SPEND: "spend_brl_micros_campaign_day_d1/v1",
    ALVO_REVENUE: "revenue_brl_micros_campaign_day_d1/v1",
    ALVO_ROAS: "roas_revenue_over_spend_x1e6_campaign_day_d1/v1",
}

FEATURE_SET_V1 = "orakul-features-asof-lagged/v1"
MODELO_NAIVE_PERSISTENCE = "naive_persistence/v1"
MODELO_NAIVE_WEEKDAY = "naive_weekday/v1"
MODELO_LAGGED_LINEAR = "lagged_linear_ridge/v1"
POLITICA_CC = "orakul-cc-policy/v1"

N_MINIMO_TREINO = 14
N_MINIMO_PROMOCAO = 21
JANELA_MINIMA_DIAS_PROMOCAO = 21
MELHORIA_MINIMA_WAPE = 0.05
REGRESSAO_CRITICA_MAE_SPEND = 0.10
FRESCO_MAX_HORAS = 36

DATASET_SINTETICO = "sintetico"
DATASET_REAL = "real"
DATASET_KINDS = (DATASET_SINTETICO, DATASET_REAL)

CENARIO_OBSERVADO = "observado"
CENARIO_PLANNED_SPEND = "planned_spend"
CENARIOS = (CENARIO_OBSERVADO, CENARIO_PLANNED_SPEND)
IDENTIFICACAO_PLANNED_SPEND = "hipotese_nao_causal_sem_identificacao"

PAPEIS_MODELO = ("candidate", "challenger", "champion", "retired")
