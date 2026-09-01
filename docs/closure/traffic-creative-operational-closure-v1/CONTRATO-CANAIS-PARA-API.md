# Contrato dos canais para a API — o que o Worker 3 chama

*Worker 2 (channel-builders) → Worker 3 (traffic-api-ui). Branch
`sprint/traffic-creative-operational-closure-v1`.*

> **Estado deste documento.** Escrito no início da rodada para não travar o
> Worker 3, e atualizado conforme o código ficou de pé. Onde este texto e o
> código divergirem, **o código é a autoridade** — me avise, não contorne.
> A seção 9 lista o que cada afirmação prova, e onde.

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
| Display | ✅ | ✅ | ✅ |
| Demand Gen | ✅ | ✅ **só com `VOLC_DEMAND_GEN_VALIDATE_ONLY`** | ❌ `CRIACAO_NAO_AUTORIZADA` |
| Performance Max | ✅ **se e só se** os requisitos reais existirem | ❌ **hoje** — `PROVA_EXTERNA_NAO_AUTORIZADA` | ❌ `MENSURACAO_INADEQUADA` / `CRIACAO_NAO_AUTORIZADA` |

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

Autorização desta sprint: `validate_only` **exclusivamente** na conta de teste
Portal Mundo Mais `547-809-6539` via MCC `601-673-9364`. **Mutate real é
proibido** em qualquer conta.

---

## 9. Prova — onde cada afirmação deste documento é verificada

| Afirmação | Prova |
|---|---|
| `plano` não importa o SDK | `testes_plano.py::test_plano_nao_importa_o_sdk_do_google` |
| O plano é projeção do payload, não segunda montagem | `testes_plano.py::test_o_plano_le_as_operacoes_reais_de_display` |
| `ausente ≠ zero` no orçamento | `testes_plano.py::test_ausencia_de_tcpa_nao_vira_zero` |
| Códigos de bloqueio são estáveis e fechados | `testes_plano.py::test_todo_codigo_emitido_esta_na_lista_publicada` |
| PMax nunca é tratado como Search | `testes_pmax.py::test_pmax_nao_reaproveita_contrato_de_search` |
| PMax sem mensuração válida não é criável | `testes_pmax.py::test_mensuracao_inadequada_bloqueia_criacao_e_prova` |
| PMax instancia e serializa protos v25 | `testes_pmax.py::test_sdk_v25_real_instancia_e_serializa_o_grafo_pmax` |
| PMax continua fora do registro do executor | `testes_pmax.py::test_pmax_continua_sem_construtor_no_perfil_e_no_executor` |
| Search segue intacto | `testes_search.py` (33 provas, contagem inalterada) |
