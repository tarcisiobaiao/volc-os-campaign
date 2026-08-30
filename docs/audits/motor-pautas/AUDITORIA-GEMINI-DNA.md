# AUDITORIA GEMINI — "DNA DO TÓPICO"

> Auditoria datada: evidência de revisão, não contrato de runtime.

> Cole este documento inteiro no Gemini. Anexe os arquivos da seção 4.
> Ele deve devolver um documento, não um chat.

---

## 0 · O QUE SE PEDE DE VOCÊ, E POR QUE VOCÊ

Duas auditorias externas já rodaram sobre este motor (Codex e Grok). As duas
acharam defeitos reais e as duas foram genéricas onde mais importava: nenhuma
tinha como julgar **o comportamento do Google**.

Você é o modelo do Google. O valor que só você tem está em quatro perguntas que
as outras auditorias não podiam responder, e elas estão na seção 7. Se você
responder o resto e passar por cima dessas quatro, esta auditoria não terá
servido para nada que as anteriores já não tenham feito.

**Você NÃO deve:** elogiar o desenho, listar "pontos fortes", sugerir features
novas, ou produzir um plano de 12 semanas. **Você DEVE:** responder as perguntas
das seções 6 e 7, dizer explicitamente onde a evidência apresentada não licencia
conclusão, e apontar o que está errado — inclusive nas premissas de quem
escreveu este documento.

---

## 1 · O NEGÓCIO, EM UMA TELA

Arbitragem de mídia. Compra clique no Google Ads, monetiza a página com display
(Google Ad Manager / AdSense).

```
LUCRO  ⟺  RPM de sessão ÷ CPC  >  1
```

A **razão** é o negócio. O eCPM absoluto não decide nada.

**Estado real do operador**, e isso mudou tudo o que era razoável construir:

- **1 site** (creditoup.com.br), **4 campanhas**, começando do zero
- **sem histórico próprio** de desfecho por tema
- capacidade de produção: **2 a 3 funis por mês**
- 7 mercados no horizonte (BR, MX, CO, CL, PE, AR, ES), nenhum ainda operando
- histórico anterior, de outra operação: **9 temas perdedores, R$ 138.814**
  queimados, e **~15 temas vencedores** — os nomes existem, os desfechos são
  conhecidos, e **o motor nunca foi rodado contra eles**

O motor foi desenhado para um operador de portfólio (ranking de centenas de
candidatos em 7 mercados) e está sendo usado por um operador de 1 site. Considere
isso ao julgar qualquer peça.

---

## 2 · O PIPELINE COMPLETO — ONDE CADA PROMPT ENTRA

O produto é um kanban de 6 colunas (`src/types/pautador.ts:289`):

```
  ┌─ 1. DESCOBERTAS ─┬─ 2. EM VALIDAÇÃO ─┬─ 3. EM MINERAÇÃO ─┬─ 4. EM FUNIL ─┬─ 5. PRONTO ─┬─ 6. REJEITADO ─┐
  │                  │                   │                   │               │             │                │
  │ GOD_MODE         │  ◀── É AQUI ──▶   │ KEYWORD_MINING    │ FUNNEL_       │ redação     │                │
  │ SEED ORACLE      │  o motor de       │ MINER             │ ARCHITECT     │ humana      │                │
  │                  │  validação        │                   │               │             │                │
  │ recebe: um PAÍS  │  recebe: entidade │ recebe: 1 oport.  │ recebe: 1     │             │                │
  │ devolve: 40      │  devolve: eixos,  │ aprovada          │ oport.        │             │                │
  │ seeds            │  portão, veredito │ devolve: cluster  │ minerada      │             │                │
  │                  │                   │ de keywords       │ devolve: funil│             │                │
  │                  │                   │                   │ de 5 páginas  │             │                │
  └──────────────────┴───────────────────┴───────────────────┴───────────────┴─────────────┴────────────────┘
                              ▲
                    A ETAPA 2 É O OBJETO DESTA AUDITORIA
```

**Etapa 1 — "disparar descobertas".** `GOD_MODE_SYSTEM_PROMPT` recebe só o nome
de um país e devolve ~40 sementes. É um antropólogo digital: faz 5+ chamadas ao
Perplexity antes de gerar qualquer coisa, monta personas locais, mapeia fluxos de
atenção. **É deliberadamente generativo e sem freio** — o freio é a etapa 2.

**Etapa 2 — "em validação".** É onde o motor de eixos vive. Hoje ele responde
"vale a pena escrever sobre isso?" com 8 eixos, portões que zeram o índice, e uma
leitura por LLM. **O operador quer transformar esta coluna em "DNA DO TÓPICO".**

**Etapa 3 — mineração.** `KEYWORD_MINING_SYSTEM_PROMPT` explode uma oportunidade
aprovada num cluster de keywords.

**Etapa 4 — funil.** `FUNNEL_ARCHITECT` monta 5 páginas de TOFU a BOFU, com
objetivo emocional por página, ganchos entre páginas e idioma por campo (conteúdo
publicável no idioma nativo, briefing sempre em pt-BR).

**Você precisa ler as etapas 1 e 4 para julgar a 2.** A etapa 2 é o filtro entre
um gerador sem freio e um construtor caro. O que ela precisa decidir é definido
pelo que vem antes e pelo que vem depois, não por si mesma.

---

## 3 · O QUE A ETAPA 2 FAZ HOJE

**Espaço de oportunidade de 10 eixos, 8 no escopo desta etapa**
(`motor_pautas/espaco.py`). Índice = média geométrica ponderada que **zera** se
qualquer portão dispara. Três famílias: demanda humana, economia, posição.

Dois tipos de eixo, e a distinção é a espinha do desenho:

| tipo | eixos | origem |
|---|---|---|
| **MEDIDO** | volume, reposição, vácuo, formato de consumo, densidade | DataForSEO. Fatos de API. |
| **JULGADO** | ignorância, engajamento, opacidade | leitura por LLM |
| *fora de escopo* | spread, produção | decisão do engine de Ads, não daqui |

**Como os eixos julgados são produzidos** (`validacao/ficha.py` +
`prompts/ficha_de_resposta.md`) — e este é o desenho de que mais se orgulha, então
ataque-o primeiro:

1. Pega as perguntas do bloco **"As pessoas também perguntam" (PAA)** do Google
   para aquela entidade. Tipicamente 4.
2. O LLM **escreve a resposta completa** de cada pergunta.
3. O LLM **conta 8 observáveis** sobre o texto que ele mesmo escreveu:
   condições pessoais (0-3), ramos de ação (1-3), fontes oficiais (1-3), sobra
   decisão? (bool), o canal oficial fecha sozinho? (bool), a regra mudou nos
   últimos 12 meses? (bool), há algo em jogo? (bool), a pessoa descobre nesta
   página que a coisa existe? (bool). Mais uma **tensão** de um vocabulário
   fechado de 7.
4. **O LLM não dá nota, nível, tier nem recomendação.** Python deriva os eixos
   das contagens por aritmética.

A tese: contagem sobre um texto que o modelo acabou de escrever é verificável;
rótulo ordinal sobre um sentimento não é.

**A tabela de 7 tensões**, escolhida pela FORMA da pergunta e nunca pelo
substantivo — é o que deveria fazer a leitura atravessar idioma:

```
medo_de_perder      "vai cair pra mim? se eu perder a data, perco o dinheiro"
dinheiro_esquecido  "tem dinheiro meu parado que eu não sei sacar?"
acesso_negado       "o direito é meu, mas o sistema não me deixa chegar nele"
obrigacao_legal     "me pediram esse documento e eu não tenho — como tiro agora?"
ascensao            "isso pode mudar minha vida e é de graça — eu entro?"
urgencia_de_renda   "preciso ganhar dinheiro essa semana — como começo?"
protecao_familiar   "se alguém aqui em casa passar mal, eu tô coberto?"
```

**O portão mais consequente:** `(engajamento, dado_unico)` — "a resposta esgota em
segundos". Zera o índice. A evidência: os 9 temas de R$ 138.814 eram todos
consulta de registro pessoal com resposta seca. Mecanismo alegado: o leitor sai
antes do anúncio ficar visível. **Nunca replicado fora daqueles 9, e os 9 são o
mesmo arquétipo.** Está declarado no código como dívida.

Custo: **US$ 0,0092 por card**.

---

## 4 · OS ARQUIVOS — ANEXE ESTES

Raiz: `/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign`

### ESSENCIAIS (sem estes a auditoria não tem objeto)

```
backend/app/motor_pautas/prompts/ficha_de_resposta.md      223 linhas  ← o prompt da etapa 2 HOJE
backend/app/validacao/ficha.py                             396 linhas  ← a derivação: LLM conta, Python decide
backend/app/motor_pautas/espaco.py                         667 linhas  ← os 10 eixos, pesos, portões, o índice
backend/app/prompts.py                                     380 linhas  ← ETAPA 1 (GOD_MODE) + mineração + funil
```

### PARA ENTENDER A JORNADA COMPLETA (o operador pediu explicitamente)

```
backend/app/n8n_prompts/funnel_builder.py                  998 linhas  ← ETAPA 4, o arquiteto de funil, verbatim do n8n
backend/app/n8n_prompts/kw_funnel_prospector.py            241 linhas  ← o garimpeiro que agrupa keywords em temas-pai
```

### O RESTO DO MOTOR (anexe se couber; não são obrigatórios)

```
backend/app/validacao/orquestrador.py                      929 linhas  ← o fluxo: SERP → tráfego → ficha → posicionar
backend/app/motor_pautas/sensores/dataforseo.py           1062 linhas  ← mapeadores puros de API → nível de eixo
backend/app/validacao/julgamento.py                        226 linhas  ← as duas passadas e a comparação
src/types/pautador.ts                                                  ← as 6 colunas do kanban
```

### DESCARTADOS, mencionados para você não se confundir se aparecerem

```
backend/app/motor_pautas/prompts/classificador_eixos.md    648 linhas  ← MORTO. Pedia 5 rótulos ordinais. 67% de estabilidade.
backend/app/motor_pautas/prompts/portao_engajamento.md     155 linhas  ← MORTO. Substituído pela ficha.
```

---

## 5 · O QUE JÁ FOI MEDIDO — leia antes de opinar

Esta seção existe para você não repetir hipóteses que já foram testadas. Todos os
números abaixo são medições reais, com custo e data.

### 5.1 · Confiabilidade teste-reteste, com INPUT FIXO

Mesmas 11 entidades, mesmas perguntas do PAA (cache, zero SERP), mesmo prompt,
**3 execuções independentes**, 43 perguntas comparáveis:

| eixo | as 3 execuções deram o MESMO nível em |
|---|---|
| engajamento, escala antiga de **5 níveis** | **51%** |
| engajamento, colapsada em **2 estados** | **79%** |
| ignorância (6 níveis) | 77% |
| opacidade (4 níveis) | **65%** |
| tensão (8 valores) | **63%** — e é a única cuja **moda migra** com input fixo |

**Isto é o teto de tudo.** Nenhuma análise a jusante pode ser mais confiável que
o input dela. Um índice que multiplica três eixos de 51–79% acumula esse ruído.

### 5.2 · A escala ordinal de 5 níveis foi aposentada

Ela concentrava 62,5% num lote e 76,2% noutro, e o teste-reteste deu 51%. Foi
colapsada para 2 estados (`esgota` / `sustenta`), o que subiu a confiabilidade
para 79%. A tentativa de substituir os 3 níveis do meio pela **contagem crua**
(ramos + condições + decisão) foi **refutada**: amplitude 2,5 numa faixa de 1 a
11, e a ordem saiu errada na cara — *"segunda via de conta de luz"* (5,5) acima de
*"pensão por morte"* (5,0). A contagem mede **ramificação**, e ramificação não é
valor: um trâmite burocrático com muitos fornecedores ramifica muito e vale pouco.

### 5.3 · A tese cross-idioma, sob input fixo, 3 execuções

```
licencia de conducir (MX)  → obrigacao_legal      4/4 perguntas nas 3 execuções   SÓLIDO
cesantias (CO)             → dinheiro_esquecido   4/4 nas execuções 1 e 3
                             nenhuma              na execução 2 — ABSTENÇÃO, nunca tensão errada
pensão por morte (BR)      → protecao_familiar / medo_de_perder / acesso_negado
                             três tensões diferentes, mesmas perguntas, 3 execuções
```

### 5.4 · Defeitos encontrados e corrigidos (para você saber o que já não é notícia)

- O bloco PAA às vezes volta **vazio**, e o código injetava a própria keyword como
  pseudo-pergunta. Toda entidade sem PAA tinha os 3 eixos julgados derivados de um
  item inventado. Removido — PAA vazio agora é **abstenção**.
- "Todas as perguntas esgotam" é regra vazia com n=1. Piso de N adicionado.
- Uma entidade rica morria quando a única pergunta congelada era de data (`DIRPF`
  travado em *"quando libera a declaração"* devolve uma DATA). Por isso a unidade
  passou a ser a ENTIDADE somando N perguntas, não uma pergunta.
- Índice zerado convivendo com `apto=True`. Corrigido.
- Faixa de spread cortando em 0,9 quando a aritmética manda cortar em 1,0
  ("0,9 era política de tolerância apresentada como aritmética").

### 5.5 · O que NUNCA foi medido, e é o buraco central

**Não existe uma única observação ligando qualquer eixo deste motor a RPM ÷ CPC
realizado.** Zero. Tudo que foi medido até aqui testa a coerência interna do
instrumento, nada testa acerto. O log de predição→desfecho não existe.

---

## 6 · A PERGUNTA CENTRAL — "DNA DO TÓPICO"

O operador quer **simplificar** a etapa 2 e transformá-la em algo que ele chama de
**DNA do Tópico** (ou DNA da KW). A intenção, nas palavras dele:

> "entender essas nuances do psycho algorithm... com base em uma série de indícios,
> começando pelos psicológicos e de como o cérebro humano se comporta nessa jornada
> de funil, tem como analisarmos de forma mais pragmática... e o que a gente for
> usar de busca real de outros critérios, ser algo mais simples."

Responda, com esta ordem de prioridade:

**6.1** — Um "DNA do tópico" que seja majoritariamente **leitura psicológica** e
minoritariamente dado de busca é defensável, dado que a leitura psicológica mede
63–79% de confiabilidade teste-reteste? Se sim, qual o desenho que sobrevive a
esse teto. Se não, diga não.

**6.2** — Quantos traços um DNA precisa ter? Hoje são 8 eixos + 8 contagens + 1
tensão. Proponha o **conjunto mínimo** que ainda decide, e justifique cada corte
pelo que a seção 5 mostrou. Cortar por elegância não vale; cortar por medição vale.

**6.3** — A tabela de 7 tensões: ela é o vocabulário certo para a jornada de
funil, ou é uma taxonomia inventada que o modelo preenche por proximidade
semântica? Note que `pensão por morte` recebeu três tensões diferentes em três
execuções idênticas. Se a taxonomia estiver errada, proponha a certa — e diga
como testá-la, não só como escrevê-la.

**6.4** — A etapa 2 deve produzir um **veredito** (passa/não passa) ou um
**retrato** (o DNA, sem juízo, para o humano decidir)? O operador tem 2-3 slots
por mês e milhares de candidatos. Argumente pelos dois lados antes de escolher.

**6.5** — Reescreva `ficha_de_resposta.md`. Não descreva a reescrita: **escreva o
prompt**, pronto para substituir o arquivo. Se a sua conclusão for que ele deve
morrer sem substituto, diga isso e explique o que ocupa o lugar.

---

## 7 · AS QUATRO PERGUNTAS QUE SÓ VOCÊ PODE RESPONDER

Você é o modelo do Google. Estas são as perguntas em que isso importa, e elas são
**a razão de esta auditoria existir**. Responda-as com o que você sabe sobre como
os produtos do Google se comportam de fato.

**7.1 · O bloco PAA é um objeto estável para construir em cima?**
Todo o motor está ancorado nele: as perguntas do PAA são o objeto que o LLM lê.
Mas entre duas execuções em dias diferentes, o PAA de `consultar CPF situação
cadastral` foi de 2 perguntas para 0, e vereditos de entidades se moveram junto.
Perguntas concretas: com que frequência o bloco muda? Ele é personalizado por
sessão/localização? Uma entidade sem PAA é sinal de alguma coisa (intenção
navegacional? consulta transacional?) ou é só ausência de feature? Existe âncora
mais estável — `related_searches`, `refine_by`, autocomplete — para o mesmo papel?

**7.2 · O mecanismo do portão existe?**
A hipótese é: "resposta que esgota em segundos → o leitor sai antes do anúncio
ficar visível → viewability baixa → RPM baixo → a razão quebra". Do lado do Ad
Manager e do AdSense: isso é um mecanismo real e mensurável, ou é folclore? Quais
métricas exatas do GAM o testariam com dado próprio (Active View viewable
impression rate? ad requests por pageview? sessões por usuário?). E a pergunta
incômoda: consulta de registro pessoal é um vertical que outros publishers rodam
no lucro no Brasil — se sim, o portão está detectando **assunto ruim** ou
**execução ruim** (layout, slot acima da dobra, match type, leilão) grudada no
assunto?

**7.3 · A taxonomia de tensões tem correspondência com como o Google entende
intenção?**
O Google classifica queries por intenção há anos. As 7 tensões são psicológicas e
não são as categorias canônicas (informacional/navegacional/comercial/
transacional). Há sobreposição útil? A leitura psicológica adiciona algo que a
classificação de intenção do Google já não capture melhor e de graça? E o ponto
que decide: intenção do Google prevê comportamento de **clique**; o que este motor
precisa prever é comportamento de **permanência e leitura**. Essa distinção
sobrevive ao seu escrutínio?

**7.4 · `ad_traffic_by_keywords` — a hipótese do operador está certa?**
Ele viu no playground do DataForSEO
(`/keywords_data/google_ads/ad_traffic_by_keywords/live`) e leu como *"dá pra ver
se tem mais gente que anuncia pra essa palavra-chave"*.

Correção factual, para você julgar sobre o fato e não sobre a suposição: esse
endpoint é o **forecast do Keyword Planner** — devolve impressões, cliques, CTR,
CPC médio e custo estimados **para um lance e um tipo de correspondência que você
informa**. Ele não devolve contagem de anunciantes. Quem sinaliza densidade de
anunciante é `competition_index` (0-100) em
`/keywords_data/google_ads/search_volume/live`, e a contagem de resultados pagos
na SERP — que o motor já usa como eixo `densidade`.

O endpoint está **mapeado e nunca foi usado**
(`sensores/dataforseo.py:78`, como `trafego_por_lance`).

Suas perguntas:
- Para arbitragem, o forecast por lance é **mais** útil que a contagem de
  anunciantes? O argumento a favor: ele dá o CPC que se pagaria de fato numa
  posição, que é o denominador da razão. Isso procede, ou o forecast do Keyword
  Planner é otimista/enviesado a ponto de não servir de denominador?
- Já se sabe que `keyword_info.cpc` do DataForSEO Labs **superestima o CPC real
  em 7,4×, com inversão de ordem** (medido nesta operação). O forecast sofre do
  mesmo viés, ou é outra fonte?
- Qual é o **conjunto mínimo de chamadas** que dá o retrato econômico honesto de
  um tópico? Hoje são até 6 endpoints por card. O operador quer menos.

---

## 8 · O FORMATO DA RESPOSTA

Um documento com estas seções, nesta ordem. Sem preâmbulo, sem resumo executivo,
sem elogio.

1. **VEREDITO** — uma linha: o DNA do Tópico como proposto é viável, viável com
   cortes, ou não é. Depois no máximo 5 frases de porquê.
2. **AS QUATRO RESPOSTAS DA SEÇÃO 7** — é a parte que só você pode escrever.
   Se você não souber, escreva "não sei" em vez de plausibilidade.
3. **O DNA MÍNIMO** — a lista dos traços que sobrevivem, cada um com: o que
   mede, de onde vem (LLM ou API), e o que acontece se ele estiver errado.
4. **O PROMPT** — `ficha_de_resposta.md` reescrito, pronto para colar.
5. **AS CHAMADAS** — quais endpoints do DataForSEO, em que ordem, a que custo por
   card, e qual pergunta cada um responde. Se algum dos 6 atuais deve sair, diga
   qual e por quê.
6. **O QUE ESTE DOCUMENTO AFIRMA E NÃO SUSTENTA** — os erros de quem o escreveu.
   Há pelo menos um; a seção 5 tem o histórico de auto-engano deste projeto.
7. **O TESTE QUE DECIDE** — a medição mais barata capaz de refutar a sua própria
   proposta, com custo estimado.

---

## 9 · REGRAS

- **Português do Brasil.**
- **Não invente medição.** Se precisar de um número que não está aqui, diga qual
  é e como obtê-lo.
- **Não proponha nada que exija dado que o operador não tem.** Ele não tem log de
  desfecho por tema. Uma proposta que dependa disso é uma proposta para daqui a
  seis meses, e tem de ser marcada como tal.
- **Não seja diplomático.** As duas auditorias anteriores acharam defeitos reais
  porque foram instruídas a atacar. A pergunta não é "isso é bom?", é "onde isso
  quebra?".
- **Discorde deste documento onde ele estiver errado.** Ele foi escrito por quem
  construiu o motor, e a seção 5.4 é a lista de coisas que essa mesma pessoa
  afirmou com confiança e depois teve de desmentir.
