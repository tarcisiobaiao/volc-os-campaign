# Assistente Criativo — rumo à primeira geração real

Branch: `execution/volc-os-operacao-80-20`. Worktree `/private/tmp/volc-os-operacao-80-20`.
Base desta rodada: `83ca75ac2a33f010d9d87241da712e1e2431c0de`.
Sem push, sem deploy, sem branch ou worktree nova.

**A primeira geração real NÃO aconteceu.** Ela está bloqueada por um item que
não é de código e que esta rodada não tinha como resolver sozinha: não existe
caminho de SQL provisionado para o Supabase oficial. O resto do caminho foi
fechado, provado e deixado pronto para o clique.

## O bloqueio, em uma frase

As três tabelas do Assistente (`criativo_agente_operacao`, `_run`, `_decisao`)
não estão no banco oficial, e sem elas o **primeiro** ato da jornada — criar a
operação — falha. Aplicá-las exige `psql`; o host publica apenas HTTPS.

## CP0 — o que roda de verdade

| | valor | estado |
|---|---|---|
| Estratégia | `gemini-3.8-flash` via `GeminiClient` (httpx cru, `:generateContent`) | **PROVADO servido** |
| Imagem | `gemini-3.1-flash-image` via `MotorGeminiImagem` | **PROVADO servido** |
| Preço de referência | US$ 0,039/imagem — tabela do provedor, **não fatura** | CONFIGURADO |
| Formatos ponta a ponta | `1x1`→1080×1080, `4x5`→1080×1350, `9x16`→1080×1920 | SUPORTADO |
| Teto por pedido | 45 renders (`MAX_RENDERS_POR_PEDIDO`), conferido antes de gravar/despachar | SUPORTADO |
| Credencial de modelo | `GEMINI_API_KEY` presente | PROVADA (ListModels 200) |
| Storage | `ArmazenamentoLocal` (`~/.volc-os/criativos`) | SUPORTADO |
| Storage oficial privado | **não existe**: `GET /storage/v1/bucket` → `200`, **0 buckets** | MEDIDO HOJE |

`gpt-image-2` **existe neste repositório, mas não neste produto**: aparece (a) num
docstring do motor Gemini, explicando por que o caminho OpenAI não foi escolhido,
e (b) na cópia quarentenada `services/creative-studio/upstream`, cujo `main.py`
levanta `UPSTREAM_REFERENCE_ONLY` e que nada sob `backend/app` ou `src` importa.
Nenhuma imagem do Estúdio pode ser produzida por ele hoje. Modelo não foi trocado.

A verificação dos dois literais foi feita com **uma chamada ListModels somente
leitura** (`GET /v1beta/models`, HTTP 200, 55 modelos servidos). ListModels não
gera token de saída: custo de geração **zero**. Isso derruba a suspeita, que a
auditoria levantou com razão, de que `gemini-3.8-flash` pudesse não ser servido.

### Ciclo de vida do processo

O 8010 sobe **sem worker, sem reaper, sem cron e sem lifespan de reconciliação**
(`startup_reconciliation: DISABLED`, medido no `/health` após o reinício desta
rodada). `QUEUED` existe no schema e nada o consome sozinho: quem executa é um
POST humano. Isso é seguro — subir o processo não gasta — e é uma limitação:
uma run abandonada fica `QUEUED` até alguém clicar.

## O que esta rodada implementou

### 1. A revisão sobrevive ao reload (a lacuna conhecida)

`GET /operacoes/{ref}` devolvia `operacao` e `runs` e mais nada. As decisões
estavam gravadas, append-only, e mesmo assim o F5 mostrava o lote inteiro como
não revisado. Agora a rota projeta `decisoes` (a efetiva de cada caminho) e
`aprovacoes_validas` **por run**. A tela deixou de ser dona da aprovação.

### 2. Aprovação passou a ser sobre conteúdo, não sobre endereço

Defeito que estava escondido atrás do primeiro: `_lote_e_aprovados` conferia só
o `path`. Como o caminho endereça por `ref` e a ref sobrevive ao refinamento,
**uma peça reescrita continuava aprovada** e liberava o botão que gasta. Agora a
aprovação só conta se o conteúdo naquele caminho ainda casar com o
`snapshot_sha256` aprovado. O dublê de teste que devolvia `snapshot: {}` foi
corrigido — ele aprovava por caminho e por isso não pegava nada.

### 3. O gasto exige consentimento, e o consentimento é reconferido

`POST /geracoes` passou a exigir `autorizacao {modelo, total_de_renders,
teto_custo_usd}`. Sem ela: `409 CRIATIVO_STUDIO_SEM_AUTORIZACAO_DE_GASTO`, com o
modelo e o total que precisam ser confirmados, e `nada_foi_criado`. Divergiu o
modelo, o total ou estourou o teto: `409` próprio, sempre antes do primeiro job.

O teto em dólar é declarado como **estimativa** na API e na tela: o provedor
cobra por token e não devolve o preço da chamada. O limite que o servidor impõe
com exatidão é a **contagem de renders**. A tela diz isso em vez de prometer um
controle financeiro que o mecanismo não tem.

### 4. Quatro defeitos que a primeira geração real encontraria

- **Galeria, leitura parcial.** `Promise.all` fazia UM id que falhasse descartar
  as leituras boas — um 404 transitório apagava da tela os formatos já prontos.
  E o `catch` matava o timer: a galeria parava de acompanhar para sempre.
  Agora é `allSettled`, leitura parcial é estado próprio e o laço continua.
- **Download.** O guard comparava `blob.type !== p.mime` com `p.mime` podendo
  ser `null` (o contrato documenta `null` como "ninguém mediu"), então toda
  rendition sem MIME registrado era indownloadável — o caso de um acervo
  recém-gerado.
- **Event loop.** `executor.disparar` é síncrono até o render terminar e era
  chamado direto da corrotina: o processo inteiro congelava durante a geração.
- **Aviso falso.** A tela dizia "Execute a estratégia quando quiser" enquanto a
  linha seguinte já executava o modelo pago.

### 5. Procedência do modelo

`criativo_agente_run.model` gravava o modelo **pedido**, e o cliente descartava
`modelVersion`. Um alias servido por outro literal ficava indetectável. Agora o
recibo grava `pedido→servido` quando divergem. Sem migration: a coluna é `text`.

### 6. Runbook oficial guardado

`scripts/aplicar-assistente-criativo-oficial.sh` conhece **três** arquivos,
confere o sha256 de cada um contra o manifesto CP3, exige `DATABASE_URL` no
ambiente (nunca lê `.env`, nunca ecoa a URL), recusa `*.supabase.co` e faz
read-back de catálogo, RLS, policies, ACL, constraints e grants, com `NOTIFY
pgrst` no fim.

O ensaio em cluster descartável **encontrou um defeito que o manifesto não
previa**: a v11_06 é idempotente sozinha, mas **não depois da v11_07** — a ponte
cria FKs compostas sobre as mesmas chaves únicas que a v11_06 derruba e recria,
e o `drop` bate em *other objects depend on it*. O runbook passou a medir as
cinco invariantes da v11_06 e a pular a migration quando as cinco valem. Meio a
meio ele **para**, em vez de escrever com a porta possivelmente aberta.

## Estado do banco oficial

Medido hoje, por PostgREST autenticado com `service_role` (somente leitura):

- 109 tabelas/views expostas, 92 RPCs, **nenhuma** RPC de SQL arbitrário.
- Presentes: `criativo_job`, `criativo_master`, `criativo_rendition`,
  `criativo_pacote`, `criativo_aprovacao`, e as 11 tabelas do parque — ou seja,
  **v11_01 e v11_02 estão aplicadas**, como o ledger registra.
- Ausentes: `criativo_render_*` (v11_03), `criativo_importacao_*` (v11_04) e
  `criativo_agente_*` (v11_05) — coerente com o ledger, que marca v11_03 como
  não aplicada.

Isso é **evidência forte, não prova física**. O que a torna forte é o ACHADO H
já registrado neste repositório: o `pg_default_acl` de `public` concede em toda
tabela nova, então uma tabela criada em `public` apareceria no catálogo do
PostgREST. Continua sendo evidência: só um catálogo por `pg_catalog` decide.

## Por que a janela não abriu

| via | resultado |
|---|---|
| porta 5432 / 6543 no host oficial | fechada/filtrada |
| HTTPS | responde (401 sem chave) — mas PostgREST não executa DDL |
| RPC de SQL arbitrário | não existe entre as 92 |
| `DATABASE_URL` / `PG*` no ambiente | ausente em todos os arquivos de env |
| SSH ao host | porta 22 aberta e `known_hosts` tem entradas, mas a política de permissão **desta sessão** bloqueou o teste; não foi contornada |

O ledger registra que as migrations anteriores foram aplicadas por
`supabase_admin` com o "runbook privado de infraestrutura", que não está neste
repositório. `P11-T03` já registrava o mesmo bloqueio em 07/09/2026.

## Provas desta rodada

- **Backend**: 855 passed / 59 skipped (suítes criativa + Pautador — o cliente
  Gemini é compartilhado e não regrediu). 17 testes novos.
- **Frontend focal**: 31 passed (a base era 26).
- **Build Vite**: OK. **TypeScript** por `tsconfig.app.json`: **76** erros
  herdados, idêntico à base, **zero** nos arquivos desta frente.
- **SQL descartável**: `provar-ciclo-assistente-criativo.sh` → *PROVA OK* nos
  sete arquivos com sha256 conferido. Ensaio do runbook → *ENSAIO OK*
  (conferir, aplicar, reaplicar).
- **Grafo**: `--check` `current=true`, "insumos idênticos".
- **8080**: no ar, servindo esta worktree, rota `200`. **8010**: reiniciado nesta
  rodada, `/health` ok, rota do agente `401` sem sessão.

### O que NÃO foi provado

- Nenhuma chamada de **geração** a nenhum provedor. Zero imagens produzidas.
- Nenhuma escrita no Supabase oficial. Nenhuma migration aplicada.
- **Inspeção visual autenticada não aconteceu**: a extensão de navegador não
  conectou nesta sessão (`Browser extension is not connected`). Não há afirmação
  de QA de pixel a partir de HTTP 200 ou de jsdom.
- Se a `GEMINI_API_KEY` tem direito de **geração de imagem** (e não só texto)
  continua desconhecido: ListModels não responde isso.

## O próximo ato exato

1. **Operador provisiona o acesso SQL localmente** — túnel ou execução no host,
   conforme o runbook privado — e exporta `DATABASE_URL` no shell. Nunca no chat,
   nunca em arquivo versionado.
2. `./scripts/aplicar-assistente-criativo-oficial.sh --conferir` — só leitura;
   devolve o catálogo real e decide se o conjunto é criação ou delta.
3. Se o catálogo confirmar criação pura: `--aplicar`, e registrar o read-back no
   ledger `supabase/migrations/README.md`.
4. **Autorizar a geração paga** informando modelo, quantidade e teto. O teste
   inicial recomendado é **uma peça × um formato = 1 render**, estimativa
   US$ 0,04. A tela já coleta e o servidor já reconfere.
5. Inspecionar visualmente com sessão real em 375/768/1440 px, claro e escuro.

Ficam pendentes, e **não** foram resolvidas aqui: o bucket privado oficial (0
buckets hoje), a coluna de custo por asset, `owner_id` nas linhas de asset, e a
ponte para a biblioteca da Meta.

## Meta

Nenhum upload, validação, criação ou ativação na Meta ou no Google Ads. O pacote
`backend/app/criativo` não importa nenhum módulo de `app.trafego` nem cliente
`graph.facebook`/`googleads`, e **nenhuma variável `META_*` existe em nenhum
arquivo de ambiente** desta worktree. Gerar imagem não aprova para mídia paga.

P11-T02, P11-T04 e o nó `cap_creative_engines` permanecem **partial**.
