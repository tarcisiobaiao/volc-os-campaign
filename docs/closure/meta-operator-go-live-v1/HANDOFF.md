# Meta Operator Go Live — fechamento da execução

Base do pacote: `4c2d17a215a13c7202c99bf89b65ef92926e9300`
HEAD documental de partida: `b3afa8b8e86d2d27650d03f4e747e5756dcf9ba6`
Branch única: `execution/volc-os-operacao-80-20` · Worktree: `/private/tmp/volc-os-operacao-80-20`
Data: 07/09/2026

## Veredito, em uma frase

O criador Meta deixou de ser ABO fixo de um conjunto e passou a ter contrato,
compilador, catálogos, importação de mídia e interface para ABO/CBO, múltiplos
conjuntos, público real e conversões existentes — **tudo provado localmente e
nada provado remotamente**. Nenhum objeto foi criado na Meta, nenhum workflow
foi publicado no n8n e nenhum schema foi aplicado no Supabase oficial.

**35 de 46 aceites em LOCAL_PASS · 5 NOT_PROVEN · 6 WAITING_OWNER · ZERO REMOTE_PASS.**

## O achado que muda o plano

Uma leitura somente-leitura do Supabase oficial (`database.agenciavolc.com.br`),
confirmada por dois ângulos independentes — tabelas por PostgREST e RPCs por
`PGRST202` — estabeleceu um fato que o pacote de especificação declarava
desconhecido:

> **Nenhuma tabela e nenhuma RPC do trilho Meta existe hoje na base oficial.**

O Estúdio Criativo está aplicado (`criativo_job`, `criativo_master`,
`criativo_projeto`); o trilho Meta não — nem `trafego_meta_ad_account`, nem
`trafego_meta_create_step`, nem `trafego_meta_persistir_snapshot`.

A consequência é operacional, não acadêmica: **hoje o runtime Meta não tem onde
gravar recibo nenhum**. Aprovação, ledger da saga, read model, insights e
registro de mídia falhariam fechados — o comportamento correto, e também a razão
pela qual nenhum marco remoto pode ser declarado pronto.

Aplicar exige `psql` (as migrations do trilho abrem com `\set ON_ERROR_STOP on`
e o manifesto declara `psql` como executor obrigatório). Esta instalação expõe
apenas `SUPABASE_URL` + `SERVICE_ROLE_KEY`, quer dizer, PostgREST. **A janela
está aguardando o operador**, não uma decisão técnica.

## O que passou a existir

| Marco | Estado | O que mudou |
|---|---|---|
| Contrato V2 | local | `receitas.py` (registro tipado, transcrito da matriz adjudicada) + `contrato_v2.py` (campanha + conjuntos[] + anúncios[]) |
| ABO/CBO | local | união discriminada: os dois níveis juntos são recusados antes de qualquer rede |
| Múltiplos conjuntos | local | `adset_key` estável; reordenar não troca identidade |
| Público | local | geo incluída **e** excluída, raio, públicos existentes, idade, posicionamentos |
| Mensuração | local | `REPORT_ONLY` × `OPTIMIZE` separados; tri-state `UNKNOWN` consertado |
| Catálogos | local | pixels/datasets, públicos e geografia — nenhum existia antes |
| Importação | local | individual e ZIP, origem `importado` aditiva, 78 provas de segurança |
| Registro de mídia | local | ato próprio, autorização por conta, recibo antes do POST |
| n8n | local | credencial real (`httpHeaderAuth`), migration de escopo, publicador dry-run |
| Canário | ficha | documento com as provas que faltam; zero execução |

### O V1 ficou intacto, e isso é provado

Um plano na forma provada continua sendo decodificado e compilado pelo mesmo
código de antes. `test_meta_contrato_v2.py::test_v2_emite_os_mesmos_payloads_que_o_v1_para_a_mesma_campanha`
compara os payloads de `campaign`, `adset` e `creative` **campo a campo**. Sem
essa igualdade, "versionar o contrato" seria só uma forma elegante de escrever
um segundo compilador que diverge em silêncio — e o preço apareceria numa conta
real, não numa suíte.

### O bug que o pacote mandou procurar

`adaptador.py`: `bool(linha.get("is_archived"))` transformava campo **ausente**
em `False`, e a conversão caía em `AVAILABLE_*`. Quer dizer: *"não sei"* era
apresentado como *"disponível"*, e um seletor de otimização ofereceria uma
conversão que a conta talvez recuse. Corrigido com `booleano_opcional`
(`None` ≠ `False`) e vocabulário estendido com `UNKNOWN`, `UNKNOWN_FRESHNESS` e
`INVALID`. Elegibilidade e frescor viraram **eixos separados**.

Houve controle de mutação: restaurando a semântica antiga, 4 das contraprovas
centrais falham. Elas mordem — não passam por construção.

## Provas que exercitaram mundo real

- **PostgreSQL descartável, três vezes.** O ciclo do registro de mídia
  (apply → uso → idempotência → isolamento → cerca → rollback → reapply)
  fechou **25/25 asserções**; a migration de escopo do n8n rodou sobre a cadeia
  real `v13_01 → v15_01 → v15_02 → 20260907210000`; a `v11_04` da importação foi
  aplicada, reaplicada e sondada com 13 verificações de comportamento.
- **Leitura remota do n8n.** 396 workflows, paginação completa, **zero
  escritas**. Nove workflows têm "meta" no nome e **não** são o artefato — três
  deles ativos. É exatamente por isso que o publicador procura por
  origem/hash/owner e nunca por nome.
- **Leitura remota do Supabase oficial.** Somente leitura, dois ângulos.

### Um defeito que só apareceu porque foi ao banco

A RPC canônica **não recusa** um snapshot de insights: ela grava
`escopo='hierarchy'` em silêncio. Uma leitura de insights entrava no ledger como
leitura de hierarquia. Isso é pior do que a incompatibilidade que a spec previa,
e só ficou visível ao alimentar a RPC real com o snapshot que o próprio JS do
workflow gera.

## O que está bloqueado, e por quê

| # | Bloqueio | Natureza | Próximo ato |
|---|---|---|---|
| 1 | Schema Meta ausente no oficial | falta string de conexão `psql` | operador fornece a conexão ou roda a janela do `SCHEMA-RUNBOOK.md` |
| 2 | Credencial n8n não provisionada | item não existe no cofre | operador cria o item Header Auth na UI segura e preenche `CRED_META_ITEM_ID` |
| 3 | Inspeção visual autenticada | extensão do navegador não conecta | operador faz login e captura desktop + mobile |
| 4 | `validate_only` do plano atual | exige conta escolhida + flag do servidor | operador escolhe uma conta e clica |
| 5 | Registro de vídeo | upload em fases + miniatura própria não implementados | tarefa separada |
| 6 | Idiomas e segmentação detalhada | catálogo do `/search` sem contrato provado | tarefa separada |

Nenhum desses virou verde por conveniência. O bloqueio 2 é **mecânico**:
`--apply` recusa antes de abrir socket. O bloqueio 3 é declarado como
`WAITING_OWNER` em vez de ser substituído por jsdom — o contrato proíbe alegar
QA de pixel a partir de um DOM simulado, e não alegamos.

## Autoridades que continuam fechadas

Zero criação de Campaign/AdSet/Ad/Creative — nem em PAUSED. Zero ativação. Zero
agenda ligada. Zero CAPI. Zero público criado. Zero conversão definida. Zero
push. As flags de criação (`META_CREATE_PAUSED_ENABLED`,
`META_CREATE_LEDGER_WRITE_ENABLED`) seguem fechadas, e a flag nova de upload de
mídia é **separada** delas: subir uma imagem e gastar verba são riscos
diferentes, e amarrá-los obrigaria a abrir a porta do gasto para poder subir uma
peça.

## Números medidos

| Medida | Baseline | Agora |
|---|---|---|
| Testes Meta (backend) | 417 | **656** |
| Suíte `backend/tests` | — | **4532** passando, 3 falhas **pré-existentes**, 89 pulados |
| Testes de interface | 139 | **199** |
| Erros TypeScript | 77 | **76** |
| Conferências do validador n8n | 265 | 293 |

### As falhas que existiam antes, e a prova de que são pré-existentes

- `test_canario_pedido_aprovado` (2) e `test_trafego` (1): `trafego.py` e
  `canario.py` estão **intactos desde a base** (`git diff --quiet` contra
  `b3afa8b`). São da lane Google Ads; nada nesta missão as tocou.
- Rodar `backend/tests volc_ads` **junto** acrescenta 16 falhas em
  `test_meta_supply_bytes` que **não** acontecem isoladamente. É poluição entre
  suítes pré-existente: `volc_ads` teve **zero** arquivos alterados nesta missão,
  e a poluição se reproduz com `pytest volc_ads backend/tests/test_meta_supply_bytes.py`.
  Vale um conserto próprio — não é desta missão.

## A revisão focal, e o que ela pegou

Seis eixos de risco revisados em paralelo, cada achado depois atacado por um
cético instruído a **refutar**. Trinta agentes; **11 achados sobreviveram**, 12
foram refutados. Sete foram corrigidos na rodada corretiva.

Os dois mais graves eram a mesma família, no registro de mídia:

1. **5xx virava FALHOU — e FALHOU autoriza nova tentativa.** Um 502 de gateway
   não prova nada: o multipart já foi encaminhado e o `adimages` pode ter
   nascido. O servidor reenviaria os mesmos bytes e criaria um **segundo ativo
   na biblioteca do cliente**. Hoje "recusa explícita" é 4xx **com** o objeto de
   erro do provedor; todo o resto é AMBIGUO.
2. **Só `TimeoutException` era capturado.** Uma queda de conexão depois do POST
   atravessava tudo e deixava a reserva pendurada em DESPACHAR.

A invariante que amarra as correções está provada: **nenhuma saída de
`_registrar_uma` deixa a reserva sem fechamento** — o teste percorre os quatro
cenários.

Um achado ALTA foi **refutado** e está registrado como tal: "evento arbitrário
vira `custom_event_type`". O cético mostrou que Traffic não admite `OPTIMIZE` e
que as receitas de conversão exigem prova remota inexistente — o caminho não é
alcançável hoje. Fica anotado, não corrigido.

Quatro achados confirmados **não** foram corrigidos, e estão nomeados em
`CHECKPOINT-RESULTS.json` com o porquê. O principal: **AMBIGUO ainda é um beco
sem saída** — sair dele exige uma RPC de reconciliação cercada, com migration e
provas próprias, e isso é tarefa, não rodada corretiva.

O co-revisor externo (Gemini, autorizado pelo operador) leu um diff delimitado
das sete invariantes do registro de mídia e não encontrou violação — um lente a
mais, e a mais fraca das duas: ausência de achado prova menos que um achado.

## Ressalvas sobre o próprio gate do grafo

Duas, ambas medidas, ambas contra o meu próprio trabalho:

1. `working_tree_dirty_at_build: true` — o digest conta bytes de arquivos
   rastreados, não limpeza da árvore.
2. **Falso verde real:** `curadoria-operacional.json` e `ROADMAP-VIVO.json`
   **não** entram em `tracked_inputs()` (verificado carregando a função: os dois
   dão NÃO, num total de 1711 insumos). Editá-los sem reconstruir deixa o
   `--check` respondendo "current" enquanto o grafo gerado já não descreve a
   curadoria. Eu reconstruí pelo wrapper, então este estado é coerente — mas o
   gate não teria acusado se eu não tivesse.

## Memória operacional

`P11-T02`, `P11-T03`, `P11-T04`, `P11-T05`, `P11-T06` e `P10-T16` continuam
**todas `partial`**. Nenhuma foi promovida. O `CURATION-HANDOFF.json` do pacote
proíbe promoção, e — mais importante — os fatos não a sustentariam.

## Ambiente do operador

Preservado e no ar, tudo nesta worktree:

- **8080** — Vite (`/trafego/meta/nova` responde 200; processo nunca tocado)
- **3001** — Express (`server/index.js`)
- **8010** — FastAPI. **Reiniciado uma vez**, com o mesmo comando e o mesmo
  `cwd`, porque rodava código anterior às mudanças e as rotas novas não existiam
  no processo vivo. As rotas novas respondem 401 sem sessão, e uma rota
  inexistente responde 404 — o contraste é a prova de que elas estão montadas.

## Trabalho de OUTRO writer preservado na árvore

Durante o fechamento apareceram, não commitados, arquivos de outra frente
(assistente estratégico de criativos Meta): `backend/app/routers/criativos_agente.py`,
`backend/app/criativo/agente/`, `docs/closure/meta-creative-agent-v1/`,
`supabase/migrations/v11_05_criativo_agente_meta.sql` e o rollback correspondente,
mais duas linhas em `backend/app/main.py` e um campo em `backend/app/config.py`.

**Foram preservados, não commitados e não tocados.** Conferi a sobreposição em
`main.py`: as adições são estritamente aditivas e as minhas linhas
(`trafego_meta_ativos`, `criativos_importacao`) continuam intactas — não há
trecho sobreposto a parar.

⚠️ Consequência para o gate do grafo: o digest de frescor lê o CONTEÚDO dos
arquivos rastreados, então `main.py` e `config.py` entraram na reconstrução com
o estado não commitado do outro writer. É por isso que `working_tree_dirty_at_build`
importa, e é por isso que ele está sendo declarado aqui em vez de ficar só no
manifesto.

## Artefatos deste fechamento

- `HANDOFF.md` (este)
- `FIELD-BINDINGS-IMPLEMENTED.json` — F01–F40 com arquivo:linha **resolvidos do
  disco**, zero não-localizados
- `CHECKPOINT-RESULTS.json` — CP0–CP6 e A01–A46, com o que falta em cada um
- `SCHEMA-APPLY-RECEIPT.json` — o achado do CP1, sem credenciais
- `N8N-REMOTE-RECEIPT.json` — zero criados, com o motivo e o próximo ato
- `CANARY-AUTHORIZATION-REQUEST.json` — ficha; nenhuma execução implícita
- `prova-sql-registro-de-midia.sh` — o ciclo descartável, 25/25

## Próximo ato único e concreto

**Fornecer a string de conexão `psql` do Supabase oficial** (ou executar a janela
do `SCHEMA-RUNBOOK.md` na ordem que `verificar_perfil_schema_meta.py
--lista-apply` imprimir).

É o bloqueio de maior alcance: sem schema não há recibo durável, sem recibo
durável não há aprovação, e sem aprovação não há canário. Os outros três
bloqueios — credencial n8n, sessão de navegador e clique de validação — são
independentes entre si e podem cair em qualquer ordem depois dele.
