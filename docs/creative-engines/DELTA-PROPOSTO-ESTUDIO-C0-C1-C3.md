# Delta proposto para o Mapa Vivo — Estúdio Criativo C0 + C1 + C3

**Status:** proposta factual, **não aplicada**
**Data:** 27/08/2026
**Branch:** `feat/estudio-criativo-c0-c1-c3` (commits `bc98dc2`…`cd2fcf3`)

## Por que este arquivo existe em vez da edição direta

O envelope desta execução paralela proíbe editar `docs/volc-os-graph/curadoria-operacional.json`,
o Roadmap Vivo e as saídas geradas do Graphify enquanto a missão Search estiver em
andamento. Duas frentes escrevendo a mesma curadoria produzem exatamente o
conflito que a curadoria existe para evitar.

Este documento é o delta para a integração aplicar **uma única vez**, depois da
convergência das duas branches. Cada item traz a evidência que o justifica; nada
aqui deve ser aplicado sem que a evidência seja reconferida no resultado combinado.

## Ressalva sobre o estado do grafo

`python3 scripts/atualizar_grafo_volc_os.py --check` retorna
`{"current": false, "reason": "UPDATE_STATUS.json ausente"}` nesta worktree, e
`graphify-out/` e `.venv-graphify/` não existem aqui (são gitignored e não foram
gerados). **Nenhuma afirmação deste relatório veio de consulta ao grafo**: tudo
foi obtido por leitura direta de código, execução real e consulta ao
`curadoria-operacional.json` versionado.

O comando de reconstrução (`python3 scripts/atualizar_grafo_volc_os.py`, sem
`--reuse-technical`, porque a camada de código mudou) deve rodar **depois** do
merge, não agora.

---

## 1. `cap_creative_engines` — de `partial` para `partial` (evidência nova)

**Não promover para `implemented`.** A capacidade continua parcial, e o motivo
mudou de lugar: antes o buraco era "nenhum caminho HTTP alcança o motor"; agora
existe caminho HTTP, e o buraco é o que está listado em "pendências" abaixo.

Evidência a **acrescentar** (a evidência anterior continua verdadeira para o
recorte de Tráfego, e não deve ser apagada):

> 27/08/2026 — existe caminho HTTP até um motor de imagem real. `POST
> /api/criativos/jobs` cria job persistido e devolve sem esperar o render;
> `services/creative_engine/motores/gemini_imagem.py` implementa
> `volc_ads.criativo.porta.MotorDeCriativo` sobre `gemini-3.1-flash-image`.
> Job real executado: 3 renditions (1080×1080, 1080×1350, 1080×1920) com **três
> `content_hash` distintos**, dimensão nativa e enquadramento registrados por
> peça (`resize`, `cover_crop`, `cover_crop`). Persistência provada num cluster
> descartável com PostgREST à frente, não em produção.
> **A ponte `criativo_ponte.py` continua sem consumidor HTTP** e o Display
> continua sem `validate_only`: o Estúdio produz patrimônio, não publica.

## 2. `concept:creative-engine-registry` — de `partial` para `partial` (evidência nova)

> 27/08/2026 — o catálogo deixou de ser só manifesto externo mais catálogo em
> memória: `criativo_brand_pack`, `criativo_projeto`, `criativo_job`,
> `criativo_master` e `criativo_rendition` existem como schema versionado
> (`supabase/migrations/v11_01_estudio_criativo.sql`), **não aplicado em
> produção**. Procedência (motor, versão, hash do insumo, brand pack) é NOT NULL
> no master.

## 3. Nós novos propostos

| id | rótulo | cluster | estado | evidência |
|---|---|---|---|---|
| `cap_estudio_criativo` | Estúdio Criativo (imagem e vídeo) | `production` | `partial` | rotas `/criativos/*` no app shell; job real de imagem com 3 formatos; biblioteca, detalhe e aprovação auditada; build de vídeo observado |
| `concept:asset-provenance` | Procedência de ativo criativo | `production` | `implemented` | `criativo_master` com motor, versão, hash do insumo, hash do conteúdo, disclosure e licença; gatilho de imutabilidade |
| `cap_video_observado` | Leitura de build de vídeo externo | `production` | `implemented` | `backend/app/criativo/video_observado.py`; `short_odete` lido com sha256 batendo o `freeze.json` |
| `doc:estudio-spec` | SPEC do Estúdio Criativo | `governance` | — | `docs/design/SPEC-ESTUDIO-CRIATIVO-VOLC.md` |
| `risco:c01-isolacao-video` | Render de vídeo concorrente é inseguro | `platform` | `open` | 21 de 26 geradores da fábrica escrevem em singletons compartilhados; os migrados não têm teste de concorrência; raiz absoluta embutida em `pipeline/buildspace.py` |
| `defeito:routers-nao-versionados` | `publicacao` e `redator` importados e nunca commitados | `platform` | `open` | `git log` vazio para os dois; `main.py` os importava no topo desde `f4cf128`; qualquer checkout limpo não subia a API |

### ⚠️ `concept:creative-job-contract` NÃO é nó novo

**Correção de 28/08/2026, tarde.** A versão anterior deste documento listava
`concept:creative-job-contract` entre os nós novos, com estado `implemented`.
Ele **já existe** na curadoria, com estado `partial`, resumo próprio, evidência
sobre `volc_ads/criativo` e a porta `MotorDeCriativo`, e **nove arestas**
apontando para ele — de `channel:DISPLAY`, `channel:DEMAND_GEN`,
`channel:PERFORMANCE_MAX`, `system:aprova-ad-studio`, `system:positivo-ad-studio`,
`system:volc-creative-port`, `concept:creative-engine-registry` e
`concept:video-production-contract`.

Aplicar aquela linha teria duplicado o id ou sobrescrito em silêncio um nó que
metade do domínio de aquisição referencia — e teria promovido para `implemented`
um contrato que a curadoria descreve como parcial por bons motivos.

O correto é **acrescentar evidência ao nó existente**, sem mudar o estado:

> 28/08/2026 — o envelope ganhou forma HTTP e persistida no recorte do Estúdio:
> `src/types/criativos.ts` declara os 7 estados canônicos com falha parcial por
> peça e cursor de eventos, e a `v11_01` os grava. Isto cobre o recorte
> Estúdio; o recorte Ads/Display do contrato original (variantes por canal,
> `criativo_ponte`) **continua sem consumidor HTTP**.

## 4. Arestas novas propostas

```
cap_estudio_criativo        --produz-->        concept:asset-provenance
cap_estudio_criativo        --implementa-->    doc:creative-service-adr
cap_estudio_criativo        --usa-->           concept:creative-job-contract
cap_estudio_criativo        --depende-de-->    cap_creative_engines
cap_video_observado         --observa-->       risco:c01-isolacao-video
cap_google_multichannel     --consome-->       cap_estudio_criativo   (planejado, C2)
cap_meta_ads                --consome-->       cap_estudio_criativo   (planejado, C5)
```

`cap_asset_vault` **não** deve ganhar aresta com o Estúdio: são coisas diferentes
(cofre de contas e credenciais versus patrimônio criativo), e a curadoria já
avisa para não confundir os dois.

## 5. O que NÃO mudar

- **Não promover nada para `implemented` por causa da interface existir.** O
  Estúdio tem tela para pacote de destino? Não. Tem entrega? Não. As tabelas
  `criativo_pacote` e `criativo_entrega` nascem vazias e sem consumidor, de
  propósito, para que C2 não precise migrar tabela povoada.
- **Não registrar a migration como aplicada.** Ela não foi.
- **Não registrar o Supabase Storage como integrado.** O bucket `criativos` não
  existe em produção (`select * from storage.buckets` = zero linhas, 27/08/2026)
  e o adaptador está escrito e **não ativado**.
- **Não registrar custo real de geração.** O provider reporta tokens, não
  dólares; o que existe é estimativa declarada com fonte.

## 6. Linha do `supabase/migrations/README.md`

A tabela de estado de aplicação deve ganhar:

| Arquivo | Estado | Quando | Ambiente | Executor | sha256 | Dependência | Rollback |
|---|---|---|---|---|---|---|---|
| `v11_01_estudio_criativo.sql` | **não aplicada** | — | — | — | (recalcular no merge) | nenhuma | `v11_01_rollback.sql` |
| `v11_01_rollback.sql` | não executada em produção | — | ciclo completo provado em cluster descartável | — | (recalcular no merge) | v11_01 aplicada | — |

O hash deve ser recalculado **depois** do merge: qualquer correção de conflito
muda o arquivo, e um hash registrado antes descreveria outra coisa.

---

# Adendo de 28/08/2026 — a v11 entrou em produção e o parque virou dado

Este adendo **substitui** as partes do delta acima que diziam "migration não
aplicada" e "registro de motores sem persistência". O resto continua valendo.

## O que mudou de fato

`v11_01` e `v11_02` foram **aplicadas em `database.agenciavolc.com.br`** em
28/08/2026 14:01:40-03, com autorização explícita do dono, backup conferido antes
e ciclo completo verde em cluster descartável. Ver `supabase/migrations/README.md`
para hashes, verificação pós-aplicação e o estado do bucket.

## Delta de curadoria, revisado

### `concept:creative-engine-registry` — continua `partial` (evidência nova)

⚠️ **Correção de 28/08/2026, tarde.** A versão anterior desta seção propunha
promover para `implemented` e se chamava de "a única promoção que a evidência
sustenta" — enquanto o parágrafo seguinte admitia que "a adaptação runtime
continua parcial". As duas frases não podem ser verdade ao mesmo tempo, e a
segunda é a correta.

Mesmo depois de `f6c7ff1`, que fez o runtime **de fato** ler o banco, três
coisas seguem impedindo `implemented`: só 1 dos 3 motores catalogados tem
adaptador real; a resolução de `motor_id`/`modo_id`/`finalidade_id` é
best-effort e devolve `null` sem validar; e o catálogo continua em três lugares
(banco, `dominio.py`, `criativos.ts`) sem um teste que compare os três.

A evidência atual diz "Persistência, leitura runtime e adaptação ainda não
existem". As duas primeiras passaram a existir:

> 28/08/2026 — `public.criativo_motor` existe em produção com 3 motores
> registrados (`gemini-imagem`, `prensa`, `volc-factory`), cada um com runtime,
> provider, modelo, custo de referência com fonte, capacidades e o
> `cofre_asset_id` que costura com o Cofre de Ativos. Junto vieram 10 tabelas de
> domínio: modos com estado de prova, formatos, finalidades, exigências de canal
> com tetos combinados, 15 skins com arco narrativo real, 14 vozes e 28 gates.
> O parque deixou de viver em quatro cópias sem árbitro.
> **A adaptação runtime continua parcial**: o backend ainda lê o catálogo de
> `dominio.py`, não do banco. As colunas de vínculo (`criativo_job.motor_id`,
> `criativo_briefing.modo_id`, `criativo_aprovacao.finalidade_id`) existem e
> ainda não são preenchidas pelo executor.

> 28/08/2026, tarde (`f6c7ff1`) — a adaptação runtime deixou de ser ausente e
> passou a ser **parcial de verdade**: `GET /api/criativos/parque` lê as nove
> tabelas do parque, e `motor_id`/`modo_id`/`finalidade_id` passam a ser
> resolvidas na criação de job, briefing e aprovação. `GET /formatos` continua
> servindo `dominio.FORMATOS` de propósito — o banco declara 7 slots e o
> executor conhece 4, e apontar a rota para o banco faria a tela oferecer um
> formato que o motor recusa. A diferença é medida e devolvida em
> `divergencias`, não escondida.

### `cap_creative_engines` — continua `partial`

Não promover. O caminho HTTP existe e o parque está persistido, mas
`criativo_ponte` segue sem consumidor HTTP e o Display segue sem `validate_only`.

### `cap_asset_vault` — evidência a acrescentar

> 28/08/2026 — o `nextAction` dos dois ativos `creative_engine`
> (`asset:engine:image-volc`, `asset:engine:video-volc`) foi parcialmente
> atendido: `criativo_motor.cofre_asset_id` referencia os dois ids, e a costura
> existe do lado do Estúdio. O Cofre continua **sem persistência própria**
> (contrato mais fixture), então a FK ainda não pode ser criada.

### Nós novos propostos

| id | rótulo | cluster | estado |
|---|---|---|---|
| `concept:creative-park` | Parque criativo persistido | `production` | `implemented` |
| `concept:channel-requirements` | Exigências de asset por canal | `production` | `partial` |
| `defeito:catalogo-em-quatro-copias` | Catálogo de formatos duplicado em 4 lugares | `platform` | `mitigado` |

`defeito:catalogo-em-quatro-copias` entra como **mitigado** e não **fechado**: o
banco é a fonte agora, mas Python e TypeScript ainda carregam a própria cópia, e
o teste que os compara continua fraco (passa com alturas trocadas).

### Arestas novas

```
concept:creative-park       --persiste-->  concept:creative-engine-registry
concept:creative-park       --costura-->   cap_asset_vault
concept:channel-requirements --alimenta-->  cap_google_multichannel
cap_estudio_criativo        --le-->        concept:creative-park
```

## O que NÃO mudar

- **O bucket não foi criado.** `storage.buckets` continua em `0`. Nada no grafo
  deve dizer que o object storage oficial está integrado.
- **Nenhum custo virou medido.** `criativo_motor.custo_referencia_usd` é preço de
  provider com fonte declarada, não fatura.
- **Nenhuma peça foi produzida em produção.** 0 jobs, 0 projetos.
