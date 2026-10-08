# GADS-CRIACAO-CANAIS v1.2 — a configuração de cada canal na criação (Google Ads)

## Changelog

**v1.2 (08/10/2026)** — ⚠️ **estratégia divergente é o MESMO 422 nos quatro
canais.** `estrategia_lance` do envelope diferente de
`configuracao_<canal>.lance.estrategia` → 422 `ESTRATEGIA_DIVERGENTE`,
`loc ["body","estrategia_lance"]`, julgado no validador do envelope (antes do
escopo, da ponte e de qualquer chamada ao Google), em `/provar` e `/subir`.
Antes só Demand Gen fazia isso; Search e Display deixavam a divergência chegar
ao builder, que a devolvia como bloqueio LOCAL do plano (HTTP 200 sem selo).
Envelope ausente não é divergência em Search/Display (a efetiva é a da
configuração); Demand Gen continua exigindo o envelope. PMax não tem lance na
configuração (`configuracao_pmax.lance` → `CAMPO_DESCONHECIDO`): a única fonte é
o envelope. Regra também publicada em `regras` do esquema; `versao` do esquema
`GADS-CRIACAO-CANAIS-v1.2`. Detalhe no §3, "Estratégia: envelope ×
configuração".

**v1.1 (08/10/2026)** — fecha as cinco divergências que o front de criação
encontrou entre a v1 e o comportamento real. Nenhum campo saiu; o que muda para
quem consome está marcado com ⚠️.

1. **Default de `configuracao_demand_gen.automacoes`** era `[]` num campo
   `type: object` (o gerador de esquema publicava o default interno do
   dataclass, uma tupla de pares). Corrigido NA ORIGEM (`config_json.esquema`:
   a forma canônica declarada pelo canal traz o próprio default): agora `{}`.
   O esquema inteiro passou a ser conferido em teste (nenhum `default` de tipo
   diferente do `type`). Tabela §6.3 regenerada.
2. ⚠️ **TODO 422 de configuração no formato do §2** — lista `detail[]`, um item
   por campo, `loc` exato, `msg` sem prefixo técnico (`Value error, …`) e
   `ctx.codigo` estável. Antes: Display/Demand Gen devolviam o campo que o
   builder não trata como `detail` em FRASE, e a configuração de outro canal
   como `loc: ["body"]` sem `ctx`. Os códigos `CONFIGURACAO_INVALIDA` e
   `CONFIGURACAO_DE_OUTRO_CANAL` do 422 foram substituídos pelo vocabulário do
   §2 (`VALOR_INVALIDO`, `CAMPO_DESCONHECIDO`, `CANAL_DIFERENTE`…). O código
   `CONFIGURACAO_INVALIDA` de BLOQUEIO do plano (`preparo`) não mudou.
3. **`POST /api/trafego/planejar-pmax` aceita `configuracao_pmax`** (§1): a
   configuração PMax pode ser julgada e projetada localmente mesmo com a prova
   PMax fechada por flag (`/provar` → 403).
4. **`target_roas` declarado para os quatro canais** (§3, "Metas"): razão,
   0,01–1000, `4.0` = 400%. Display, Demand Gen e PMax aceitavam qualquer
   positivo (PMax, até negativo) e agora recusam fora da faixa, como Search.
5. **Prova viva de Display `MANUAL_CPM`** (§7): `validate_only` real aceito.

**v1 (08/10/2026)** — primeira versão.

Contrato HTTP de `POST /api/trafego/provar` e `POST /api/trafego/subir` para os
quatro canais (Search, Display, Demand Gen, Performance Max), para quem faz o
front. Backend: `backend/app/routers/trafego.py` (HTTP) →
`backend/app/trafego/configuracao_canais.py` (adaptador JSON ⇄ motor) →
`volc_ads/campanha/<canal>_config.py` (a régua de cada canal) →
`volc_ads/campanha/config_json.py` (forma e esquema, uma régua para os quatro).

**Esquema vivo:** `GET /api/trafego/canais/esquema` devolve o JSON Schema
(draft 2020-12) de cada configuração, gerado dos MESMOS dataclasses que validam
o pedido — enums, limites e defaults vêm de lá. As tabelas do §6 foram geradas
desse esquema em 08/10/2026 (regeneradas na v1.1); em caso de divergência, a
rota vence. `versao` do esquema: `GADS-CRIACAO-CANAIS-v1.2`.

---

## 1. O que mudou no envelope

`ProvarEntrada` / `SubirEntrada` ganharam cinco campos opcionais:

| campo | canal | o que é |
|---|---|---|
| `configuracao_search` | SEARCH | `ConfiguracaoSearch` — lance (5 estratégias), rede, AI Max, RSA (path/fixação), agenda, dispositivo, geo, datas, meta de conversão |
| `configuracao_display` | DISPLAY | `ConfiguracaoDisplay` — lance (5), segmentação, exclusões, frequência, agenda, dispositivos, presença geo, RDA |
| `configuracao_demand_gen` | DEMAND_GEN | só a parte **v25** de `ConfiguracaoDemandGenV25` — formato (multi-asset/vídeo/carrossel), lance, CTA, vídeo, público, agenda, automações. A base continua no objeto `demand_gen` |
| `configuracao_pmax` | PERFORMANCE_MAX | só a parte **v25** de `ConfiguracaoPMaxV25` — path, URL options, vídeos, asset groups adicionais, automações, crawl, exclusões, guias, negativas tipadas, marcas, metas. A base continua no objeto `pmax` |
| `match_por_keyword` | SEARCH | `{chave(texto): "EXACT"\|"PHRASE"\|"BROAD"}` — o `rascunho.matchPorKeyword` da tela (§4) |

**`POST /api/trafego/planejar-pmax` (v1.1)** aceita o mesmo `configuracao_pmax`.
É a projeção LOCAL de PMax — sem flag, sem leitura da conta, sem
`validate_only`, sem mutate — e julga a configuração exatamente como `/provar`:
mesma forma (422 do §2 antes do escopo), mesmo adaptador (`cfgcan.de_pmax`) e o
mesmo portão de política nas imagens de `grupos_adicionais[i].imagens`. A única
diferença é a base: a mensuração fica `None` (a rota não lê a conta), e o plano
nomeia `MENSURACAO_INADEQUADA` + `PMAX_FORA_DO_EXECUTOR` em vez de fingir um
recibo. Quando há vídeo por id, a resposta traz `videos_sem_portao_de_politica`
(lista de ids) — o mesmo fato que `/provar` põe no aviso
`VIDEO_SEM_PORTAO_DE_POLITICA`.

**A dependência de flag, declarada:** a prova externa de PMax (`/provar` com
`canal=PERFORMANCE_MAX`) continua atrás de `servidor_oferece_pmax_validate_only`
+ capacidade da sessão; com a flag fechada, `/provar` responde **403** antes de
julgar qualquer coisa. Para validar a forma e ver o plano com a configuração,
use `/planejar-pmax`, que não depende dela. O mesmo vale para Demand Gen
(`servidor_oferece_demand_gen_validate_only`), que não tem rota de projeção
local: com a flag fechada, a configuração DG não é julgada por HTTP.

`ReconciliarEntrada` ganhou `asset_groups_esperados` (inteiro ≥ 1): PMax com
grupos adicionais declara quantos asset groups o plano criou, e a releitura
acusa DIVERGENTE se a conta tiver menos.

**Ausente (`null` ou omitido) = o comportamento de antes, byte a byte.** Provado:
a impressão dos payloads legados dos quatro canais é idêntica antes e depois
desta versão (sha dos protos), e a impressão aprovável do plano não ganha
chave nenhuma.

## 2. Regras de fronteira

1. **Um objeto por canal, e só o do `canal` do pedido.** `configuracao_display`
   num pedido `canal=SEARCH` → **422** `CANAL_DIFERENTE` com `loc` no campo (o
   validador do envelope recusa antes de qualquer projeção). Vale também para
   `match_por_keyword` fora de Search e para os objetos verticais de outro
   canal (`demand_gen`, `assets_demand_gen`, `assets_display`, `pmax`,
   `assets_pmax`).
2. **Chave desconhecida é 422, nunca descarte**, em qualquer nível.
3. **Tipo errado é 422, sem coerção**: `"3"` não vira `3`, `0/1` não vira booleano.
4. **Combinação impossível é 422** — é o `__post_init__` do dataclass do motor
   que julga (ex.: `TARGET_IMPRESSION_SHARE` sem teto, `path2` sem `path1`,
   `formato=VIDEO_RESPONSIVO` sem `video`).
5. A forma é julgada **antes do escopo e de qualquer rede**: nenhum 422 de
   configuração fala com o Google.
6. Objeto presente **entra na impressão aprovável** do plano: trocar um campo
   entre `/provar` e `/subir` invalida a autorização (como trocar uma headline).
   No ledger, números da configuração viajam como decimal em texto (`1`, `1.0`
   e `1.00` são a mesma chave).

### Formato do 422 de configuração

O mesmo de qualquer erro de corpo do FastAPI — `detail[]`, **um item por campo
recusado**, `loc` exato:

```json
{"detail": [{
  "type": "valor_invalido",
  "loc": ["body", "configuracao_display", "frequencia", 0, "impressoes"],
  "msg": "esperado inteiro, veio texto",
  "input": null,
  "ctx": {"codigo": "VALOR_INVALIDO",
          "caminho": "configuracao_display.frequencia[0].impressoes"}
}]}
```

Garantias (v1.1, valem para TODO 422 de configuração, nas rotas `/provar`,
`/subir` e `/planejar-pmax`, venha ele do validador do envelope, da guarda do
canal ou da montagem):

- `detail` é sempre **lista** — nunca uma frase solta;
- `loc` começa em `"body"` e aponta o **campo** (nunca só `["body"]`);
- `msg` é a frase para gente, **sem** o prefixo `Value error, …`;
- `ctx.codigo` é um dos códigos abaixo — é por ele que a tela ramifica;
- `ctx.caminho` é o mesmo endereço em notação de ponto;
- `type` é informativo: o código em minúsculas, exceto na projeção estrita de
  Demand Gen, que preserva o tipo nativo do pydantic (`extra_forbidden`,
  `too_long`, `string_too_long`…) para não quebrar quem já o lia.

| `ctx.codigo` | quando | exemplo de `loc` |
|---|---|---|
| `CAMPO_DESCONHECIDO` | chave que o dataclass do canal não tem (em qualquer nível), ou campo fora da projeção estrita de Demand Gen | `["body","configuracao_search","lance","teto"]`, `["body","campo_fantasma"]` |
| `CAMPO_OBRIGATORIO` | campo sem default ausente; objeto vertical obrigatório ausente (`pmax`, `assets_pmax`, `demand_gen`, `assets_demand_gen`); `cpc_inicial` com Display `MANUAL_CPC` | `["body","cpc_inicial"]` |
| `VALOR_INVALIDO` | tipo errado, enum fora da lista, faixa (ex.: `target_roas`), combinação impossível julgada pelo motor | `["body","target_roas"]`, `["body","configuracao_search","lance"]` |
| `CANAL_DIFERENTE` | configuração / objeto vertical / `match_por_keyword` de outro canal | `["body","configuracao_display"]` |
| `CAMPO_NAO_OPERADO` | campo do envelope que o builder do canal pedido não materializa (`match_type`, `keywords_fora`, `ai_max`, `cpc_inicial`… em Display/DG/PMax) | `["body","match_type"]` |
| `ESTRATEGIA_DIVERGENTE` | `estrategia_lance` do envelope ≠ `configuracao_<canal>.lance.estrategia` — Search, Display e Demand Gen (v1.2); em DG também o envelope ausente | `["body","estrategia_lance"]` |
| `MATCH_FORA_DO_CONJUNTO` | `match_por_keyword` com chave fora do conjunto pago aprovado (§4) | `["body","match_por_keyword","<chave>"]` |

Quando o motor recusa a COMBINAÇÃO, o `loc` aponta o objeto que a contém
(`["body", "configuracao_search", "lance"]`) e `msg` traz a frase do motor.

Fora deste formato continuam só os 422 que **não são de configuração**: erro
de forma nativo do pydantic no envelope de Search (campos legados), recusa da
política criativa (`detail` objeto com `codigo POLICY_*`) e as recusas do
`Brief` que não dependem de configuração (país, URL…), que seguem em frase.

Recusas que dependem da conta ou do brief (lista de outra conta, local de outro
país, ajuste de lance num regime que o ignora, agenda sobreposta no Display…)
não são 422 de forma: voltam no `preparo` da prova como bloqueio do plano, com
o código `CONFIGURACAO_INVALIDA` (novo em `plano.CODIGOS`; antes caíam em
`BLOQUEIO_NAO_CLASSIFICADO`).

## 3. Regras por canal

### Search
- **Lance**: `MANUAL_CPC`, `TARGET_SPEND` (maximizar cliques; teto opcional),
  `MAXIMIZE_CONVERSIONS` (tCPA opcional), `MAXIMIZE_CONVERSION_VALUE` (tROAS
  opcional), `TARGET_IMPRESSION_SHARE` (local + fração + teto obrigatórios).
  `MAXIMIZE_CLICKS` não existe — o nome da API é `TARGET_SPEND`.
- Com `configuracao_search.lance` declarado e `estrategia_lance` AUSENTE,
  **a estratégia efetiva é a da configuração** — é ela que o brief carrega,
  que o portão de mensuração julga e que fica registrada. Presente e
  diferente (inclusive `MANUAL_CPC` explícito) → 422 `ESTRATEGIA_DIVERGENTE`
  (v1.2; ver "Estratégia: envelope × configuração").
- **Rede**: com configuração, a rede é decisão obrigatória (em `rede` do
  envelope OU em `configuracao_search.rede`; as duas iguais se vierem as
  duas). `display_expansion=true` é aceito e sempre gera aviso no plano. O
  canário de Search continua recusando parceiros e expansão.
- BROAD (por keyword ou por AI Max com correspondência de termos) só com lance
  por conversão.

### Display
- **Lance**: `MAXIMIZE_CONVERSIONS` (com `tcpa` do envelope vira `target_cpa`),
  `MAXIMIZE_CONVERSION_VALUE` (`target_roas` do envelope agora chega ao brief),
  `TARGET_SPEND`, `MANUAL_CPC`, `MANUAL_CPM` (exige `lance.cpm_visivel`). Pelo
  envelope sem configuração: MaxConv, MaxConvValue e TARGET_SPEND.
- `MANUAL_CPC` na configuração **exige `cpc_inicial` explícito** no envelope (ele
  é o lance do grupo; ausente → 422 `CAMPO_OBRIGATORIO`); sem `MANUAL_CPC`,
  `cpc_inicial` explícito continua recusado (`CAMPO_NAO_OPERADO`).
- `estrategia_lance` do envelope: igual a `configuracao_display.lance.estrategia`
  ou ausente. Presente e diferente → 422 `ESTRATEGIA_DIVERGENTE` antes de
  qualquer rede (v1.2; até a v1.1 era bloqueio local do plano com HTTP 200).
  `MANUAL_CPM` com envelope `MANUAL_CPM` foi provado vivo (§7):
  `campaign.manual_cpm` + `ad_group.cpm_bid_micros` = `cpm_visivel` × 10⁶.
- **Objeto presente = doutrina de nascimento**: `{}` já liga as exclusões padrão
  (todos os apps + rótulos `PARKED_DOMAIN`, `SEXUALLY_SUGGESTIVE`, `PROFANITY`,
  `TRAGEDY`, `SOCIAL_ISSUES`, `JUVENILE`) e presença geo `PRESENCE`. Ausente =
  grafo antigo.
- Itens de segmentação aceitam id numérico ou resource name; resource name de
  outra conta é bloqueio.

### Demand Gen
- `estrategia_lance` do envelope: `MAXIMIZE_CONVERSIONS` sem configuração de
  lance; **com `configuracao_demand_gen.lance`, precisa ser igual a
  `lance.estrategia`** (422 `ESTRATEGIA_DIVERGENTE` se divergir ou faltar). Estratégias: MaxConv (tCPA → avulso),
  MaxConvValue (tROAS → avulso; exige histórico de valor na conta), TARGET_SPEND,
  TARGET_CPC (alvo obrigatório).
- **Formatos**: `MULTI_ASSET` (default), `VIDEO_RESPONSIVO`, `CARROSSEL`.
  - Vídeo: `video.youtube_ids` 1..5, `copy.long_headlines` 1..5 (aceitas só neste
    formato), `assets_demand_gen` com **exatamente um** `logo_quadrado` e nada
    mais (a régua de imagem do lote é recortada para o logo).
  - Carrossel: **indisponível pela fronteira HTTP** — a imagem do cartão precisa
    ser asset já na conta com recibo (o cartão não resolve id temporário,
    medido), e a fronteira ainda não transporta asset remoto aprovado. Qualquer
    imagem de cartão → 422 com o motivo. O esquema marca esses campos com
    `x-volc-indisponivel-por-http: true`.
- **Automações** (objeto tipo → status): só as do formato escolhido; ausente =
  `OPTED_OUT`. Multi-asset: 3; vídeo: 4 (`GENERATE_LANDING_PAGE_PREVIEW`,
  `GENERATE_LANDING_PAGE_TEXT`, `GENERATE_SHORTER_YOUTUBE_VIDEOS`,
  `GENERATE_VERTICAL_YOUTUBE_VIDEOS`); carrossel: nenhuma.
- Sem frequency cap (a API recusa em DG v25).

### Performance Max
- Lance continua no envelope (`estrategia_lance` MaxConv/MaxConvValue + `tcpa`/
  `target_roas`). Mensuração é lida no servidor e pode bloquear (§7).
- A prova (`/provar`) depende da flag `servidor_oferece_pmax_validate_only`; a
  projeção local (`/planejar-pmax`) aceita a mesma `configuracao_pmax` sem ela
  (§1).
- **Grupos adicionais**: `grupos_adicionais[i].imagens` é uma lista de
  **envelopes de asset, no mesmo formato de `assets_pmax`** — cada lote passa
  pelo MESMO portão de política e pela MESMA ponte do grupo 0, e os recibos
  entram no `supply_sha256`. Com `pmax.brand_guidelines_enabled=true`, logos são
  da campanha: o grupo adicional **não** leva `logo_quadrado`/`logo_paisagem`.
  Teto da fronteira: 85 envelopes por grupo; 100 asset groups por campanha.
- `sinais`: `[]` é "sem dica" (escolha); `null` é "ninguém escolheu" (recusado).
- Automações: as 7 que a API aceita em PMax viajam sempre; `automacoes_optadas`
  liga as escolhidas. `FINAL_URL_EXPANSION_…` exige `TEXT_ASSET_AUTOMATION`
  junto; `AUTOMATED_VIDEO_CRAWL` exige fontes em `video_crawl` e
  `video_crawl_direitos_declarados=true`.
- `pmax.videos_youtube` (resource names) continua recusado; vídeo entra por id
  em `configuracao_pmax.videos` / `grupos_adicionais[i].videos`.

### Estratégia: envelope × configuração (os quatro canais, v1.2)
Uma estratégia por pedido. Quando a configuração do canal declara
`lance.estrategia`, o `estrategia_lance` do envelope precisa dizer a mesma — ou
faltar (Search/Display). A recusa é idêntica nos canais e acontece no
validador do envelope, antes do escopo, da ponte e de qualquer chamada ao
Google, em `/provar` e `/subir`:

```json
{"detail": [{"type": "estrategia_divergente",
  "loc": ["body", "estrategia_lance"],
  "msg": "canal DISPLAY com `configuracao_display.lance.estrategia=MANUAL_CPM` exige `estrategia_lance=MANUAL_CPM` no envelope; recebido TARGET_SPEND. …",
  "input": null,
  "ctx": {"codigo": "ESTRATEGIA_DIVERGENTE", "caminho": "estrategia_lance"}}]}
```

| canal | fonte da estratégia na configuração | envelope ausente | envelope diferente |
|---|---|---|---|
| SEARCH | `configuracao_search.lance.estrategia` | herda a da configuração | 422 `ESTRATEGIA_DIVERGENTE` |
| DISPLAY | `configuracao_display.lance.estrategia` | herda a da configuração | 422 `ESTRATEGIA_DIVERGENTE` |
| DEMAND_GEN | `configuracao_demand_gen.lance.estrategia` | 422 `ESTRATEGIA_DIVERGENTE` | 422 `ESTRATEGIA_DIVERGENTE` |
| PERFORMANCE_MAX | — (não existe; `configuracao_pmax.lance` → 422 `CAMPO_DESCONHECIDO`) | envelope obrigatório (MaxConv/MaxConvValue, 422 `VALOR_INVALIDO`) | não há com o que divergir |

O builder de cada canal continua recusando a divergência como bloqueio local —
é a segunda trava, para chamadores do motor que não passam pela rota.

### Metas: `target_roas` (os quatro canais)
Medido no motor (v1.1): **nenhum builder converte** o número — ele vai ao proto
como está. A unidade é a da API do Google: **razão**, `4.0` = 400%.

| canal | onde se declara | vai ao proto como | faixa |
|---|---|---|---|
| SEARCH | `configuracao_search.lance.target_roas` (ou `target_roas` do envelope, que precisa ser igual quando vierem os dois) | `campaign.maximize_conversion_value.target_roas` | 0,01–1000 |
| DISPLAY | `target_roas` do envelope, com `MAXIMIZE_CONVERSION_VALUE` | `campaign.maximize_conversion_value.target_roas` | 0,01–1000 |
| DEMAND_GEN | `configuracao_demand_gen.lance.target_roas` (envelope recusado com lance declarado) | estratégia avulsa `campaign.target_roas.target_roas` | 0,01–1000 |
| PERFORMANCE_MAX | `target_roas` do envelope, com `MAXIMIZE_CONVERSION_VALUE` | `campaign.maximize_conversion_value.target_roas` | 0,01–1000 |

Fora da faixa → 422 `VALOR_INVALIDO` (`loc` `["body","target_roas"]` ou o
objeto `lance` da configuração). Ausência de meta é `null`, nunca `0`. A faixa
mora em `brief.ROAS_MIN/ROAS_MAX` e é a mesma da gestão
(`gestao.acoes.TROAS_MAXIMO`). Até a v1, Display e Demand Gen aceitavam
qualquer positivo e PMax qualquer número (inclusive negativo).

### Vídeo do YouTube (Display, Demand Gen, PMax)
Vídeo entra por **id público** e o asset nasce no mesmo mutate. O portão de
política criativa julga bytes, e o servidor não tem os bytes de um vídeo do
YouTube: **não há hash, inspeção nem recibo**. A rota aceita (decisão do dono:
vídeo vive dentro de DG e PMax) e o plano traz o aviso
`VIDEO_SEM_PORTAO_DE_POLITICA` com os ids; os ids estão na impressão aprovável.

## 4. Correspondência por keyword (`match_por_keyword`, só Search)

O seletor de correspondência da tela (`rascunho.matchPorKeyword`) agora chega
ao servidor. Chave = texto normalizado (`chave()`: minúscula, espaços
colapsados, acento preservado — a mesma função dos dois lados).

- Só **troca** a correspondência de keyword que já está no **conjunto pago
  aprovado**: não acrescenta, não retira, não duplica.
- Chave fora do conjunto → **422** no formato do §2 (`ctx.codigo =
  MATCH_FORA_DO_CONJUNTO`, `loc` `["body","match_por_keyword","<chave>"]`).
  Ela é julgada na montagem (precisa do conjunto aprovado), depois do escopo.
- BROAD continua exigindo lance por conversão (o `Brief` recusa sob CPC manual).
- A troca aparece no plano (`MATCH_TYPE_ESCOLHIDO_NA_TELA`) e entra na
  impressão aprovável quando o mapa não é vazio (`{}` = ausência).
- A pós-condição do portão pago passa a conferir o brief final contra o
  conjunto **com** as trocas aplicadas.

## 5. Avisos novos no plano (`avisos[].codigo`)

| código | quando |
|---|---|
| `VIDEO_SEM_PORTAO_DE_POLITICA` | a configuração traz vídeo do YouTube por id |
| `MATCH_TYPE_ESCOLHIDO_NA_TELA` | `match_por_keyword` trocou ao menos uma correspondência |

E no plano do motor (`plano.CODIGOS`): `CONFIGURACAO_INVALIDA`.

## 6. Campos, tipos, defaults e validações

Gerado de `GET /api/trafego/canais/esquema`. "obrigatório" vale quando o
objeto que contém o campo é enviado.

### 6.1 Search

**`configuracao_search` (raiz)** — Tudo que Search decide além do `Brief`. Cada campo `None`/vazio preserva o comportamento de antes desta entrega — exceto a rede, que deixa de ter default quando a configuração existe (`resolver_rede`).

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `lance` | objeto `LanceSearch` \| null | `null` |  |  |
| `rede` | objeto `RedeSearch` \| null | `null` |  |  |
| `ai_max` | objeto `AiMaxSearch` \| null | `null` |  |  |
| `anuncio` | objeto `AnuncioSearch` \| null | `null` |  |  |
| `programacao` | lista de objeto `FaixaDeHorario` | `[]` |  | até 6 faixas por dia, sem sobreposição |
| `dispositivos` | lista de objeto `AjusteDeDispositivo` | `[]` |  |  |
| `geo` | objeto `SegmentacaoGeo` \| null | `null` |  |  |
| `inicio` | texto \| null | `null` | formato date |  |
| `fim` | texto \| null | `null` | formato date |  |
| `meta_de_conversao` | objeto `MetaDeConversao` \| null | `null` |  |  |

**`AiMaxSearch`** — AI Max para Search, com cada automação declarada — nunca herdada.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `correspondencia_de_termos` | booleano | **obrigatório** |  |  |
| `personalizacao_de_texto` | booleano | **obrigatório** |  |  |
| `expansao_de_url_final` | booleano | **obrigatório** |  |  |
| `grupos_sem_correspondencia` | lista de texto | `[]` |  |  |
| `exclusoes_de_url` | lista de texto | `[]` | item: mín. chars 1; padrão `^\S+$` |  |
| `listas_de_marca_incluidas` | lista de texto | `[]` | item: padrão `^customers/(\d+)/sharedSets/(-?\d+)$` |  |
| `listas_de_marca_excluidas` | lista de texto | `[]` | item: padrão `^customers/(\d+)/sharedSets/(-?\d+)$` |  |
| `termos_excluidos` | lista de texto | `[]` | máx. itens 25; item: mín. chars 1; máx. chars 30 |  |
| `restricoes_de_mensagem` | lista de texto | `[]` | máx. itens 40; item: mín. chars 1; máx. chars 300 |  |

**`AjusteDeDispositivo`** — `CampaignCriterion.device` + `bid_modifier`. `fator=0` exclui o dispositivo.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `dispositivo` | texto | **obrigatório** | um de `MOBILE`, `TABLET`, `DESKTOP` |  |
| `fator` | número | **obrigatório** | ≥ 0; ≤ 10.0 | 0 exclui o dispositivo; senão entre 0.1 e 10.0 |

**`AnuncioSearch`** — Caminho exibido e fixações do RSA.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `path1` | texto | `""` | máx. chars 15; padrão `^[^/\n]*$` |  |
| `path2` | texto | `""` | máx. chars 15; padrão `^[^/\n]*$` | exige path1 |
| `fixacoes` | lista de objeto `Fixacao` | `[]` |  |  |

**`FaixaDeHorario`** — Um `AdScheduleInfo`: dia, início, fim e ajuste opcional de lance.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `dia` | texto | **obrigatório** | um de `MONDAY`, `TUESDAY`, `WEDNESDAY`, `THURSDAY`, `FRIDAY`, `SATURDAY`, `SUNDAY` |  |
| `inicio` | texto | **obrigatório** | padrão `^([01]\d\|2[0-4]):(00\|15\|30\|45)$` | HH:MM, minutos 00/15/30/45 |
| `fim` | texto | **obrigatório** | padrão `^([01]\d\|2[0-4]):(00\|15\|30\|45)$` | HH:MM (24:00 = fim do dia) |
| `ajuste` | número \| null | `null` | ≥ 0.1; ≤ 10.0 | bid_modifier (1.2 = +20%); só em MANUAL_CPC/TARGET_SPEND |

**`Fixacao`** — Um texto da copy preso a uma posição (`AdTextAsset.pinned_field`).

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `texto` | texto | **obrigatório** | mín. chars 1 |  |
| `posicao` | texto | **obrigatório** | um de `HEADLINE_1`, `HEADLINE_2`, `HEADLINE_3`, `DESCRIPTION_1`, `DESCRIPTION_2` |  |

**`LanceSearch`** — Estratégia de lance da campanha, com só os campos que ELA tem.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `estrategia` | texto | **obrigatório** | um de `MANUAL_CPC`, `TARGET_SPEND`, `MAXIMIZE_CONVERSIONS`, `MAXIMIZE_CONVERSION_VALUE`, `TARGET_IMPRESSION_SHARE` |  |
| `target_cpa` | número \| null | `null` | > 0 | tCPA em moeda da conta; só em MAXIMIZE_CONVERSIONS |
| `target_roas` | número \| null | `null` | ≥ 0.01; ≤ 1000.0 | razão (4.0 = 400%); só em MAXIMIZE_CONVERSION_VALUE |
| `teto_cpc` | número \| null | `null` | > 0 | teto de CPC em moeda da conta; TARGET_SPEND (opcional) e TARGET_IMPRESSION_SHARE (obrigatório) |
| `local_impressao` | texto \| null | `null` | um de `ANYWHERE_ON_PAGE`, `TOP_OF_PAGE`, `ABSOLUTE_TOP_OF_PAGE` | obrigatório em TARGET_IMPRESSION_SHARE |
| `fracao_impressao` | número \| null | `null` | > 0; ≤ 1 | obrigatório em TARGET_IMPRESSION_SHARE (0.6 = 60%) |

**`MetaDeCategoria`** — Um `CampaignConversionGoal` (categoria × origem) e se ele entra no lance.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `categoria` | texto | **obrigatório** | um de `DEFAULT`, `PAGE_VIEW`, `PURCHASE`, `SIGNUP`, `DOWNLOAD`, `ADD_TO_CART`, `BEGIN_CHECKOUT`, `SUBSCRIBE_PAID`, `PHONE_CALL_LEAD`, `IMPORTED_LEAD`, `SUBMIT_LEAD_FORM`, `BOOK_APPOINTMENT`, `REQUEST_QUOTE`, `GET_DIRECTIONS`, `OUTBOUND_CLICK`, `CONTACT`, `ENGAGEMENT`, `STORE_VISIT`, `STORE_SALE`, `QUALIFIED_LEAD`, `CONVERTED_LEAD`, `YOUTUBE_FOLLOW_ON_VIEWS`, `IN_APP_AD_REVENUE` |  |
| `origem` | texto | **obrigatório** | um de `WEBSITE`, `GOOGLE_HOSTED`, `APP`, `CALL_FROM_ADS`, `STORE`, `YOUTUBE_HOSTED`, `LOCAL_SERVICES_ADS` |  |
| `lance` | booleano | **obrigatório** |  |  |

**`MetaDeConversao`** — Para qual conversão ESTA campanha otimiza — o mecanismo certo da v25.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `meta_personalizada` | texto \| null | `null` | padrão `^customers/(\d+)/customConversionGoals/(\d+)$` |  |
| `acoes_de_conversao` | lista de texto | `[]` | item: padrão `^customers/(\d+)/conversionActions/(\d+)$` |  |
| `categorias` | lista de objeto `MetaDeCategoria` | `[]` |  |  |

**`RedeSearch`** — As três chaves de `network_settings`, todas sem default.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `google_search` | booleano | **obrigatório** | = True |  |
| `parceiros` | booleano | **obrigatório** |  |  |
| `display_expansion` | booleano | **obrigatório** |  |  |

**`SegmentacaoGeo`** — `geo_target_type_setting` + locais e idiomas múltiplos.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `tipo_positivo` | texto | **obrigatório** | um de `PRESENCE`, `PRESENCE_OR_INTEREST`, `SEARCH_INTEREST` |  |
| `tipo_negativo` | texto | **obrigatório** | um de `PRESENCE`, `PRESENCE_OR_INTEREST` |  |
| `locais` | lista de inteiro | `[]` | item: ≥ 1 | ids de geoTargetConstant do país do brief; vazio = o país |
| `locais_excluidos` | lista de inteiro | `[]` | item: ≥ 1 |  |
| `idiomas` | lista de texto | `[]` |  | códigos de idioma; precisa conter o idioma do brief |

### 6.2 Display

**`configuracao_display` (raiz)** — Tudo o que Display decide além do brief. Ver docstring do módulo.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `lance` | objeto `LanceDisplay` \| null | `null` |  |  |
| `segmentacao` | objeto `SegmentacaoDisplay` | `{"listas_de_usuarios": [], "publicos_personalizados": [], "publicos_combinados": [], "interesses": [], "topicos": [], "placements": [], "palavras_chave": [], "publicos_em_observacao": false, "segmentacao_otimizada": false}` |  |  |
| `exclusoes` | objeto `ExclusoesDisplay` | `{"placements": [], "apps": [], "categorias_de_app": [], "excluir_todos_os_apps": true, "rotulos_de_conteudo": ["PARKED_DOMAIN", "SEXUALLY_SUGGESTIVE", "PROFANITY", "TRAGEDY", "SOCIAL_ISSUES", "JUVENILE"], "topicos": [], "listas_existentes": [], "lista_nova": null}` |  |  |
| `frequencia` | lista de objeto `FrequenciaMaxima` | `[]` |  |  |
| `agenda` | lista de objeto `JanelaDeVeiculacao` | `[]` |  | até 6 janelas por dia, sem sobreposição |
| `dispositivos_excluidos` | lista de texto | `[]` | item: um de `MOBILE`, `TABLET`, `DESKTOP` |  |
| `presenca_geo` | texto | `"PRESENCE"` | um de `PRESENCE`, `PRESENCE_OR_INTEREST` | `geo_target_type_setting.positive_geo_target_type`. ⚠️ Default PRESENCE: o RPM do GAM é por país, e "interesse no local" compra clique de fora. O negativo é sempre PRESENCE. |
| `anuncio` | objeto `AnuncioDisplay` | `{"chamada_para_acao": null, "cor_principal": null, "cor_destaque": null, "cores_flexiveis": true, "formato": "ALL_FORMATS", "videos_youtube": [], "melhorias_de_asset": false, "video_automatico": false}` |  |  |

**`AnuncioDisplay`** — Campos do RDA além de texto e imagem.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `chamada_para_acao` | texto \| null | `null` | máx. chars 30 | `call_to_action_text`, largura máxima 30. |
| `cor_principal` | texto \| null | `null` | padrão `^#[0-9A-Fa-f]{6}$` | `main_color`/`accent_color` "#RRGGBB" — os dois ou nenhum (field_error.REQUIRED medido). |
| `cor_destaque` | texto \| null | `null` | padrão `^#[0-9A-Fa-f]{6}$` |  |
| `cores_flexiveis` | booleano | `true` |  | `allow_flexible_color`. Precisa ser True quando não há cores. |
| `formato` | texto | `"ALL_FORMATS"` | um de `ALL_FORMATS`, `NATIVE`, `NON_NATIVE` | `format_setting`: ALL_FORMATS / NATIVE / NON_NATIVE. |
| `videos_youtube` | lista de texto | `[]` | máx. itens 5; item: padrão `^[A-Za-z0-9_-]{11}$` | IDs do YouTube (11 chars). Viram `YoutubeVideoAsset` no MESMO mutate. |
| `melhorias_de_asset` | booleano | `false` |  | `control_spec.enable_asset_enhancements` — default DESLIGADO (peça aprovada = peça servida). |
| `video_automatico` | booleano | `false` |  | `control_spec.enable_autogen_video` — default DESLIGADO. |

**`ExclusoesDisplay`** — Exclusões de campanha. Os defaults SÃO o padrão de nascimento.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `placements` | lista de texto | `[]` |  | Sites (CampaignCriterion.placement, negative=True). |
| `apps` | lista de texto | `[]` | item: padrão `^(?:1-\d+\|2-[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)$` | Apps: "1-<id App Store>" ou "2-<pacote Android>" (mobile_application). |
| `categorias_de_app` | lista de texto | `[]` | item: padrão `^(\d+\|mobileAppCategoryConstants/\d+)$` | `mobileAppCategoryConstants/<id>` (mobile_app_category, negativo). |
| `excluir_todos_os_apps` | booleano | `true` |  | ⚠️ Default LIGADO: clique em app é acidental demais e a sessão não cai no portal monetizado. Exclui `CATEGORIA_TODOS_OS_APPS`. |
| `rotulos_de_conteudo` | lista de texto | `["PARKED_DOMAIN", "SEXUALLY_SUGGESTIVE", "PROFANITY", "TRAGEDY", "SOCIAL_ISSUES", "JUVENILE"]` | item: um de `SEXUALLY_SUGGESTIVE`, `BELOW_THE_FOLD`, `PARKED_DOMAIN`, `JUVENILE`, `PROFANITY`, `TRAGEDY`, `VIDEO`, `VIDEO_RATING_DV_G`, `VIDEO_RATING_DV_PG`, `VIDEO_RATING_DV_T`, `VIDEO_RATING_DV_MA`, `VIDEO_NOT_YET_RATED`, `EMBEDDED_VIDEO`, `LIVE_STREAMING_VIDEO`, `SOCIAL_ISSUES`, `BRAND_SUITABILITY_CONTENT_FOR_FAMILIES` | `content_label` negativos. Default = `ROTULOS_PADRAO`. |
| `topicos` | lista de texto | `[]` | item: padrão `^(\d+\|topicConstants/\d+)$` | Tópicos negativos (`topicConstants/<id>`). |
| `listas_existentes` | lista de texto | `[]` | item: padrão `^(\d+\|customers/\d+/sharedSets/\d+)$` | Listas NEGATIVE_PLACEMENTS já existentes: `customers/<cid>/sharedSets/<id>`. |
| `lista_nova` | objeto `ListaDeExclusaoNova` \| null | `null` |  | Lista nova, criada no mesmo mutate atômico. |

**`FrequenciaMaxima`** — `campaign.frequency_caps[]` — evento IMPRESSION, `time_length` 1.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `impressoes` | inteiro | **obrigatório** | ≥ 1 |  |
| `unidade` | texto | `"DAY"` | um de `DAY`, `WEEK`, `MONTH` |  |
| `nivel` | texto | `"AD_GROUP_AD"` | um de `AD_GROUP_AD`, `AD_GROUP`, `CAMPAIGN` |  |

**`JanelaDeVeiculacao`** — `CampaignCriterion.ad_schedule`. Fim exclusivo; 24:00 é o fim do dia.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `dia` | texto | **obrigatório** | um de `MONDAY`, `TUESDAY`, `WEDNESDAY`, `THURSDAY`, `FRIDAY`, `SATURDAY`, `SUNDAY` |  |
| `inicio_hora` | inteiro | **obrigatório** | ≥ 0; ≤ 23 |  |
| `fim_hora` | inteiro | **obrigatório** | ≥ 0; ≤ 24 |  |
| `inicio_minuto` | inteiro | `0` | um de `0`, `15`, `30`, `45` |  |
| `fim_minuto` | inteiro | `0` | um de `0`, `15`, `30`, `45` |  |

**`LanceDisplay`** — A estratégia de Display, quando ela não cabe em `brief.estrategia_lance`.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `estrategia` | texto | **obrigatório** | um de `MAXIMIZE_CONVERSIONS`, `MAXIMIZE_CONVERSION_VALUE`, `TARGET_SPEND`, `MANUAL_CPC`, `MANUAL_CPM` |  |
| `teto_cpc` | número \| null | `null` | > 0 | TARGET_SPEND: `cpc_bid_ceiling_micros`, em moeda da conta. `None` = sem teto. |
| `cpm_visivel` | número \| null | `null` | > 0 | lance vCPM do grupo; obrigatório em MANUAL_CPM |

**`ListaDeExclusaoNova`** — `SharedSet` NEGATIVE_PLACEMENTS criado no MESMO mutate e ligado à campanha.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `nome` | texto | **obrigatório** | mín. chars 1 |  |
| `placements` | lista de texto | `[]` |  |  |
| `apps` | lista de texto | `[]` | item: padrão `^(?:1-\d+\|2-[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)$` |  |
| `categorias_de_app` | lista de texto | `[]` |  |  |

**`SegmentacaoDisplay`** — Critérios POSITIVOS do ad group. Vazio = inventário aberto (e avisado).

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `listas_de_usuarios` | lista de texto | `[]` | item: padrão `^(\d+\|customers/\d+/userLists/\d+)$` | `customers/<cid>/userLists/<id>` — remarketing (AdGroupCriterion.user_list). |
| `publicos_personalizados` | lista de texto | `[]` | item: padrão `^(\d+\|customers/\d+/customAudiences/\d+)$` | `customers/<cid>/customAudiences/<id>` (AdGroupCriterion.custom_audience). |
| `publicos_combinados` | lista de texto | `[]` | item: padrão `^(\d+\|customers/\d+/combinedAudiences/\d+)$` | `customers/<cid>/combinedAudiences/<id>` (AdGroupCriterion.combined_audience). |
| `interesses` | lista de texto | `[]` | item: padrão `^(\d+\|customers/\d+/userInterests/\d+)$` | Afinidade e in-market: `customers/<cid>/userInterests/<id>` (AdGroupCriterion.user_interest). Ex.: 92000 "Avid News Readers" (AFFINITY), 80226 "Education" (IN_MARKET). |
| `topicos` | lista de texto | `[]` | item: padrão `^(\d+\|topicConstants/\d+)$` | `topicConstants/<id>` (TopicInfo). Ex.: 369 "Vocational & Continuing Education". |
| `placements` | lista de texto | `[]` |  | Site onde o anúncio PODE aparecer (PlacementInfo.url, positivo). A contradição das duas fontes oficiais foi resolvida pela API: aceito. |
| `palavras_chave` | lista de texto | `[]` | item: mín. chars 1; máx. chars 80 | Palavras-chave de CONTEÚDO (KeywordInfo, BROAD — Display não casa termo de busca; o match type não tem efeito de consulta aqui). |
| `publicos_em_observacao` | booleano | `false` |  | `True` = públicos em OBSERVAÇÃO (bid_only, não restringem); `False` = SEGMENTAÇÃO (restringem). `ad_group.targeting_setting` AUDIENCE. |
| `segmentacao_otimizada` | booleano | `false` |  | `ad_group.optimized_targeting_enabled`. ⚠️ Default DESLIGADO e escrito sempre: ligado, o Google expande para além dos critérios acima, que é o oposto do controle de inventário que a arbitragem precisa. |

### 6.3 Demand Gen

**`configuracao_demand_gen` (raiz)** — `ConfiguracaoDemandGen` + as decisões v25.2. Todo campo novo defaultado.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `formato` | texto | `"MULTI_ASSET"` | um de `MULTI_ASSET`, `VIDEO_RESPONSIVO`, `CARROSSEL` |  |
| `lance` | objeto `LanceDemandGen` \| null | `null` |  |  |
| `call_to_action` | texto \| null | `null` | um de `Saiba Mais`, `Inscreva-se`, `Inscrever-se`, `Reservar`, `Fale conosco`, `Visitar site`, `Comprar agora`, `Ver mais`, `Learn more`, `Learn More`, `Apply now`, `Book now`, `Contact us`, `Download`, `Visit site`, `Shop now`, `Sign up`, `Get quote`, `Subscribe`, `See more`, `Get offer`, `Call now` | multi-asset e carrossel; no vídeo o CTA é `video.call_to_action` |
| `video` | objeto `VideoDemandGen` \| null | `null` |  |  |
| `carrossel` | objeto `CarrosselDemandGen` \| null | `null` |  |  |
| `publico` | objeto `PublicoDemandGen` \| null | `null` |  |  |
| `segmentacao_otimizada` | booleano \| null | `null` |  | optimized targeting do ad group; null = não emitido |
| `automacoes` | objeto (mapa) | `{}` | chaves: `GENERATE_DESIGN_VERSIONS_FOR_IMAGES`, `GENERATE_VIDEOS_FROM_OTHER_ASSETS`, `GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS`, `GENERATE_LANDING_PAGE_PREVIEW`, `GENERATE_LANDING_PAGE_TEXT`, `GENERATE_SHORTER_YOUTUBE_VIDEOS`, `GENERATE_VERTICAL_YOUTUBE_VIDEOS`; valores: `OPTED_IN`, `OPTED_OUT` | tipo → OPTED_IN/OPTED_OUT; tipo ausente viaja OPTED_OUT. Só os tipos do formato escolhido: MULTI_ASSET: GENERATE_DESIGN_VERSIONS_FOR_IMAGES, GENERATE_VIDEOS_FROM_OTHER_ASSETS, GENERATE_ANIMATED_IMAGES_FROM_OTHER_ASSETS; VIDEO_RESPONSIVO: GENERATE_LANDING_PAGE_PREVIEW, GENERATE_LANDING_PAGE_TEXT, GENERATE_SHORTER_YOUTUBE_VIDEOS, GENERATE_VERTICAL_YOUTUBE_VIDEOS; CARROSSEL: nenhuma |
| `agenda` | lista de objeto `FaixaDeAgendaDemandGen` | `[]` |  | até 6 faixas por dia, sem sobreposição |

**`CarrosselDemandGen`** — 2..10 cartões, mesmas orientações em todos (Help Center: proporção consistente). Headline/description do anúncio vêm de `brief.copy`, com EXATAMENTE um item cada; logo é `imagens_demand_gen.logo_quadrado` (1).

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `cartoes` | lista de objeto `CartaoCarrosselDemandGen` | **obrigatório** | mín. itens 2; máx. itens 10 |  |

**`CartaoCarrosselDemandGen`** — Um cartão. Imagens por papel; ao menos paisagem ou quadrada.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `headline` | texto | **obrigatório** | mín. chars 1; máx. chars 40 |  |
| `marketing` | — (não aceito por HTTP) \| null | `null` |  |  |
| `marketing_quadrada` | — (não aceito por HTTP) \| null | `null` |  |  |
| `marketing_retrato` | — (não aceito por HTTP) \| null | `null` |  |  |
| `url_final` | texto \| null | `null` | padrão `^https://` |  |
| `call_to_action` | texto \| null | `null` | um de `Saiba Mais`, `Inscreva-se`, `Inscrever-se`, `Reservar`, `Fale conosco`, `Visitar site`, `Comprar agora`, `Ver mais`, `Learn more`, `Learn More`, `Apply now`, `Book now`, `Contact us`, `Download`, `Visit site`, `Shop now`, `Sign up`, `Get quote`, `Subscribe`, `See more`, `Get offer`, `Call now` |  |

**`FaixaDeAgendaDemandGen`** — Uma janela de veiculação: dia + "HH:MM" de início e fim (fuso da conta).

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `dia` | texto | **obrigatório** | um de `MONDAY`, `TUESDAY`, `WEDNESDAY`, `THURSDAY`, `FRIDAY`, `SATURDAY`, `SUNDAY` |  |
| `inicio` | texto | **obrigatório** | padrão `^([01]\d\|2[0-4]):(00\|15\|30\|45)$` |  |
| `fim` | texto | **obrigatório** | padrão `^([01]\d\|2[0-4]):(00\|15\|30\|45)$` |  |

**`LanceDemandGen`** — A estratégia de lance, com a meta que a acompanha — e só ela.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `estrategia` | texto | **obrigatório** | um de `MAXIMIZE_CONVERSIONS`, `MAXIMIZE_CONVERSION_VALUE`, `TARGET_SPEND`, `TARGET_CPC` |  |
| `target_cpa` | número \| null | `null` | > 0 | só em MAXIMIZE_CONVERSIONS (vira `target_cpa` avulso) |
| `target_roas` | número \| null | `null` | ≥ 0.01; ≤ 1000.0 | razão (4.0 = 400%); só em MAXIMIZE_CONVERSION_VALUE (vira `target_roas` avulso) |
| `target_cpc` | número \| null | `null` | > 0 | obrigatório em TARGET_CPC |

**`LookalikeDemandGen`** — Segmento semelhante criado NO MESMO mutate (`UserList.lookalike_user_list`).

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `nome` | texto | **obrigatório** | mín. chars 1 |  |
| `sementes` | lista de inteiro | **obrigatório** | mín. itens 1; item: ≥ 1 |  |
| `expansao` | texto | **obrigatório** | um de `NARROW`, `BALANCED`, `BROAD` |  |
| `paises` | lista de texto | **obrigatório** | mín. itens 1; item: padrão `^[A-Z]{2}$` |  |

**`PublicoDemandGen`** — Uma `Audience` composta no mesmo mutate e anexada ao ad group.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `nome` | texto | **obrigatório** | mín. chars 1 |  |
| `user_lists` | lista de texto | `[]` | máx. itens 20; item: padrão `^customers/(\d+)/userLists/(\d+)$` |  |
| `lookalikes` | lista de objeto `LookalikeDemandGen` | `[]` | máx. itens 10 |  |
| `exclusoes_user_list` | lista de texto | `[]` | máx. itens 20; item: padrão `^customers/(\d+)/userLists/(\d+)$` |  |
| `idades` | lista de texto | `[]` | item: um de `18-24`, `25-34`, `35-44`, `45-54`, `55-64`, `65+` |  |
| `incluir_idade_indeterminada` | booleano | `true` |  |  |
| `generos` | lista de texto | `[]` | item: um de `MALE`, `FEMALE` |  |
| `incluir_genero_indeterminado` | booleano | `true` |  |  |
| `rendas` | lista de texto | `[]` | item: um de `INCOME_RANGE_0_50`, `INCOME_RANGE_50_60`, `INCOME_RANGE_60_70`, `INCOME_RANGE_70_80`, `INCOME_RANGE_80_90`, `INCOME_RANGE_90_UP` |  |
| `incluir_renda_indeterminada` | booleano | `true` |  |  |
| `status_parentais` | lista de texto | `[]` | item: um de `PARENT`, `NOT_A_PARENT` |  |
| `incluir_status_parental_indeterminado` | booleano | `true` |  |  |

**`VideoDemandGen`** — O que só o vídeo responsivo tem. Textos vêm de `brief.copy`.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `youtube_ids` | lista de texto | **obrigatório** | mín. itens 1; máx. itens 5; item: padrão `^[A-Za-z0-9_-]{11}$` |  |
| `call_to_action` | texto \| null | `null` | um de `LEARN_MORE`, `GET_QUOTE`, `APPLY_NOW`, `SIGN_UP`, `CONTACT_US`, `SUBSCRIBE`, `DOWNLOAD`, `BOOK_NOW`, `SHOP_NOW`, `BUY_NOW`, `DONATE_NOW`, `ORDER_NOW`, `PLAY_NOW`, `SEE_MORE`, `START_NOW`, `VISIT_SITE`, `WATCH_NOW` |  |
| `breadcrumb1` | texto \| null | `null` | mín. chars 1; máx. chars 15 |  |
| `breadcrumb2` | texto \| null | `null` | mín. chars 1; máx. chars 15 | exige breadcrumb1 |

### 6.4 Performance Max

**`configuracao_pmax` (raiz)** — `ConfiguracaoPMax` + as decisões da v25.2. Todo campo novo tem default que reproduz o payload de antes (exceto as correções medidas, ver pmax.py).

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `path1` | texto | `""` | máx. chars 15; padrão `^[^/ ]*$` |  |
| `path2` | texto | `""` | máx. chars 15; padrão `^[^/ ]*$` | exige path1 |
| `opcoes_de_url` | objeto `OpcoesDeUrl` \| null | `null` |  |  |
| `videos` | lista de objeto `VideoYouTube` | `[]` | máx. itens 15 |  |
| `grupos_adicionais` | lista de objeto `AssetGroupPMax` | `[]` | máx. itens 99 | asset groups 1..N; o grupo 0 nasce do brief (copy, assets_pmax, url_final, pmax.sinais) |
| `automacoes_optadas` | lista de texto | `[]` | item: um de `FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION`, `TEXT_ASSET_AUTOMATION`, `GENERATE_IMAGE_ENHANCEMENT`, `GENERATE_ENHANCED_YOUTUBE_VIDEOS`, `GENERATE_IMAGE_EXTRACTION`, `AUTOMATED_VIDEO_CRAWL`, `GENERATE_DESIGN_VERSIONS_FOR_IMAGES`; sem repetição | automações OPTED_IN; as ausentes viajam OPTED_OUT. FINAL_URL_EXPANSION exige TEXT_ASSET_AUTOMATION junto; AUTOMATED_VIDEO_CRAWL exige video_crawl + direitos declarados |
| `video_crawl` | lista de objeto `FonteDeVideoCrawl` | `[]` |  |  |
| `video_crawl_direitos_declarados` | booleano | `false` |  | declaração do dono de que tem direito sobre os vídeos encontrados; obrigatória com AUTOMATED_VIDEO_CRAWL |
| `exclusoes_de_url` | lista de objeto `ExclusaoDeUrl` | `[]` |  |  |
| `termos_excluidos` | lista de texto | `[]` | máx. itens 25; item: mín. chars 1; máx. chars 30 |  |
| `restricoes_de_mensagem` | lista de texto | `[]` | máx. itens 40; item: mín. chars 1; máx. chars 300 |  |
| `diretrizes_de_marca` | objeto `DiretrizesDeMarca` \| null | `null` |  | só com pmax.brand_guidelines_enabled=true |
| `negativas_tipadas` | lista de objeto `NegativaPMax` | `[]` |  |  |
| `listas_de_negativas` | lista de texto | `[]` | item: padrão `^customers/(\d+)/sharedSets/(\d+)$` |  |
| `marcas_excluidas` | lista de objeto `MarcaExcluida` | `[]` |  |  |
| `listas_de_marcas_excluidas` | lista de texto | `[]` | item: padrão `^customers/(\d+)/sharedSets/(\d+)$` |  |
| `metas_de_conversao` | lista de objeto `MetaDeConversao` | `[]` |  |  |
| `meta_cliente_novo` | objeto `MetaClienteNovo` \| null | `null` |  |  |

**`AssetGroupPMax`** — Um asset group ADICIONAL, com tudo que é dele — e nada herdado.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `nome` | texto | **obrigatório** | mín. chars 1 |  |
| `url_final` | texto | **obrigatório** | padrão `^https://` |  |
| `textos` | objeto `TextosPMax` | **obrigatório** |  |  |
| `imagens` | lista de objeto | **obrigatório** |  | envelopes de asset, no MESMO formato de `assets_pmax`: cada item passa pelo portão de política e pela ponte criativa, que decide o papel pelo `tipo` |
| `sinais` | lista de objeto `SinalDeAudiencia` \| null | **obrigatório** |  | [] = sem dica (escolha); null = ninguém escolheu (recusado) |
| `videos` | lista de objeto `VideoYouTube` | `[]` | máx. itens 15 |  |
| `path1` | texto | `""` | máx. chars 15; padrão `^[^/ ]*$` |  |
| `path2` | texto | `""` | máx. chars 15; padrão `^[^/ ]*$` |  |
| `opcoes_de_url` | objeto `OpcoesDeUrl` \| null | `null` |  |  |

**`DiretrizesDeMarca`** — `Campaign.brand_guidelines` — só com `brand_guidelines_enabled=True`.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `cor_principal` | texto | `""` | padrão `^(#[0-9A-Fa-f]{6})?$` |  |
| `cor_destaque` | texto | `""` | padrão `^(#[0-9A-Fa-f]{6})?$` |  |
| `fonte` | texto | `""` | um de ``, `Open Sans`, `Roboto`, `Montserrat`, `Poppins`, `Lato`, `Oswald`, `Playfair Display`, `Roboto Slab` |  |

**`ExclusaoDeUrl`** — `CampaignCriterion.webpage` NEGATIVO — só morde com a expansão de URL ligada.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `nome` | texto | **obrigatório** | mín. chars 1 |  |
| `argumento` | texto | **obrigatório** | mín. chars 1 |  |
| `operando` | texto | `"URL"` | um de `URL`, `PAGE_TITLE`, `PAGE_CONTENT` |  |
| `operador` | texto | `"CONTAINS"` | um de `CONTAINS`, `EQUALS` |  |

**`FonteDeVideoCrawl`** — `AutomatedVideoCrawlInfo` (v25.2): uma URL onde o Google pode buscar vídeo.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `url` | texto | **obrigatório** | padrão `^https://` |  |
| `plataforma` | texto | **obrigatório** | um de `LANDING_PAGE`, `SOCIAL`, `YOUTUBE` |  |
| `habilitada` | booleano | `true` |  |  |

**`MarcaExcluida`** — Uma marca do catálogo do Google (`BrandSuggestionService`), por entidade.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `entity_id` | texto | **obrigatório** | padrão `^/[gm]/[A-Za-z0-9_]+$` |  |
| `nome` | texto | `""` |  |  |

**`MetaClienteNovo`** — Aquisição de cliente novo no esquema UNIFICADO da v25.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `goal` | texto | **obrigatório** | padrão `^customers/(\d+)/goals/(\d+)$` | `customers/<cid>/goals/<id>` — o Goal NEW_CUSTOMER_ACQUISITION da conta. |
| `modo` | texto | **obrigatório** | um de `TARGET_ALL`, `TARGET_SPECIFIC` | TARGET_ALL = todos, com ajuste de valor para cliente novo; TARGET_SPECIFIC = só cliente novo. |
| `valor_adicional` | número \| null | `null` | > 0 |  |
| `multiplicador_de_valor` | número \| null | `null` | > 0 |  |

**`MetaDeConversao`** — `CampaignConversionGoal` — sobrescreve, NESTA campanha, o biddable da conta.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `categoria` | texto | **obrigatório** | um de `DEFAULT`, `PAGE_VIEW`, `PURCHASE`, `SIGNUP`, `DOWNLOAD`, `ADD_TO_CART`, `BEGIN_CHECKOUT`, `SUBSCRIBE_PAID`, `PHONE_CALL_LEAD`, `IMPORTED_LEAD`, `SUBMIT_LEAD_FORM`, `BOOK_APPOINTMENT`, `REQUEST_QUOTE`, `GET_DIRECTIONS`, `OUTBOUND_CLICK`, `CONTACT`, `ENGAGEMENT`, `STORE_VISIT`, `STORE_SALE`, `QUALIFIED_LEAD`, `CONVERTED_LEAD`, `YOUTUBE_FOLLOW_ON_VIEWS`, `IN_APP_AD_REVENUE` |  |
| `origem` | texto | **obrigatório** | um de `WEBSITE`, `GOOGLE_HOSTED`, `APP`, `CALL_FROM_ADS`, `STORE`, `YOUTUBE_HOSTED`, `LOCAL_SERVICES_ADS` |  |
| `biddable` | booleano | **obrigatório** |  |  |

**`NegativaPMax`**

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `texto` | texto | **obrigatório** | mín. chars 1 |  |
| `match_type` | texto | `"BROAD"` | um de `BROAD`, `PHRASE`, `EXACT` |  |

**`OpcoesDeUrl`** — URL options do ASSET GROUP (v25.2) — a marcação por grupo sem duplicar campanha.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `sufixo_extra` | lista de par [texto, texto] | `[]` | item: mín. itens 2; máx. itens 2 | pares [chave, valor] acrescentados ao sufixo da campanha neste grupo |
| `tracking_url_template` | texto | `""` |  | começa com {lpurl} ou https:// e carrega {lpurl} |
| `parametros_personalizados` | lista de par [texto, texto] | `[]` | máx. itens 8; item: mín. itens 2; máx. itens 2 | pares [chave, valor]; chave alfanumérica 1..16, usada como {_chave} |

**`SinalDeAudiencia`** — `AssetGroupSignal` — a dica que substitui targeting positivo em PMax.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `tipo` | texto | **obrigatório** | um de `audience`, `search_theme` |  |
| `valor` | texto | **obrigatório** | mín. chars 1 |  |

**`TextosPMax`**

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `headlines` | lista de texto | **obrigatório** |  |  |
| `long_headlines` | lista de texto | **obrigatório** |  |  |
| `descriptions` | lista de texto | **obrigatório** |  |  |

**`VideoYouTube`** — `YOUTUBE_VIDEO` CRIADO no mesmo mutate a partir do id público do vídeo.

| campo | tipo | default | validação | nota |
|---|---|---|---|---|
| `video_id` | texto | **obrigatório** | padrão `^[A-Za-z0-9_-]{11}$` |  |
| `nome` | texto | `""` |  |  |

## 7. Prova viva (08/10/2026, Crédito Up 547-809-6539, MCC 601-673-9364)

`POST /api/trafego/provar` em processo (TestClient), `validate_only` real, com a
configuração máxima de cada canal (payloads do §8). Supabase desligado; dublês:
oportunidade/cockpit, conjunto pago de Search, `montar_brief` de Search,
detector de pixel do portão e as flags experimentais de DG/PMax.

| canal | ops | veredito do `validate_only` |
|---|---|---|
| SEARCH | 29 | aceito (selo emitido) |
| DISPLAY | 35 | aceito (selo emitido) |
| DEMAND_GEN (vídeo responsivo) | 18 | aceito (selo emitido) |
| PERFORMANCE_MAX (2 asset groups) | 63 | aceito com o portão de mensuração do builder desligado; com ele ligado, recusa local `MENSURACAO_INADEQUADA` (as 5 ações primárias da conta estão fora da métrica de conversões) |
| DISPLAY `MANUAL_CPM` (v1.1) | 19 | aceito (selo emitido) — envelope `estrategia_lance=MANUAL_CPM` igual à configuração `lance={"estrategia":"MANUAL_CPM","cpm_visivel":4.5}`; o builder emitiu `campaign.manual_cpm` e `ad_group.cpm_bid_micros=4500000` (espião de leitura no `display.construir`) |
| DISPLAY envelope `TARGET_SPEND` × configuração `MANUAL_CPM` (contraprova) | 0 | v1.2: **422 `ESTRATEGIA_DIVERGENTE`** em 0,0 s, sem montagem nem rede (na v1.1 era recusa local do plano, HTTP 200). Nos dois casos, nada foi ao Google |

Nos quatro, o selo saiu **retido pelo portão de destino**: a LP
`creditoup.com.br/r/guia-cursos-senac/` não está elegível como destino pago
(falta divulgação, CNPJ, contato). É a barreira que deve agir — `/provar` não
emite `plano_impressao` para destino inelegível.

O MCC da casa (6016739364), exigido pelo escopo da rota, enxerga a conta (o
`validate_only` e a leitura de `customer_conversion_goal` responderam por ele).

## 8. Exemplos de payload (os da prova viva)

Envelopes de asset abreviados (`dados_base64` é o PNG em base64).

### 8.1 Search

```json
{
  "opportunity_id": 990001,
  "customer_id": "5478096539",
  "login_customer_id": "6016739364",
  "budget_diario": 20.0,
  "canal": "SEARCH",
  "estrategia_lance": "MAXIMIZE_CONVERSIONS",
  "cpc_inicial": 0.2,
  "copy": {
    "headlines": [
      "Cursos Gratuitos do Senac",
      "Veja Como se Inscrever",
      "Guia Completo de Cursos"
    ],
    "descriptions": [
      "Entenda como funcionam os cursos gratuitos e quem pode participar.",
      "Guia informativo com prazos, requisitos e links oficiais."
    ],
    "sitelinks": [
      {
        "texto": "Como se inscrever",
        "descricao1": "Passo a passo",
        "descricao2": "Requisitos basicos"
      },
      {
        "texto": "Cursos disponiveis",
        "descricao1": "Areas de estudo",
        "descricao2": "Modalidades"
      }
    ],
    "callouts": [
      "Conteudo informativo",
      "Links oficiais"
    ]
  },
  "match_por_keyword": {
    "cursos senac 2026": "EXACT",
    "cursos gratuitos senac": "BROAD"
  },
  "configuracao_search": {
    "lance": {
      "estrategia": "MAXIMIZE_CONVERSIONS",
      "target_cpa": 4.5
    },
    "rede": {
      "google_search": true,
      "parceiros": false,
      "display_expansion": false
    },
    "ai_max": {
      "correspondencia_de_termos": true,
      "personalizacao_de_texto": true,
      "expansao_de_url_final": true,
      "exclusoes_de_url": [
        "/blog/",
        "/contato"
      ],
      "termos_excluidos": [
        "gratis garantido"
      ],
      "restricoes_de_mensagem": [
        "Não prometer vaga ou aprovação."
      ]
    },
    "anuncio": {
      "path1": "cursos",
      "path2": "senac",
      "fixacoes": [
        {
          "texto": "Cursos Gratuitos do Senac",
          "posicao": "HEADLINE_1"
        }
      ]
    },
    "programacao": [
      {
        "dia": "MONDAY",
        "inicio": "07:00",
        "fim": "23:00"
      },
      {
        "dia": "TUESDAY",
        "inicio": "07:00",
        "fim": "23:00"
      },
      {
        "dia": "WEDNESDAY",
        "inicio": "07:00",
        "fim": "23:00"
      },
      {
        "dia": "THURSDAY",
        "inicio": "07:00",
        "fim": "23:00"
      },
      {
        "dia": "FRIDAY",
        "inicio": "07:00",
        "fim": "23:00"
      }
    ],
    "dispositivos": [
      {
        "dispositivo": "TABLET",
        "fator": 0
      }
    ],
    "geo": {
      "tipo_positivo": "PRESENCE",
      "tipo_negativo": "PRESENCE",
      "idiomas": [
        "pt",
        "en"
      ]
    },
    "inicio": "2026-10-20",
    "fim": "2026-12-31",
    "meta_de_conversao": {
      "acoes_de_conversao": [
        "customers/5478096539/conversionActions/7467141090"
      ],
      "categorias": [
        {
          "categoria": "PURCHASE",
          "origem": "WEBSITE",
          "lance": false
        }
      ]
    }
  }
}
```

### 8.2 Display

```json
{
  "opportunity_id": 990001,
  "customer_id": "5478096539",
  "login_customer_id": "6016739364",
  "budget_diario": 20.0,
  "canal": "DISPLAY",
  "estrategia_lance": "TARGET_SPEND",
  "copy": {
    "headlines": [
      "Cursos do Senac",
      "Guia de Cursos 2026"
    ],
    "long_headlines": [
      "Guia informativo de cursos do Senac com modalidades e inscrição"
    ],
    "descriptions": [
      "Veja áreas, modalidades e como se inscrever."
    ],
    "business_name": "Credito Up"
  },
  "assets_display": [
    {
      "tipo": "imagem_marketing",
      "nome": "disp_paisagem",
      "conteudo_hash": "sha256:<hex>",
      "origem": "gerado",
      "dados_base64": "<base64 do PNG>",
      "procedencia": {
        "motor": "…",
        "versao_do_motor": "…",
        "insumo": "…",
        "quando": "2026-10-08T21:00:00+00:00"
      }
    },
    "… mais 3 envelope(s)"
  ],
  "configuracao_display": {
    "lance": {
      "estrategia": "TARGET_SPEND",
      "teto_cpc": 0.35
    },
    "segmentacao": {
      "listas_de_usuarios": [
        "9304580046"
      ],
      "interesses": [
        "92000",
        "80226"
      ],
      "topicos": [
        "369"
      ],
      "placements": [
        "g1.globo.com/educacao"
      ],
      "palavras_chave": [
        "cursos senac",
        "curso tecnico"
      ],
      "publicos_em_observacao": true,
      "segmentacao_otimizada": false
    },
    "exclusoes": {
      "placements": [
        "site-ruim.com"
      ],
      "apps": [
        "2-com.exemplo.jogo"
      ],
      "topicos": [
        "1493"
      ],
      "lista_nova": {
        "nome": "Exclusoes Display prova",
        "placements": [
          "outro-ruim.com"
        ],
        "apps": [
          "1-123456789"
        ]
      }
    },
    "frequencia": [
      {
        "impressoes": 3,
        "unidade": "DAY",
        "nivel": "AD_GROUP_AD"
      },
      {
        "impressoes": 10,
        "unidade": "WEEK",
        "nivel": "CAMPAIGN"
      }
    ],
    "agenda": [
      {
        "dia": "MONDAY",
        "inicio_hora": 6,
        "fim_hora": 24
      },
      {
        "dia": "TUESDAY",
        "inicio_hora": 6,
        "fim_hora": 12,
        "inicio_minuto": 15,
        "fim_minuto": 30
      }
    ],
    "dispositivos_excluidos": [
      "TABLET"
    ],
    "presenca_geo": "PRESENCE",
    "anuncio": {
      "chamada_para_acao": "Saiba mais",
      "cor_principal": "#0A3D91",
      "cor_destaque": "#F2A900",
      "cores_flexiveis": false,
      "videos_youtube": [
        "jNQXAC9IVRw"
      ]
    }
  }
}
```

### 8.3 Demand Gen (vídeo responsivo)

```json
{
  "opportunity_id": 990001,
  "customer_id": "5478096539",
  "login_customer_id": "6016739364",
  "budget_diario": 30.0,
  "canal": "DEMAND_GEN",
  "estrategia_lance": "TARGET_CPC",
  "copy": {
    "headlines": [
      "Guia de cursos Senac",
      "Cursos Senac 2026",
      "Inscrições Senac",
      "Cursos técnicos Senac",
      "Cursos livres Senac"
    ],
    "long_headlines": [
      "Guia completo de cursos Senac: modalidades e inscrições",
      "Cursos técnicos e livres do Senac em um só guia",
      "Como se inscrever nos cursos do Senac em 2026",
      "Requisitos, duração e unidades dos cursos Senac",
      "Compare cursos presenciais e EAD do Senac"
    ],
    "descriptions": [
      "Veja cursos, modalidades e como se inscrever.",
      "Compare cursos técnicos e livres do Senac.",
      "Saiba datas, requisitos e unidades.",
      "Guia informativo sobre cursos do Senac.",
      "Entenda as modalidades presencial e EAD."
    ],
    "business_name": "Credito Up"
  },
  "demand_gen": {
    "upgraded_targeting": false,
    "controles_de_canal": {
      "estrategia": "SELECTED_CHANNELS",
      "selected_channels": [
        "youtube_in_stream",
        "youtube_in_feed",
        "youtube_shorts",
        "discover",
        "gmail",
        "display",
        "maps"
      ]
    },
    "audiencias": [],
    "intencoes": [],
    "exclusoes_de_audiencia": []
  },
  "assets_demand_gen": [
    {
      "tipo": "logo_quadrado",
      "nome": "dg_logo",
      "conteudo_hash": "sha256:<hex>",
      "origem": "gerado",
      "dados_base64": "<base64 do PNG>",
      "procedencia": {
        "motor": "…",
        "versao_do_motor": "…",
        "insumo": "…",
        "quando": "2026-10-08T21:00:00+00:00"
      }
    }
  ],
  "configuracao_demand_gen": {
    "formato": "VIDEO_RESPONSIVO",
    "lance": {
      "estrategia": "TARGET_CPC",
      "target_cpc": 0.6
    },
    "video": {
      "youtube_ids": [
        "M7lc1UVf-VE",
        "jNQXAC9IVRw"
      ],
      "call_to_action": "LEARN_MORE",
      "breadcrumb1": "cursos",
      "breadcrumb2": "senac"
    },
    "publico": {
      "nome": "Publico Cursos Senac (prova integracao)",
      "user_lists": [
        "customers/5478096539/userLists/9305091609"
      ],
      "lookalikes": [
        {
          "nome": "LAL visitantes (prova integracao)",
          "sementes": [
            9304580046
          ],
          "expansao": "BALANCED",
          "paises": [
            "BR"
          ]
        }
      ],
      "exclusoes_user_list": [
        "customers/5478096539/userLists/9302797284"
      ],
      "idades": [
        "18-24",
        "25-34",
        "35-44"
      ],
      "generos": [
        "FEMALE",
        "MALE"
      ],
      "rendas": [
        "INCOME_RANGE_0_50",
        "INCOME_RANGE_50_60"
      ],
      "status_parentais": [
        "NOT_A_PARENT",
        "PARENT"
      ]
    },
    "segmentacao_otimizada": true,
    "automacoes": {
      "GENERATE_SHORTER_YOUTUBE_VIDEOS": "OPTED_IN",
      "GENERATE_LANDING_PAGE_TEXT": "OPTED_OUT"
    },
    "agenda": [
      {
        "dia": "MONDAY",
        "inicio": "08:00",
        "fim": "22:30"
      },
      {
        "dia": "TUESDAY",
        "inicio": "08:00",
        "fim": "22:30"
      },
      {
        "dia": "WEDNESDAY",
        "inicio": "08:00",
        "fim": "22:30"
      },
      {
        "dia": "THURSDAY",
        "inicio": "08:00",
        "fim": "22:30"
      },
      {
        "dia": "FRIDAY",
        "inicio": "08:00",
        "fim": "22:30"
      }
    ]
  }
}
```

### 8.4 Performance Max (dois asset groups)

```json
{
  "opportunity_id": 990001,
  "customer_id": "5478096539",
  "login_customer_id": "6016739364",
  "budget_diario": 20.0,
  "canal": "PERFORMANCE_MAX",
  "estrategia_lance": "MAXIMIZE_CONVERSIONS",
  "tcpa": 3.5,
  "copy": {
    "headlines": [
      "Cursos Senac 2026",
      "Guia de Cursos do Senac",
      "Veja Áreas e Modalidades"
    ],
    "long_headlines": [
      "Guia informativo com áreas, modalidades e como se inscrever no Senac"
    ],
    "descriptions": [
      "Conheça as áreas de cursos do Senac.",
      "Guia informativo com modalidades, requisitos e passo a passo de inscrição."
    ],
    "business_name": "Credito Up"
  },
  "pmax": {
    "brand_guidelines_enabled": true,
    "audiencias": [],
    "search_themes": [
      "cursos senac",
      "senac cursos 2026"
    ],
    "negativas": [
      "download pirata"
    ],
    "nome_do_asset_group": "Senac — Guia geral"
  },
  "assets_pmax": [
    {
      "tipo": "imagem_marketing",
      "nome": "pm_paisagem",
      "conteudo_hash": "sha256:<hex>",
      "origem": "gerado",
      "dados_base64": "<base64 do PNG>",
      "procedencia": {
        "motor": "…",
        "versao_do_motor": "…",
        "insumo": "…",
        "quando": "2026-10-08T21:00:00+00:00"
      }
    },
    "… mais 4 envelope(s)"
  ],
  "configuracao_pmax": {
    "path1": "cursos",
    "path2": "senac",
    "opcoes_de_url": {
      "sufixo_extra": [
        [
          "vc_ag",
          "geral"
        ]
      ]
    },
    "videos": [
      {
        "video_id": "M7lc1UVf-VE",
        "nome": "video_senac_guia"
      }
    ],
    "grupos_adicionais": [
      {
        "nome": "Senac — Cursos livres",
        "url_final": "https://creditoup.com.br/r/guia-cursos-senac/?secao=livres",
        "textos": {
          "headlines": [
            "Cursos Livres do Senac",
            "Áreas e Modalidades",
            "Como se Inscrever"
          ],
          "long_headlines": [
            "Guia dos cursos livres do Senac com áreas, carga horária e inscrição"
          ],
          "descriptions": [
            "Veja as áreas de cursos livres.",
            "Entenda modalidades, carga horária e o passo a passo para se inscrever."
          ]
        },
        "imagens": [
          {
            "tipo": "imagem_marketing",
            "nome": "pm_paisagem_g2",
            "conteudo_hash": "sha256:<hex>",
            "origem": "gerado",
            "dados_base64": "<base64 do PNG>",
            "procedencia": {
              "motor": "…",
              "versao_do_motor": "…",
              "insumo": "…",
              "quando": "2026-10-08T21:00:00+00:00"
            }
          },
          "… mais 2 envelope(s)"
        ],
        "sinais": [
          {
            "tipo": "search_theme",
            "valor": "cursos livres senac"
          }
        ],
        "videos": [
          {
            "video_id": "jNQXAC9IVRw"
          }
        ],
        "path1": "cursos",
        "path2": "livres",
        "opcoes_de_url": {
          "sufixo_extra": [
            [
              "vc_ag",
              "livres"
            ],
            [
              "vc_tema",
              "{_tema}"
            ]
          ],
          "tracking_url_template": "{lpurl}?vc_tpl={_tema}",
          "parametros_personalizados": [
            [
              "tema",
              "livres"
            ]
          ]
        }
      }
    ],
    "automacoes_optadas": [
      "FINAL_URL_EXPANSION_TEXT_ASSET_AUTOMATION",
      "TEXT_ASSET_AUTOMATION",
      "AUTOMATED_VIDEO_CRAWL"
    ],
    "video_crawl": [
      {
        "url": "https://creditoup.com.br/r/guia-cursos-senac/",
        "plataforma": "LANDING_PAGE"
      },
      {
        "url": "https://www.youtube.com/@senacbrasil",
        "plataforma": "YOUTUBE"
      }
    ],
    "video_crawl_direitos_declarados": true,
    "exclusoes_de_url": [
      {
        "nome": "sem blog",
        "argumento": "/blog/"
      }
    ],
    "termos_excluidos": [
      "gratis",
      "garantido"
    ],
    "restricoes_de_mensagem": [
      "Não prometer vaga, bolsa ou aprovação."
    ],
    "diretrizes_de_marca": {
      "cor_principal": "#0B3D91",
      "cor_destaque": "#F2A900",
      "fonte": "Roboto"
    },
    "negativas_tipadas": [
      {
        "texto": "senac vagas emprego",
        "match_type": "PHRASE"
      },
      {
        "texto": "senac login",
        "match_type": "EXACT"
      }
    ],
    "marcas_excluidas": [
      {
        "entity_id": "/g/11trqcwsy6",
        "nome": "Coursera"
      }
    ],
    "metas_de_conversao": [
      {
        "categoria": "PURCHASE",
        "origem": "WEBSITE",
        "biddable": false
      }
    ]
  }
}
```

## 9. O que este contrato NÃO cobre

- Carrossel de Demand Gen pela fronteira HTTP (§3).
- Meta de cliente novo de PMax (`meta_cliente_novo`): aceita na forma e
  avisada; é aplicada numa SEGUNDA chamada pós-criação (`CampaignGoalConfig`
  não existe em `MutateOperation`) e não está no `validate_only`.
- Criação real de Demand Gen e PMax: continuam fechadas (`permite_mutacao_real`
  e canário), independentemente da configuração.
