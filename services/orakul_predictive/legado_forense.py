"""Tabela forense do legado n8n. Fato observado, não reescrita do algoritmo."""

from __future__ import annotations

from typing import Tuple

# fato | hipótese | regra histórica | risco | destino no Core V1
LinhaForense = Tuple[str, str, str, str, str]

TABELA_FORENSE: Tuple[LinhaForense, ...] = (
    (
        "O sistema declara prever spend e receita de D+1 (e ROAS derivado) por campanha-dia.",
        "O alvo real de produto é o lado direito da equação RPC−CPC amanhã.",
        "PredictiveModel.predict() emite prediction_tomorrow=receita e estimated_spend_tomorrow.",
        "Sem persistência, o alvo nunca foi medido fora da amostra.",
        "Alvos canônicos spend e revenue em horizonte 1; ROAS só derivado.",
    ),
    (
        "Features de spend incluem budget_utilization=spend_t/budget, cpc, zscore, ewma, max_7d do próprio dia t.",
        "O estágio 1 aprende a reconstruir spend_t, não a prever spend_{t+1}.",
        "R² in-sample Ridge 0,987 / XGB 1,0 medido no inventário 05-PREDITIVO.",
        "Target leakage. Empate técnico com amanhã=hoje.",
        "Feature set as-of lagged/v1; nomes contemporâneos do alvo são VazamentoDeFuturo.",
    ),
    (
        "fillna(0) em métricas e budget_utilization NaN→0 nas rotas B/C.",
        "Ausência, budget nulo e zero medido colapsam no mesmo número.",
        "Code7 fillna(0); rota B replace inf→nan→dropna; rota A divide sem guarda.",
        "Campanha sem budget vira spend previsto 0 e zera ROAS.",
        "EstadoSemantico ausente/zero_medido/falha/nao_aplicavel/antigo; valor None se não medido.",
    ),
    (
        "Comparador lê realizado de ontem e o modelo prevê hoje; ontem estava no treino.",
        "A 'validação' mede persistência in-sample com offset de dois dias.",
        "GET date=eq.hoje-1 vs last_row.date+1=hoje; treino date<hoje.",
        "Nenhum número do n8n mede acurácia.",
        "Reconciliação exige target_date idêntico; split walk-forward temporal.",
    ),
    (
        "Nenhuma previsão é persistida. Terminais Code1/5/8 só logam comparisons.",
        "Sem ledger não há assertividade, drift nem champion/challenger.",
        "Zero POST; tabelas %predi%/%forecast% inexistentes no self-hosted.",
        "P14-T06 continua todo.",
        "PredictionLedger append-only in-memory; schema_migracao documenta forecast_*.",
    ),
    (
        "boost_factor = 0.9 + gam_ctr_mean*0.5 após o Code já ter dividido CTR por 100.",
        "Vira haircut ~5–10%, constante, não um boost de CTR.",
        "Rotas B/C clipam em [0.95, 1.08] e medem 0.95 sempre.",
        "Maquiagem da saída fora do treino.",
        "Não portado. CTR entra só se for feature as-of, o modelo aprende o coeficiente.",
    ),
    (
        "Intervalo 90% calibrado in-sample cobre ~60–64%.",
        "O operador confia num intervalo otimista.",
        "Rota A 1.96σ; B/C quantil 90% dos resíduos de treino.",
        "Alegação de 90% não é cobertura medida (P14-T08).",
        "Margem quantil; calibrado_fora_da_amostra só com resíduos OOF; n<21 = insuficiente.",
    ),
    (
        "XGBoost subsample=0.9 sem random_state; Ridge spend sem scaler.",
        "Duas execuções no mesmo dado divergem; L2 pune features pequenas.",
        "n_estimators=200, max_depth=4 em 23–53 linhas.",
        "Determinismo falso e overfit.",
        "Stdlib ridge + z-score de treino; zero RNG; byte-idêntico.",
    ),
    (
        "planned_spend existe na assinatura e nunca é chamado.",
        "O simulador de cenário é a joia não usada.",
        "if planned_spend is not None: estimated_spend = planned_spend",
        "P14-T09 fica bloqueado até haver previsão persistida.",
        "PredictionRequest.cenario=planned_spend; ainda sem mutação e sem UI.",
    ),
    (
        "Árbitro integrado veta aumento se ROAS previsto < 1.30.",
        "Previsão não calibrada vira trava de lance.",
        "orakul-predictive-integrado-v1 Árbitro + Motor 1.",
        "Core V1 não executa mudança; veto preditivo fica fora desta fatia.",
        "mutacao_campanha=False; recusar_executor().",
    ),
    (
        "Supabase hospedado txvvzpstquqmbhljudfn; campanha hardcoded 23731140888 / 22976442661.",
        "Não é o Supabase oficial Hetzner. Campanha do bola de cristal não existe no self-hosted.",
        "GET PostgREST daily_campaign_metrics e campaigns.",
        "Reativar n8n apontaria para autoridade partida.",
        "Nenhuma conexão. Fixtures sintéticas. Migration futura única documentada, não aplicada.",
    ),
    (
        "Datas start/end nos nós Campos são letra morta; janela real 2025-09-07 até ontem.",
        "O bake-off A/B/C leu a mesma janela.",
        "Três rotas gêmeas; só o código do modelo muda.",
        "Experimento que o operador achava fazer nunca aconteceu.",
        "janela_inicio/fim explícitos no contrato; uma feature set, três modelos comparáveis.",
    ),
    (
        "Mínimo anunciado 8 dias; dropna de lag7 exige 12.",
        "Mensagem de erro mente sobre a suficiência.",
        "len<8 vs dropna + len<5.",
        "Dataset curto falha com texto errado.",
        "DatasetInsuficiente com n_minimo_treino=14 e n_minimo_promocao=21.",
    ),
    (
        "Receita prevista pode ser negativa (rotas A/C); só B faz max(0).",
        "ROAS negativo vira pausa indevida se um dia alimentar lance.",
        "Code7 medido prediction_tomorrow=-0.03 numa série real.",
        "Clip silencioso também esconde falha de modelo.",
        "ponto_bruto_micros preserva o sinal; ponto_micros clipeado em 0; estado explícito.",
    ),
    (
        "Motor 1 usa predicted_roas=0 quando a previsão falha (safe_float default 0).",
        "Falha vira zero e some do alerta (só alerta se >0 e <1.30).",
        "safe_float(..., 0) no integrado v1.",
        "Ausência transformada em zero na decisão.",
        "disponivel=False; ponto None; N/A para ROAS sem spend.",
    ),
)

JOIAS_PRESERVADAS = (
    "Dois estágios: spend é decisão/cenário, receita é resposta.",
    "Gancho planned_spend para simulador.",
    "Intervalo que cresce com residual, volatilidade e discordância — recalibrar OOF.",
    "Vocabulário prediction_available + prediction_for_date (este último faltava).",
    "Curva de retorno (legado: spend_squared) como ideia, não como quadrático solto.",
)

DIVIDA_DESCARTADA = (
    "12 features contemporâneas de spend.",
    "boost_factor.",
    "XGBRegressor em dezenas de linhas.",
    "is_payday {1,21,27} como lei.",
    "teto min(..., budget_amount) — Google permite ~2× no dia.",
    "Três rotas duplicadas e a quarta cópia no integrado.",
)
