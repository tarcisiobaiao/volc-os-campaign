# ADRs — camada de Tráfego

**Estado:** ADR-01 a ADR-20 ✅ aprovados e congelados em 24/08/2026 · ADR-21 a ADR-27 propostos em 26/08/2026 (rodada Google Growth Engine), aguardando aceite do dono
**Porta de entrada:** [TRAFEGO.md](./TRAFEGO.md) · **Fatos:** [ledger](./EVIDENCIAS-TRAFEGO.md)

> **Marcação:** **[F]** fato comprovado (com `E-nn` do ledger) · **[I]** inferência ·
> **[DA]** decisão aceita · **[DP]** decisão pendente · **[R]** risco ·
> **[DE]** dependência externa.
>
> Números não são repetidos aqui — cada `E-nn` aponta para o ledger.

---

## ADR-01 · A conta de anúncio é a autoridade sobre existência e status

**[DA] Aceita.** O Google Ads define o que existe e em que estado; o banco é memória
governada com carimbo de frescor.

**Contexto.** **[F]** `campaigns` tem quatro linhas com `customer_id` vazio e não contém a
campanha FGTS, que existe na conta ([E-01](./EVIDENCIAS-TRAFEGO.md#e-01), [E-02](./EVIDENCIAS-TRAFEGO.md#e-02)).

**Alternativa rejeitada.** Tratar `campaigns` como verdade — reproduziria o defeito que
tornou a FGTS invisível.

**Consequência.** Divergência entre conta e banco é **informação exibida**, não erro
corrigido em silêncio.

---

## ADR-02 · Duas identidades internas: instância e linhagem

**[DA] Aceita.** O VOLC O.S. passa a ter **duas** identidades internas, com papéis distintos:

| identidade | granularidade | o que agrupa | muda quando |
|---|---|---|---|
| `volcCampaignId` | **1:1 com uma campanha externa** | uma instância | nunca |
| `campaignLineageId` | **1:N sobre instâncias** | a intenção operacional: testes, relançamentos, substituições | nunca |

A identidade **externa** continua sendo o par `(customer_id, campaign_id)`.

**Contexto.** **[F]** A FGTS gerou três campanhas externas em uma noite, duas delas
declaradas como teste de Ad Strength no recibo; a Maquininha, duas ([E-05](./EVIDENCIAS-TRAFEGO.md#e-05)). Uma identidade
só não consegue ser ao mesmo tempo estável por instância (para URL, auditoria e recibo) e
agregadora por intenção (para histórico e prevenção de duplicidade). **[F]** `customer_id`
vazio nas quatro linhas torna a identidade externa incompleta hoje ([E-02](./EVIDENCIAS-TRAFEGO.md#e-02), [E-10](./EVIDENCIAS-TRAFEGO.md#e-10)).

**Alternativa rejeitada.** Uma identidade só, agrupando relançamentos — perderia a
correspondência 1:1 com o recibo e com a campanha real, que é o que torna a auditoria
possível.

**Rotas.**

```
/trafego/campanhas/:volcCampaignId          ← canônica, uma instância
/trafego/linhagens/:campaignLineageId       ← histórico da intenção  [DP: só se ganhar uso]
/dashboard/campaign/:campaignId             ← compatibilidade, redireciona
```

**Consequência.** URLs estáveis; recibo e auditoria por instância; histórico e prevenção
de duplicidade por linhagem.
**[R]** Um `campaignId` legado ambíguo deve levar a uma escolha explícita, nunca a um palpite.
**[DP]** Como a linhagem é atribuída: derivada do funil/oportunidade, declarada no
lançamento, ou inferida por equivalência. Recomendação: **declarada no lançamento**, com
inferência apenas como sugestão.

---

## ADR-03 · Duplicidade se decide por composição, não por um sinal

**[DA] Aceita.** Antes de subir, uma prova **somente leitura na conta real** avalia sinais e
compõe um veredito. **URL final idêntica, isoladamente, não bloqueia.**

**Contexto.** **[F]** O quadro exibe "montar campanha" para a FGTS agora ([E-04](./EVIDENCIAS-TRAFEGO.md#e-04)); **[F]**
relançar é legítimo e aconteceu cinco vezes com motivo declarado ([E-05](./EVIDENCIAS-TRAFEGO.md#e-05)). Uma mesma URL pode
legitimamente receber campanhas distintas — canal diferente, segmentação diferente, ou uma
substituição planejada.

**Regra de composição.** Os sinais são de duas naturezas, e a distinção é o que decide:

| natureza | sinal | peso |
|---|---|---|
| **pré-requisito** | mesma conta | sem isto, nada compõe |
| **de destino** | mesma URL final | forte |
| **de destino** | mesmo canal | forte |
| **de intenção** | mesma linhagem (`campaignLineageId`) | forte |
| **de intenção** | mesmo funil / oportunidade | forte |
| **de intenção** | sobreposição relevante de keywords exatas | forte |
| **de contexto** | mesma segmentação (geo, idioma, rede) | médio |
| **de contexto** | mesmo slug na taxonomia do nome | médio |

**Veredito:**

- **bloqueio** — mesma conta **e** ≥ 2 sinais fortes, dos quais **ao menos um é de
  intenção** (linhagem, funil/oportunidade ou sobreposição de keywords), com a campanha
  existente não removida;
- **advertência com confirmação** — mesma conta e qualquer combinação que não satisfaça o
  acima: **inclusive URL final idêntica sozinha, e inclusive URL + mesmo canal**;
- **segue** — nenhum sinal forte.

**Por que URL + canal não basta.** Duas campanhas Search para a mesma página podem ser
deliberadas: teste A/B de copy, separação por geo, ou uma substituição em andamento. O que
caracteriza duplicidade não é apontar para o mesmo lugar — é **disputar a mesma demanda**.
Só um sinal de intenção prova isso. Bloquear sem ele transforma a prova num obstáculo a
trabalho legítimo, e o operador aprende a ignorar o bloqueio.

**Alternativas rejeitadas.** Tratar URL idêntica como "equivalente certo" (bloquearia
substituição planejada). Tratar URL + canal como suficiente (bloquearia teste A/B e
separação por geo, que são trabalho legítimo).

**Consequência.** Bloqueio nunca é opinião: ele nomeia os sinais que compuseram e a qual
natureza cada um pertence. Relançar continua disponível em qualquer veredito, exigindo motivo.
**[DP]** O limiar de "sobreposição relevante" de keywords.
**[R]** Sem sinal de intenção disponível — campanha sem linhagem nem vínculo, como a FGTS
hoje — o veredito máximo é advertência. É o preço de não bloquear trabalho legítimo, e ele
diminui à medida que a reconciliação avança.

---

## ADR-04 · Sete conceitos de sinal, não uma tabela genérica

**[DA] Aceita.** Sinal · Ocorrência · Incidente · Reconhecimento · Proposta ·
Execução/Recibo · Resolução. A notificação é **projeção**, não entidade.

**Contexto.** **[F]** Não existe tabela de alerta hoje ([E-06](./EVIDENCIAS-TRAFEGO.md#e-06)); estreia e reincidência são
indistinguíveis, porque a única medida de tempo é "horas ligada", não duração da condição.

**Consequência.** A auto-resolução é preservada com rastro (`causa_sumiu`). O sino pode ser
removido da arquitetura sem perda de informação. Escopo por onda: ver ADR-14.

---

## ADR-05 · Fronteira com o n8n, em vez de expulsão

**[DA] Aceita.** Núcleo (políticas, autorização, estado de domínio, mutação de conta) é do
VOLC O.S. O n8n permanece legítimo como **scheduler** e **adaptador**, chamando contratos
internos autenticados. Proibido: superfície pública sem autenticação, mutação de conta fora
do Executor, e segundo dono de escrita em tabela de domínio.

**Contexto.** **[F]** Os dois fluxos JoinAds são a única ingestão viva e apontam para o banco
correto; o webhook de mineração é chamado pelo próprio backend ([E-12](./EVIDENCIAS-TRAFEGO.md#e-12)).

**Alternativa rejeitada.** "n8n: zero papel" — desligaria a única ingestão viva e trataria a
ferramenta como o problema, quando o problema é a fronteira.

---

## ADR-06 · Investigação por log, nunca por rotação-sonda

**[DA] Aceita.** Ordem: ler execuções e logs → classificar com a fonte → propor autenticação
real, allowlist, rotação coordenada ou desativação aprovada → executar com aprovação e janela.

**Contexto.** A proposta anterior de "rotacionar o path e observar quem quebra" foi
**retirada**: path não é autenticação, e usar a quebra de terceiros como instrumento de
medição faz o consumidor externo descobrir a falha antes de nós.

**Consequência.** **[DA]** Ausência de memória sobre consumidores não é evidência de desuso.
Endpoint crítico indeterminado **não fica ligado indefinidamente** — ver ADR-15.
**[DE]** O passo 1 depende do histórico de execuções do n8n.

---

## ADR-07 · O cockpit existente é capacidade preservada

**[DA] Aceita.** `/dashboard/campaign/:campaignId` não é substituído. A tela e seus
componentes permanecem; a **fonte** muda e a rota canônica passa a ser interna (ADR-02).

**Contexto.** **[F]** Seis componentes de gestão já construídos, mais frescor, filtro de
período, gráficos e as regras de moeda, imposto e ROAS ([E-17](./EVIDENCIAS-TRAFEGO.md#e-17)).

**Consequência.** O caminho de ação da caixa de lance sai; a caixa fica e passa a produzir
Proposta.
**[R]** O cockpit lê `daily_campaign_metrics` ([E-20](./EVIDENCIAS-TRAFEGO.md#e-20)), cuja autoridade não está resolvida —
trocar a fonte sem resolver isso reproduz o problema numa tela nova.

---

## ADR-08 · A leitura da conta sai do caminho de renderização

**[DA] Aceita.** Sincronização agendada no backend; a tela lê snapshot com carimbo;
degradação honesta; atualização manual limitada por escopo e frequência.

**Contexto.** **[F]** O sino mora no `Layout` e cada carregamento custa 2,4 s de descoberta
mais ~5 consultas seriais por conta, em três contas; o polling só corre com a aba em foco
([E-07](./EVIDENCIAS-TRAFEGO.md#e-07), [E-13](./EVIDENCIAS-TRAFEGO.md#e-13)).

**Consequência.** Custo constante em vez de proporcional à navegação.
**[R]** O custo cresce com o número de campanhas; reavaliar a partir de ~50.

---

## ADR-09 · Vínculo campanha → funil é auditável, corrigível e reversível

**[DA] Aceita.** O sistema sugere; o operador confirma. O vínculo registra quem, quando,
qual regra casou, qual evidência e qual vínculo anterior foi substituído. Desvincular é
operação de primeira classe.

**Contexto.** **[F]** A regra da URL final casa a FGTS ao funil run 9 ([E-01](./EVIDENCIAS-TRAFEGO.md#e-01), [E-03](./EVIDENCIAS-TRAFEGO.md#e-03)) — e ainda
assim não basta.

**Consequência.** **[R]** vínculo errado contamina atribuição de receita de forma permanente
e silenciosa; o custo de confirmar recai sobre o operador, e é deliberado.
**[DP]** Se, medida a taxa de acerto da sugestão, a confirmação pode ser dispensada em
casamento exato.

---

## ADR-10 · Procedência declarada pela aplicação não pode ser derivada pelo banco

**[DA] Aceita.** Separar o que o banco **deriva** (o estado que espelha a conta) do que a
aplicação **declara** (a procedência do cadastro): campos distintos, donos distintos.

### O que está comprovado

**[F]** O trigger `sync_status_from_google_ads` sobrescreve `status_source` para `'auto'`
sempre que `google_ads_status` não é nulo, e a porta de criação sempre o envia ([E-08](./EVIDENCIAS-TRAFEGO.md#e-08)).
**Existe um conflito comprovado entre a aplicação e um trigger do banco**: a procedência que
a aplicação declara é inalcançável por construção.

**[F]** O filtro do INSERT descarta apenas nulos — string vazia atravessa.
**[F]** Falha de persistência vira aviso no corpo da resposta HTTP, exibido uma vez e nunca
guardado.

### O que continua em investigação

**[I]** A **origem do `customer_id` vazio** não está estabelecida: o recibo do lançamento traz
a conta preenchida ([E-05](./EVIDENCIAS-TRAFEGO.md#e-05)) e a linha resultante está vazia ([E-10](./EVIDENCIAS-TRAFEGO.md#e-10)).
**[I]** O **intervalo de nove minutos** entre o lançamento e o `created_at` não tem explicação
comprovada.
**[I]** O **caminho exato do INSERT** não está identificado: [E-09](./EVIDENCIAS-TRAFEGO.md#e-09) mostra um INSERT registrado
com `customer_id` na lista de colunas, por role `postgres`, mas a extensão não guarda tempo
nem processo.

> **Este ADR não declara a existência de dois escritores independentes.** O que está provado
> é o conflito aplicação × trigger. A hipótese de um segundo produtor de INSERT permanece
> hipótese até que a investigação a confirme ou descarte.

**Consequência.** Três consertos distintos: separar autoridade de campo; recusar vazio no
identificador de conta; transformar falha de persistência em evento operacional (ADR-14).
**[DA]** A investigação precede qualquer backfill — **[R]** backfillar antes de entender o
mecanismo pode ser sobrescrito por ele.
**[F]** DML não é logado e os logs de contêiner já rotacionaram a janela relevante ([E-11](./EVIDENCIAS-TRAFEGO.md#e-11));
**[DE]** ampliar a instrumentação exige decisão do dono.

---

## ADR-11 · Nenhuma regra de bidding, graduação ou automação está aprovada

**[DA] Aceita como estado.** Ficam **[DP]**: promoção de termo sempre gerar campanha nova ·
aumentar sempre exigir humano na hora · só reduzir ser automatizável · aposentadoria
definitiva de cada workflow · regras de graduação e teto de tCPA.

**Contexto.** **[F]** O gatilho "30 conversões" não tem sensor e o sistema não sabe ajustar,
só criar e remover ([E-15](./EVIDENCIAS-TRAFEGO.md#e-15)). **[F]** O regime de Smart Bidding de 17/08 transformou meta em
gasto efetivo.

**Consequência.** O P0 não implementa atuação; P0-A entrega parecer, não execução.
**[R]** Um parecer que conclua "é lance" cria pressão por atuação sem porta governada.

---

## ADR-12 · Campanhas de teste permanecem pausadas

**[DA] Aceita.** As campanhas de teste da FGTS **não são removidas**; permanecem pausadas até
o inventário reconciliado ([E-05](./EVIDENCIAS-TRAFEGO.md#e-05)).

**Consequência.** O inventário do primeiro dia mostra mais campanhas do que "as duas no ar",
e isso é correto: são fatos da conta. **[DP]** o destino delas após a reconciliação.

---

## ADR-13 · Estados de presença honestos, sem "sumiu da conta"

**[DA] Aceita.** O estado `sumiu da conta` está **retirado** — ele funde causas diferentes num
rótulo que sugere um fato (a campanha deixou de existir) que a varredura não consegue provar.

| estado | significa | como se chega |
|---|---|---|
| `removida` | a conta declara a campanha como removida | lida na conta, com status removido |
| `não encontrada` | a conta foi lida com sucesso e a campanha não estava lá | varredura bem-sucedida, sem correspondência |
| `conta não identificada` | não sabemos em que conta procurar | **[F]** `customer_id` vazio nas quatro linhas ([E-02](./EVIDENCIAS-TRAFEGO.md#e-02)) |
| `fora de escopo` | a conta existe, mas não está sob o MCC da casa | fora de [E-13](./EVIDENCIAS-TRAFEGO.md#e-13) |
| `sincronização falhou` | não foi possível ler a conta nesta varredura | erro na varredura |
| `legado não reconciliado` | veio de antes do inventário e nunca foi conferido | estado inicial de linhas históricas |

**[DA]** As três linhas de fevereiro começam como **`legado não reconciliado`** — não como
"não encontrada". **[F]** Elas têm `customer_id` vazio ([E-02](./EVIDENCIAS-TRAFEGO.md#e-02)), então nem sequer sabemos onde
procurá-las: afirmar ausência seria inventar uma medição.

**Consequência.** Cada estado tem um caminho de saída diferente, e nenhum deles é apagar a
linha.

---

## ADR-14 · O P0 registra evento operacional; o modelo completo é do P1

**[DA] Aceita — opção (b).** O P0 **não** entrega o núcleo de Ocorrência/Incidente. Ele
entrega um **evento operacional mínimo**: registro append-only, com carimbo, tipo, chave de
agrupamento, sujeito (campanha/conta) e carga. No P1 esse registro é **promovido** a
Ocorrência, e a agregação em Incidente é construída sobre ele.

**Contexto.** O P0 precisa de uma coisa só: que uma falha de persistência (e depois qualquer
detecção) **não se perca** — hoje ela vira aviso volátil no corpo HTTP. Reconhecimento,
severidade, dedupe e resolução são necessidades do P1, quando existirem incidentes para
reconhecer.

**Alternativa rejeitada.** Entregar o núcleo mínimo de Ocorrência/Incidente já no P0 —
ampliaria o escopo com decisões (chave de dedupe, política de severidade) que ainda não têm
casos suficientes para serem decididas com evidência.

**Consequência.** A promoção é **aditiva**, não migração: o evento operacional é um subconjunto
estrito de Ocorrência. **[R]** Se a chave de agrupamento for mal escolhida no P0, a agregação
do P1 herda o defeito — por isso ela é gravada como campo livre e opaco no P0, sem semântica
embutida.

---

## ADR-15 · Endpoint crítico indeterminado exige aceitação temporária de risco

**[DA] Aceita.** Nenhum endpoint crítico permanece ligado por tempo indefinido com a
justificativa de "não sabemos se é usado". Classificação `indeterminado` obriga a um
**registro de aceitação de risco** com quatro campos:

| campo | conteúdo |
|---|---|
| **aceite** | quem, nominalmente, aceita o risco |
| **prazo** | data-limite da aceitação |
| **controle compensatório** | o que reduz o risco enquanto isso |
| **reavaliação** | data em que a decisão volta à mesa |

Controles compensatórios aceitáveis, em ordem de preferência: autenticação real ·
allowlist de origem · limite de taxa · monitoramento de invocação com alerta.

**Contexto.** **[F]** `apply-bidding` muta lance na conta real e `factory v3` cria campanha
por formulário público ([E-12](./EVIDENCIAS-TRAFEGO.md#e-12)); **[DE]** a evidência de uso depende do histórico de execuções
do n8n.

**Consequência.** "Indeterminado" deixa de ser um estado de repouso e passa a ser um estado
com relógio. **[R]** Sem prazo, indeterminado vira permanente — que é como esses endpoints
chegaram até aqui.

---

## ADR-16 · Uma porta documental e um ledger de evidências

**[DA] Aceita.** [TRAFEGO.md](./TRAFEGO.md) é a única porta de entrada da camada.
[EVIDENCIAS-TRAFEGO.md](./EVIDENCIAS-TRAFEGO.md) é a fonte única dos fatos medidos; PRD,
SPEC, planos e ADRs **linkam** `E-nn` em vez de repetir números.

**Contexto.** O mesmo número aparecia em quatro documentos; a primeira medição a mudar
deixaria três deles errados sem que ninguém percebesse.

**Consequência.** Fato desatualizado se conserta em um lugar. Documento que cita número sem
`E-nn` está fora do padrão. **[DA]** Todo documento declara se é vigente, vigente em parte
ou superado — a tabela de precedência vive na porta.

---

## ADR-17 · Núcleo comum de operação + perfil/adaptador por canal

**[DA] Aceita.** A camada de Tráfego é um **Hub de Controle de Mídia**: um núcleo horizontal
que não conhece Search, e um perfil por canal que injeta a semântica específica.

**O núcleo comum** — nenhum destes conceitos pode citar keyword, asset group, placement ou
audiência: conta de mídia · campanha concreta · linhagem/intenção · projeto · funil ·
**canal e subtipo** · estado externo · snapshot e frescor · vínculo e procedência · evento
operacional · sinal/incidente · proposta · autorização · execução e recibo · política ·
auditoria.

**O perfil de canal** declara, de forma tipada: que estágios o cockpit mostra · que painéis
o detalhe injeta · que campos o pedido carrega · que provas o `validate_only` roda · que
tipos de proposta existem · como o adaptador lê e escreve na API.

**Contexto.** **[F]** Existe **um único construtor de grafo** (`campanha/search.py`); Display
e Demand Gen têm ajuste de campanha sem construtor, e PMax levanta exceção ([E-21](./EVIDENCIAS-TRAFEGO.md#e-21)). O sistema
está no melhor momento possível para separar núcleo de canal: **antes** do segundo canal
existir, e **depois** do primeiro provar o ciclo.

**Alternativas rejeitadas.** *JSON genérico por canal* — perde tipagem e empurra validação
para runtime, exatamente onde a API do Google é implacável. *`if canal === …` espalhado* —
cada canal novo vira uma varredura pelo produto inteiro. *Abstrair antes de Search fechar o
ciclo* — abstração sobre um exemplo só é adivinhação (ver ADR-19).

**Consequência.** Regra de acoplamento: **nenhum tipo do núcleo importa um tipo de canal**.
A dependência aponta sempre de canal → núcleo. O teste é mecânico e vira gate: procurar
`keyword`, `asset_group`, `placement`, `audience` nos módulos do núcleo deve dar zero.

---

## ADR-18 · Vocabulário canônico de canal, com subtipo

**[DA] Aceita.** Um único vocabulário de canal, igual em engine, backend, banco e front, com
os nomes do **enum do Google Ads** — e um campo `subtipo` separado.

| canal | estado real hoje |
|---|---|
| `SEARCH` | **construtor completo** — o único |
| `DISPLAY` | ajuste de campanha, **sem construtor de grafo** |
| `DEMAND_GEN` | ajuste de campanha, **sem construtor de grafo** |
| `PERFORMANCE_MAX` | **não existe** — levanta exceção |
| `VIDEO`, `SHOPPING`, `DISCOVERY` | citados em listas soltas, sem implementação |

**Contexto.** **[F]** O vocabulário diverge em cinco lugares ([E-21](./EVIDENCIAS-TRAFEGO.md#e-21)): o front declara
`PMAX`, a taxonomia declara `PERFORMANCE_MAX`, o construtor implementa três canais e
levanta `ValueError` no resto, a marcação conhece cinco, um tipo do front lista seis, e o
backend aceita `canal: str` **livre, sem validação**. A string `PMAX` não existe no enum do
Google nem no engine — ela falharia no `getattr`.

**Decisão.** `PERFORMANCE_MAX` é o nome canônico. `PMAX` é apelido de tela, nunca valor de
contrato. O backend valida o canal contra o vocabulário e **recusa canal sem construtor**
com mensagem que diz o que existe — em vez de deixar o `ValueError` do engine vazar.

**Consequência.** **[DA]** PMax **não é tratado como existente** em nenhum documento, tela
ou contrato. Aparece apenas no vocabulário, com estado declarado.
**[R]** O front hoje oferece `PMAX` num tipo; até a unificação, um pedido com esse valor
falha tarde e com mensagem ruim.
**[DP]** Se `subtipo` (por exemplo, Search padrão × Search dinâmico, ou PMax com feed ×
sem feed) entra já no vocabulário ou quando o segundo canal chegar.

---

## ADR-19 · Extension point declarado, não implementado

**[DA] Aceita.** O P0 prepara **pontos de extensão**, não implementações. Um ponto de
extensão só é legítimo se satisfizer os três critérios:

1. **Nasce da estrutura, não da especulação** — existe porque o núcleo precisa dele para
   funcionar com Search, não porque um canal futuro talvez precise.
2. **Tem um consumidor real hoje** — Search o exercita. Ponto de extensão com zero
   consumidores é código morto com nome bonito.
3. **Custa pouco se estiver errado** — trocar um contrato interno sem consumidor externo é
   barato; trocar um schema com dados é caro.

**Proibido no P0:** tela vazia por canal · tabela por canal sem linhas · interface com uma
implementação e um `NotImplementedError` · campo `jsonb` "para o futuro" · rota registrada
sem destino.

**Contexto.** **[F]** O repositório já tem o padrão do erro a evitar: `src/types/trafego.ts`
declara quatro canais e só um tem tela; `Brief.conversao` viaja do pedido até o engine e
**nenhum módulo o lê**; a esteira de escala da fábrica legada referencia um nó que não
existe. Abstração sem consumidor não fica parada — ela apodrece e depois mente.

**Consequência.** A régua de aceite de cada ponto de extensão é: *"Search usa isto hoje?"*
Se a resposta for não, ele sai do P0.

---

## ADR-20 · Matriz de autoridade documental, não precedência linear

**[DA] Aceita.** A regra *"o código ganha de tudo"* está **retirada**: ela é verdadeira sobre
comportamento e falsa sobre intenção. A autoridade depende do **tipo de pergunta**.

| pergunta | autoridade | por quê |
|---|---|---|
| "o que o sistema **faz** hoje?" | **o código** | é o que executa |
| "o que **existe** na conta de anúncio?" | **a conta** (via snapshot com frescor) | ADR-01 |
| "qual é o **número** medido?" | **o ledger** ([E-nn](./EVIDENCIAS-TRAFEGO.md)) | tem data e método |
| "**por que** está assim?" | **os ADRs** | guardam o contexto e a alternativa rejeitada |
| "o que **deve** ser construído?" | **PRD e SPEC** | o código não sabe o que ainda não é |
| "o que é **proibido**?" | **as regras duras do dono** | acima de tudo |
| "o que a **operação** decidiu?" | **o dono** | nenhum documento decide por ele |

**Contexto.** A precedência linear anterior tornava impossível registrar dívida: se o código
sempre ganha, um defeito conhecido vira especificação. **[F]** O caso concreto: o trigger
apaga a procedência da aplicação ([E-08](./EVIDENCIAS-TRAFEGO.md#e-08)) — o código "ganha" no comportamento e **perde** na
intenção; é defeito, não contrato.

**Consequência.** Divergência entre código e SPEC é **item de trabalho**, não erro de
documento. Quando o código contraria um ADR, um dos dois muda — deliberadamente, e o ADR
registra qual.

---

# Rodada Google Growth Engine — 26/08/2026

> Os ADRs abaixo foram decididos na missão do **Google Growth Engine**, que abre
> criação em lote, multicanal e autogestão assistida. Eles não revogam nenhum dos
> vinte anteriores; ADR-11 (nenhuma automação de bidding aprovada) e ADR-12
> (campanhas de teste permanecem pausadas) continuam valendo e são **pressuposto**
> de ADR-26.

---

## ADR-21 · "Em massa" é preparação em massa, ativação progressiva

**[DA] Aceita.** O lote prepara, valida e cria **pausado**. Ativar é um ato separado,
com aprovação própria, e começa por **um** canário — nunca pelo lote inteiro.

**Contexto.** A palavra "massa" carrega uma ambiguidade cara: preparar cinquenta
campanhas e ligar cinquenta campanhas parecem o mesmo trabalho e têm consequências
de ordens de grandeza diferentes. Preparar em massa é ganho de velocidade e é
reversível — nada gastou. Ligar em massa é a única operação da esteira que **não**
tem desfazer barato: o dinheiro já saiu, e o aprendizado do leilão já começou
errado em cinquenta lugares ao mesmo tempo.

**Alternativa rejeitada.** Um único portão de aprovação cobrindo criação e ativação.
Ele economiza um clique e transforma "revisei a estrutura" em "autorizei o gasto",
que são duas afirmações diferentes feitas pela mesma pessoa em momentos em que ela
sabe coisas diferentes.

**Consequência.** A esteira tem **dois** portões humanos, e eles não se fundem:
`aprovar criação pausada` e `aprovar ativação`. Uma campanha criada e nunca ativada
é um resultado legítimo do lote, não um lote incompleto.

---

## ADR-22 · A idempotência da criação é da aplicação; a API não a oferece

**[DA] Aceita.** Cada item de lote carrega uma `idempotency_key` determinística,
**persistida antes** da chamada. A chave é derivada da intenção, não do relógio.

**Contexto.** O `MutateOperation` do Google Ads não aceita chave de idempotência de
cliente. Um `mutate` que atinge timeout de rede deixa a aplicação sem saber se a
campanha existe. É o caso que separa um lote confiável de um que cria duplicatas
sob carga — e é justamente sob carga que ele acontece.

O engine já tem metade da resposta: o `Selo` de `volc_ads/subir.py` carrega a
impressão digital das operações, então o payload não muda entre a prova e a escrita
sem que alguém perceba. Falta a outra metade — saber, depois de um silêncio, se
aquele payload chegou a virar campanha.

**Alternativa rejeitada.** Chave derivada de carimbo de tempo. Ela é única, o que
parece bom, e por isso mesmo **não** reconhece a retomada: a segunda tentativa do
mesmo item ganha chave nova e cria a segunda campanha.

**Consequência.** A chave entra no banco **antes** do envio, com o estado
`enviando`. Quem retoma encontra o registro e pergunta à conta antes de agir.

---

## ADR-23 · Resultado remoto indeterminado reconcilia; nunca repete

**[DA] Aceita.** Diante de timeout, erro de rede ou resposta ilegível, o sistema
**consulta a conta** antes de qualquer nova tentativa. Repetição cega é proibida.

**Contexto.** É o corolário operacional do ADR-22, e merece ADR próprio porque a
tentação é estrutural: toda biblioteca de retry do mundo repete por padrão, e o
retry automático é exatamente o comportamento certo para leitura e exatamente o
errado para criação. `volc_ads/gads/client.py` já classifica falha em retentável e
terminal — a classificação precisa passar a considerar **o que a operação faria**,
não só o que o erro diz.

**Alternativa rejeitada.** Confiar no `request_id` para deduplicar do lado do
Google. Ele identifica a requisição para suporte; não impede a segunda.

**Consequência.** Existe um estado `indeterminado` no ciclo de vida do item de
lote, e ele **não** é um estado de erro: é um estado que exige leitura. Sair dele
só por evidência da conta.

---

## ADR-24 · Regra de otimização é dado versionado com relógio declarado

**[DA] Aceita.** Nenhuma regra de autogestão entra como código. Toda regra é um
registro versionado que declara, obrigatoriamente: `objetivo` ·
`canais_aplicaveis` · `janela_minima_dias` · `atraso_de_conversao_dias` ·
`amostra_minima` · `dados_obrigatorios` · `teto_de_orcamento` ·
`limite_de_alteracao` · `cooldown_horas` · `confianca` · `condicao_de_rollback` ·
`responsavel`.

⚠️ **A unidade vai no nome do campo, e isso não é preciosismo.** `janela_minima: 2`
não diz se são dois dias ou duas horas, e a regra que interpretar errado espera 24×
mais ou 24× menos do que deveria — silenciosamente, porque os dois valores são
plausíveis. O inventário do legado n8n adotou essa convenção antes deste ADR
existir; o ADR seguiu o código.

**Contexto.** Uma regra em código não tem como ser desligada por quem opera, não
guarda quem a escreveu nem por quê, e — o pior — não consegue declarar sua própria
insuficiência. Uma regra que não sabe dizer "minha amostra é pequena demais para
esta conta" recomenda com a mesma voz nos dois casos.

Campo desconhecido é `null`, nunca um número plausível. Um valor inventado de
amostra mínima é pior que a ausência dele: a ausência bloqueia a regra, o número
inventado a libera.

**Alternativa rejeitada.** Configuração em arquivo de ambiente. Ela não versiona, não
audita e não sobrevive à pergunta "por que esta campanha foi pausada em agosto?".

**Consequência.** A regra é dado, então ela é consultável, diffável e reversível — e
uma proposta pode citar **qual versão** da regra a gerou.

---

## ADR-25 · Nenhuma regra universal de pausa, lance, orçamento ou negativa

**[DA] Aceita.** Estão proibidas, como regra do sistema: *"CPA acima de X pausa"* ·
*"aumente sempre 20%"* · *"CPC baixo é sempre o problema"* · *"sem conversão em um
dia significa campanha ruim"*.

**Contexto.** Cada uma dessas frases é verdadeira em algum lugar e falsa na conta ao
lado, e nenhuma delas declara em qual dos dois está. "CPC baixo é o problema" é o
exemplo vivo desta rodada: ele é a hipótese de partida das duas campanhas Search, é
plausível, e **não pode ser aceito sem prova** — se a campanha não for elegível, o
lance é irrelevante e agir sobre ele consome a única janela de teste disponível
tratando o sintoma errado.

**Negativas têm exigência adicional.** Só podem ser propostas a partir de relatório
**real** de termos de busca, com contexto do negócio e revisão explícita de
overblocking. Lista genérica de negativas, "termos comumente excluídos" ou exemplo
ilustrativo não substituem o relatório — e não devem sequer ser oferecidos como
ponto de partida, porque um exemplo vira um padrão.

**Alternativa rejeitada.** Regras universais com limiar configurável. O limiar
configurável dá a impressão de que a regra foi adaptada, quando o que precisava
mudar era a pergunta.

**Consequência.** Toda proposta carrega a evidência que a sustenta e a amostra que
a limita. Uma proposta sem amostra suficiente é **exibida como insuficiente**, não
escondida — quem opera precisa saber que o sistema olhou e não soube.

---

## ADR-26 · T1 é o teto desta rodada — a automação recomenda, o humano aplica

**[DA] Aceita.** O motor de autogestão nasce em **T1**: detecta, diagnostica e
propõe. A aplicação é humana. A arquitetura prepara **T2** (delegação limitada),
e T2 **não é ativado**.

**Contexto.** É a continuação direta do ADR-11 — nenhuma regra de bidding, graduação
ou automação está aprovada — agora com um nome para o degrau seguinte, de modo que
"preparar para T2" e "ligar T2" sejam pedidos distintos que ninguém confunda.

**Alternativa rejeitada.** Ligar T2 para mudanças "pequenas" (lance abaixo de um
delta, orçamento dentro de um teto). O tamanho da mudança não é o que a torna
segura; o que a torna segura é a evidência que a sustenta, e essa evidência é
exatamente o que ainda não existe nesta conta.

**Consequência.** Existe um campo de nível de autonomia por regra, e **todo valor
diferente de T1 é recusado** na validação enquanto o ADR não for revisto. O ponto
de extensão satisfaz o ADR-19 porque T1 o exercita hoje.

---

## ADR-27 · Custo e receita ficam lado a lado até a janela ser reconciliada

**[DA] Aceita.** Enquanto receita e atribuição não estiverem reconciliadas, custo
do Google Ads e receita de monetização são **exibidos lado a lado**, com a limitação
declarada na própria tela. Nenhuma soma, subtração, razão ou margem entre os dois.

**Contexto.** Os dois números existem, e é por isso que o erro é fácil: janelas
diferentes (dia da conta de anúncio × dia do relatório de receita), fusos diferentes,
moedas potencialmente diferentes e definições de atribuição diferentes. Um ROAS
calculado sobre isso não é aproximado — é uma afirmação sobre uma quantidade que
ninguém mediu, com a aparência de precisão que um número decimal carrega.

**Alternativa rejeitada.** Calcular a margem com uma nota de rodapé sobre a
limitação. A nota é lida uma vez; o número é lido todo dia, e entra em decisão.

**Consequência.** A camada econômica é construída **de baixo para cima**: primeiro a
reconciliação de janela, fuso e moeda; só depois o indicador composto. Até lá, a
tela mostra dois números honestos em vez de um número conveniente.
