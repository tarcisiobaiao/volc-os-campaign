# Gates

Base: `origin/volc-os-v2 @ 34dc7b41bce901bd8bebfdec0a01e293678cbf08`
Branch: `sprint/pautador-paid-keyword-eligibility-v1`
Worktree: `/private/tmp/volc-pautador-paid-keyword-eligibility-v1`
Python: `backend/.venv/bin/python` (3.14) · `pytest.ini` com `asyncio_mode = auto`

Nenhuma suíte completa rodou em paralelo com outra.

## Baseline, medido ANTES de tocar em qualquer código

```
backend/tests/test_mining_pipeline.py test_api_kw_funnel.py
test_funnel_grounding.py test_funnel_roles.py test_funnel_prompt.py
test_funnel_reviewer.py test_entity_funnel_semantic.py
    -> 61 passed em 0,86s
```

## Focais, durante o trabalho

| gate | resultado |
|---|---|
| contraprovas da lane (`test_pautador_paid_keyword_counterproofs.py`) | **61 passed** — 61 coletados, 0 pulados |
| focais do Pautador/mineração (11 arquivos, inclui o baseline acima) | **158 passed** |
| `motor_pautas/testes` + `volc_ads` (ponte + critério) | **190 passed** |

As 61 contraprovas nasceram TODAS vermelhas no commit `ed37cb5`, antes de
qualquer correção. Nenhuma descreve código que já funcionava.

## Fechamento, sequencial

| gate | resultado |
|---|---|
| `backend/tests` inteiro | **3113 passed, 112 skipped** em 89,54s |
| `backend/tests` + `motor_pautas/testes` + `volc_ads` (após a rodada Codex) | **3315 passed, 112 skipped** em 94,13s |
| TypeScript (`tsc --noEmit`) | **sem erro** |
| `vite build` | **ok, 7,69s** |
| `git diff --check` | **limpo** |
| scanner de segredos sobre o diff completo | **0 ocorrências** |
| arquivos do benchmark versionados | **0** |
| chamada de mutação Google introduzida | **0** (o único casamento textual é a frase de DECISION-CONTRACT.json dizendo que `ready_for_campaign_plan` NÃO é "autorização para mutate") |

Os 112 `skipped` são herdados do baseline e não têm relação com esta lane.

## Queda de baseline

Nenhuma. O conjunto focal saiu de 61 para 158 passed porque a lane ACRESCENTOU
testes; nenhum teste pré-existente mudou de resultado, e nenhum foi editado.

Uma mudança de COMPORTAMENTO — deliberada, não regressão — precisa ficar
registrada: `gold_miner_classify` passou a exigir preço medido na regra de
preço, então `production_ads_queue` pode ficar MENOR do que ficava para
entradas sem CPC. Os testes existentes de Gold Miner passam sem alteração
porque todas as suas fixtures declaram CPC explicitamente. A prova de que essa
é a correção, e não uma perda, está em `COUNTERPROOFS.md` seção D: antes, o
mesmo termo era aprovado sem CPC e descartado com CPC 4,20.

## Ownership

Nenhum arquivo fora da fronteira da lane foi tocado. Em particular, seguem
intactos e não aparecem no diff:

```
backend/app/landing_policy/**
backend/app/routers/publicacao.py
backend/app/routers/trafego.py
backend/app/routers/pautador.py
volc_ads/pautador_ponte.py
volc_ads/campanha/criterio.py
volc-os-workbook/ROADMAP-VIVO.json
docs/volc-os-graph/**
supabase/migrations/**
```

`volc_ads` foi LIDO para reaproveitar `Criterio` em vez de duplicá-lo, e a
importação é preguiçosa justamente para não criar dependência dura da
mineração num pacote de outra lane.

## Ações externas

| ação | estado |
|---|---|
| mutate no Google Ads | **nenhuma** |
| criar/alterar/pausar/remover/ativar campanha | **nenhuma** |
| criar keyword ou negativa em conta | **nenhuma** |
| alterar lance ou orçamento | **nenhuma** |
| DataForSEO pago | **nenhuma chamada** |
| Supabase WRITE | **nenhuma** |
| Supabase READ | GET em `pautador_keyword_clusters`: 3 linhas de índice + 1 linha completa (`id=7`) |
| migration | **nenhuma** |
| WordPress / n8n / deploy | **nenhum** |
| merge em `volc-os-v2` ou `main` | **nenhum** |
| escrita no benchmark Webgo | **nenhuma** |

## Revisão cross-model

| revisor | modelo | veredito | achados |
|---|---|---|---|
| Codex | `gpt-5.6-sol`, effort high, sandbox read-only | **BLOCK** → 11 achados reproduzidos e fechados | ver `COUNTERPROOFS.md` |
| Gemini | `gemini-3.7-flash` via API, pacote sanitizado | **APROVADO_COM_RESSALVAS** | 4 achados reproduzidos e fechados |

A primeira execução do Codex morreu sem produzir relatório: eu estava editando
a worktree enquanto ele lia, e ele reiniciou a análise até esgotar. Está
registrado porque a causa foi minha, não dele — a segunda execução rodou contra
uma árvore congelada em `a4194e2` e entregou o relatório acima.

Ao Gemini foi enviado apenas código do VOLC, com o run-id do benchmark e as
estatísticas agregadas dele REDIGIDOS antes do envio (a sanitização é
verificada por asserção no script, não por inspeção). Nenhum dataset, métrica
privada por campanha, página privada ou dado cru do benchmark saiu da máquina.

---

# Rodada 2 — wiring do nascimento da campanha

## Processo órfão, adjudicado

`PID 32870` — o shell que esperava `codex-review.md` da PRIMEIRA execução do
Codex, que morreu sem escrever o arquivo. Rodava havia 48 minutos num `until`
que nunca terminaria. Encerrado, e só ele.

Os 7 processos `vite` vivos pertencem a outras lanes
(`volc-baseline-main`, `volc-estudio-criativo`, `volc-search-measurement-ux-v1`,
`volc-design-review-global`, `volc-review-estudio-criativo`,
`volc-integration-estudio-criativo`, `volc-runtime-current`) e seguem intactos —
conferido antes e depois.

## Gates

| gate | resultado |
|---|---|
| focais da lane (elegibilidade + wiring + mining + api) | **101 passed** |
| contraprovas do caminho real (`test_pautador_campaign_birth_wiring.py`) | **18 passed** |
| ponte/tráfego (7 arquivos de trafego + volc_ads) | **249 passed, 13 skipped** |
| integração (`backend/tests` + `motor_pautas` + `volc_ads`) | **3333 passed, 112 skipped** em 100,12s |
| TypeScript (`tsc --noEmit`) | **sem erro** |
| `vite build` | **ok, 12,36s** |
| `git diff --check` | **limpo** |
| scanner de segredos | **0 ocorrências** |
| mutate Google introduzido | **0** |

Baseline anterior: 3315 passed / 112 skipped. Agora 3333 / 112 — **+18, que são
exatamente as contraprovas novas. Nenhum teste pré-existente mudou de
resultado.**

## Uma queda transitória, causada e resolvida

Ao ligar o portão, 5 testes de `test_trafego_portoes_de_escrita.py` passaram a
falhar com `N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED`. **Foi regressão minha,
e o portão estava certo**: a fixture hermética `_linhas_da_rota` monta um
cluster com `production_ads_queue` e sem `conjunto_pago` — exatamente a
assinatura que o portão recusa.

A correção foi dar à fixture o que o contrato agora exige, construído pelo
MOTOR REAL sobre a mesma keyword da própria fixture — não um segundo algoritmo,
e não um afrouxamento do portão. A fixture continua sendo "recorte mínimo da
porta de leitura; o contrato depois dela é real", que é o que ela sempre
declarou ser.

## Um teste que já falhava sozinho, e não é meu

`test_trafego_canario.py::test_provar_e_subir_reconstroem_o_mesmo_plano_antes_da_rede`
falha quando o arquivo roda ISOLADO, tentando alcançar `oauth2.googleapis.com`
por `contas.meta_de_conversao`. Conferido contra a base com `git stash`: falha
igual, com o mesmo endereço, **sem nenhuma alteração desta lane**. É dependência
de ordem — o autouse `_leituras_vivas_desligadas` vive noutro arquivo — e na
suíte completa ele passa. Registrado por honestidade, não corrigido: mexer nele
seria a rodada arquitetural que esta missão proíbe.

---

# Rodada 3 — mutação pós-aprovação fechada

O fechamento anterior ainda permitia que o corpo HTTP acrescentasse uma
positiva com outro match type ou retirasse uma selecionada por
`keywords_fora`, depois de `approved_set_sha256` existir. A contraprova
material mediu 3 positivas aprovadas virando 4 critérios, com o mesmo termo em
`PHRASE` e `EXACT`.

## Gates desta microcorreção

| gate | resultado |
|---|---|
| `test_pautador_campaign_birth_wiring.py` | **33 passed** — inclui chamadas diretas de `/provar` e `/subir` para as duas mutações |
| suíte ampla compatível com o sandbox (`backend/tests` + `backend/app/motor_pautas/testes` + `volc_ads`, menos os 3 arquivos abaixo) | **3882 passed, 112 skipped** em 52,52s |
| `py_compile` dos 3 arquivos tocados | **verde** |
| `gate_sem_mutacao_google.py` no venv | **3/3 verde**, incluindo 5 contraprovas da rota |
| `verificar_segredos.py` | **nenhum padrão forte** |
| `git diff --check` | **limpo** |

O comando amplo literal também foi tentado. Ele chegou a **3891 passed, 113
skipped**, mas terminou com 9 falhas e 99 erros exclusivamente nas famílias
`test_adspower_broker_hermetico.py`, `test_publicacao_organica_e2e.py` e
`test_trafego_persistencia.py`: o sandbox Codex recusou `bind()` em loopback e
`initdb` com `PermissionError`. A repetição excluiu somente esses três arquivos
ambientalmente impedidos e ficou verde. Não foi pedido acesso externo porque a
missão proíbe rede/serviços reais e os gates diretamente afetados já são
herméticos.

O gate completo herdado do HEAD `406b08c` continua sendo **3333 passed, 112
skipped**. Ele não é reapresentado como se tivesse sido executado depois desta
microcorreção.

## Confirmação — mesmo alvo, ambiente sem a restrição de sandbox

O comando usado ao longo de todo este fechamento —
`backend/tests` + `backend/app/motor_pautas/testes` + `volc_ads/testes_pautador_ponte.py`
+ `volc_ads/campanha/testes_criterio.py` — foi reexecutado nesta sessão, num
ambiente sem a limitação de `bind()`/`initdb` relatada acima.

```
3348 passed, 112 skipped, 0 failed, 0 error, em 93,40s
```

Isso inclui, sem exclusão, os três arquivos que o sandbox anterior não
conseguiu coletar (`test_adspower_broker_hermetico.py`,
`test_publicacao_organica_e2e.py`, `test_trafego_persistencia.py`) —
confirmados aqui, isolados: **117 passed, 1 skipped**, zero falha. A restrição
relatada era mesmo do ambiente, não um defeito desta lane.

`3348 = 3333 (baseline do HEAD 406b08c) + 15`, e 15 é exatamente o número de
casos novos em `test_pautador_campaign_birth_wiring.py` desta rodada (33 − 18).
Nenhum teste pré-existente mudou de resultado. Este é o número que a lane
carrega como evidência de fechamento — completo, sem exclusão de arquivo,
zero falha.

`tsc --noEmit` e `vite build` confirmados de novo nesta sessão, sem erro.
