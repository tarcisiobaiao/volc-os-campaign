# SCREEN-CONTRACTS — cada superfície: conteúdo, ação dominante, estados

Base factual: `207e91f`. Autoridade visual: `design.md`. Autoridade de dado: `DATA-AND-AUTHORITY-MAP.md`. Vocabulário de estado: `STATE-MATRIX.md`.

**Formato de cada contrato:** objetivo · pergunta dominante · hierarquia · dados exibidos · vazio · ausência · stale · erro · indeterminado · ação dominante · ação secundária · origem de cada veredito · teclado · mobile · movimento reduzido.

**Três regras que valem para todas as superfícies e não se repetem em cada uma:**

1. **Uma ação primária por região.** As demais são visualmente mais quietas.
2. **Ação desabilitada nunca é silenciosa.** `disabled` + `aria-disabled` + parágrafo de razão **visível**, ligado por `aria-describedby`. O modelo existe: `lote/QuadroDoLote.tsx:305-335`. O contra-modelo a matar: `NovaCampanhaPage.tsx:461-479`, onde uma razão só aparece de `sm:` para cima e a outra **em nenhum breakpoint**.
3. **Estado nunca só por cor.** Glifo + palavra + descrição, via o `Chip` de `inventario/Selos.tsx:104-118` — que já implementa glifo `aria-hidden`, palavra visível e descrição em `title` **e** `sr-only`, e que **13 módulos fora da pasta já importam**.

---

## 1. Hub de Tráfego — `/trafego`

**Objetivo.** Responder "o que existe, o que está gastando, o que pode virar campanha, o que pede atenção" sem entrar em nenhuma delas.

**Pergunta dominante.** *O que merece minha atenção agora?*

**Hierarquia.** kicker + H1 (Space Grotesk 32–40, `aurora-rule w-16`) + propósito + **uma** ação primária → eixos (rede/canal/nível) → **abas segmentadas** → conteúdo. Orçamento de cabeçalho 220–280px (`design.md:89`).

**Mudanças obrigatórias:**

| # | Hoje | Depois |
|---|---|---|
| 1 | abas **sublinhadas** (`HubDeTrafegoPage.tsx:109-115, 570-573`) — as únicas dos 12 `<TabsList>` do repositório | poço `bg-muted` + pílula `bg-card shadow-card`, do primitivo `ui/tabs.tsx:15,42` |
| 2 | **cinco** abas; o cabeçalho do arquivo documenta três e `ABAS` exporta três (`:2-6, 73-75`) | **quatro** abas; `canais` absorvida por `criar`; `ABAS` removido |
| 3 | a aba `canais` é a única **sem guarda de rede** (`:654-656`) | todas com guarda |
| 4 | `criar` escreve no **mesmo** `?canal=` que filtra o inventário (`:669-672`) | parâmetro próprio |
| 5 | três vocabulários de seleção na mesma tela (abas + `aria-pressed` + chips, `EixosDoHub.tsx:47-49, 90-101`) | **dois**: abas segmentadas para tarefa, chips para filtro |
| 6 | contador da aba `atenção` conta só escopo de campanha; a fila mostra também conta (`useAtencao.ts:150`) | contador e conteúdo contam o mesmo |

**Estados.** Herda o inventário (§2). A aba `atenção` traz o contador como **metadado quieto**, nunca no lugar do rótulo.

**Teclado.** Abas com roving tabindex (modelo: `QGAgenticoPage.tsx:71-99`). Aba selecionada `aria-selected`.

**Mobile.** Abas roláveis no eixo x **dentro do poço**; a página não rola lateralmente. Eixos viram chips empilháveis.

**Reduzido.** Troca de aba é crossfade de conteúdo, sem deslocamento.

---

## 2. Inventário — `/trafego?aba=campanhas`

**Objetivo.** Comparar campanhas reais com procedência e frescor.

**Pergunta dominante.** *Qual campanha está fora do esperado?*

**Hierarquia.** filtros (sticky) → grupo de conta (sticky, tinta, **sem** segundo cartão elevado) → linha densa → expansão.

**Dados.** As **onze** colunas de `LinhaDeCampanha.tsx:718-730`, larguras em % somando 100 com `table-fixed` (`:760-771`). Em `media` elas se reagrupam em **quatro** células (`:829-852`) — e ⚠️ **a coluna `estrategia` some**, ao contrário do que o comentário do arquivo promete. Ou ela entra numa das quatro, ou a perda é declarada.

**Estados** — o que já existe e se preserva:

| Estado | Comportamento | Onde |
|---|---|---|
| vazio | `InventarioVazio` ensina o que aquilo mostraria | `EstadosDoInventario.tsx` |
| falhou | **503, nunca lista vazia**; 8 motivos fechados, cada um com próximo passo | `trafego_inventario.py:288-293`; `erros.ts:46-54` |
| stale | `AvisoDeDadoAntigo`; frescor desconhecido **nunca** vira `recente` | `InventarioDeCampanhas.tsx:271-272` |
| parcial | `AvisoDeLeituraParcial`; falha de uma conta não contamina outras | — |
| ausência | `—` e nunca `0`; medida sem `entrega.leitura` **não é exibida** | `LinhaDeCampanha.tsx:204-212` |

**Dois defeitos a corrigir:**

1. O código de erro exibido **não é** o registrado no console — `FalhaDoInventario` sorteia um novo (`InventarioDeCampanhas.tsx:263`). **Passar a ocorrência pronta**, que `useInventario` já expõe.
2. `conta.motivo` — texto livre do servidor — é impresso **sem sanitização** (`GrupoDeConta.tsx:219-223`), enquanto o mesmo campo é descartado no aviso de leitura parcial. **Uma política só**: passa pelo vocabulário, ou não aparece.

**Ação dominante:** abrir a linha. **Secundária:** releitura read-only da conta.

**Mobile.** `densidade: compacta` — `<ul>` de linhas altas, **`<table>` ausente do DOM** (`RESPONSIVE-AND-A11Y.md §2.2-2.3`).

---

## 3. Antessala de canal — `/trafego?aba=criar`

**Objetivo.** Dizer o que **cada canal permite agora**, sem simetria falsa.

**Pergunta dominante.** *Este canal pode, e se não, quem destrava?*

**Hierarquia.** um cartão por canal: identidade → **escada de 4 portões** → causa dominante com **origem** → ação dominante → próximo desbloqueio.

**Dados.** Exclusivamente `canais[].portoes[]` de `GET /canais`. A tela **conta pelo campo `aberto` que o servidor emite** (`canais.ts:549-574`) e não reimplementa a régua.

| Elemento | Regra |
|---|---|
| tom do portão | 4 estados, 4 tons; **só `PERMITIDO` pinta positivo** (`canais.ts:485-496`) |
| tom do **bloqueio** | diferente do tom do portão: `produto` e `politica` são **neutros** (`decidido`), não erro (`canais.ts:506-522`) |
| "a quem pedir" | 8 frases, uma por origem (`canais.ts:530-539`) |

**Correções obrigatórias:**

| # | Hoje | Depois |
|---|---|---|
| 1 | `jornada.ts:639-647` `cruzar()` recalcula API+backend+permissão+trava **no navegador** | consome só os portões do servidor |
| 2 | monta sobre **6 canais fixos do frontend** (`jornada.ts:879`) | itera a resposta de `GET /canais` |
| 3 | dois renderizadores discordam de cor (`PortoesDoCanal.tsx:55-79` × `PainelDaMensuracao.tsx:67-74`) | **um** renderizador |
| 4 | dentro de `PortoesDoCanal`, o âmbar de `BLOQUEADO` colide com o âmbar de `permissao` (`:89-94`) | tons distintos |
| 5 | **216** ocorrências de paleta crua em 6 arquivos, zero token semântico | tokens |
| 6 | CTA de cockpit aponta para `preparar` enquanto o botão do cabeçalho aponta para `criar` (`jornada.ts:816`) | um destino por intenção |
| 7 | prévia de 13 etapas com `respostas: {}` | **sai**. Etapa sem decisão é ruído |

**Vazio/ausência/erro.** Canal sem manifesto (`null`) e canal com `capacidades: []` são **respostas diferentes** e o invariante já as separa (`canal/__tests__/capacidades.test.ts:29-44`): "o Hub não opera este canal" ≠ "opera e não pode nada".

**Indeterminado.** Mensuração chega **sempre** `lida=false` e a observabilidade de PMax **sempre** `INDETERMINADO` (`trafego.py:5512-5516`). A tela diz "não se sabe", **não** "não pode".

**Ação dominante:** a do canal — "montar campanha" (Search), "preparar por Search" (os outros). **Nunca botão cinza sem razão.**

---

## 4. Preparar — `/trafego?aba=preparar`

**Objetivo.** Escolher a oportunidade sabendo se ela pode virar campanha.

**Pergunta dominante.** *Qual funil está pronto para virar campanha?*

**Dados.** Cinco colunas + ação (`oportunidades/linguagem.ts:80-81`). A coluna de keywords **distingue ausência de zero**: sem cluster, marcador de ausente em vez de número (`QuadroDeOportunidades.tsx:404-405`). Ganha **uma** coluna: o estado do portão de destino.

**Ausência declarada na própria tela:** não há coluna de performance, e a justificativa vem do servidor (`:257-259`). Preservar.

**Correções:**

| # | Hoje | Depois |
|---|---|---|
| 1 | `relancar=1` é **escrito e nunca lido** (`:309-315`; `grep -rn 'relancar' src/pages src/hooks` → 0) | ou a Bancada o lê e abre em Revisão, ou **o parâmetro sai** |
| 2 | o ramo de relançamento é avaliado **antes** do que verifica keywords mineradas, e o selo da mesma linha faz o contrário (`:309, 318, 381`) | uma ordem só |
| 3 | `hub/contrato.ts:63-72` inventa um sexto estado visual `pendente` que não existe no vocabulário do backend | ou o backend emite, ou sai |

`podeRelancar` só é verdadeiro no estado `somente_historico` (`preparar/estados.ts:100-112`) — preservar.

---

## 5. Bancada — moldura comum

**Objetivo.** Levar da oportunidade à campanha criada pausada, com a evidência de cada decisão ao lado dela.

**Hierarquia.** identidade (180–220px) → mapa de paradas (sticky 56px) → coluna de decisão → Pedido (≥1100px de conteúdo) → rodapé.

**Mapa de paradas.** `<nav aria-label="paradas do lançamento">` + `<ol>`. Parada alcançável: `<Link>`, a atual com `aria-current="step"`. **Parada bloqueada é `<span aria-disabled="true">` com a causa por `aria-describedby`** — nunca `<button disabled>`.

**Kickers:** no máximo **4** na Bancada inteira (`VISUAL-DIRECTION.md §C1`). Nunca kicker por bloco de evidência.

**Erro de carga.** Hoje o ramo de erro do cockpit renderiza **apenas o texto** e não tem botão de tentar de novo (`NovaCampanhaPage.tsx:510-514`). Passa a ter: frase do vocabulário + código copiável **igual ao registrado** + tentar de novo.

**Frescor.** Hoje **nem o servidor emite** (`projecao.py:157-177`). Até B3 existir, a Bancada carimba **"sem carimbo de leitura"** — e não inventa um relógio local.

---

## 6. Parada 1 — Destino

**Pergunta dominante.** *Para onde este clique vai, e o destino aguenta?*

**Decisão do operador.** Nenhuma no caminho feliz. Quando indeterminado: **reauditar**.

**Dados.** As cinco perguntas, com os rótulos **em forma de pergunta** que já existem (`prontidao.ts:124-130`) + completude da evidência + deriva ao vivo + janela de 24h do contrato.

| Estado | O que a parada mostra |
|---|---|
| `APTO` | veredito + as cinco respostas + de quando é a evidência |
| `BLOQUEADO` | a causa, e **quem** recusou |
| `INDETERMINADO` | o que não foi lido + **o ato de reauditar** |
| `NAO_AVALIADO` | "não avaliado neste ponto" — **≠ indeterminado** (`:93-98`) |
| `DESCONHECIDA_POR_CONTRATO` | só para `google`: "desconhecida — e continuará" |

**A pergunta `google` é permanente.** `google_approval` é o literal `"unknown"` (`recibo.py:164-170`), sem nenhuma entrada que o mude. A tela diz que **nenhuma leitura dela muda esse estado**, e não oferece ação.

⚠️ **Corrigir:** a prop `reauditoria` existe em `PainelDoDestinoPago` e **nenhum chamador a passa** (`grep -rn 'reauditoria={' src/` → 0). A reauditoria tem sete etapas, `confirmar` possível em **uma** só, e distingue "não havia com o que comparar" de "nada mudou" (`reauditoria.ts:163-170, 254-259, 280-286`). É boa, e está desligada.

**Ação dominante:** confirmar e seguir. **Secundária:** reauditar ao vivo.

---

## 7. Parada 2 — Política

**Pergunta dominante.** *Sob que regra este anúncio é julgado?*

**Decisão.** vertical (1 de N) + certificações (N).

**Dados.** `GET /politica/verticais`, com severidade **por país**. A certificação é **auto-declaração do operador** — e a tela diz isso: `grep 'advertiser_verification\|identity_verification'` em `backend/ volc_ads/` → **0**. Nenhuma leitura confirma.

**Quatro inversões obrigatórias** (`DATA-AND-AUTHORITY-MAP.md §4.2`):

| # | Hoje | Depois |
|---|---|---|
| 1 | vertical fora da lista → nota **verde** "Sem portão de habilitação" (`PortaoDePolitica.tsx:167-172`) | **`INDETERMINADO`**; a parada não avança |
| 2 | falha da rota → lista vazia → painel **escondido**, sem erro (`NovaCampanhaPage.tsx:155, 702`) | estado de erro visível; parada bloqueada |
| 3 | o `barra` **nunca entra** em `podeLancar` (`:332-343`) | pendência emitida pelo servidor |
| 4 | servidor: vertical desconhecida → **zero violações** (`spec.py:163-168`) | alinhar com `contrato.severidade()`, onde não classificado **bloqueia** |

**Estados.** `bloqueio` e `limitacao` são palavras distintas e não colapsam.

**Ação dominante:** confirmar a política.

---

## 8. Parada 3 — Termos

**Pergunta dominante.** *O que esta campanha compra?*

**Decisão.** manter/remover cada termo · correspondência · **exclusões**.

**Hierarquia.** régua de leilão → mesa de termos → exclusões → o que a mesa **não** decide.

**Dados por termo:** texto, volume, CPC com procedência, correspondência, tags.

⚠️ **A correção que muda esta parada inteira.** Hoje a ponte coage `volume` e `cpc` a zero (`pautador_ponte.py:451-456, 505-506`), e três ramos de ausência que a tela **já escreveu** são código morto (`MesaDeCriterios.tsx:201-202`, `ListaDeKeywords.tsx:140-142`, `ReguaDeLeilao.tsx:78,92,230`). Com B2 (a ponte para de coagir), eles passam a executar e a parada fica honesta **sem código novo de tela**.

**O que precisa passar a aparecer:**

| Dado | Onde já vive | Hoje |
|---|---|---|
| aviso de procedência do CPC (fator 7,4×) | `cockpit.procedencia.aviso` | **não renderizado** |
| keywords descartadas, com motivo e destino | `cockpit.descartadas` (`projecao.py:164-166`) | **nunca lido** |
| motivo por keyword | payload | **não renderizado** |

**Régua de leilão.** Largura = participação no volume; altura = CPC na escala do mais caro; teto 96px, piso 4px (`ReguaDeLeilao.tsx:44-45, 117-124`). CPC ponderado por volume, e a divergência entre ponderado e simples é publicada como número de concentração acima de 15% (`:83-96, 212-218`). O limiar de dominância é 40% e está **declarado como arbitrário no próprio código** (`:59-63`) — a tela repete essa ressalva. ⚠️ E ele **não governa só texto**: `b.domina` decide também a **cor** do bloco (40% ou mais pinta `bg-foreground`, `:169-172`). Um limiar arbitrário que muda a cor precisa dizer que é arbitrário **onde a cor aparece**, não só no `aria-label`.

**Quatro correções na régua:**

| # | Defeito | Onde |
|---|---|---|
| 1 | `mix-blend-difference` a 10px, e 9px no rótulo de lance | `:175-179`, `:190` |
| 2 | **`aoPassar` não é passado** no único call site, e a peça não tem `title` nem tooltip próprio | `NovaCampanhaPage.tsx:615` |
| 3 | ⚠️ **os blocos respondem só a mouse**: `onMouseEnter`/`onMouseLeave` são os únicos manipuladores; **zero** `title`, `tabIndex`, `onFocus` ou `onKeyDown`, e só o dominante tem `aria-label` | `:149-160` |
| 4 | ⚠️ keyword com volume zero é **descartada das barras e continua contada** no número publicado: `barras` filtra `k.volume > 0`, enquanto `m.n` é `selecionadas.length` | `:91, 114, 150, 205` |

⚠️ **E a régua desaparece inteira quando todos os CPCs selecionados são zero** (`if (!m.volume || !m.cpcMax) return []`, `:112`). Com a coerção da ponte (§8), esse é um estado alcançável **por construção** — a peça some sem dizer por quê. Com B2, ela passa a poder dizer "não medido".

🔴 **E a correspondência por termo não tem canal para chegar ao servidor.** `PedidoDeProva` oferece apenas um `match_type` **global** fora de `criterios` (`types/trafego.ts:951-956`); a escolha individual de hoje vira **critério positivo** (`NovaCampanhaPage.tsx:362-381`), e todo positivo do corpo é **recusado** (`portao_conjunto_pago.py:250-272`). O conjunto do servidor nasce com a **própria** correspondência (`paid_eligibility.py:920-929`), e ela **participa da identidade** que o portão confere (`:240-247`) — mudá-la muda o hash e invalida a aprovação.

**Consequência:** ou a parada Termos **não oferece** correspondência por termo, ou existe uma operação de "alterar correspondência e reaprovar o conjunto" que **não existe hoje e nenhuma fatia constrói**. Esta spec **não decide** qual — é decisão de produto, registrada como `Q13` em `DECISION-LOG.md §8`. Até lá, a parada oferece **apenas o `match_type` global** e diz que a correspondência fina é do conjunto aprovado.

⚠️ **A seleção do operador não decide as positivas.** Em `/provar`, a `Escolha` é montada com `keywords_por_grupo(<conjunto aprovado>)` (`trafego.py:2977-2981`): a marcação keyword a keyword **não entra na conta**. A parada diz isso.

**A colisão do conjunto positivo.** A Bancada envia **apenas negativas e correspondências**. O conjunto positivo é do servidor, travado por três guardas com pós-condição por multiconjunto (`portao_conjunto_pago.py:352-364`). A frase "o que você vê é o que vai para o Google" (`MesaDeCriterios.tsx:497-501`) é **substituída** por: *"o conjunto positivo é o aprovado na mineração. Aqui você define correspondência e exclusões."*

**Exclusões.** Negativa nasce `PHRASE` por decisão declarada (`criterios.ts:263-264`). **Nada sugere negativa** — três lugares declaram isso, e a tela repete. E não existe leitor de `search_term_view` (o insumo que produziria negativa com evidência medida).

⚠️ **Trava dura:** o `oneof` do critério e o campo `negative` são **Immutable** — alternar entre segmentação e exclusão exige **recriar** o critério (`comum.md:404-407`).

**Selo "medida na conta":** hoje depende de `evidencia.tipo === 'MEDIDO'` e **nenhum caminho de produção cria essa evidência** (`MesaDeCriterios.tsx:402-410`). Ou passa a existir produtor, ou o selo sai.

**Mobile.** `<ul>`, não tabela, com o aviso de `RESPONSIVE-AND-A11Y.md §2.4`.

---

## 9. Parada 4 — Anúncio

**Pergunta dominante.** *Com que texto ela aparece?*

**Decisão.** gerar / editar / aceitar.

**Dados.** mínimos do RSA, força do anúncio **como diagnóstico** (nunca como nota), congruência termo→anúncio→página, e os carimbos de tempo. ⚠️ **Correção:** `criado_em` **é exibido** hoje — alimenta o cronômetro de `CartaoCopy.tsx:93-96, 422-430`. O que falta é `atualizado_em`: a tela diz quando a copy nasceu, não quando mudou.

**Estados.** `POST /copy` é assíncrono por contrato: grava `running`, dispara em segundo plano, responde na hora (`trafego.py:1118, 1148-1152`). E `CopyPersistida.perdida` existe porque `status === 'running'` **não prova** que algo roda — um reinício deixa a linha running para sempre (`types/trafego.ts:1329-1348`). A tela mostra `perdida` como estado próprio, com o ato de reescrever.

**Uma definição de "copy pronta":** `status === 'done'`. Hoje são **duas** regras em **quatro** sítios — `:335` e `:652` já usam `status === 'done'`; `:442` (`copy={!!escrita}`) e `:795-797` usam mera existência. **A correção é nos dois últimos**, não nos quatro.

⚠️ **Trava dura que a parada não pode esconder:** `AdGroupAd.ad` é **Immutable** (`search.md:66, 73-75`). Editar o criativo de um RSA publicado é impossível pela API; o caso de uso é *replace-and-retire*, com **dois `AdGroupAd` distintos no histórico**. A tela nunca oferece "editar anúncio publicado" como edição — oferece "substituir e aposentar", e diz o que isso deixa no histórico.

**Ação desabilitada.** Hoje "Escrever a copy" desabilita por dois motivos e a página só envia `motivoBloqueio` para um (`:658-661`). Passa a enviar os dois.

`copyDesatualizada` compara **apenas os textos** das keywords, ordenados (`:221-225`): mudança de match type ou inclusão de negativa **não** marca a copy como desatualizada. Ou o critério passa a incluir isso, ou a tela declara o que ele cobre.

---

## 10. Parada 5 — Economia

**Pergunta dominante.** *Como ela nasce e quanto pode custar?*

**Decisão.** estratégia · lance · orçamento · graduação.

**Hierarquia.** conta (moeda, fuso) → estratégia → lance e orçamento → **teto do dia** → os 7 portões → graduação.

**Os sete portões vêm para cá.** Hoje eles aparecem em `Lancamento.tsx:497-506` — na tela onde o clique **cria** — e **não** onde o operador escolhe estratégia, lance e orçamento. A ordem de exibição usa a do backend (`prontidao.py:256-283`), não a do frontend (`portoes.ts:59-67`), e a divergência fica registrada.

Regra de pintura: **só `PRONTO` pinta positivo**; `PARCIAL` e `INDETERMINADO` são "não sei" (`portoes.ts:119-124`).

**Estratégia.** Duas na tela, **cinco** classificadas no backend em três famílias (`prontidao.py:720-752`). As três sem caminho de escolha (`TARGET_CPA`, `MAXIMIZE_CONVERSION_VALUE`, `TARGET_ROAS`) **não** ganham controle — a tela declara que a casa opera com duas.

Cartão inteiro clicável com `aria-pressed`, alvo é o cartão e não o rádio de 12px — **já correto** em `MesaDeLance.tsx:246-254`.

**O teto do dia.** A única derivação autorizada do navegador (`DATA-AND-AUTHORITY-MAP.md §6.2`), sob cinco condições, e com as **três ressalvas** viajando junto:

```
orçamento          R$ 10,00 / dia     você, agora
teto do dia        R$ 20,00           regra do Google: 2× o orçamento diário médio
teto de 3 dias     R$ 60,00           3 × teto do dia
```

Ressalvas exibidas, não em tooltip: `payment_mode = CONVERSIONS` não tem limite diário (`comum.md:471-474`); existe limite de gasto **no nível da conta** que sobrepõe o de campanha e **não pode ter aumento solicitado** (`:603-614`); `STANDARD` é pacing **mensal**, não trava diária de 1× (`:562-566`).

E toda leitura de gasto diz **"servido"**: `metrics.cost_micros` é custo servido, não cobrado, e **não existe métrica de custo cobrado na v25** (`:504-518`).

**Graduação.** O número 30 vem do flow n8n legado (`trafego.py:1435-1441`). ⚠️ `graduacao_em_conversoes` é aceito pelo modelo HTTP e **nunca lido, persistido ou executado**. A tela **para de dizer** que o "motor de gestão" a executa (`MesaDeLance.tsx:219-223`) e passa a dizer: *"registrada como intenção. Nenhum processo deste sistema a executa hoje."*

**Parse do dinheiro.** Uma função só. Hoje `MesaDeLance` normaliza vírgula e o pedido usa `Number(budget) || 0` (`NovaCampanhaPage.tsx:391-392`) — `"10,50"` vira **0** no pedido.

**Campo numérico.** Altura igual à do botão; borda **1px em todos os estados** (foco por `outline`, nunca `border-width`); validação no blur; ajuda com altura reservada; o valor formatado nunca é reescrito enquanto o campo tem foco.

---

## 11. Parada 6 — Revisão, e o Pedido

**Pergunta dominante.** *Está tudo certo?*

**Decisão.** Nenhuma. Confere e dispara a prova.

**O Pedido é projeção.** Toda linha tem rótulo, valor, **fonte** e — quando medida — **frescor**. `FALTA` vem do servidor. `próximo ato` é frase, não botão.

**Estados.** `—` acompanhado de **quem não leu**; nunca `0`, nunca em branco. Linha alterada recebe tinta de fundo por 1200ms, **sem movimento**.

**Ação dominante:** "Provar contra a conta". Desabilitada ⇒ razão adjacente ligada por `aria-describedby`, **visível em todos os breakpoints**.

**O que a tela diz sobre a prova, antes de disparar:** que ela **não cria nada**, que confere forma e política, e que **não existe lista oficial exaustiva do que ela deixa passar** (`fontes.json:946-1130`).

---

## 12. Ignição

**Objetivo.** Provar, aprovar e criar pausada, num lugar só, sem ambiguidade.

**Pergunta dominante.** *Posso autorizar isto?*

**A escada.** Quatro degraus sempre visíveis: `destino` → `copy` → `prova` → `escrita`. Dois são atos reais (uma chamada cada); dois são vereditos locais — **e a tela diz qual é qual**.

**Preservado por mérito:** a parada antes de gastar; as três travas encadeadas; recusa e indeterminação com saídas **opostas** e testadas.

**Correções obrigatórias:**

| # | Defeito | Onde | Correção |
|---|---|---|---|
| 1 | `role="dialog" aria-modal` **sem** foco preso, portal ou `inert` | `Lancamento.tsx:261-262` | implementar os três |
| 2 | **zero** `aria-live` / `role="alert"` / `aria-busy` | idem | escada com `aria-live="polite"`; erro com `role="alert"` |
| 3 | foco vai ao painel **uma vez, no mount** (deps `[]`) | `:118` | refocar a cada troca de estado |
| 4 | botão de fechar **desmontado** durante `escrevendo` | `:279-284` | desabilitado, com título explicando |
| 5 | `Esc` inerte sem feedback | `:107, 120-126` | a tela **diz por que não fecha** |
| 6 | degrau `copy` com veredito literal `ok`, podendo exibir `copy ✓ —` | `:299` | lê o estado real |
| 7 | `AVANCO` não monotônico: `reprovada` **recua** para 0,1 | `:676-684` | o horizonte **para**, não recua |
| 8 | `indeterminado` e `escrevendo` compartilham 0,85 | `:681-683` | valores distintos |
| 9 | 18 de 47 `text-white/NN` abaixo de AA, incluindo os identificadores copiáveis | `:584-626, 907` | mínimo `/70` |
| 10 | 22 `text-[11px]` + 1 `text-[10px]` | — | piso de 14px para o que decide |
| 11 | `.reveal` por degrau dentro de modal que re-renderiza | `:693` | sai |
| 12 | `pedido` reconstruído a cada render sem `useMemo`, e `provar` depende da identidade dele | `NovaCampanhaPage.tsx:384-421` × `:169-171` | memoizar |
| 13 | o cronômetro roda em **todos** os estados, re-renderizando o modal a cada segundo | `:109-114` | só enquanto há chamada aberta; `aria-hidden` |
| 14 | ⚠️ **o motivo nasce pré-preenchido** (`lançamento de "${titulo}"`), satisfazendo por construção as três guardas de 10 caracteres | `:99` | campo **vazio**, com a exigência escrita ao lado |
| 15 | ⚠️ **o diálogo não rola**: `.ignicao` é `display:grid; overflow:hidden` e o painel usa `justify-center` sem contêiner de rolagem | `:270-271`, `index.css:925-928` | painel com rolagem própria |
| 16 | ⚠️ **todo valor do recibo é `truncate`, sem `title`, sem `<abbr>`, sem botão de cópia** — inclusive o request id que o operador precisa enviar ao suporte | `:905-910` | valor completo acessível + cópia |
| 17 | o recibo omite `estado` e `explicacao`, campos **não-opcionais** de `ReciboDeLancamento` | `types/trafego.ts:759-771` | exibir |
| 18 | ⚠️ **nenhum estado de falha tem "tentar de novo"**: em `erro`, `reprovada`, `fora_do_canario` e `destino_reprovado` o único botão chama `onFechar`, que desmonta e descarta tudo | `:638-641` | voltar preserva o pedido |
| 19 | `travada`, `indeterminado` e `criada` **não oferecem botão nenhum** | `:636-642` | cada um com seu ato |

**Movimento.** Sem fase fictícia: `POST /provar` é **uma** requisição, teto de 120s. Spinner funcional + cronômetro real. Nada avança porque o relógio andou.

---

## 13. Recibo

**Objetivo.** Provar o que passou a existir, e permitir voltar a ler.

**Pergunta dominante.** *O que exatamente foi criado, e o que faço agora?*

**Superfície própria e retornável** — região com `id="recibo"`, alcançável por link direto. **Não** estado de modal: hoje `onFechar` faz `setLancando(false)`, desmontando o componente e descartando o `useState` (`NovaCampanhaPage.tsx:789-810`), e não há persistência (`grep 'localStorage'` em `Lancamento.tsx` → 0).

**Dados** — a união das duas superfícies de hoje:

| Campo | Onde já existe |
|---|---|
| campanha, conta, carimbo, recursos criados, request id, aprovador, plano de mensuração, ledger | `Lancamento.tsx:801-879` |
| **motivo declarado** e **impressão do pedido** | `recibos/CartaoDeRecibo.tsx:107-114` — a superfície mais completa, hoje **inalcançável** |

`recibo.ts` já prova a leitura contra o formato real e trava que falta de carimbo **ou** de impressão **anula o recibo**, e que falha em texto puro não é recibo (`__tests__/recibo.test.ts:58-63, 128-134`). A conferência de impressão tem três estados, e a ausência responde **"não dá para conferir"** — nunca "confere" (`:157-162`).

**Estados.**

| Estado | O que o Recibo faz |
|---|---|
| `sucesso` | recibo completo + a frase de §13.1 |
| `falhou` | código + o que corrigir; **reentrável** |
| `indeterminado` | o que se sabe + **o botão de reconciliar** + "reenvio é proibido" |
| `em_voo` (`registrado: false`) | "não há recibo registrado" + reconciliar; **nunca** lido como sucesso |

**Revelação.** Máscara radial a partir do botão disparador, 400ms, `mask` + `opacity`. Uma vez por campanha criada. Sob movimento reduzido, fade de 150ms.

**Sem histórico.** `GET …/recibos` não existe (`grep -rn 'router\.get("[^"]*recibo' backend/` → 0). A região mostra o recibo da sessão e **declara** que não há histórico.

### 13.1 A frase que o Recibo precisa carregar

> Esta campanha nasceu **pausada**. O coletor contínuo não alcança campanhas pausadas — ele filtra `ENABLED` e `SEARCH`. A releitura por identidade existe e ainda não tem agenda. Confira na conta.

Não é falha: é o preço da segurança, e o operador precisa saber que o silêncio não é boa notícia.

---

## 14. Reconciliação de resultado indeterminado

**Objetivo.** Fechar um recibo aberto **sem** criar nada.

**Pergunta dominante.** *A campanha existe na conta ou não?*

**Onde vive.** Dentro do Recibo, no estado `indeterminado`. Não é tela nova.

**Hierarquia.** o que se sabe → o que não se sabe → **o ato** → o que o ato faz e não faz.

**O que a tela diz antes do ato:**

> Reconciliar **lê** a conta e fecha este recibo. Ela **não** reenvia o pedido. Se a campanha existir, o recibo fecha como criada; se não existir, fecha como falha; se houver mais de uma, nada é carimbado e você decide.

⚠️ **A ação dominante depende de quem está olhando.** `POST /reconciliar` exige `exigir_admin` (`trafego.py:4442-4446`), e `backend/app/seguranca/identidade.py:216-228` devolve **403** para qualquer identidade válida que não seja admin.

| Quem | Ação dominante |
|---|---|
| admin | **"Reconciliar na conta"** |
| operador | **nenhuma ação executável.** A região mostra o `item_id` **copiável**, a frase "reconciliar exige perfil de administrador" e o caminho de escalonamento. O botão **não** aparece desabilitado — um botão que nunca vai funcionar para esta pessoa é pior que a frase |

Enquanto `Q3` (`DECISION-LOG.md §8`) não for decidida, esta é a apresentação. Se o perfil for aberto ao operador, a linha de cima desaparece.

**Ação dominante (admin):** "Reconciliar na conta". **Nenhuma ação secundária** — e explicitamente **nenhum** botão de reenviar: `reenvio_permitido` é `false` **fixo no tipo** (`types/trafego.ts:794-824`).

**Entrada.** `item_id` + `customer_id` + (`campaign_id` **ou** `marca`). Quando não há id externo — o caso que mais precisa da saída — a `marca` é o caminho (`trafego.py:4186-4195`).

**Estados de retorno:**

| Retorno | Tela |
|---|---|
| `achou: true` | recibo fecha como **criada pausada** |
| `achou: false` | recibo fecha como **falha**; passa a ser reentrável |
| **409 duplicidade** | "encontrei mais de uma. **Nada foi carimbado.**" + as candidatas |
| ⚠️ **403** | **é o retorno esperado para o operador comum** (`seguranca/identidade.py:216-228`), e a tela o trata como estado de primeira classe — nunca como erro genérico |
| 409 item de outra conta / 404 inexistente | frase do vocabulário + código |

**Por que isto existe:** a API **não oferece chave de idempotência** (`comum.md:151-154`). Sem ela, o timeout é ambíguo por construção. A tela diz isso em uma linha.

---

## 15. Página canônica da campanha — `/trafego/campanhas/:volcCampaignId`

**Objetivo.** Diagnosticar uma campanha com procedência.

**Pergunta dominante.** *Por que esta campanha está assim?*

**Ordem das oito seções, preservada** (`CampanhaCanonPage.tsx:155, 181, 200, 260, 263, 274, 286, 303`): identidade → entrega e frescor → evidência observada → diagnóstico → funil e linhagem → estrutura do canal → histórico e recibos → trilha de ação.

**Ganha:** o **Guardião 72h** como faixa própria acima do veredito — declarando que é **classificação de janela**, não vigilância (§15.1).

**Correções:**

| # | Hoje | Depois |
|---|---|---|
| 1 | a seção 6 é a **única das oito que não renderiza** quando falta o dado (`:274-283`) | toda seção declara ausência |
| 2 | H1 a `text-2xl md:text-3xl` (`:101, 118, 157`) | 32–40px, como o contrato pede |
| 3 | `CaixaDePropostas` renderizada **sem** `aoSubmeter`; o botão nasce desabilitado (`:506-510`) | ou ganha destino, ou a caixa declara que é leitura |
| 4 | componente `Fato` definido e nunca usado (`:515-520`) | remover |

**Preservar:** os quatro ramos de não-resposta do diagnóstico, **nenhum devolvendo `null`** (`:457-473`); o reúso de `medidaSemData` e `tetoDaCampanha` do inventário em vez de reimplementar (`:204-218`); a declaração de ausência de histórico como ausência de **capacidade** (`:292-299`).

**Só a identidade interna endereça esta página** — o id externo do Google não é único no VOLC O.S. (`types/trafego.ts:1750-1758`).

### 15.1 O Guardião 72h — o que a faixa diz

| Fato | Fonte |
|---|---|
| a janela é calculada **por requisição**, de `horas_ligada` | `diagnostico_persistido.py:1343-1354` |
| `horas_para_incidente = 24.0`, amarrado a `dominio.HORAS_ATE_ALERTAR` — divergir faria a campanha aparecer numa tela e não na outra | `sentinela.py:325-329` |
| `None` e `NaN` são **idade desconhecida**, nunca zero nem campanha madura | `:384-398` |
| ⚠️ **não há agendador**, não há tabela de incidentes, e `consolidar`/`incidente_do_veredito` não têm chamador de produção | `grep 'APScheduler\|celery'` → 0 |

A faixa diz: *"classificação da janela, calculada agora a partir das horas ligadas. Não há processo vigiando esta campanha entre uma visita e outra."*

---

## 16. Fila de atenção — `/trafego?aba=atencao`

**Objetivo.** Agrupar condições por **decisão do operador**, não por fonte.

**Pergunta dominante.** *O que exige decisão hoje?*

**Dados por item** (`atencao/projecao.ts:252-283`): chave de foco, sintoma, escopo, campanha, conta, desde quando, evidência, o sintoma cru do servidor, o alerta original, URL externa.

**Correções:**

| # | Hoje | Depois |
|---|---|---|
| 1 | a **cor** vem de segunda tabela escrita à mão, que não deriva de `SINTOMAS[].ordem` (`visual.ts:40-53`) | cor deriva da ordem |
| 2 | o mapeamento tom→classe é reescrito **duas vezes** (`FilaDeAtencao.tsx:300-304`) | uma vez |
| 3 | contador ≠ conteúdo (`useAtencao.ts:150`) | contam o mesmo |
| 4 | `AlertaDeEntrega` (o cartão rico) **não é renderizado em produção** | ou entra, ou sai |
| 5 | o tipo TS declara `impressoes`/`cliques`/`custo` **não-nuláveis**; o backend os declara `Optional` e zera para `None` (`types/trafego.ts:1490-1492`) | o tipo passa a admitir `null` |

**Preservar:** a declaração, **dentro da própria tela**, das quatro decisões que a fila não cobre por falta de sensor (`projecao.ts:811-830`). É o melhor exemplo de honestidade do módulo.

**Um alerta nasce** de `dominio.merece_alerta` (`backend/app/trafego/dominio.py:761-767`): campanha **LIGADA** + custo **MEDIDO e igual a zero** + idade conhecida **≥24h**. As três, juntas.

**Nenhum alerta é acionável no sentido de mudar a conta.** `mutacao_externa=False` é campo constante, e o texto disso vai para a tela (`sentinela.py:39-43`). A ação que sobra é `ordem_de_revisao` — lista o que conferir e **recusa sugerir valor** por ADR-11 (`backend/app/trafego/dominio.py:717-732`).

⚠️ **`LOW_DEMAND` não é oferecido como estado possível** enquanto não tiver produtor: ele está declarado em `PRECEDENCIA`, `ESTADOS_DE_INCIDENTE` e `SEVERIDADE`, tem verbete no frontend, e **nada o emite**.

**Severidade.** A fila herda a da sentinela (5 graus, `POLICY_REVIEW` deliberadamente **média**). O quadro de alertas do sino **não tem campo de severidade** (`alertas.py`, 569 linhas, `grep 'severidade'` → 0) — a fila **não inventa** um.
