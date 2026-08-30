"""Contrato de uma futura migration única. Este arquivo NÃO é SQL aplicável.

P14-T06 pede forecast_model_versions / predictions / evaluations / drift.
SPEC v12 descreve trafego_previsao amarrada a proposta — outro objeto.
O Core V1 não aplica migration e não fala com o Supabase oficial.
"""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA_MIGRACAO_UNICA: Mapping[str, Any] = {
    "id": "v12_forecast_lifecycle_proposta",
    "aplicada": False,
    "supabase_alvo": "https://database.agenciavolc.com.br",
    "proibida_em": "feat/orakul-predictive-core-v1",
    "separacao": {
        "trafego_previsao": "expectativa da política/proposta (SPEC §5), não é registry de modelo",
        "forecast_*": "lifecycle preditivo champion/challenger (P14-T06)",
    },
    "tabelas": {
        "forecast_model_versions": {
            "pk": "version_id uuid",
            "colunas": [
                "papel text check (papel in ('candidate','challenger','champion','retired'))",
                "alvo text",
                "feature_set_id text",
                "code_hash text",
                "artifact_hash text",
                "parent_version_id uuid null",
                "criado_em timestamptz",
                "chave_idempotencia text unique",
            ],
        },
        "forecast_predictions": {
            "pk": "previsao_id uuid",
            "append_only": True,
            "unique": "(campanha_id, alvo, target_date, cenario, versao_modelo)",
            "colunas": [
                "volc_campaign_id uuid null",
                "campanha_id text",
                "conta_id text null",
                "observado_em timestamptz",
                "janela_inicio date",
                "janela_fim date",
                "horizonte_dias int",
                "target_date date",
                "ponto_micros bigint null",
                "intervalo_low_micros bigint null",
                "intervalo_high_micros bigint null",
                "hash_inputs text",
                "procedencia jsonb",
                "estado_semantico text",
                "chave_idempotencia text unique",
                "mutacao_campanha boolean not null default false check (mutacao_campanha = false)",
            ],
            "invariantes": [
                "métricas NULLABLE",
                "ausente ≠ 0",
                "actual não vive nesta tabela",
            ],
        },
        "forecast_outcomes": {
            "pk": "outcome_id uuid",
            "unique": "previsao_id",
            "colunas": [
                "valor_micros bigint null",
                "estado_semantico text",
                "fechado boolean check (fechado = true)",
                "lido_em timestamptz",
                "fonte text",
            ],
        },
        "forecast_evaluations": {
            "pk": "result_id uuid",
            "colunas": [
                "versao_modelo text",
                "janela_inicio date",
                "janela_fim date",
                "metricas jsonb",
                "naive_metricas jsonb",
                "n int",
                "dataset_kind text",
                "entra_em_contagens_reais boolean",
                "leakage_detectado boolean check (leakage_detectado = false)",
            ],
        },
        "forecast_drift_events": {
            "pk": "signal_id uuid",
            "colunas": [
                "tipo text",
                "feature text null",
                "mag numeric null",
                "evidencia_suficiente boolean",
                "acao text check (acao in ('nenhuma','suspender_influencia','usar_baseline','indisponivel'))",
            ],
        },
        "forecast_cc_decisions": {
            "pk": "decision_id uuid",
            "colunas": [
                "veredito text",
                "promocao text check (promocao in ('proposta','preservar','rollback_proposto'))",
                "explicacao jsonb",
                "n_pares int",
                "politica_id text",
                "humano_confirmou boolean default false",
            ],
        },
    },
    "rls": "FORÇADA, zero policies, só service_role no backend",
    "nao_fazer": [
        "não criar nesta branch",
        "não apontar para *.supabase.co",
        "não reusar JWT demo",
        "não ligar o Core V1 a writer de campanha",
    ],
}
