# Leitura VIVA da conta real — 01/09/2026

*Somente leitura. Cinco GAQL `SELECT`. Nenhum recurso criado, alterado ou removido.*
*Conta 5478096539 (Portal Mundo Mais) sob o MCC 6016739364.*

Esta leitura não é telemetria: ela **derrubou um defeito meu** e é a prova de que
o portão de Smart Bidding deixou de ser infalsificável.

## O que a conta respondeu

| fato | valor lido |
|---|---|
| `goal_config_level` | **CUSTOMER** (a campanha herda a conta) |
| metas da conta | 2 lidas, `com_dados` |
| meta **biddable** | **uma só: `DOWNLOAD/APP`** |
| ações de conversão | 10, `com_dados` |
| ação que mede DOWNLOAD/APP | `#7498530235`, tipo `ANDROID_INSTALLS_ALL_OTHER_APPS` |
| `primary_for_goal` dela | **`false` DECLARADO** (não ausente) |
| auto-tagging | ligado |
| tracking | `#17862729897`, dono `5478096539`, `MANAGED_BY_SELF`, termos aceitos |
| ações com tag do Google | 8 |
| ações de GA4 | 0 |

## O defeito que isso expôs

A primeira versão de `eleger_acao_canonica` caía em `primarias or candidatas` —
o default otimista. Com ele, o sistema **elegeu** a ação `#7498530235` e devolveu:

```
conversion_goal_status = PRONTO
measurement_readiness  = PRONTO
```

Isso está errado, e a doc oficial não deixa margem:

> "If a conversion action's `primary_for_goal` bit is false, the conversion
> action is non-biddable for all campaigns **regardless** of their customer
> conversion goal or campaign conversion goal."

Uma ação não-biddable eleita como alvo é um alvo que o lance **não persegue**: o
plano diria "medido por #7498530235" e o Google não estaria medindo nada por ela.

## O que a conta responde depois do conserto

```
meta_efetiva.resolvida = true          (há objetivo: DOWNLOAD/APP)
acao_alvo              = null
acao_alvo_causa        = "o objetivo desta campanha (DOWNLOAD/APP) existe na conta,
                          e a única ação que o mede está marcada como NÃO primária
                          — o que a torna não-biddable em toda campanha, qualquer
                          que seja a meta."
destino.resolvido      = false
conversion_goal_status = NAO_PRONTO
conversion_signal_status = PRONTO   ← tag do Google + auto-tagging, COMPROVADOS
measurement_readiness  = NAO_PRONTO
observability_status   = INDETERMINADO
smart_bidding_eligible = false
```

⚠️ Repare no par: `conversion_signal_status` chegou a **PRONTO** por leitura real,
e `smart_bidding_eligible` continuou `false`. Antes desta entrega, `PRONTO` era
inalcançável em qualquer campo de G1 — e por isso "Smart Bidding está bloqueado"
passava com QUALQUER entrada, inclusive com uma conta perfeitamente medida.

## Fronteiras

- Google Ads **mutate**: nenhum.
- Data Manager: nenhum evento, nem em `validateOnly`.
- Supabase: nenhuma escrita, nenhuma migration aplicada.
