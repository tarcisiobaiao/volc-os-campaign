# Prova — validate_only real contra a conta Meta

Primeira execução real de `execution_options=validate_only` desta lane contra a
Marketing API v26.0. Duas chamadas foram observadas, ambas disparadas por
**clique explícito do operador**; o agente não disparou nenhuma.

**Zero objetos criados. Zero mutate. Zero ativação.**

> ⚠️ **Classificação: `ROOTS_VALIDATE_ONLY_ACCEPTED`.**
> Não é `FULL_PLAN_ACCEPTED` e não deve ser lido como tal em nenhum artefato
> derivado. A cobertura é parcial por construção — ver secção 4.

---

## 1. As duas chamadas

| # | HEAD | Status | Resultado |
|---|---|---|---|
| 1 | `17b40f8cdbfa03c6c5c502d3ccb8c46c5552acc9` | **422** | Meta recusou — código 100, subcódigo 4005 |
| 2 | `c46f0cded9b03455ba56c7e4996c01f4f7ca5441` | **200** | `ROOTS_VALIDATE_ONLY_ACCEPTED` |

Ambiente: worktree `/private/tmp/volc-os-operacao-80-20`, branch
`execution/volc-os-operacao-80-20`, árvore limpa nos dois cliques, backend
subido por `./start-dev.sh --meta-validate-only`.

Gates de segurança ativos nos dois momentos, verificados no processo:
`META_VALIDATE_ONLY_ENABLED=1`; `FORGE_PERMITIR_ESCRITA` **ausente**;
`META_CREATE_LEDGER_WRITE_ENABLED` **ausente**. As rotas `criar`, `nascer`,
`aprovar`, `habilitar` e `ativar` responderam **404** em todas as sondas — doze
sondas, todas 404, nenhuma delas partindo da interface.

---

## 2. A recusa (chamada 1)

```
objeto:     campaign
código:     100
subcódigo:  4005
mensagem:   Não é possível usar o compartilhamento do orçamento do conjunto
            de anúncios sem uma estratégia de lance.
```

**Causa factual.** O plano levava `is_adset_budget_sharing_enabled=true`. A
receita P0 tem exatamente um AdSet, com orçamento e `bid_strategy` no AdSet e
nenhuma estratégia de lance no Campaign. Com um único conjunto, compartilhar
orçamento não produz benefício operacional — e a correção que a Meta aceitaria,
mover uma estratégia de lance para o Campaign, mudaria a semântica da receita
aprovada.

**Correção aplicada** (commit `dc8a362`), sem tocar na receita:

- a receita fixa `is_adset_budget_sharing_enabled=false`;
- o campo continua viajando **explícito** no form-urlencoded como `false` —
  nunca omitido, porque a ausência não é neutra do lado da Meta;
- `true` passa a ser **recusado localmente** com
  `META_BUDGET_SHARING_REQUIRES_MULTI_ADSET_RECIPE`, antes de qualquer chamada,
  em vez de convertido em silêncio: a conversão faria o payload divergir da
  intenção aprovada e o hash deixaria de descrever o que o operador pediu;
- **nenhum `bid_strategy` foi adicionado ao Campaign**;
- a rota passou a validar o plano **antes** de abrir o Keychain, então uma
  recusa local não toca segredo nem rede.

---

## 3. A aceitação (chamada 2)

```
status:                            200
classificação:                     ROOTS_VALIDATE_ONLY_ACCEPTED
cobertura:                         INDEPENDENT_ROOTS_ONLY
plano_sha256:                      10e5b56aaf0d1d4c4b87bc309532c148463f40ab721ac44de6b60cfcb061d767
operações compiladas:              4
operacoes_validadas:               campaign, creative:variation-001
operacoes_dependentes_pendentes:   adset, ad:variation-001
objetos_criados:                   0
conta:                             metaacct_55c4…04f9f  (referência opaca, mascarada)
ativo:                             metaasset_ef9b…f145  (referência opaca, mascarada)
endpoint lógico:                   POST /api/trafego/meta/local/criacao/validar
                                   → graph.facebook.com/v26.0/act_<conta>/campaigns
                                   → graph.facebook.com/v26.0/act_<conta>/adcreatives
código / subcódigo:                nenhum
campo recusado:                    nenhum
```

Nenhum token, nenhum ID bruto da Meta e nenhuma URL assinada de CDN aparecem
neste documento, nos logs desta rodada ou na resposta da rota. O caminho Meta
não tem uma única instrução de log — é o que garante isso — e o corpo da
resposta existiu apenas no navegador do operador, de onde os valores acima foram
transcritos.

---

## 4. O que este 200 prova, e o que não prova

### Provado pela Meta

| Objeto | Campos exercitados |
|---|---|
| **Campaign** | `objective=OUTCOME_TRAFFIC`, `buying_type=AUCTION`, `special_ad_categories`, `status=PAUSED`, **`is_adset_budget_sharing_enabled=false`** |
| **AdCreative** (×1) | `object_story_spec`, `link_data`, `image_hash`, `link`, `message`, `name`, `description`, `call_to_action` |

### NÃO provado — continua sem validação remota

| Objeto | Campos que nunca chegaram à Meta |
|---|---|
| **AdSet** | `targeting_automation.advantage_audience`, **ausência de `destination_type`**, `optimization_goal=LANDING_PAGE_VIEWS`, `daily_budget`, `billing_event`, `bid_strategy`, `start_time`, `targeting` |
| **Ad** (×1) | `adset_id`, `creative_id`, `status=PAUSED`, `name` |

A razão é estrutural, não uma omissão: AdSet e Ad carregam os marcadores
`$campaign.id` / `$adset.id` / `$creative.id`, e a Meta não aceita um filho antes
de o pai existir. `validar_raizes` (`executor.py`) só despacha operações marcadas
`validavel_sem_criar_pai=True` — a Campaign e os N AdCreatives — e devolve as
demais em `operacoes_dependentes_pendentes`. A própria resposta declara isso em
`cobertura="INDEPENDENT_ROOTS_ONLY"`.

**Consequência operacional:** a metade mais arriscada da receita —
Advantage+ Audience, orçamento, agendamento, otimização por LPV e a ausência
deliberada de `destination_type` — só será exercitada contra a Meta no primeiro
canário PAUSED, que continua não autorizado e sem rota montada.

---

## 5. O que continua pendente

1. **Migration oficial não aplicada.** `20260904183418_meta_create_paused_executor.sql`
   segue fora do Supabase oficial. Ver `RUNBOOK-MIGRATION-META-CREATE-PAUSED.md`.
2. **Canário PAUSED não executado.** Não existe rota de criação; `criar_pausada`
   não tem chamador de produção; `META_CREATE_LEDGER_WRITE_ENABLED` fechado.
3. **AdSet e Ad sem validação remota**, como na secção 4.
4. **Sem inspeção visual no navegador.** A extensão do Chrome não esteve
   conectada em nenhum momento desta missão. A tela foi exercitada por testes em
   jsdom e pelo próprio operador, não por inspeção automatizada.
5. Riscos remanescentes do caminho PAUSED em `REMAINING-RISKS.md` e na secção 9
   do runbook da migration.
