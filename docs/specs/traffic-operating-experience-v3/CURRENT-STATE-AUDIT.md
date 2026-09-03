# CURRENT-STATE-AUDIT — o que existe hoje, medido

Base factual: `207e91f1da290130e8d02b78c3ba1c8e9a761111`, ancestral de `origin/volc-os-v2 @ 3331c0c`.
Toda afirmação deste arquivo tem `arquivo:linha`. Toda ausência tem a busca que voltou vazia.

**O que este arquivo NÃO é:** não é um plano, não é um julgamento de mérito e não é uma lista de tarefas. É o retrato. O plano está em `IMPLEMENTATION-SLICES.md`; o julgamento, em `DECISION-LOG.md`.

---

## 1. Método, e o que ele não alcança

**Como foi levantado.** Leitura direta do código na worktree isolada, com investigação paralela por eixo e uma passada adversarial de refutação sobre cada afirmação. Contagens são de comando, não de estimativa.

**Três limites reais, declarados uma vez e válidos para o arquivo inteiro:**

1. **Nenhuma rota autenticada foi aberta em navegador.** Não há captura de `/trafego`, `/trafego/nova/:id` ou `/trafego/campanhas/:id` com sessão. O diagnóstico visual é de código.
2. **Nenhuma chamada foi feita a nenhuma conta do Google Ads.** Nada aqui descreve o estado ao vivo de nenhuma conta.
3. **O Mapa Vivo não foi consultado como autoridade.** `graphify-out/` **não existe nesta worktree** (`ls -d graphify-out` → não existe). Qualquer leitura de grafo feita durante a missão foi na cópia principal do repositório, que está em outra linha de commits. Nenhuma afirmação desta auditoria depende do grafo.

---

## 2. Inventário das superfícies reais

### 2.1 Rotas da aplicação

Quatro rotas de tráfego, todas em `src/App.tsx`:

| Rota | Linha | Página |
|---|---|---|
| `/trafego` | `src/App.tsx:129` | `HubDeTrafegoPage` (com `<QuadroDeOportunidades />` injetado por prop) |
| `/trafego/laboratorio/inteligencia/:scenarioId` | `:130` | `DecisionIntelligenceLabPage` |
| `/trafego/campanhas/:volcCampaignId` | `:131` | `CampanhaCanonPage` |
| `/trafego/nova/:opportunityId` | `:132` | `NovaCampanhaPage` |

Adjacentes, fora do módulo mas sobre o mesmo objeto:

| Rota | Linha | Observação |
|---|---|---|
| `/settings/campaigns` | `:105` | segunda lista de campanhas — **dívida nomeada**, ver §5.6 |
| `/dashboard/campaign/:campaignId` | `:101` | terceira superfície sobre campanha |

⚠️ **Não existe rota `/qa/trafego/*`.** `grep -n '<Route' src/App.tsx` lista 40 rotas e nenhuma começa com `/qa`. O isolamento de bundle que existe é do **laboratório**, provado em `src/components/trafego/laboratorio/__tests__/projection.test.ts:82-97` (`describe('isolamento do bundle do laboratório')`), e o de segredos em `src/lib/__tests__/seguranca-bundle.test.ts`.

### 2.2 As cinco abas do Hub

`src/pages/trafego/HubDeTrafegoPage.tsx` tem 687 linhas e monta **cinco** abas (`:574-607`), com a lista canônica em `src/components/trafego/hub/contrato.ts:23,31-33`:

| Aba (valor de URL) | Monta | Guarda de rede |
|---|---|---|
| `campanhas` | `InventarioDeCampanhas` | sim |
| `canais` | `PainelDeCanais` | **não** (`:654-656`) |
| `preparar` | conteúdo injetado ou `TrafegoPage` → `QuadroDeOportunidades` | sim |
| `criar` | `EstudioLigado` → `EstudioMulticanal` | sim |
| `atencao` | `FilaDeAtencao` | sim |

`oportunidades` é apelido legado de URL para `preparar`, e a tradução está escrita **duas vezes**: no parser da URL e no handler de troca de aba (`:455`).

⚠️ **O próprio arquivo se contradiz sobre quantas abas tem.** O comentário de cabeçalho (`:2-6`) ainda descreve **três** abas e chama a segunda de "Oportunidades"; o export `ABAS` (`:73-75`), marcado como deprecated mas ainda exportado, também lista três. `ABAS_DO_HUB` lista cinco.

### 2.3 Endpoints HTTP

Três routers compartilham o prefixo `/api/trafego`, registrados em `backend/app/main.py:180-188`. **32 endpoints no total.**

O portão de identidade é do **router**, não da rota: `trafego.py:101`, `trafego_inventario.py:75-83` e `trafego_diagnostico.py:31-35` declaram `dependencies=[Depends(exigir_usuario)]` no `APIRouter`. Uma rota nova nasce fechada.

**As duas únicas rotas que escrevem na conta do Google:**

| Rota | Linha | Trava |
|---|---|---|
| `POST /subir` | `trafego.py:3434` | `exigir_admin` + `volc_ads.gads.modo.destravar` (dois fatores: código + `FORGE_PERMITIR_ESCRITA=1`) |
| `POST /remover` | `trafego.py:5731` | idem; exige `remover_ativa: true` para campanha `ENABLED` (`:5786-5791`) |

`POST /provar` (`:2874`) é `validate_only` e **não passa pela trava** — a própria docstring declara que "`validate_only` é leitura para todos os efeitos" (`:2879-2884`).

**Consumo pelo frontend.** Todas as chamadas de tráfego saem de `src/lib/pautadorApi.ts` (1.070 linhas), com 26 caminhos `/api/trafego/…` entre `:641` e `:948`. Não há segundo cliente: `grep -n 'trafego' src/lib/secureApi.ts` → 0 resultados, e nenhum componente ou hook de tráfego chama `fetch()` direto.

**Rotas sem consumidor no frontend** — cada uma é uma capacidade de servidor que não chega ao operador:

| Rota | Prova de ausência |
|---|---|
| `POST /reconciliar` (`trafego.py:4442`) | `grep -rn 'api/trafego/reconciliar' src/ api/` → **0** |
| `GET /plano-de-mensuracao` (`:4281`) | `grep -c 'plano-de-mensuracao' src/lib/pautadorApi.ts` → **0** |
| `GET /canais/{canal}` (`:5534`) | só existe `request('/api/trafego/canais')` em `pautadorApi.ts:755` |
| `GET /contas` (`:329`) | `grep -c 'trafego/contas' src/lib/pautadorApi.ts` → **0** |
| `POST /remover` (`:5731`) | `grep -rn 'trafego/remover' src/` → **0** |

### 2.4 Componentes

`src/components/trafego/` tem 12 subpastas. Os componentes que decidem gasto: `Lancamento.tsx` (a Ignição), `MesaDeLance.tsx`, `MesaDeCriterios.tsx`, `ListaDeKeywords.tsx`, `ReguaDeLeilao.tsx`, `PortaoDePolitica.tsx`, `CartaoCopy.tsx`, `PainelDoLancamento.tsx`.

**Componentes de produção inalcançáveis** — existem, estão corretos, e nenhuma rota os monta:

| Componente | Situação | Prova |
|---|---|---|
| `recibos/CartaoDeRecibo.tsx` | o único consumidor de produção é `lote/QuadroDoLote.tsx:293`, que nenhuma rota monta; dois arquivos de teste o renderizam direto | `grep -rn 'QuadroDoLote\|CartaoDeRecibo' src/pages/ src/App.tsx` → **0** |
| `criacao/ConversaDeCriacao.tsx` + `conversa.ts` | 13 etapas declaradas, nenhuma rota monta | `grep -rn 'ConversaDeCriacao' src/pages src/App.tsx` → **0** |
| `NovaCampanhaPage.tsx:987-995` `Campo` | definido, nunca renderizado | `grep -n '<Campo' …` → **0** |
| `CampanhaCanonPage.tsx:515-520` `Fato` | definido, nunca renderizado | `grep -n '<Fato' …` → **0** |
| `inventario/Selos.tsx:174,186` `SeloDeVinculo`, `SeloDeProcedencia` | exportados, sem consumidor | `grep -rn 'SeloDeVinculo' src/` → definição + 1 comentário |
| `lib/trafego/canais.ts:485-496` `tomDoEstado` | a régua declarada dos 4 portões, sem consumidor de produção | o renderizador codifica as classes direto no mapa `DESENHO` |

---

## 3. A arquitetura atual, e onde a autoridade mora

### 3.1 O que o servidor decide bem

Esta é a parte que **não** precisa ser reconstruída, e a auditoria registra isso antes de listar defeitos.

| Domínio | Onde | O que garante |
|---|---|---|
| Contrato de canais | `backend/app/trafego/contrato_canais.py` | 4 canais × 4 portões, 4 estados, 8 origens de recusa; invariante de construção recusa `BLOQUEADO` sem bloqueador e `PERMITIDO` com bloqueador (`:207-219`) |
| Nascimento pausado | `volc_ads/campanha/comum.py:207` | `camp.status = PAUSED` é literal do construtor |
| Confirmação humana | `backend/app/trafego/canario.py:147-151` | `CanarioRecusado` quando falta `confirmar_criacao_pausada` |
| Destino pago | `backend/app/landing_policy/` | 10 varreduras, 5 papéis, 5 pontos de portão, 4 vereditos, 43 códigos de achado — **100% com fonte em `support.google.com`**, 0 código sem fonte e 0 fonte órfã |
| Conjunto positivo | `backend/app/agents/mining/portao_conjunto_pago.py:352-364` | três guardas, a terceira uma pós-condição por **multiconjunto** (`Counter`, não `set`) sobre o brief final |
| Prontidão | `backend/app/trafego/prontidao.py:32-42, 137-142` | `INDETERMINADO` é o default declarado; o tipo levanta `ValueError` se alguém construir elegibilidade sem as duas provas |
| Meta efetiva | `backend/app/trafego/plano_mensuracao.py:68-87, 544-557` | 7 estados de leitura; `nao_coletado` ≠ `vazio_confirmado` ≠ `falhou`; ausência é objeto explícito, nunca `None` |
| Erros ao operador | `src/components/trafego/inventario/erros.ts:46-54` | vocabulário fechado de 8 motivos, cada um obrigado a carregar um próximo passo |

### 3.2 Onde a autoridade está no navegador — o defeito estrutural

**A decisão central da tela onde o dinheiro passa a ser possível é derivada no navegador.**

```
podeLancar = pendencias.length === 0
```
`src/pages/trafego/NovaCampanhaPage.tsx:332-343`. `pendencias` é montado **a cada render**, juntando conta vinculada + keywords marcadas + status da copy + avisos filtrados pelo cliente + pendências do destino.

E o servidor **já calcula a mesma coisa**:

- `volc_ads/pautador_ponte.py:266-272` — o dataclass `Cockpit` do backend expõe `bloqueado` e `bloqueios`.
- `backend/app/trafego/projecao.py:157-177` — a função que monta o JSON da rota lista os campos um a um e **não inclui nenhum dos dois**.

Prova de ausência: `grep -n '"bloqueado"' backend/app/trafego/projecao.py` → 0; `grep -rn 'pode_lancar' backend/ src/` → **0 em todo o repositório**.

**E as duas regras divergem.** O servidor barra apenas em `severidade == 'bloqueio'`; o cliente barra em tudo que não for `informacao`/`atencao` (`NovaCampanhaPage.tsx:91, 309-310`). Não são a mesma pergunta com dois donos: são duas respostas diferentes, e a que vale é a do navegador.

Outros pontos de autoridade derivada no cliente:

| O quê | Onde | Consequência |
|---|---|---|
| Prontidão do destino, **incluindo frescor do recibo** | `src/lib/landing-policy/prontidao.ts:434, 547` usa `Date.now()`; memoizado em `[cockpit]` (`NovaCampanhaPage.tsx:324-330`) | o relógio é amostrado **uma vez por carga** e nunca reavaliado. Um recibo pode vencer na tela aberta e a interface não percebe |
| Interseção de escrita da aba Criar | `src/components/trafego/canal/jornada.ts:639-647` `cruzar()` combina API + backend + permissão + trava | a aba `criar` faz exatamente o cálculo que a aba `canais` **recusa** fazer (`PainelDeCanais.tsx:11-13` declara por escrito que não calcula autorização) |
| Severidade de aviso | `NovaCampanhaPage.tsx:91` reimplementa a regra no cliente | ver divergência acima |

---

## 4. Duplicações e desacordos medidos

### 4.1 Duas definições de "copy pronta", espalhadas por quatro sítios

No mesmo arquivo, `NovaCampanhaPage.tsx`:

| Linha | Definição | Qual |
|---|---|---|
| `:335` | a pendência exige `status === 'done'` | **A** |
| `:442` | o Trilho passa `copy={!!escrita}` — **qualquer linha existente** | **B** |
| `:652` | o cartão 03 exige `status === 'done'` | **A** |
| `:795-797` | o resumo do overlay lê `escrita.copy.headlines.length` com guarda só em `escrita` | **B**, e é o padrão que o comentário de `:646-650` descreve como a causa de uma tela branca anterior |

São **duas** regras (`A`: provada; `B`: existente) em **quatro** sítios. O defeito não é a quantidade de definições — é que a mais frouxa governa o indicador de progresso e o resumo da ignição.

E a etapa `origem` do Trilho é um **literal** (`:440`, passada sem valor ⇒ `true`), contradizendo o `pronto={destino.apto_para_campanha}` que o próprio cartão 01 usa (`:562`).

### 4.2 Dois renderizadores de portão que discordam de cor

⚠️ **Correção factual.** A segunda superfície **não** é `estudio/JornadaDoCanal.tsx` — esse arquivo **não existe nesta base** (§5.2). Os dois renderizadores reais são:

| Renderizador | Linha | BLOQUEADO / negativo | INDETERMINADO | Fundo |
|---|---|---|---|---|
| `canais/PortoesDoCanal.tsx` | `:55-79` | âmbar | slate-600/400 | nenhum estado tem fundo |
| `canais/PainelDaMensuracao.tsx` | `:67-74` | **rosa** | slate | com fundo |

E dentro do próprio `PortoesDoCanal`, o âmbar do estado `BLOQUEADO` **colide** com o âmbar do tom de bloqueio `permissao` (`:89-94`).

### 4.3 Duas réguas chamadas "portões" que medem coisas diferentes

| Módulo | Quantos | Estados | Regra positiva |
|---|---|---|---|
| `src/lib/trafego/canais.ts:485-496` | 4 portões **de canal** | 4 | só `PERMITIDO` → tom `aberto` |
| `src/lib/trafego/portoes.ts:119-124` | 7 portões **de mensuração** | 5 | só `PRONTO` → `provado`; `PARCIAL` e `INDETERMINADO` caem no default `ignorado` |

Confundir as duas produz cor errada. `portoes.ts:21-23, 112-115` declara a regra em palavras: `PARCIAL` e `INDETERMINADO` são "não sei", nunca degraus para o verde.

### 4.4 Quatro vocabulários de canal que não coincidem

| Fonte | N |
|---|---|
| contrato de portões (`contrato_canais.py:131`) | 4 |
| tipo do frontend (`src/types/trafego.ts:1009-1024`) | 6 |
| gramática do Estúdio (`canal/jornada.ts:879`) | 6 fixos, **derivados de `CANAIS` do frontend e não da lista que o servidor devolve** |
| vocabulário canônico do espelho (`dominio.py:136-153`) | 15 (enum do Google) |

A fronteira única de tradução é `canalCanonico` (`types/trafego.ts:1061-1073`), que devolve `null` — nunca string solta. Em `src/` só **dois** arquivos de produção a chamam.

### 4.5 Vocabulários visuais concorrentes na mesma tela

| Vocabulário | Onde |
|---|---|
| aba sublinhada | `HubDeTrafegoPage.tsx:109-115` (gatilho) e `:570-573` (lista) |
| aba segmentada em poço | o primitivo `src/components/ui/tabs.tsx:15,42` — usado pelos **outros 11** `<TabsList>` do repositório |
| grupo segmentado com `aria-pressed` | `hub/EixosDoHub.tsx:47-49` (Rede) |
| chips com borda | `hub/EixosDoHub.tsx:90-101` (Canal/Nível) |

O Hub é **o único dos 12 `<TabsList>` do repositório** com o vocabulário sublinhado — e é o arquivo que `design.md:136` nomeia como referência a copiar.

### 4.6 Duas superfícies de recibo com tipos diferentes

| Superfície | Mostra | Alcançável? |
|---|---|---|
| `Lancamento.tsx:801-879` (local) | campanha, conta, carimbo, recursos, request id, aprovador, plano, ledger | sim — mas só como estado de modal |
| `recibos/CartaoDeRecibo.tsx:107-114` | **exatamente os dois campos que a ignição omite**: "motivo declarado" e "impressão do pedido" | **não** |

### 4.7 Contagem contraditória na mesma tela

`NovaCampanhaPage.tsx:584-586` — o cartão 02 diz "N em M ad groups" derivado dos grupos da triagem, enquanto o `PainelDoLancamento`, **logo acima**, diz sempre "1 conjunto".

### 4.8 Divergências menores, todas medidas

| Divergência | Onde |
|---|---|
| parse do dinheiro: `MesaDeLance` normaliza vírgula; o pedido usa `Number(budget) \|\| 0` | `NovaCampanhaPage.tsx:391-392` |
| abrir sem `?run=`: o cockpit trata como "o mais recente"; a leitura da copy trata como `run_id IS NULL` | `trafego.py:785` × `:1023` |
| `permitirBroadPositivo` liga BROAD sob `MAXIMIZE_CONVERSIONS`, mas a tabela `DECORRE_DA_ESTRATEGIA` declara PHRASE para as duas estratégias | `NovaCampanhaPage.tsx:636` |
| ordem dos 7 portões difere entre backend e frontend | `prontidao.py:256-283` × `portoes.ts:59-67` |
| três pares de nomes duplicados emitidos ao mesmo tempo em `ProntidaoDoLancamento` | `types/trafego.ts:565-591` |
| a cor do item da fila de atenção **não** deriva de `SINTOMAS[].ordem`: vem de segunda tabela escrita à mão | `atencao/projecao.ts:680-684` × `atencao/visual.ts:40-53` |
| o contador da aba `atenção` conta só itens de escopo de campanha; a fila exibe também os de escopo de conta | `atencao/useAtencao.ts:150` |
| o CTA de cockpit da aba `criar` aponta para `preparar`, enquanto o botão do cabeçalho aponta para `criar` | `canal/jornada.ts:816` |
| a aba `criar` escreve no **mesmo** parâmetro `canal` da URL que recorta o inventário da aba `campanhas` | `HubDeTrafegoPage.tsx:669-672` |

---

## 5. A doutrina da ausência: implementada nos extremos, quebrada no meio

Este é o achado mais consequente da auditoria, porque contradiz a premissa que o produto declara sobre si.

### 5.1 A doutrina, onde ela funciona

- `backend/app/agents/mining/paid_eligibility.py:107-109, 120-121` — o tipo `Sinal` **recusa** valor numérico em estado de ausência: `Sinal(0.0, AUSENTE)` levanta exceção.
- `:243-245, 262` — zero sem confirmação vira `DESCONHECIDO` com `valor=None`; só `confirmed_zero` autoriza ler zero como demanda zero.
- `src/types/trafego.ts:1525-1537` — o contrato do inventário declara: nenhum número sem frescor; ausência é `null` e nunca zero; falha de uma conta não contamina as outras.
- `inventario/LinhaDeCampanha.tsx:135-164` — `tetoDaCampanha` **recusa dividir orçamento por lance** mesmo tendo os dois números na mão, porque "calcular aqui um número que a leitura não trouxe seria inventá-lo com aparência de medido".

### 5.2 Onde ela quebra — a ponte coage ausência a zero

`volc_ads/pautador_ponte.py:451-456` e `:505-506`:

- `_cpc` transforma `None` em `0.0` e carimba `medido_na_conta=False`.
- o volume ausente também é coagido a zero na mesma montagem.

**Consequência medida:** pelo caminho do cockpit, **nenhum volume e nenhum CPC chega nulo**. E os ramos de ausência que a tela escreveu para esse caso são **código morto**:

| Ramo morto | Onde |
|---|---|
| "volume não medido" | `MesaDeCriterios.tsx:201-202` (testa `== null`) |
| "—" para CPC | `ListaDeKeywords.tsx:140-142` |
| "N sem CPC nenhum" | `ReguaDeLeilao.tsx:78, 92, 230` — `semCpc` é sempre 0, a frase nunca é impressa |

A tela **sabe** dizer a verdade. O payload nunca lhe dá a chance.

### 5.3 Quatro lugares onde ausência é lida como permissão

Todos no portão de **vertical**, não no de destino:

| # | Onde | O que acontece |
|---|---|---|
| 1 | `PortaoDePolitica.tsx:167-172` | `atual === undefined` (vertical fora da lista, ou lista vazia) → renderiza a nota **verde** "Sem portão de habilitação" |
| 2 | `NovaCampanhaPage.tsx:155` e `:702` | falha da rota de verticais vira `{ verticais: [] }` no cliente, e a lista vazia **esconde o painel inteiro** — sem mensagem de erro |
| 3 | `NovaCampanhaPage.tsx:332-343` | o `barra` calculado pelo `PortaoDePolitica` **nunca entra** em `pendencias` nem em `podeLancar`; não existe prop de callback (`grep 'onBarra\|onBloqueio\|onPortao'` → 0) |
| 4 | `volc_ads/policy/spec.py:163-168` | no **servidor**: vertical fora da matriz devolve lista **vazia** de violações — o oposto de `contrato.severidade()` (`landing_policy/contrato.py:455-464`), onde código não classificado **bloqueia** |

O portão de **destino** faz o contrário e faz certo: `prontidao.ts:400-407` — `status_wp` nulo devolve `INDETERMINADO`, nunca `APTO`, e é o conserto nomeado do defeito `status_wp !== 'draft'`. E `tomDaProntidao` (`:182-187`) é fail-closed: só a string exata `'APTO'` sai como `provado`.

### 5.4 Um degrau da Ignição que nunca pode falhar

`Lancamento.tsx:299` — o degrau `copy` tem veredito **fixo** `estado="ok"`, literal no JSX, sem depender de nenhum campo. E `NovaCampanhaPage.tsx:795-797` envia `resumoDaCopy="—"` quando não há copy.

Resultado na tela: **`copy ✓ —`** — um degrau aprovado cujo detalhe é a marca de ausência.

### 5.5 Selos e avisos que nunca aparecem

| O quê | Por quê |
|---|---|
| selo "medida na conta" da mesa (`MesaDeCriterios.tsx:402-410`) | depende de `evidencia.tipo === 'MEDIDO'`, e nenhum caminho de produção do front cria essa evidência — `novoCriterio` nasce com `evidencia: null` |
| aviso de procedência do CPC com o fator de 7,4× | viaja em `cockpit.procedencia.aviso` e **não é renderizado**: `grep -rn 'procedencia.aviso' src/` → 0 |
| keywords descartadas com motivo e destino | `cockpit.descartadas` (`projecao.py:164-166`) — `grep -rn 'cockpit.descartadas' src/` → 0 |
| o motivo por keyword | `grep -n 'k.motivo' ListaDeKeywords.tsx` → 0 |
| reauditoria ao vivo do destino | `PainelDoDestinoPago` aceita a prop `reauditoria` e **nenhum chamador a passa** (`grep -rn 'reauditoria={' src/` → 0) |

### 5.6 `/settings/campaigns` — dívida nomeada

`src/App.tsx:105`. Segunda lista de campanhas com botões próprios de pausar/ativar. Enquanto existir, duas telas podem discordar sobre se uma campanha está rodando. **Fora do escopo deste redesign** e registrado como dívida em `IMPLEMENTATION-SLICES.md`.

---

## 6. A colisão do conjunto positivo

A tela monta e envia **positivas** no campo `criterios` do pedido, com match type escolhido keyword a keyword (`NovaCampanhaPage.tsx:367-381, 413`).

O portão do servidor **recusa positiva vinda do corpo, fechada — não filtrada** (`portao_conjunto_pago.py:259-272, 286-305`), e as três guardas são aplicadas em `/provar` (`trafego.py:3001-3002`) e `/subir` (`:3042-3043`), sempre **antes** de `sb.preparar`. A trava está travada por teste que lê o próprio código-fonte da rota e exige que cada guarda venha antes da chamada de rede (`test_pautador_campaign_birth_wiring.py:512-518, 528-536`).

E a mesa afirma ao operador que "o que você vê é o que vai para o Google" (`MesaDeCriterios.tsx:497-501`).

**Três fatos que não fecham.** A auditoria não resolve a colisão — ela a nomeia, e `END-TO-END-FLOWS.md` descreve o comportamento observável de cada ramo.

### 6.1 E a seleção do operador não decide as positivas

Mais grave que a colisão: em `/provar`, a `Escolha` é montada com `keywords_por_grupo(<conjunto aprovado>)` (`trafego.py:2977-2981`). **A marcação keyword a keyword que o operador faz na mesa não entra nessa conta.** A promessa de `MesaDeCriterios.tsx:497-501` — *"o que você vê é o que vai para o Google"* — é falsa em duas direções ao mesmo tempo: o que a tela envia é recusado, e o que vale é um conjunto que a tela não escolheu.

### 6.2 E nada aprova o conjunto que o portão exige

O portão recusa conjunto não aprovado (`portao_conjunto_pago.py:158-163`). Mas:

- `funnel_factory.py:391` **grava sem aprovar**;
- `paid_eligibility.py:1166-1181` tem uma função de aprovação **sem nenhum chamador**.

Ou seja: o portão pode recusar por um estado que **nenhum caminho do sistema produz**. Isto é uma lacuna de servidor, não de tela, e está em `DATA-AND-AUTHORITY-MAP.md §9`.

### 6.3 O 409 do portão carrega um código estável que a tela não usa

O corpo do 409 traz códigos fechados — `CONJUNTO_PAGO_AUSENTE`, `NAO_APROVADO`, `HASH_DIVERGENTE`, `BLOQUEADO`, `VAZIO`, `POSITIVA_DO_CORPO` (`trafego.py:3068-3078`) — e a ignição lê apenas parte deles (`Lancamento.tsx:165-167`). Seis causas distintas chegam ao operador como uma recusa genérica.

---

## 7. O teto econômico: existe em documento, não em código

| Fato | Fonte |
|---|---|
| limite diário = **2× o orçamento diário médio** | `docs/growth-engine/matriz-api/comum.md:459` |
| limite mensal = **30,4×** o diário | `comum.md:460` |
| teto defensável de N dias = N × (2 × diário); o nominal é **explicitamente negado** como teto | `comum.md:480-486` |
| `metrics.cost_micros` é **custo servido**, não cobrado; a API expõe **somente** o servido | `comum.md:506-518` |
| um gatilho de aborto lido de `cost_micros` **pode disparar falso** | `comum.md:524` |
| duas campanhas de R$ 10/dia por 72h: nominal R$ 60, **real R$ 120** | `docs/growth-engine/PLANO-DE-CANARIO.md:150-163` |
| gatilho de interrupção em **R$ 150** (folga de 25% sobre R$ 120) | `PLANO-DE-CANARIO.md:200-210` |

**Nada disso atravessou para o código.** Provas de ausência:

- `grep -rniE "2 ?[x×] ?(o )?or[çc]amento|teto real de gasto|limite di[áa]rio de gasto" src/` → **0**
- `grep -rnF "30,4" src/` → **0**
- `grep -rniE "custo servido|custo cobrado|served cost|billed cost" src/ backend/ volc_ads/` → **0**
- nenhuma constante 120 ou 150 em módulo de tráfego; nenhum gatilho de aborto implementado

O único "teto" calculado em código é `teto_de_cliques` (`backend/app/trafego/dominio.py:1031-1037`), que divide a verba **nominal** pelo lance — assume **1×** o diário. E `metrics.cost_micros` é apresentado ao operador como "gasto" e "custo" sem marcação (`AlertaDeEntrega.tsx:90`).

### 7.1 O canário limita taxa, nunca acumulado

`backend/app/trafego/canario.py:25-34, 50-51` — conta **5478096539** (Portal Mundo Mais), MCC 6016739364, canal SEARCH, cria pausada, ativação fora do escopo. Tetos: **R$ 20,00/dia** de orçamento e **R$ 1,00** de CPC.

Os dois são checagens **por pedido**, contra valores declarados no corpo (`:153-163`). Prova de ausência: `grep -niE "acumulad|exposicao|30.4" backend/app/trafego/canario.py` → **0 resultados**. Não há soma sobre dias, não há leitura de custo real, não há gatilho de aborto.

### 7.2 A graduação que ninguém executa

O número 30 vem do flow n8n legado `New Campaigns Validation`, nó `Code1`, constante `TCPA_GRADUATION_CONVS` (`trafego.py:1435-1441`). A tela declara que a graduação é **registrada** e executada pelo "motor de gestão" (`MesaDeLance.tsx:219-223`).

`graduacao_em_conversoes` é aceito pelo modelo HTTP e **nunca lido, persistido ou executado**: `grep -rn 'graduacao_em_conversoes' backend/ volc_ads/ api/` → 3 resultados, todos definição de campo ou repasse.

### 7.3 Os sete portões não estão onde a decisão econômica acontece

`Lancamento.tsx:497-506` monta os sete portões **na tela onde o clique cria**. `NovaCampanhaPage.tsx` — onde o operador escolhe estratégia, lance e orçamento — importa apenas `PortaoDePolitica`. `PainelDaMensuracao` não é montado ali.

---

## 8. A Ignição: o que é bom e o que está quebrado

### 8.1 O que preservar por mérito

- **A escada para antes de gastar.** O portão de destino está em dois pontos: o estado inicial (`Lancamento.tsx:88-90`) e o primeiro `return` de `provar()` (`:132-135`), **antes de qualquer `await`**. Com destino não apto, **zero requisições saem do navegador**.
- **Três travas encadeadas na criação**, e as três se repetem no servidor: motivo com ≥10 caracteres úteis (`:561-565` × `trafego.py:3416-3423` × `volc_ads/subir.py:936` — as três medem com `strip`), o checkbox "somente PAUSADA" (`:552-560`), e um segundo `return` dentro de `escrever()` antes do `setEstado('escrevendo')` (`:174-177`).

⚠️ **Mas a trava do motivo é vazia na prática.** `Lancamento.tsx:99` inicializa o campo **pré-preenchido** com texto gerado pela máquina:

```ts
const [motivo, setMotivo] = useState(`lançamento de "${titulo}"`);
```

Para qualquer título com um caractere, `lançamento de "x"` já tem 17 caracteres. **As três guardas de 10 caracteres nascem satisfeitas**, e o motivo que vai para o recibo é, por padrão, uma frase que ninguém escreveu. A trava existe, é medida em três lugares, e não pede nada de ninguém.

⚠️ E o botão que cria a campanha é **cinza e mudo**: `disabled` por duas condições independentes (motivo curto **ou** caixa desmarcada) e **nenhum texto diz qual das duas falta**.
- **Recusa e indeterminação têm saídas opostas**, e isso é testado: a recusa mostra código, recibo e item e **mantém** "Voltar e ajustar"; a indeterminação **remove** o botão (`__tests__/lancamento.test.tsx:252, 270`).
- `lib/trafego/lancamento.ts:59-62` — `indeterminacaoDeclarada` **rejeita primeiro** qualquer corpo que se nomeie com outro estado, e só então aplica a regra frouxa; `recusaDeclarada` é **estrita** (exige o rótulo). A assimetria está documentada como escolha de custo: na dúvida, tratar como indeterminado, porque tratar indeterminado como recusa pode criar campanha duplicada.

### 8.2 O que está quebrado

| Defeito | Onde |
|---|---|
| `role="dialog" aria-modal="true"` **sem** armadilha de foco, portal ou `inert` | `Lancamento.tsx:261-262`; `grep 'createPortal\|FocusTrap\|inert'` → **0** |
| **nenhuma região viva**: sem `aria-live`, `role="status"`, `role="alert"`, `aria-busy` | `grep 'aria-live\|role="status"\|aria-busy'` → **0** |
| o foco vai ao painel **uma única vez, no mount** (efeito com deps `[]`) | `:118` |
| o botão de fechar é **desmontado** durante `escrevendo`, não desabilitado | `:279-284` |
| `Esc` é **inerte** durante `escrevendo`, sem nenhum feedback | `:107, 120-126` |
| o recibo é **apenas estado de modal**: `onFechar` faz `setLancando(false)`, desmontando e descartando o `useState` | `NovaCampanhaPage.tsx:789-810` |
| o recibo **não é persistido** em lugar nenhum | `grep 'localStorage\|sessionStorage'` em `Lancamento.tsx` → **0** |
| o `pedido` é objeto literal reconstruído a cada render **sem `useMemo`**, e `provar` é `useCallback` cuja identidade muda com ele | `NovaCampanhaPage.tsx:384-421` × `Lancamento.tsx:169-171` |
| `AVANCO` não é monotônico: `provando` 0,15 e `reprovada` **0,1** — o horizonte **recua** numa reprovação; `indeterminado` e `escrevendo` compartilham 0,85 | `:676-684` |
| `proximoAtoSeguro` devolve `reconciliar_na_conta` por padrão — **e não existe consumidor de `/reconciliar`** | `lib/trafego/lancamento.ts:141-147` |

### 8.3 Contraste medido dentro da Ignição

47 ocorrências de `text-white/NN` em `Lancamento.tsx`. Calculado contra a camada de fundo mais escura declarada em `.ignicao` — `hsl(222 30% 4%)` (`src/index.css:933`):

| Opacidade | Razão | AA (4.5:1) |
|---|---|---|
| `/30` | 2,58:1 | **reprova** |
| `/35` | 3,12:1 | **reprova** |
| `/40` | 3,76:1 | **reprova** |
| `/45` | 4,49:1 | **reprova por 0,01** |

**Dezoito das 47** usam essas faixas. E os rótulos `kicker` do recibo e dos identificadores de erro (código, recibo, item, request id) usam justamente `/40` e `/45` (`:584, 589, 592, 597, 621, 626, 907`) — os identificadores que o operador precisa copiar para pedir ajuda.

Somado: 22 ocorrências de `text-[11px]` e 1 de `text-[10px]` no mesmo arquivo.

---

## 9. Comparação factual com `sprint/traffic-operating-cockpit-v2`

**Ponta real:** `85666dad16460846eb4077d4c8ff4e98c7bed961`. **Base:** `git merge-base 85666da 207e91f` → `207e91f` — que é o HEAD desta worktree. A sprint anterior partiu exatamente daqui.

**Diff base→ponta:** 43 arquivos, **+6.368 / −84**.

| Onde | Saldo |
|---|---|
| `docs/closure/traffic-operating-cockpit-v2/` (13 arquivos, 1 commit) | **+4.142 — 65% do total** |
| `src/` testes | +812 / −51 |
| `src/` não-teste | +1.164 / −27 (boa parte é `src/pages/qa/BancadaVisual.tsx`, 430 linhas, e o gate de bundle) |
| `backend/` produção | **um único módulo**: `plataforma.py` (+24/−3), mudança **textual** na lista de indisponibilidades de PMax |

Em `src/components/trafego/`: **2 arquivos criados** (`estudio/JornadaDoCanal.tsx`, 442 linhas, e o teste dele, 445 linhas), **15 modificados**, **nenhum removido**.

### 9.1 O cockpit não foi tocado

- `git diff 207e91f 85666da -- src/pages/trafego/NovaCampanhaPage.tsx` → **0 bytes**
- `git log --oneline 207e91f..85666da -- <arquivo>` → **vazio**
- o blob é literalmente o mesmo objeto (`a36304afab50d9818496d4715553e2c281c63fe8`) nos dois commits

O próprio fechamento da sprint admite isso e cita o tamanho do arquivo (`REMAINING-RISKS.md:74-77` no blob de `85666da`) — 1.014 linhas, número que confere com `wc -l` nesta worktree.

### 9.2 O que ela entregou de visível

`JornadaDoCanal.tsx` tem **dois** pontos de montagem no código do v2: a aba do estúdio, e só quando há canal escolhido (`EstudioLigado.tsx@85666da:98-109` no blob de `85666da`), e a bancada de QA visual (`src/pages/qa/BancadaVisual.tsx:43, 256-258`). A jornada de treze etapas é montada com `respostas: {}` fixo, e **a própria tela declara que as respostas são dadas no cockpit da campanha** (`:230-256`) — é uma prévia de leitura, não um fluxo executável. E `NovaCampanhaPage.tsx` não importa `JornadaDoCanal` nem `conversa` em nenhum dos dois SHAs.

### 9.3 O veredito dela, e o que ficou por fazer

`HANDOFF.md:3-7` (blob de `85666da`): veredito **PARCIAL**, por duas provas que não aconteceram — rotas reais nunca abertas em navegador e revisão Gemini não executada. A revisão adversarial devolveu **REPROVADO por Codex, com 2 achados bloqueantes** (`:59-61, 77-84`).

**M1 — serializar `bloqueado`/`bloqueios` em `projecao.cockpit`** — é nomeada pelo handoff anterior como o próximo ato de maior valor e explicitamente **não foi feita** (`HANDOFF.md@85666da:105-106`, `REMAINING-RISKS.md:78-80`). **Continua não implementada no HEAD atual** (§3.2).

`GATES.md:18, 36`: vitest saiu de 1.481 passed / 5 skipped para **1.513 passed / 6 skipped** — delta de 32 casos. `:21-25` registra uma falha de pytest herdada que reproduz na árvore intocada no SHA da base — logo, **esperada também no HEAD do v3**.

### 9.4 ⚠️ Nada disso existe nesta base

`docs/closure/traffic-operating-cockpit-v2/` e `src/components/trafego/estudio/JornadaDoCanal.tsx` **existem apenas dentro do commit `85666da`**. Toda citação de linha desses arquivos nesta spec é de blob lido via `git show`, e está marcada como tal.

`ls -d docs/closure/traffic-operating-cockpit-v2/` → não existe. `ls src/components/trafego/estudio/JornadaDoCanal.tsx` → não existe.

`docs/closure/` no HEAD tem **26 diretórios**; 12 tocam o domínio de tráfego por referência literal a caminhos de código.

---

## 10. O que serve, o que não serve

### 10.1 Serve, e a Bancada herda sem reescrever

| Peça | Por quê |
|---|---|
| `inventario/Selos.tsx:104-118` `Chip` | glifo `aria-hidden` + palavra visível + descrição em `title` **e** `sr-only`; a cor fica na borda/fundo/glifo, nunca na palavra (`:79-95`). **13 módulos fora da pasta já o importam** |
| `inventario/erros.ts:46-54` | 8 motivos fechados, cada um com próximo passo; o caminho lateral está fechado (`:381` descarta texto que não seja do vocabulário). Do corpo do servidor atravessam **dois** fatos, ambos não-narrativos: o **instante** do 429 (`:253-260`) e o **identificador de ocorrência** (`idDoServidor` lê `correlation_id`, `id_da_ocorrencia`, `request_id` ou `trace_id` e `descreverFalha` o promove a código — `:182-199, 336`) |
| `inventario/densidade.tsx` | as três formas são marcações **diferentes**, decididas em JS no primeiro render — não `hidden md:table` |
| ordem do servidor no inventário | provada duas vezes: ausência do arquivo de ordenação e ausência de qualquer primitiva de ordenação no código-fonte (`__tests__/ordem-do-servidor.test.tsx:92-104`), com fixture hostil ao alfabeto (`Zebra PAUSED` antes de `Alpha ENABLED`, e a tela preserva) |
| `lote/QuadroDoLote.tsx:305-335` | o modelo correto de ação desabilitada: parágrafo de razão ligado por `aria-describedby` |
| a escada da Ignição | §8.1 |
| `landing-policy/prontidao.ts` | fail-closed em cinco pontos independentes (`:182-187`, `:400-407`, `:568-573`, `:589-596`, `:707-716`) |
| `reauditoria.ts:163-170, 254-259, 280-286` | 7 etapas, `confirmar` possível em só uma; distingue "não havia com o que comparar" de "nada mudou" |

### 10.2 Não serve, e será reconstruído

| Peça | Defeito dominante |
|---|---|
| `NovaCampanhaPage.tsx` | 18 blocos empilhados sem ordem obrigatória; elegibilidade no navegador; três definições de "copy pronta"; constantes literais de economia e canal; zero frescor |
| aba `criar` (`EstudioMulticanal` + `EstudioLigado`) | recalcula no navegador o que a aba `canais` recusa recalcular; monta sobre 6 canais fixos do frontend, não sobre a lista do servidor |
| aba `canais` (`PainelDeCanais`) | responde a mesma pergunta que `criar`; não aceita prop nenhuma, ignorando o recorte de canal da URL; 96/28/25 classes de paleta bruta, zero token semântico |
| abas do Hub | vocabulário sublinhado, único no repositório, no arquivo que o contrato nomeia como referência |
| recibo | estado de modal, descartado no fechamento; a superfície mais completa é inalcançável |

### 10.3 Existe e não é alcançado

Ver §2.4 e §5.5. Somando: **duas** superfícies de produção inteiras (`CartaoDeRecibo`, `ConversaDeCriacao`), **duas** rotas de servidor sem consumidor (`/reconciliar`, `/plano-de-mensuracao`), **cinco** campos de payload nunca renderizados, e **uma** prop de reauditoria que nenhum chamador passa.

---

## 11. Contagens visuais — medidas, com o comando

Escopo: `src/pages/trafego` + `src/components/trafego`, **excluindo `__tests__`**. Comando base: `grep -rn '<padrão>' src/pages/trafego src/components/trafego | grep -v __tests__ | wc -l`.

| Padrão | Escopo inteiro | Onde se concentra |
|---|---:|---|
| `text-[11px]` | **235** | 22 só em `Lancamento.tsx`; nos arquivos do inventário são **26** (12 em `LinhaDeCampanha`, 6 em `GrupoDeConta`, 3 em `FilaDeAtencao`, 5 nos demais) |
| `text-[10px]` | **19** | 4 no inventário, todas coladas a `.kicker` (`FiltrosDoInventario:105,159,207,222`) |
| `text-[9px]` | **2** | `NovaCampanhaPage.tsx:855` (numerais do trilho), `ReguaDeLeilao.tsx:190` |
| `border-l-2` | **12** — **5 neutras, 7 coloridas** | ver desdobramento abaixo |
| `border-r-2` | **0** | — |
| `card-volc` | **8** ocorrências, **7 aplicações reais** (uma é comentário) | `NovaCampanhaPage`, `PainelDoLancamento`, `PortaoDePolitica`, `VereditoDePolitica`, `JaNoAr` |
| `.reveal` | **10** ocorrências da string, **8 aplicações reais** (2 são o keyframe `di-reveal` de `bancada.css`) | `NovaCampanhaPage` (7), `Lancamento.tsx:693` (1) |
| `backdrop-blur` | **2** | ambas em barras fixas: `NovaCampanhaPage.tsx:437`, `GrupoDeConta.tsx:295-298` |
| `uppercase` fora de `.kicker` | **30** | nenhuma na mesma linha que `.kicker` |
| `mix-blend-difference` | **1 em todo o `src/`** | `ReguaDeLeilao.tsx:175-179`, a 10px |
| `text-white/NN` | **47** | todas em `Lancamento.tsx`; 18 abaixo de AA |
| `transition-all` / `transition: all` | **0 reais em todo o `src/`** | os 2 matches são um comentário e uma regex de teste |

### 11.1 As 12 `border-l-2`, desdobradas

**Neutras (5) — citação, e passam:** `MesaDeLance.tsx`, `VereditoDePolitica.tsx`, `diagnostico/VereditoDaSentinela.tsx`, `inventario/LinhaDeCampanha.tsx:572` (`border-border/60`), `atencao/ItemDeAtencao.tsx`.

**Coloridas (7) — violam `design.md:99,130`:** `Lancamento.tsx` ×3 (`border-warning/60` ×2, `border-destructive/60` ×1), `canais/PlanoDeMensuracao.tsx` (`border-l-violet-400`), `canais/PainelDaMensuracao.tsx` ×2 (`border-l-rose-400`, `border-l-slate-400`), `canais/PortoesDoCanal.tsx` (a cor não está na mesma linha: vem de um mapa de quatro faixas cruas logo acima, `:89-101`).

O filete colorido da linha aberta do inventário, por contraste, é implementado como `box-shadow` inset com o token primário (`LinhaDeCampanha.tsx:792-798`) — **não como borda**. É a solução correta e deve ser copiada.

### 11.2 ⚠️ Correção: a paleta crua é maior do que a spec dizia

`VISUAL-DIRECTION.md §2` registra **93** ocorrências de paleta crua. A medição é **216**, em **6 arquivos**:

| Família | Ocorrências |
|---|---:|
| `slate` | 169 |
| `amber` | 15 |
| `rose` | 14 |
| `emerald` | 10 |
| `violet` | 4 |
| `sky` | 4 |

Comando: `grep -rnoE '(text|bg|border|border-l|border-r|dark:text|dark:bg|dark:border)-(slate|rose|violet|amber|emerald|sky)-[0-9]{2,3}' src/pages/trafego src/components/trafego | grep -v __tests__ | wc -l` → **216**.

A dívida está **concentrada, não espalhada**: as três superfícies de `canais/` respondem pela maior parte, e `PainelDeCanais.tsx` sozinho por cerca de metade. Isso é uma boa notícia para o plano: é uma fatia, não uma varredura.

**As demais contagens de `VISUAL-DIRECTION.md §2` conferem** (235, 19, 2, 12, 30). A única correção é a da paleta crua, registrada em `DECISION-LOG.md`.

### 11.3 Primitivas do sistema que o tráfego não consome

| Primitiva | Usos em `src/` | Usos no escopo de tráfego |
|---|---:|---:|
| `.touch-target` | — | **0** |
| `.hover-lift` | — | **0** |
| `.card-hover` | — | **0** |
| `.glass` | — | **0** |
| `transition-volc` (`tailwind.config.ts:102-104`, exclui `width/height/top/left`) | — | **0** |
| `[data-motion="essencial"]` | **1** (`src/components/ui/loading-spinner.tsx:47`) | **0** |

Somam 173 usos em `src/` e **zero** no módulo de tráfego. E `.kicker` é usada 110 vezes em 30 arquivos do escopo — enquanto o mesmo efeito é reimplementado à mão 30 vezes, com tracking diferente.

### 11.4 Dois defeitos na própria primitiva `.card-volc`

`src/index.css:427-439` sobe **3px em 250ms**, contra os `-2px` e 150–220ms de `design.md:114-118`. Além disso:

1. **Não tem guarda de ponteiro.** `.hover-lift`, `.hover-glow` e `.card-hover` têm `@media (hover: hover) and (pointer: fine)`; `.card-volc` não.
2. **Não está no bloco de `prefers-reduced-motion`.** `src/index.css:602` zera o `transform` de `.hover-lift:hover` e `.card-hover:hover` e **não lista `.card-volc:hover`**.

A utilidade `.hover-lift` (`:523-526`) cumpre o contrato: −2px, 200ms, com guarda. Ela existe e o tráfego não a usa.

## 12. Achados nos artefatos pré-existentes desta própria spec

A auditoria se aplica também ao que já estava escrito. Oito citações não resolvem contra a base:

| # | Defeito | Onde na spec | Verificação |
|---|---|---|---|
| D1 | `estudio/JornadaDoCanal.tsx` citado como existente | `EXPERIENCE-ARCHITECTURE.md §2.2, §8`; `VISUAL-DIRECTION.md §5` | não existe em `207e91f`; só em `85666da` |
| D2 | `EstudioLigado.tsx@85666da:100` | `EXPERIENCE-ARCHITECTURE.md §2.2` | o arquivo na base tem **64 linhas** |
| D3 | `docs/closure/traffic-operating-cockpit-v2/**` | `MASTER-SPEC.md §7`; `EXPERIENCE-ARCHITECTURE.md §2.2, §12, §13`; `MOTION-AND-INTERACTION.md §2.1` | não existe na base |
| D4 | `src/lib/trafego/__tests__/contrato-unico.test.ts` | `EXPERIENCE-ARCHITECTURE.md §7` | **não existe em lugar nenhum**; e não há teste que varra âncora interna (`grep -rn 'href="/' src --include='*.test.ts*'` → 0) |
| D5 | `scripts/gate_bancada_fora_do_bundle.py` | `MASTER-SPEC.md` trava #16 | **não existe na base** — foi **criado pela sprint anterior** (`A: scripts/gate_bancada_fora_do_bundle.py` no diff `207e91f..85666da`), junto de `src/pages/qa/BancadaVisual.tsx`. Na base, o gate real é `laboratorio/__tests__/projection.test.ts:82-97` |
| D6 | rota `/qa/trafego/*` listada como existente | `EXPERIENCE-ARCHITECTURE.md §8` | **não existe em `App.tsx` na base** — a bancada de QA é da sprint anterior, no mesmo lote de D5 |
| D7 | `graphify-out/UPDATE_STATUS.json` citado | `MASTER-SPEC.md §7` | `graphify-out/` não existe nesta worktree |
| D8 | "nove blocos empilhados" | `MASTER-SPEC.md §1`; `EXPERIENCE-ARCHITECTURE.md §2.1` | são **18** blocos (`NovaCampanhaPage.tsx:426-812`) |

Correções aplicadas em `DECISION-LOG.md §3`.

---

## 13. As lacunas de servidor, resumidas

Nenhuma é pré-requisito para começar. Cada uma tem dono.

| Lacuna | Consequência | Dono |
|---|---|---|
| `projecao.cockpit` não serializa `bloqueado`/`bloqueios` | a elegibilidade continua sendo montada no navegador | servidor |
| nenhum carimbo de frescor na resposta do cockpit | a tela não pode dizer quando leu (`projecao.py:157-177` não emite campo de tempo) | servidor |
| `GET /canais` não passa `prontidao_por_canal` nem `prontidao_pmax` | mensuração sempre `lida=false`; observabilidade de PMax sempre `INDETERMINADO` | servidor |
| nenhum `response_model` em `trafego.py` e `trafego_inventario.py` | não há contrato tipado de resposta para programar contra | servidor |
| `POST /reconciliar` sem consumidor | a saída de indeterminado não tem porta na tela | frontend |
| `GET /plano-de-mensuracao` sem consumidor | os 7 portões não chegam por esta rota | frontend |
| não existe `GET …/recibos` | não há histórico de recibo | servidor |
| `graduacao_em_conversoes` aceito e nunca executado | a tela promete um efeito que não acontece | servidor |
| o teto real de gasto não existe em código | o operador lê o nominal como se fosse teto | servidor |
| não existe rota de ativação | **intencional** — não fechar sem decisão de produto | produto |
