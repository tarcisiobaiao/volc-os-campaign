# Contrato dos canais para a API — o que o Worker 3 chama

*Worker 2 (channel-builders) → Worker 3 (traffic-api-ui). Branch
`sprint/traffic-creative-operational-closure-v1`.*

> **Estado deste documento.** Escrito no início da rodada para não travar o
> Worker 3, e **fechado em 01/09/2026 com o código de pé**. Onde este texto e o
> código divergirem, **o código é a autoridade** — me avise, não contorne.
> A seção 9 lista onde cada afirmação é provada, com o nome do teste.

---

## 1. A regra de import que não pode ser quebrada

`backend/app/**` **não depende do SDK do Google em tempo de import**, e dois
testes de árvore sintática vigiam isso (`backend/tests/test_trafego_plataforma.py`,
`backend/tests/test_trafego_canal_de_criacao.py`). O contrato respeita a regra
separando os dois lados:

| Módulo | Importa o SDK? | Pode entrar no topo de um arquivo do backend? |
|---|---|---|
| `volc_ads.campanha.plano` | **Não.** Dataclasses puras | **Sim** |
| `volc_ads.campanha.{search,display,demand_gen,pmax}` | **Sim** | **Não** — import tardio, dentro da função |
| `volc_ads.campanha.perfil` | Sim (importa os canais) | **Não** — import tardio |

Ou seja: os **tipos** viajam livres, o **planejador** entra tarde. É o mesmo
desenho que `trafego.py` já usa com `_ponte()`.

---

## 2. Função de entrada — uma por canal, mesma assinatura

```python
def planejar(cid: str, brief: Brief, *, login_customer_id: str) -> PlanoDeCanal
```

| Canal | Módulo | Entrada |
|---|---|---|
| Search | `volc_ads.campanha.search` | `search.planejar(...)` |
| Display | `volc_ads.campanha.display` | `display.planejar(...)` |
| Demand Gen | `volc_ads.campanha.demand_gen` | `demand_gen.planejar(...)` |
| Performance Max | `volc_ads.campanha.pmax` | `pmax.planejar(...)` |

Search aceita ainda `ai_max: bool = False`, que é opção **só dele**
(`search.OPCOES`). Pedir `ai_max` em outro canal é recusado, não ignorado.

Despacho por nome, sem `if canal == …` na camada HTTP:

```python
from volc_ads.campanha import perfil          # import TARDIO, dentro da função
plano = perfil.planejar(canal, cid, brief, login_customer_id=mcc)
```

`perfil.planejar()` levanta `perfil.CanalSemPlanejador` para canal que não sabe
planejar, e `perfil.OpcaoIndisponivel` para opção que o canal não tem.

**`planejar()` nunca fala com o Google.** Ele monta o grafo offline e projeta.
`validate_only` continua sendo `validar()`, chamada à parte.

---

## 3. Tipo do brief — o que já existia

`volc_ads.campanha.brief.Brief`. Um brief para os quatro canais; cada canal
opera um subconjunto e **recusa** — nunca descarta em silêncio — o que não é
dele. Os campos por canal:

| Campo do `Brief` | Search | Display | Demand Gen | PMax |
|---|:--:|:--:|:--:|:--:|
| `copy.headlines` | ✅ 3–15 | ✅ 1–5 | ✅ 1–5 | ✅ 3–15 |
| `copy.long_headlines` | — | ✅ 1 (singular) | — | ✅ 1–5 |
| `copy.descriptions` | ✅ 2–4 | ✅ 1–5 | ✅ 1–5 | ✅ 2–5 (uma ≤ 60) |
| `copy.business_name` | — | ✅ 1 | ✅ 1 | ✅ 1 |
| `copy.sitelinks/callouts/snippet` | ✅ | ❌ recusa | ❌ recusa | ❌ recusa |
| `keywords` / `match_type` | ✅ | ❌ recusa | ❌ recusa | ❌ recusa (só negativa) |
| `negativas_campanha` | ✅ | — | — | ✅ (até 10.000) |
| `sub_intencoes` | ✅ (N ad groups) | ❌ recusa | ❌ recusa | ❌ recusa |
| `imagens_display` | — | ✅ | ❌ recusa | ❌ recusa |
| `imagens_demand_gen` | — | ❌ recusa | ✅ | ❌ recusa |
| `imagens_pmax` | — | ❌ recusa | ❌ recusa | ✅ |
| `demand_gen` (config) | — | — | ✅ obrigatória | — |
| `pmax` (config) | — | — | — | ✅ obrigatória |
| `estrategia_lance` | `MANUAL_CPC`, `MAXIMIZE_CONVERSIONS` | `MAXIMIZE_CONVERSIONS` | `MAXIMIZE_CONVERSIONS` | `MAXIMIZE_CONVERSIONS`, `MAXIMIZE_CONVERSION_VALUE` |
| `videos` | — | ✅ (resource name) | ❌ recusa | ✅ (resource name) |
| `ai_max` | ✅ | ❌ recusa | ❌ recusa | ❌ recusa |

---

## 4. Tipo do plano — `plano.PlanoDeCanal`

`volc_ads.campanha.plano`. Todos os campos são JSON-nativos depois de
`.para_json()`: `str`, `int`, `float`, `bool`, `None`, `list`, `dict`. Não há
`datetime`, `Enum`, `bytes` nem protobuf no retorno.

```jsonc
{
  "canal": "DISPLAY",
  "customer_id": "8017851692",
  "login_customer_id": "6016739364",
  "nome_da_campanha": "BR - 20260901_072600 / Saque Anual / https://… [Display]",
  "tipo_de_campanha": "DISPLAY",          // advertising_channel_type
  "status_inicial": "PAUSED",             // a campanha SEMPRE nasce pausada
  "url_final": "https://creditoup.com.br/r/saque-anual/",

  "orcamento": {
    "diario_micros": 10000000,            // micros; a moeda é da CONTA, não do plano
    "total_micros": null,
    "periodo": "UNSPECIFIED",             // "DAILY" quando o canal o declara
    "compartilhado": false,
    "estrategia_lance": "MAXIMIZE_CONVERSIONS",
    "tcpa_micros": null,
    "target_roas": null
  },

  "segmentacao": {
    "criterios": [
      {"tipo": "location", "valor": "geoTargetConstants/2076",
       "nivel": "campanha", "negativo": false},
      {"tipo": "language", "valor": "languageConstants/1014",
       "nivel": "campanha", "negativo": false}
    ],
    "sinais": [],                          // AssetGroupSignal — só PMax
    "nivel_geo_idioma": "campanha",        // "ad_group" em Demand Gen upgraded
    "aberto_por_ausencia": ["audiencia"]   // ⚠️ ver §6
  },

  "unidades": [                            // ad_group nos 3 canais; asset_group em PMax
    {
      "tipo": "ad_group",                  // "ad_group" | "asset_group"
      "nome": "AdGroup_20260901_072600",
      "status": "ENABLED",
      "urls_finais": [],
      "anuncios": [
        {
          "tipo": "responsive_display_ad",
          "headlines": ["…"], "long_headlines": ["…"], "descriptions": ["…"],
          "business_name": "Credito Up",
          "urls_finais": ["https://…"],
          "status": "ENABLED",
          "assets": [
            {"papel": "MARKETING_IMAGE", "origem": "resource_name",
             "identidade": "customers/8017851692/assets/111",
             "conteudo_hash": null, "mime": null, "largura": null,
             "altura": null, "bytes_totais": null,
             "com_recibo": null, "catalogo_id": null}
          ]
        }
      ],
      "assets": [],                        // preenchido em PMax (AssetGroupAsset)
      "criterios": [],
      "sinais": []
    }
  ],

  "assets_de_campanha": [],                // CampaignAsset (PMax com brand guidelines)

  "bloqueios": [ {"codigo":"…","campo":"…","causa":"…","valor":"…"} ],
  "avisos":    [ {"codigo":"…","campo":"…","causa":"…","valor":"…"} ],
  "nao_operado": ["sitelink: Display não declara field_type para extensões"],

  "prontidao": {
    "monta": true,
    "pode_provar": true,
    "pode_criar": true,
    "motivo_nao_monta": "", "motivo_nao_prova": "", "motivo_nao_cria": ""
  },

  "codigos_de_bloqueio": ["CONTEUDO_REPROVADO"],   // distintos, na ordem de ocorrência

  "operacoes": {
    "quantidade": 6,
    "tipos": ["campaign_budget_operation", "campaign_operation", …],
    "bytes": 1234,                          // soma dos protos serializados
    "impressao": "sha256 hex das operações, em ordem"
  }
}
```

### O plano é PROJEÇÃO do payload, não uma segunda montagem

`planejar()` chama o `construir()` do canal e **lê as operações protobuf que
iriam para a API**. Não existe um segundo caminho que remonte o plano a partir
do brief — logo não existe divergência possível entre o que a tela mostra e o
que seria enviado. `operacoes.bytes` e `operacoes.impressao` são prova
executável de que o grafo v25 existe e serializa.

`impressao` **não é** o `Selo` de `subir.py`. O selo é emitido depois do
`validate_only` aprovado e é o que autoriza gastar; `impressao` é só a
identidade do payload projetado. Não use um no lugar do outro.

---

## 5. Readiness — três perguntas, três respostas, três motivos

`prontidao` responde separadamente, e **nenhuma resposta é derivada das outras**:

| Campo | Pergunta | Falso significa |
|---|---|---|
| `monta` | O grafo foi emitido? | Nenhuma operação existe — veja `bloqueios` |
| `pode_provar` | `validate_only` é permitido para este canal? | Fronteira externa fechada; veja `motivo_nao_prova` |
| `pode_criar` | O executor encaminha este canal ao mutate real? | Veja `motivo_nao_cria` |

Estado por canal **hoje**:

| Canal | `monta` | `pode_provar` | `pode_criar` |
|---|:--:|:--:|:--:|
| Search | ✅ | ✅ | ✅ (provado em canário real, `24195821946`, PAUSED) |
| Display | ✅ | ✅ — **`validate_only` APROVADO em 01/09/2026**, 9 operações | ✅ |
| Demand Gen | ✅ | ✅ — **`validate_only` APROVADO em 01/09/2026**, 9 operações | ❌ (motivo cita `PROVADORES_POR_CANAL` × `CONSTRUTORES_POR_CANAL`) |
| Performance Max | ✅ **se e só se** os requisitos reais existirem | ❌ `PMAX_FORA_DO_EXECUTOR` | ❌ (dois bloqueios independentes; ver abaixo) |

⚠️ **`pode_provar` é a capacidade do BUILDER, não a da rota.** Demand Gen sabe
provar; a rota HTTP acrescenta um portão de ambiente
(`VOLC_DEMAND_GEN_VALIDATE_ONLY`) que não é fato do módulo de canal, e afirmá-lo
lá seria o builder declarar algo que quem o lê não pode verificar.

⚠️ **PMax tem DOIS bloqueios de criação, e eles são independentes.** O canal está
fora do executor, *e* a régua de mensuração precisa passar. O segundo continua
valendo no dia em que o primeiro sair —
`testes_pmax.py::test_mensuracao_inadequada_bloqueia_mesmo_com_canal_habilitado`
força a prontidão para "tudo liberado" e exige que o bloqueio de mensuração
continue de pé. Sem esse teste, o portão desapareceria junto com o outro e a
suíte continuaria verde.

Medido em 01/09/2026 contra a conta real: das **10 ações de conversão** da
Portal Mundo Mais, **zero** têm `include_in_conversions_metric = True`. O
bloqueio de PMax nessa conta é factual, não hipotético. Detalhes em
`verificacao/VALIDATE-ONLY-CANAIS.md` §3.

⚠️ **PMax não está no registro do executor.** `perfil.PERFORMANCE_MAX.construtor`
continua `None` de propósito: promovê-lo mudaria `perfil.canais_que_provam()`, e
`volc_ads/subir.py` levanta no import quando a vista dele e o perfil discordam —
o que quebraria a rota HTTP inteira, para todos os canais. `pmax.planejar()` e
`pmax.construir()` existem e são chamáveis diretamente; `POST /api/trafego/provar`
com `canal=PMAX` **continua devendo responder 422**, como o teste
`backend/tests/test_trafego_canal_de_criacao.py::test_provar_recusa_canal_sem_builder_com_422`
exige. Habilitar exige mudança coordenada em `subir.py` + backend + `plataforma.py`,
e está registrado em `backlog-channel-builders.md`.

---

## 6. `ausente ≠ zero ≠ falha ≠ não aplicável`

Os quatro estados moram em lugares diferentes, e a tela **precisa** distingui-los:

| Estado | Onde aparece | Exemplo |
|---|---|---|
| **ausente** | `null` em campo opcional | `orcamento.tcpa_micros: null` — ninguém definiu tCPA |
| **zero** | o número `0` | só aparece quando a API o recebeu de fato |
| **falha** | item em `bloqueios`, com `codigo` | `{"codigo":"ASSET_SEM_RECIBO", …}` |
| **não aplicável** | string em `nao_operado` | `"sitelink: Display não declara field_type"` |

E o quinto, que é o mais caro deste domínio:

**`segmentacao.aberto_por_ausencia`** — uma campanha sem critério de audiência
**não** é "segmentada com zero audiências": ela roda em **inventário aberto**,
escolhido pelo lance. Renderize isso com todas as letras. Uma lista de audiências
vazia ao lado de um rótulo "Segmentação" é a mentira mais cara que esta tela pode
contar.

---

## 7. Códigos de bloqueio — a lista fechada

`volc_ads.campanha.plano.CODIGOS`. São **estáveis**: o `causa` (texto em
português) pode ser reescrito a qualquer momento; o `codigo` não. Ligue
comportamento de UI ao código, **nunca** a substring da causa.

| Código | Significa | Canais |
|---|---|---|
| `CANAL_SEM_BUILDER` | O canal não tem builder — nada a planejar | todos |
| `SDK_V25_INDISPONIVEL` | O `google-ads` instalado não tem o namespace/campo v25 emitido | DG, PMax |
| `CONTEUDO_REPROVADO` | Texto fora de limite, contagem, duplicata ou DKI | todos |
| `POLITICA_REPROVADA` | Texto barrado no portão país × vertical | todos |
| `ASSET_OBRIGATORIO_AUSENTE` | Papel de asset exigido pelo formato veio vazio | DIS, DG, PMax |
| `ASSET_ACIMA_DO_TETO` | Papel de asset acima do máximo (ou do teto combinado) | DIS, DG, PMax |
| `ASSET_SEM_RECIBO` | Asset chegou sem `ReciboAssetAprovado` da ponte criativa | DG, PMax |
| `ASSET_RECIBO_DIVERGENTE` | Recibo existe e não bate com bytes, papel, hash, canal ou conta | DG, PMax |
| `RESOURCE_NAME_INVALIDO` | Fora de `customers/<cid>/assets/<id>`, ou id temporário | DIS, DG, PMax |
| `CAMPO_NAO_OPERADO` | O brief trouxe campo que este canal não opera | todos |
| `CONFIGURACAO_AUSENTE` | Decisão obrigatória do canal não foi tomada (nem `True` nem `False`) | DG, PMax |
| `LANCE_NAO_PERMITIDO` | `estrategia_lance` fora da lista fechada do canal | todos |
| `MENSURACAO_INADEQUADA` | Sem conversão válida declarada — **PMax não pode ser criado** | PMax |
| `SINAL_OBRIGATORIO_AUSENTE` | Subtipo exige `AssetGroupSignal` e não veio nenhum | PMax |
| `CRIACAO_NAO_AUTORIZADA` | O grafo monta, o executor não encaminha ao mutate real | DG, PMax |
| `PMAX_FORA_DO_EXECUTOR` | PMax planeja e serializa offline; a porta do executor ainda não abriu | PMax |
| `PROVA_EXTERNA_NAO_AUTORIZADA` | O grafo monta, o `validate_only` não está habilitado | DG, PMax |
| `VALIDATE_ONLY_RECUSADO` | A API respondeu recusando o payload | todos |
| `BLOQUEIO_NAO_CLASSIFICADO` | Achado real que a tabela ainda não nomeia | todos |

`BLOQUEIO_NAO_CLASSIFICADO` **não é silêncio**: é um contrato explícito de que a
UI deve mostrar o `causa` cru em vez de decidir sozinha. Se ele aparecer com
frequência num campo, me avise — é tabela minha a completar, não bug seu.

---

## 8. `validate_only` — quando existir tela para isso

```python
resultado, falha, n_ops = <canal>.validar(cid, brief, login_customer_id=mcc)
```

- `falha is None` **e** `resultado.ok` → payload aprovado pela API.
- `falha` é um `volc_ads.gads.errors.FalhaGads` classificado; use
  `falha.resumo()` para texto e `falha.classe` para decidir retry.
- `resultado.ok is False` → **nem chegou à API**; `n_ops == 0`.

Autorização desta sprint: `validate_only` **exclusivamente** na conta
Portal Mundo Mais `547-809-6539` via MCC `601-673-9364`. **Mutate real é
proibido** em qualquer conta, e não foi executado em nenhuma.

⚠️ Essa conta **não é `test_account` do Google** (`test_account=False`, moeda
BRL). Ela é "de teste" no sentido operacional do VOLC. A validação que ela
aplica é a de PRODUÇÃO — mais estrita, o que torna a aprovação mais forte e um
`validate_only=False` acidental mais caro.

**Executado em 01/09/2026** (registro completo em
`verificacao/VALIDATE-ONLY-CANAIS.md`):

| Canal | Resultado | Operações |
|---|---|---|
| Display | **APROVADO** (`falha is None`) | 9 |
| Demand Gen | **APROVADO** (`falha is None`) | 9 |
| Performance Max | recusa **local** pelo portão de mensuração; não chegou à API | 0 |

Duas constraints reais que a API ensinou e que a UI precisa saber:

1. **Asset é identificado pelo CONTEÚDO.** Dois assets com os mesmos bytes e
   nomes diferentes fazem a API recusar o request inteiro
   (`asset_error.DUPLICATE_ASSETS_WITH_DIFFERENT_FIELD_VALUE`), com o sintoma
   aparecendo no ANÚNCIO (`RESOURCE_NOT_FOUND` em cascata) e a causa no asset.
   Display agora barra localmente; a mensagem cita o erro da API.
2. **Demand Gen tem mínimo de orçamento por dia que Display não tem.** Em BRL,
   nessa conta: **R$ 25,40**. A API devolve o número em
   `budget_per_day_minimum_error_details`. Não está em `limites.yaml` porque é
   por moeda — ver `backlog-channel-builders.md` §1.

---

## 9. Prova — onde cada afirmação deste documento é verificada

| Afirmação | Prova |
|---|---|
| `plano` não importa o SDK (nem nada de `campanha/`) | `testes_plano.py::test_plano_nao_importa_o_sdk_do_google` — por árvore sintática |
| O retorno é JSON-nativo até as folhas | `testes_plano.py::test_o_plano_e_json_nativo_ate_as_folhas` |
| O plano é projeção do payload, não segunda montagem | `testes_plano.py::test_o_plano_le_as_operacoes_reais_de_display` |
| `impressao` identifica o payload e muda quando ele muda | `testes_plano.py::test_a_impressao_e_dos_bytes_e_muda_quando_o_payload_muda` |
| Um tipo de plano para os quatro canais | `testes_plano.py::test_todos_os_canais_projetam_com_o_mesmo_vocabulario` |
| Search não colapsa a partição em N ad groups | `testes_plano.py::test_search_particiona_em_ad_groups_e_o_plano_mostra_todos` |
| `ausente ≠ zero` no orçamento | `testes_plano.py::test_ausencia_de_tcpa_nao_vira_zero` |
| Os quatro estados moram em campos diferentes | `testes_plano.py::test_os_quatro_estados_moram_em_campos_diferentes` |
| **Display sem imagem bloqueia, não vira plano feliz** | `testes_plano.py::test_display_sem_imagem_e_bloqueio_e_nao_plano_feliz` |
| As três perguntas de prontidão são independentes | `testes_plano.py::test_prontidao_responde_as_tres_perguntas_separadamente` |
| `CANAL_SEM_BUILDER` só quando nada mais explica | `testes_plano.py::test_canal_sem_builder_so_aparece_quando_nada_mais_explica` |
| Códigos de bloqueio são fechados e estáveis | `testes_plano.py::test_todo_codigo_emitido_esta_na_lista_publicada` |
| O código dito pelo builder ganha do adivinhado | `testes_plano.py::test_o_codigo_dito_pelo_builder_ganha_do_adivinhado` |
| Código desconhecido é declarado, não silencioso | `testes_plano.py::test_codigo_desconhecido_e_declarado_e_nao_silencioso` |
| `canais_que_planejam ⊇ canais_que_provam ⊇ canais_que_criam` | `testes_plano.py::test_o_perfil_e_o_plano_concordam_sobre_quem_planeja` |
| `PMAX` como apelido resolve sem vazar (ADR-18) | `testes_plano.py::test_planejar_por_apelido_de_tela_funciona_sem_apelido_vazar` |
| PMax nunca é tratado como Search (sem ad group, sem anúncio, sem rede) | `testes_pmax.py::test_pmax_nao_reaproveita_contrato_de_search` |
| Keyword em PMax só existe como negativa | `testes_pmax.py::test_keyword_positiva_e_recusada_e_a_negativa_vira_criterio` |
| Brand guidelines decide o NÍVEL de BUSINESS_NAME/LOGO | `testes_pmax.py::test_brand_guidelines_decide_o_NIVEL_de_business_name_e_logo` |
| PMax sem mensuração válida não é criável | `testes_pmax.py::test_mensuracao_inadequada_bloqueia_criacao_e_prova` |
| **E o portão de mensuração vale POR SI, sem depender do canal desabilitado** | `testes_pmax.py::test_mensuracao_inadequada_bloqueia_mesmo_com_canal_habilitado` |
| Recibo de mensuração autoatestado não é leitura | `testes_pmax.py::test_recibo_de_mensuracao_autoatestado_nao_e_leitura` |
| PMax instancia e serializa 15 objetos v25 REAIS | `testes_pmax.py::test_sdk_v25_real_instancia_e_serializa_o_grafo_pmax` |
| Nenhum caminho de `pmax.py` alcança `mutar` nem `destravar` | `testes_pmax.py::test_ler_mensuracao_nao_tem_caminho_para_mutar` — por árvore sintática |
| A cobertura de asset usa a régua de `observabilidade_pmax` | `testes_pmax.py::test_a_cobertura_do_plano_usa_a_regua_do_observador` |
| PMax continua fora do executor, com código próprio | `testes_pmax.py::test_pmax_continua_sem_construtor_no_perfil_e_no_executor` · `::test_o_plano_de_pmax_carrega_codigo_proprio_e_nao_o_de_canal_inexistente` |
| Demand Gen monta offline com a rede FECHADA | `testes_demand_gen.py::test_protos_v25_e_grafo_sao_montados_com_a_rede_FECHADA` |
| Demand Gen prova e não cria, e o plano diz isso | `testes_demand_gen.py::test_o_plano_de_demand_gen_diz_que_prova_e_nao_cria` |
| Asset duplicado por conteúdo é recusado como a API recusa | `testes_display.py::test_asset_repetido_por_conteudo_e_recusado_como_a_api_recusa` |
| E a guarda não dispara no caso legítimo | `testes_display.py::test_artes_diferentes_por_papel_continuam_passando` |
| Search segue intacto | `testes_search.py`, contagem inalterada |

**Gate:** `backend/.venv/bin/python -m pytest volc_ads/campanha -q` →
**267 passed** (baseline na base: 193).
