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

---

## Segunda leitura: a campanha 24195821946, e o filtro por resource name

A primeira leitura foi de CONTA (`campaign_id=None`, o caso do nascimento). Esta
segunda é contra a campanha canário real — e ela existe para provar por EXECUÇÃO
a única afirmação que estava apoiada só na documentação: que
`conversion_goal_campaign_config.campaign` é filtrável, e que o valor é o resource
name `customers/{cid}/campaigns/{id}` e não `campaign.id`.

```
ler_nivel(5478096539, "24195821946")
  → ('com_dados', 'CUSTOMER', None, None)

ler_metas_da_campanha(5478096539, "24195821946")
  → estado: com_dados
       PURCHASE/WEBSITE  biddable: False
       DOWNLOAD/APP      biddable: True
```

O filtro funcionou: a consulta executou e devolveu a linha da campanha. E o que
ela devolveu é a **reprodução exata** do fato que criou P05-T12 no roadmap —
`goal_config_level=CUSTOMER` e o único `campaign_conversion_goal` biddable é
`DOWNLOAD/APP`, enquanto a conta declara compras como primárias.

⚠️ Repare que as metas da campanha EXISTEM (`com_dados`, duas linhas) e **não
decidem**: com o nível em `CUSTOMER`, quem manda é a conta. `metas_que_mandam`
devolve a lista da conta. Neste caso específico as duas listas concordam — o que
é esperado, já que a campanha herda —, e por isso o teste que separa os dois
níveis usa fixture, e não esta conta.

Plano montado com a campanha real:

```
completo    = false
acao_alvo   = null
causa       = "o objetivo desta campanha (DOWNLOAD/APP) existe na conta, e a única
               ação que o mede está marcada como NÃO primária — o que a torna
               não-biddable em toda campanha, qualquer que seja a meta."
```
