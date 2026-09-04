# GADS_MULTICHANNEL_BIRTH_V1_PARTIAL_CHECKPOINT

> Checkpoint histórico, superado pelo `FINAL-HANDOFF.md`. As falhas abaixo
> descrevem o estado de `9c92e381`, não o fechamento adjudicado posterior.

Este documento preserva um checkpoint parcial para retomada por Codex + Gemini 3.1 Pro Preview. Não é aceitação de engine, não é suíte verde, não é produção pronta e não torna nenhum canário elegível.

## Base e branch

- Base autorizada: `0aa090eb6a97e66b5ebdeb1c288d214003b06cbf`
- Branch: `sprint/hermes-gads-multichannel-birth-v1`
- Worktree: `/root/work/volc-runs/hermes-gads-multichannel-birth-v1`
- Data UTC: `2026-09-04T02:20:25Z`

## Gemini usado

- Modelo solicitado: `gemini-3.1-pro-preview`
- Modelo efetivo retornado: `gemini-3.1-pro-preview`
- SDK: `google-genai`
- SDK versão: `2.22.0`
- Primeira chamada arquitetural preservada em: `GEMINI-ARCHITECTURE-REVIEW.json`
- Contexto sanitizado enviado ao Gemini preservado em: `SANITIZED-CONTEXT-FOR-GEMINI.json`
- Segunda chamada Gemini: não executada neste checkpoint.

## Arquivos alterados no checkpoint

- `docs/closure/hermes-gads-multichannel-birth-v1/GEMINI-ARCHITECTURE-REVIEW.json`
- `docs/closure/hermes-gads-multichannel-birth-v1/PARTIAL-CHECKPOINT.md`
- `docs/closure/hermes-gads-multichannel-birth-v1/SANITIZED-CONTEXT-FOR-GEMINI.json`
- `volc_ads/campanha/comum.py`
- `volc_ads/campanha/demand_gen.py`
- `volc_ads/campanha/perfil.py`
- `volc_ads/campanha/pmax.py`
- `volc_ads/campanha/testes_demand_gen.py`
- `volc_ads/campanha/testes_display.py`
- `volc_ads/campanha/testes_multichannel_birth_v1.py`
- `volc_ads/subir.py`

## O que já foi implementado parcialmente

- Worktree isolada criada a partir de `origin/volc-os-v2`.
- Preflight do Gemini 3.1 Pro Preview realizado com SDK `google-genai`.
- Contexto técnico sanitizado salvo para retomada.
- Review arquitetural Gemini salvo.
- Teste focal novo `volc_ads/campanha/testes_multichannel_birth_v1.py` criado.
- PMax começou a ser promovido ao registry Python de prova/criação PAUSED.
- Demand Gen começou a ser promovido ao registry Python de criação PAUSED.
- PMax passou a emitir, no payload, opt-out de `FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION` via `Campaign.asset_automation_settings`.
- `PMAX_FORA_DO_EXECUTOR` começou a ser removido do plano quando o payload monta localmente.
- Alguns testes antigos começaram a ser atualizados para o novo contrato, mas essa reconciliação está incompleta.

## Testes conhecidos

### Teste novo focal

Comando:

```bash
python3 -m pytest volc_ads/campanha/testes_multichannel_birth_v1.py -q
```

Resultado conhecido:

```text
4 passed in 1.72s
```

### Suíte focal maior

Comando:

```bash
python3 -m pytest \
  volc_ads/campanha/testes_display.py \
  volc_ads/campanha/testes_demand_gen.py \
  volc_ads/campanha/testes_pmax.py \
  volc_ads/campanha/testes_plano.py \
  volc_ads/testes_subir.py \
  backend/tests/test_trafego_contrato_canais.py \
  backend/tests/test_trafego_capacidades.py \
  backend/tests/test_trafego_plano_persistido.py \
  -q
```

Resultado conhecido:

```text
12 failed, 316 passed, 4 warnings in 7.06s
```

## 12 falhas conhecidas

| Teste | Classificação inicial |
|---|---|
| `volc_ads/campanha/testes_display.py::test_o_registro_de_subir_e_uma_vista_do_perfil_e_nao_uma_segunda_lista` | expectativa antiga / atualização incompleta |
| `volc_ads/campanha/testes_display.py::test_o_canal_que_nao_cria_declara_a_ausencia_em_vez_de_ficar_vazio` | expectativa antiga / atualização incompleta |
| `volc_ads/campanha/testes_demand_gen.py::test_perfil_prova_demand_gen_mas_registry_real_e_executor_recusam` | expectativa antiga / atualização incompleta |
| `volc_ads/campanha/testes_pmax.py::test_pmax_continua_sem_construtor_no_perfil_e_no_executor` | expectativa antiga / atualização incompleta |
| `volc_ads/campanha/testes_pmax.py::test_pmax_planeja_mesmo_sem_construtor` | expectativa antiga / atualização incompleta |
| `volc_ads/campanha/testes_pmax.py::test_o_plano_de_pmax_carrega_codigo_proprio_e_nao_o_de_canal_inexistente` | expectativa antiga / atualização incompleta |
| `volc_ads/campanha/testes_pmax.py::test_exigir_prova_recusa_pmax_e_exigir_planejador_aceita` | expectativa antiga / atualização incompleta |
| `volc_ads/campanha/testes_pmax.py::test_o_plano_declara_as_ausencias_em_vez_de_escondê_las` | expectativa antiga / atualização incompleta; precisa adjudicar novo opt-out explícito |
| `volc_ads/campanha/testes_plano.py::test_o_perfil_e_o_plano_concordam_sobre_quem_planeja` | expectativa antiga / atualização incompleta |
| `volc_ads/testes_subir.py::test_canal_sem_construtor_falha_antes_de_montar[PERFORMANCE_MAX-PERFORMANCE_MAX]` | expectativa antiga / atualização incompleta |
| `volc_ads/testes_subir.py::test_canal_sem_construtor_falha_antes_de_montar[PMAX-PERFORMANCE_MAX]` | expectativa antiga / atualização incompleta |
| `backend/tests/test_trafego_plano_persistido.py::test_o_plano_persistido_nao_abre_a_criacao_de_pmax` | expectativa antiga / atualização incompleta / ainda não adjudicada contra HTTP |

Nenhuma falha acima deve ser convertida em sucesso por documentação. A próxima sessão precisa atualizar código/testes ou reverter/adjudicar conforme o contrato final.

## Zero mutação externa

- Zero chamada Google Ads nesta etapa de checkpoint.
- Zero `validate_only` real nesta missão multichannel.
- Zero campanha criada.
- Zero Google Ads mutate.
- Zero Supabase write.
- Zero n8n.
- Zero WordPress.
- Zero Data Manager.
- Zero deploy.
- Zero merge em `volc-os-v2` ou `main`.
- Zero rebase, amend ou force push.

## Próximo comando recomendado para retomada

```bash
cd /root/work/volc-runs/hermes-gads-multichannel-birth-v1
python3 -m pytest volc_ads/campanha/testes_multichannel_birth_v1.py -q
python3 -m pytest \
  volc_ads/campanha/testes_display.py \
  volc_ads/campanha/testes_demand_gen.py \
  volc_ads/campanha/testes_pmax.py \
  volc_ads/campanha/testes_plano.py \
  volc_ads/testes_subir.py \
  backend/tests/test_trafego_contrato_canais.py \
  backend/tests/test_trafego_capacidades.py \
  backend/tests/test_trafego_plano_persistido.py \
  -q
```

Retomar pela reconciliação dos testes antigos e pela confirmação do contrato HTTP de PMax, sem declarar aceitação até suíte focal verde e revisão final Gemini.
