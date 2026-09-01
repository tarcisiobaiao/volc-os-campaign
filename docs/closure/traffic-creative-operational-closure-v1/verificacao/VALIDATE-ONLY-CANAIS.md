# `validate_only` real por canal — comando, resposta e o que ela ensinou

*Worker 2 (channel-builders) · 01/09/2026 · branch
`sprint/traffic-creative-operational-closure-v1`*

## 0. Escopo da autorização, e o que NÃO foi feito

| Ação | Estado |
|---|---|
| Leitura GAQL (`conversion_action`) na conta 547-809-6539 | **EXECUTADA** |
| `validate_only=True` na conta 547-809-6539 via MCC 601-673-9364 | **EXECUTADO** |
| `validate_only` em qualquer outra conta | **NÃO EXECUTADO** |
| **Mutate real (`validate_only=False`)** | **NÃO EXECUTADO, em conta nenhuma** |
| Criar, ativar, pausar, remover, alterar budget ou bidding | **NÃO EXECUTADO** |
| `FORGE_PERMITIR_ESCRITA` / `modo.destravar()` | **NÃO TOCADOS** |

`volc_ads/gads/client.validar_mutacoes()` fixa `request.validate_only = True` e
`partial_failure = False`. `mutar()` não é importado nem chamado por nenhum
módulo desta entrega —
`testes_pmax.py::test_ler_mensuracao_nao_tem_caminho_para_mutar` lê a árvore
sintática de `campanha/pmax.py` e derruba a suíte se `mutar` ou `destravar`
aparecerem entre os importados ou os chamados.

⚠️ **A conta 547-809-6539 NÃO é `test_account` do Google** — leitura do próprio
`customer` devolve `test_account=False`, moeda BRL. Ela é "de teste" no sentido
operacional do VOLC, não no técnico. Logo a validação que ela aplica é a de
PRODUÇÃO, que é mais estrita — o que torna estes resultados mais fortes, e um
`validate_only=False` acidental mais caro.

---

## 1. Display — **APROVADO**

```
display.validar("5478096539", brief, login_customer_id="6016739364")
```

**Resposta:** `falha is None` · **9 operações** · `resultado.ok is True`.

Grafo: `campaign_budget` → `campaign` (DISPLAY, PAUSED) → `campaign_criterion`
(geo) → `campaign_criterion` (idioma) → `ad_group` (DISPLAY_STANDARD) →
3 × `asset_operation` (imagens com bytes inline) → `ad_group_ad`
(responsive_display_ad).

Brief usado: `budget_diario=10.0`, `MAXIMIZE_CONVERSIONS`, 2 headlines,
1 long headline, 2 descriptions, business name, e três `ImagemParaSubir` com
PNG real — 1200×628 (marketing), 1200×1200 (quadrada), 1200×1200 (logo
quadrado), **cada uma com bytes distintos**.

### 1.1 A primeira tentativa foi RECUSADA, e o defeito era nosso

```
asset_error.DUPLICATE_ASSETS_WITH_DIFFERENT_FIELD_VALUE
  @mutate_operations[7].asset_operation.create.name:
  Duplicate assets across mutates cannot have different asset level fields.
mutate_error.RESOURCE_NOT_FOUND
  @mutate_operations[8].ad_group_ad_operation.create.ad.responsive_display_ad.square_marketing_images: Resource was not found.
mutate_error.RESOURCE_NOT_FOUND
  @mutate_operations[8].ad_group_ad_operation.create.ad.responsive_display_ad.square_logo_images: Resource was not found.
mutate_error.RESOURCE_NOT_FOUND
  @mutate_operations[8].ad_group_ad_operation.create.ad.responsive_display_ad.marketing_images: Resource was not found.
```

`RequestId: EepaLiOkghFZmlwHARty3A`.

**Causa:** duas imagens com os MESMOS BYTES em papéis diferentes e `name`
distinto. O Google identifica asset pelo **conteúdo**; dois
`asset_operation.create` com a mesma imagem e nomes diferentes são o mesmo asset
pedindo dois nomes, e ele recusa o request inteiro. Os três `RESOURCE_NOT_FOUND`
são cascata: os ids temporários dos assets recusados deixaram de resolver — **o
sintoma aparece no ANÚNCIO e a causa está no ASSET**.

**Demand Gen já tinha guarda de duplicidade por conteúdo. Display não tinha.**
A assimetria era invisível offline, e a suíte ficava verde sobre um payload que
a API recusa — porque a fixture `_png()` devolvia sempre os mesmos bytes.

Correções: `06a0d12` (a fixture parou de mentir) e `2b6392f` (a guarda em
`display.py`). Provas:
`testes_display.py::test_asset_repetido_por_conteudo_e_recusado_como_a_api_recusa`,
`::test_resource_name_repetido_tambem_e_recusado` e
`::test_artes_diferentes_por_papel_continuam_passando` — este último existe
porque uma recusa que dispara no caso legítimo é uma recusa que alguém desliga.

---

## 2. Demand Gen — **APROVADO**

```
demand_gen.validar("5478096539", brief, login_customer_id="6016739364")
```

**Resposta:** `falha is None` · **9 operações** · `resultado.ok is True`, com
`budget_diario=60.0`.

Grafo: budget → campanha (DEMAND_GEN, PAUSED, `upgraded_targeting=False`) →
geo → idioma → ad group → 3 × asset → `demand_gen_multi_asset_ad`.

### 2.1 Constraint real descoberta: mínimo de orçamento por dia

Com `budget_diario=10.0`, a API recusou:

```
campaign_budget_error.BUDGET_BELOW_PER_DAY_MINIMUM
  @mutate_operations[1].campaign_operation.create.campaign_budget:
  Budget amount or total amount must be above the per-day minimum.
  See the error's details.budget_per_day_minimum_error_details field for more information.
```

E o `details` traz o número exato:

```
budget_per_day_minimum_error_details {
  currency_code: "BRL"
  budget_per_day_minimum_micros: 25400000
  minimum_budget_amount_micros: 25400000
  failed_budget_amount_micros: 10000000
}
```

**R$ 25,40/dia** é o mínimo de Demand Gen nesta conta, nesta moeda. Display
aceitou os mesmos R$ 10,00 — **o mínimo é por canal**, não da conta.

⚠️ **Este número NÃO foi codificado em `limites.yaml`, e a omissão é
deliberada.** Ele depende da moeda (`currency_code: "BRL"`) e a API o entrega
por conta. Gravar `25.40` num YAML que vale para os seis países da operação
transformaria um fato medido numa mentira em cinco deles — exatamente o defeito
que a nota dos `snippet_headers_es` já documenta no mesmo arquivo. O caminho
certo está no backlog: traduzir `BUDGET_BELOW_PER_DAY_MINIMUM` num bloqueio
legível que carregue o mínimo que a própria API devolveu.

---

## 3. Performance Max — **RECUSA LOCAL: a mensuração barrou antes da API**

### 3.1 A leitura (somente leitura, autorizada)

```
pmax.ler_mensuracao("5478096539", login_customer_id="6016739364")
```

**10 ações de conversão lidas · 0 válidas para lance · 0 com valor.**

| Ação | tipo | status | primária | inclui em conversões |
|---|---|:--:|:--:|:--:|
| `AdClick` | WEBPAGE | ENABLED | ✅ | ❌ |
| `adViewInterstitial` | WEBPAGE | ENABLED | ✅ | ❌ |
| `adView` | WEBPAGE | ENABLED | ✅ | ❌ |
| `[BR] - [Portalmundomais.com] (web) purchase` | GA4_PURCHASE | **HIDDEN** | ❌ | ❌ |
| `Compra` | WEBPAGE | ENABLED | ✅ | ❌ |
| `adViewRewarded` | WEBPAGE | ENABLED | ✅ | ❌ |
| `adviewinterstitial - Programa Pé de Meia` | WEBPAGE | ENABLED | ✅ | ❌ |
| `adviewinterstitial - RG Digital` | WEBPAGE | ENABLED | ✅ | ❌ |
| `adviewinterstitial - Cursos Senai` | WEBPAGE | ENABLED | ✅ | ❌ |
| `Android installs (all other apps)` | ANDROID_INSTALLS | ENABLED | ❌ | ❌ |

**Nenhuma das dez tem `include_in_conversions_metric = True`.** Elas estão
ligadas e são primárias da meta, mas ficam FORA da métrica de conversões que o
Smart Bidding otimiza. Uma campanha PMax nessa conta gastaria em Search,
Display, YouTube, Discover, Gmail e Maps — **sem controle de rede, por
construção do canal** — otimizando por um sinal que não entra na conta.

### 3.2 O portão

```
pmax.validar("5478096539", brief, login_customer_id="6016739364")
```

**Resposta:** recusa LOCAL, `0 operações`, **a chamada à API nunca aconteceu**:

```
[erro] pmax.mensuracao: nenhuma ação de conversão está ENABLED, primária da meta
       e incluída na métrica de conversões ao mesmo tempo. As três condições são
       da API, não de gosto: pausada não recebe, fora de
       include_in_conversions_metric não entra na métrica que o lance otimiza, e
       não-primária não participa do objetivo. Criação e ativação de PMax ficam
       BLOQUEADAS
       →  '10 ações lidas, 0 válidas'

[aviso] pmax.mensuracao: `conversoes_ultimos_30d` é None em todas as ações
        válidas: ninguém mediu o volume. Isso NÃO é zero conversões — é a
        ausência da medida
       →  'volume não medido'
```

**Este é o resultado que a missão pediu, e ele veio de uma conta real.** O
bloqueio não é o construtor ausente fazendo o trabalho: é a régua de mensuração,
aplicada sobre dez ações lidas por GAQL. `testes_pmax.py::
test_mensuracao_inadequada_bloqueia_mesmo_com_canal_habilitado` força a
prontidão para "tudo liberado" e exige que o bloqueio continue de pé — sem esse
teste, o portão desapareceria junto no dia em que alguém habilitasse o canal, e
a suíte continuaria verde.

### 3.3 O que substitui o `validate_only` que PMax não rodou

O payload de PMax **não chegou à API**, e por dois motivos independentes: o
canal está fora do registro do executor (decisão de 01/09/2026, ratificada) e a
mensuração da conta é inadequada. No lugar da prova externa:

| Prova | Onde |
|---|---|
| 15 objetos v25 instanciados e serializados, incluindo 5 `MutateOperation` | `testes_pmax.py::test_sdk_v25_real_instancia_e_serializa_o_grafo_pmax` |
| Todas as operações do plano serializam; impressão sha256 de 64 chars | `::test_todas_as_operacoes_do_plano_serializam_de_verdade` |
| Montagem com `socket.socket` levantando (offline por FORÇA) | `testes_demand_gen.py::test_protos_v25_e_grafo_sao_montados_com_a_rede_FECHADA` |
| Cobertura de asset julgada por `observabilidade_pmax` | `::test_a_cobertura_do_plano_usa_a_regua_do_observador` |

Um plano completo de PMax sai com **27 operações e 19.928 bytes de protobuf
serializado** (medido com o brief de referência).

---

## 4. Search — não tocado

Search foi provado num canário real (campanha `24195821946`, PAUSED, ledger
v10) na sprint anterior. Esta entrega **não reexecutou** `validate_only` de
Search e **não alterou** o caminho de montagem dele — a única mudança em
`search.py` é a conferência da própria lista de lances, que recusa
`MAXIMIZE_CONVERSION_VALUE` e não altera nenhum payload que antes era válido.
`testes_search.py` continua verde, com a mesma contagem.

---

## 5. Reprodução

O roteiro está em `scripts/` **não**: ele foi executado a partir de um script de
scratchpad, deliberadamente não versionado, porque um script que fala com a
conta real não deve ficar a um `python` de distância de alguém. Os comandos
exatos estão nas seções acima e reproduzem a partir de:

```python
from volc_ads.campanha import display, demand_gen, pmax
# imagens: PNG real por papel, BYTES DISTINTOS entre papéis
display.validar("5478096539", brief, login_customer_id="6016739364")
demand_gen.validar("5478096539", brief, login_customer_id="6016739364")  # budget >= 25.40
recibo = pmax.ler_mensuracao("5478096539", login_customer_id="6016739364")
pmax.validar("5478096539", brief_com(recibo), login_customer_id="6016739364")
```
