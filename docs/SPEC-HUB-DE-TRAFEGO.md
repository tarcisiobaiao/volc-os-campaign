# Hub de Tráfego — spec e PRD

**Data:** 18/08/2026 · **Registro:** product · **Estado:** parcialmente construído — ver §10

> ### ⚠️ Estado deste documento — atualizado em 24/08/2026
>
> **Vigente em parte.** A porta de entrada da camada é **[TRAFEGO.md](./TRAFEGO.md)**; os
> fatos medidos vivem em **[EVIDENCIAS-TRAFEGO.md](./EVIDENCIAS-TRAFEGO.md)**.
>
> | seção | estado |
> |---|---|
> | §4.2, §4.3, §5, §6, §10 | **vigentes** — cockpit de nascimento, provas, travas, retrato do que existe |
> | §4.1 (`/trafego` — o quadro) | **superada** por [SPEC do P0 §6](./SPEC-P0-TRAFEGO.md): o quadro vira uma aba e o padrão passa a ser o inventário |
> | §1 — *"`metrics.` tem zero ocorrências; uma tela com ROAS seria ficção"* | **superada como fato** (ver [E-01](./EVIDENCIAS-TRAFEGO.md#e-01)), mantida como princípio: não desenhar número que não se mede |
> | §8, §9 (o que construir / aceite) | **superadas** pelo backlog do [PRD](./PRD-TRAFEGO-OPERACAO.md) §7 |

> **§10 é a única seção que diz o que EXISTE.** As seções 1 a 9 são o desenho e
> continuam válidas; algumas descrevem coisas que ainda não foram construídas.
> Na dúvida entre o spec e o código, o código ganha.

---

# 1. O QUE ESTE MÓDULO É

A terceira e última etapa do ciclo **PAUTA → FUNIL → CAMPANHA → RESULTADO**.

O Pautador acha o tema e minera as keywords. O Redator escreve o funil e sobe os
rascunhos. O Hub de Tráfego **compra o clique** que leva alguém até lá.

> ⚠️ **Corrigido em 24/08/2026.** O parágrafo abaixo dizia que `metrics.` tinha zero
> ocorrências no `volc_ads/`. **Isso deixou de ser verdade**: o módulo de entrega passou a
> ler impressões, cliques e custo ([E-01](./EVIDENCIAS-TRAFEGO.md#e-01)). O que continua verdadeiro é o mais importante —
> não existe camada de **resultado** (conversões, receita, ROAS: [E-15](./EVIDENCIAS-TRAFEGO.md#e-15)) nem executor de
> ajuste, e o princípio de não desenhar número que não se mede permanece.

Não é um dashboard de performance, e essa decisão é de fato, não de gosto: o sistema mede
**custo e entrega**, e não mede **resultado**. Uma tela com ROAS e curva de gasto seria
ficção desenhada. O que existe de verdade — e é muito — é uma **mesa de
prova**: um engine que monta a campanha inteira num mutate atômico e a valida
contra a conta real antes de criar nada.

## 1.1 O que muda em relação ao n8n

| n8n | volc_ads |
|---|---|
| 13 HTTP em sequência; a 7ª falha deixa meia campanha na conta | **mutate atômico** de ~72 operações: entra tudo ou não entra nada |
| "erro" é uma coisa só | três classes com tratamentos opostos; `TERMINAL` de política **nunca** retenta |
| falha silenciosa | `validate_only` contra a conta real, custo zero, antes de existir campanha |
| "prefira morno a reprovado" | corpus de **6.651 headlines aprovados** como régua |

A página tem que ser a mesa de prova, não um formulário com um botão. Se ela
esconder o `validate_only`, ela desperdiça a única coisa que o n8n não tinha.

---

# 2. O ELO QUE EU ENCONTREI, E QUE MUDA TUDO

O `README` do `volc_ads` diz que o `Brief` exige `keywords` e `copy` e que
"nenhum motor de descoberta produz isso hoje". **Isso está desatualizado.**

Medido em 18/08/2026 no Supabase, tabela `pautador_keyword_clusters`, linha
`id=4`, `opportunity_id=73` — **o mesmo card que virou o funil #6 do Redator**:

```
opportunity_id 73  ──┬──▶  pautador_keyword_clusters #4    (as keywords)
                     └──▶  pautador_funnel_runs #6         (o funil escrito)
                                    │
                                    └──▶  a campanha        (este módulo)
```

## 2.1 O que a mineração já entrega

| campo | conteúdo medido |
|---|---|
| `production_ads_queue` | **23 keywords já triadas para anúncio**, cada uma com `cpc`, `volume`, `competition`, `trend_score`, `tags` e `reason` |
| `content_seo_queue` | as que servem a conteúdo, não a anúncio — triagem já feita |
| `funis_sugeridos` | funis ranqueados, com `keyword_ancora`, `volume_ancora` e `justificativa` |
| `funis_sugeridos[].sub_intencoes` | **grupos tipados** com keywords, volume e CPC por grupo |
| `summary.breakdown` | 20 gems · 11 seasonal · 10 hidden_trends · 5 questions · 2 future · 1 titan · **63 descartes** |
| `total_volume` | 37.350 |

As sub-intenções do funil rank 1:

| sub-intenção | keywords | volume | CPC médio |
|---|---:|---:|---:|
| ACESSO | 7 | 31.030 | 0,74 |
| ELEGIBILIDADE | 26 | 11.580 | 1,09 |
| VALOR | 5 | 1.980 | 1,50 |
| OUTROS | 5 | 530 | 0,16 |

**Isto resolve duas pendências de uma vez.** As keywords deixam de ser digitadas
à mão, e as sub-intenções são a estrutura natural de **múltiplos ad groups** —
que o `README` lista como pendência nº 2 (`4b. Cria AdGroup Discovery` do n8n).
O engine cria um ad group só; a mineração já entrega quatro grupos com spread de
CPC de 9× entre eles.

## 2.2 ⚠️ O CPC minerado provavelmente não é o CPC real

`services_used` da linha #4 é `["n8n:google_ads", "n8n:dataforseo", "n8n:gemini"]`.

O `DATAFORSEO-MEDIDO.md` mediu, com 96 chamadas e fatura de US$ 1,977, que
**`keyword_info.cpc` superestima o CPC real em 7,4× (média geométrica)** — e que
o erro **não é de escala**: a ordem inverte dentro do próprio cluster, então
nenhum fator de correção resolve.

Não afirmo que os CPCs desta linha vêm dali; `engine` é `n8n` e não tenho o
código do flow. Mas `avg_cpc_local` e `currency` estão **nulos**, ou seja nem a
moeda está declarada.

**Requisito de tela:** todo CPC minerado aparece com a procedência ao lado, e
**nunca** como "CPC estimado" sem qualificador. Onde houver CPC real da operação
(GAQL em `keyword_view`), ele ganha destaque e o minerado vira referência
secundária. Um número de proveniência desconhecida apresentado como medição é
exatamente o defeito que o `PORTOES_EXIGEM_MEDICAO` existe para impedir.

---

# 3. QUEM USA, E EM QUE ESTADO DE ESPÍRITO

Operador de arbitragem, administrador do sistema. Chega aqui com um funil pronto
e três rascunhos no WordPress, sabendo que a próxima ação **gasta dinheiro de
verdade** e que uma campanha mal montada não é só desperdício: uma reprovação de
política suja a conta.

Ele está **atento e avesso a risco**, não explorando. Quer ver a prova antes de
apertar. A tela ganha a confiança dele mostrando o que verificou, não escondendo
a complexidade.

Frequência: baixa. Poucas campanhas por semana. Isso significa que **ele não
memoriza a interface** — cada campo precisa dizer o que é sem treinamento.

---

# 4. AS TRÊS TELAS

```
/trafego                         o quadro: campanhas por estado do ciclo
/trafego/nova                    o cockpit de lançamento (4 estágios)
/trafego/campanha/:id            uma campanha: o que subiu e o veredito de política
```

## 4.1 `/trafego` — o quadro

Mesmo vocabulário do `/redator`: colunas por estado, cards, e o gasto acumulado
na régua superior. Quatro colunas:

| coluna | de onde vem |
|---|---|
| **prontos para anunciar** | funis do Redator com páginas publicadas E cluster de keywords no Pautador. É a coluna que gera trabalho. |
| **rascunho** | briefs montados e ainda não provados |
| **provados** | passaram nos três juízes; o botão de subir está aceso |
| **no ar (pausadas)** | subiram. Nascem `PAUSED` — ver §6.3 |

O card de "pronto para anunciar" mostra o que a campanha herdaria: o domínio, a
LP, quantas keywords o cluster tem e o volume agregado. É a peça que responde
"vale a pena?" antes de abrir o cockpit.

## 4.2 `/trafego/nova` — o cockpit

Quatro estágios, e a ordem é a ordem em que as decisões dependem umas das outras.
**Não é wizard com bloqueio**: os quatro ficam visíveis o tempo todo, numa coluna
lateral que mostra o que já está resolvido e o que falta. Wizard esconde o
tamanho do trabalho, e este operador precisa vê-lo.

### Estágio 1 · ORIGEM

Duas portas, conforme decidido:

**A · Do funil (padrão).** Escolhe um funil escrito. Herda de graça:
`url_final` (a LP, nunca uma `/rec/`), `nicho`, `slug`, os fatos verificados da
pesquisa (que alimentam o `{fatos}` do `PROMPT.md`), e o `opportunity_id` — que é
a chave para achar o cluster de keywords.

**B · Avulsa.** URL colada à mão, para anunciar página que não veio do Redator.
Perde a herança e **perde a checagem de congruência** (§6.1) — e a tela diz isso,
porque é a diferença entre as duas portas.

### Estágio 2 · KEYWORDS

Vem da `production_ads_queue` do cluster. Não é uma lista chapada: é a triagem
que a mineração já fez, apresentada como triagem.

```
23 aprovadas para anúncio · de 112 mineradas · 63 descartadas
volume agregado 37.350

  ACESSO                      7 kw · vol 31.030 · CPC¹ 0,74     ▸ ad group
  ┌──────────────────────────────────────────────────────────┐
  │ ☑ banco pan telefone          27.100   0,93   LOW  TITAN │
  │ ☑ cartão de crédito caixa…     1.600   0,39   LOW  HIDDEN│
  │ ☐ solicitar cartão caixa…      1.300   0,49   LOW        │
  └──────────────────────────────────────────────────────────┘

  ELEGIBILIDADE              26 kw · vol 11.580 · CPC¹ 1,09     ▸ ad group
  …

  ¹ CPC minerado (n8n:dataforseo) — não é o CPC da sua conta.
    Ver §2.2. [medir na conta →]
```

Cada sub-intenção vira **um ad group**, com o nome dela. Isso resolve a pendência
nº 2 do `README` usando estrutura que já existe, em vez de inventar um "ad group
discovery" artificial.

O operador desmarca o que não quer. O contador de volume e o CPC ponderado
respondem na hora — porque a escolha de keyword É a escolha de quanto vai custar.

### Estágio 3 · COPY

O `PROMPT.md` gera; o `ciclo.py` conserta. O operador vê os dois lados:

- **os assets gerados**, editáveis, com o contador de caracteres do jeito que o
  Google conta (DKI pelo fallback);
- **a cascata**, quando ela rodar: qual asset foi regenerado, por qual regra, e
  quantas tentativas restam. `TETO_ASSET = 2`, e a mesma regra falhando duas
  vezes encerra aquele asset.

O que **não** aparece: um botão "gerar" que devolve um bloco de texto opaco. A
cascata é o produto — ela é a razão de isto não ser o n8n.

### Estágio 4 · CONTA E LANCE

`customer_id` + `login_customer_id`, orçamento diário, CPC inicial, match type,
negativas. Campos poucos e conhecidos.

⚠️ **A negativa que se contradiz.** O brief do FGTS negativa `meutudo`, `nubank`,
`bmg`, `santander` — as quatro marcas que a própria LP usa como argumento. A tela
cruza as negativas com o texto da página e avisa. É barato de checar e caro de
descobrir depois.

## 4.3 A PROVA — obrigatória, e é o clímax da tela

O botão de subir **nasce apagado**. Acende quando os três juízes rodaram.

```
┌─ PROVA ────────────────────────────────────────────────┐
│                                                        │
│  FORMA        ✓ passou            determinístico       │
│  15 headlines · 30/30 chars · 0 duplicata · 0 emoji    │
│                                                        │
│  GOOGLE       ✓ aceitou           validate_only        │
│  72 operações · conta 8017851692 · nada foi criado     │
│                                                        │
│  CORPUS       ◐ morno             6.651 aprovados      │
│  verbo de execução   4,2%   (aprovados 12,2%)          │
│  pergunta            0,0%   (aprovados  7,2%)          │
│  marcador leitura   58,0%   (aprovados 29,9%)          │
│                                                        │
│  ────────────────────────────────────────────────────  │
│  [ SUBIR COMO PAUSADA ]                                │
└────────────────────────────────────────────────────────┘
```

**O terceiro juiz não reprova nada, e isso é declarado na tela.** Ele existe
porque a falha mais cara do gerador anterior não era reprovação — era **mornidão**,
e mornidão não aparece em `validate_only`. A copy antiga tinha verbo 0,0% contra
12,2% dos aprovados, pergunta 0,0% contra 7,2%, e o Google **aceitava**.

FORMA e GOOGLE são portão. CORPUS é espelho.

---

# 5. O DESENHO

## 5.1 Cor

Restrained, como o resto do produto. O acento existe em três lugares e em mais
nenhum: o estado da prova, a faixa de estado do card, e o botão de subir quando
ele acende.

⚠️ **O mesmo problema medido no Redator vale aqui.** `--success` dá 3,03:1 sobre
`--card` no tema claro e `--warning` dá 2,38:1 — três dos cinco tokens semânticos
reprovam o piso de 4,5:1, e os números **invertem** entre os temas. Então o estado
da prova é **glifo + palavra**, com cor em último e só onde ela passa nos dois
temas.

## 5.2 A cena, que decide o tema

*"O operador confere a última tela antes de gastar dinheiro real, de dia, no
mesmo monitor onde o resto do Volc OS está aberto."*

Isso força **claro por padrão, escuro disponível** — a mesma regra do produto.
Não é uma superfície de plantão noturno; é uma mesa de conferência.

## 5.3 O elemento assinatura

**A régua de custo do leilão**, no estágio 2. Enquanto o operador marca e
desmarca keywords, uma barra horizontal mostra o CPC ponderado do conjunto contra
o lance declarado — e o quanto de volume entra em cada faixa de preço.

É o único lugar da tela onde a forma carrega a informação em vez de rotulá-la, e
é a informação que decide a campanha: **RPM ÷ CPC > 1**. Uma lista de checkboxes
com um número no rodapé diria a mesma coisa e não ensinaria nada.

Toda a ousadia vai aí. O resto é quieto.

## 5.4 O que reusar, e o que não inventar

**Usar:** `.kicker`, `tabular`, `.font-display`, `.hairline`, `.reveal`, o bloco
de aurora + grão de duas camadas, e o vocabulário de card do `/redator` — quadro,
faixa de estado no topo, régua de medidas na horizontal.

**Não usar:** `Progress` (é `rounded-full` chapado), `AnimatedGradient` (está
quebrado: a classe e a var não existem), `.text-aurora` sobre número que muda.

Números **sempre** em `tabular`. CPC em **duas** casas (é moeda, o operador lê em
reais); custo de API em quatro (as células do Redator vão de US$ 0,0026 a
US$ 0,4556 e duas casas apagariam metade).

---

# 6. AS TRAVAS

## 6.1 Congruência anúncio × página

O problema aberto do FGTS, em uma frase: o brief declara `vertical="informativo"`
e a LP tem `antecipar` 16×, `pix` 8× e quatro bancos nomeados. **A página
intermedeia crédito.**

O precedente medido: `GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES` deixou **57
anúncios FULLY_LIMITED** em 39 contas, e o padrão reprovado é sempre o mesmo —
imperativo que sugere que o site executa o serviço ("Baixe seu Novo RG").

Quando a campanha nasce do funil, a tela tem os dois lados na mão: o texto da LP
(`drafts[N].content`) e o texto do anúncio. Ela cruza e avisa. Não bloqueia — a
decisão é do operador — mas não deixa passar em silêncio.

## 6.2 A trava de escrita continua fechada

`gads/modo.py` é de dois fatores: `destravar()` no código **e**
`FORGE_PERMITIR_ESCRITA=1` no ambiente. `validate_only` é isento de propósito.

O backend **não** liga a trava por conta própria. Subir exige as duas coisas, e
o botão da tela dispara uma rota que verifica ambas e recusa com a mensagem do
próprio `EscritaBloqueada` quando falta uma.

## 6.3 A campanha nasce PAUSADA

`comum.py` já faz isso. Consequência que a tela precisa explicar: **lançar custa
zero** e já produz o veredito real de política do Google sobre recurso
persistido — que é a única coisa que o `validate_only` não dá.

Então "subir" não é o fim. É o quarto juiz.

## 6.4 A blocklist morta

`campanha/limites.yaml` proíbe `empréstimo`, `crédito`, `antecipação`. Medido nos
6.651 aprovados: `crédito` aparece **54×** e em **nenhum** punido. A tela **não**
aplica essa lista, e `campanha/validacao.py` (100% pt-BR) deve ser substituído
por `policy/spec.py` (pt/es/en, com portão país × vertical) nesta entrega.

---

# 7. O QUE FICA DE FORA, E POR QUÊ

| fora | motivo |
|---|---|
| métrica, ROAS, curva de gasto | `metrics.` = 0 ocorrências. Seria ficção. |
| Display, Demand Gen, PMax | a taxonomia nomeia os quatro canais e o `Brief` os serve, mas existe **um** construtor: `search.py` |
| ajuste automático de lance | o `beast/` ficou para trás com defeito reproduzido: dia sem gasto vira ROAS 0 e corta orçamento; 20 dias com `spend=0` cortam de 100 para 70 |
| pedir isenção de política | `errors.py` já preserva `ChavePolitica` e `is_exemptible`; a ação em si é a próxima entrega |

---

# 8. O QUE PRECISA SER CONSTRUÍDO

Ver §10 — esta seção foi escrita antes da construção e está superada.

---

# 9. CRITÉRIOS DE ACEITE

1. O botão de subir está desabilitado até FORMA e GOOGLE passarem.
2. Nenhum CPC minerado aparece sem a procedência ao lado.
3. Cada sub-intenção marcada vira um ad group nomeado no payload.
4. A régua de leilão recalcula ao marcar/desmarcar, sem ida ao servidor.
5. Campanha vinda de funil mostra o cruzamento anúncio × LP.
6. Negativa que aparece no texto da LP é sinalizada.
7. Subir com a trava fechada devolve a mensagem do `EscritaBloqueada`, e a tela
   a mostra inteira.
8. O estado da prova é legível sem cor (glifo + palavra).
9. A campanha criada nasce `PAUSED` e a tela diz por quê.
10. Nenhuma tela mostra métrica de performance.


---

# 10. O QUE EXISTE HOJE — 18/08/2026, fim do dia

Escrito depois de construir. Tudo abaixo foi executado, não planejado.

## Engine (`volc_ads/`)

| peça | estado | prova |
|---|---|---|
| `pautador_ponte.py` | **construído** | 33/33 · `python -m volc_ads.testes_pautador_ponte` |
| `campanha/search.py` — N ad groups por sub-intenção | **construído** | 29/29 pytest |
| `campanha/brief.py` — `SubIntencao`, `keywords` XOR `sub_intencoes` | **construído** | idem |
| `policy/spec.py` ligado no lugar de `validacao.py` | **construído** | idem |
| `subir.py` + `isencao.py` | **construído, NUNCA EXECUTADO** | 22/22 com dublê · trava fechada ao fim |
| `copy/cliente.py` + `copy/render.py` | **construído** | 14/14 · `python -m volc_ads.copy.testes_cliente` |
| SDK `google-ads` | instalado no `backend/.venv` (31.3.0) | `campanha.search` importa |

⚠️ Os testes se chamam `testes_*.py` e o pytest não os coleta por padrão:
```bash
backend/.venv/bin/python -m pytest volc_ads/ -q --override-ini="python_files=testes_*.py test_*.py"
```
Dois deles (`testes_pautador_ponte`, `testes_subir`) são módulos executáveis no
estilo do `copy/provar.py`, não pytest.

## Backend (`backend/app/`)

```
GET  /api/trafego/quadro                    funis publicados + cluster
GET  /api/trafego/candidatos/{opp_id}        o cockpit (inclui `conta`, derivada)
POST /api/trafego/provar                     monta o Brief + os 3 juízes
POST /api/trafego/subir                      o caminho de escrita
GET  /api/trafego/trava                      estado da trava, antes de tentar
POST /api/trafego/copy                       o estágio 3 — a cascata escreve
GET  /api/trafego/escopo                     a árvore da casa, pronta p/ a tela
GET  /api/trafego/contas?mcc=…               descobre contas sob um MCC (diagnóstico)
GET  /api/trafego/projetos                   projetos e a conta de cada um
PUT  /api/trafego/projetos/{id}/conta        vincula (escreve em `projects`)
DEL  /api/trafego/projetos/{id}/conta        desfaz o vínculo
```

`app/trafego/projecao.py` traduz os objetos do `volc_ads` para a tela — e é onde
mora a invariante **nenhum CPC sai sem procedência**.
`app/trafego/contas.py` é a descoberta de contas (leitura pura).

## O PORTÃO DA CASA — `app/trafego/escopo.py`

Medido em 18/08/2026: a credencial alcança **39 contas anunciáveis distintas sob
9 MCCs**, e **3 são da VOLC**. O resto é de cliente (IESDE, Colégio Positivo, os
MCCs pessoais). Um seletor com 39 linhas transforma "vincular na conta errada"
num clique cuja consequência só aparece no `subir`, dentro de outra empresa.

O portão é o MCC `6016739364`, constante no código — **não** lido do ambiente:
`backend/.env` traz `GOOGLE_ADS_LOGIN_CUSTOMER_ID=8696453882`, que é "Projetos
Fla&Fe" (17 contas de terceiro), e um `.env` editado moveria a fronteira sem
rastro em revisão.

Duas camadas, a segunda medida com `contas.detalhe()` sempre sob o MCC da casa:

| conta pedida | veredito |
|---|---|
| `8017851692` Crédito Up — filha do MCC | passou |
| `5838529870` IESDE — outro MCC | `USER_PERMISSION_DENIED` |
| `8552871761` Colégio Positivo — acesso DIRETO da credencial | `USER_PERMISSION_DENIED` |

Forçar o `login_customer_id` faz o próprio Google recusar — inclusive conta que
a credencial alcança sozinha. Por isso o portão não guarda lista nem cache.

⚠️ Ele **não vive na tela**: `customer_id` viaja no corpo de `/provar` e de
`/subir`, e as duas recusam com **403**. Em `/subir` a conferência é a cara
(`conta_da_casa`, ~1,6 s) porque é o único caminho que cria recurso.
`/api/trafego/contas` é a única rota fora do portão — é o diagnóstico que mediu
o problema, e não leva a operação nenhuma. A linha é entre OLHAR e OPERAR.

## O ESTÁGIO 3 — ligado em 18/08/2026

`volc_ads/copy/encomendar.py` traduz `pautador_ponte.Cockpit` para
`render.Encomenda` e roda `ciclo.gerar()`. Medido no card 73, com LLM real:

| medida | valor |
|---|---|
| tempo | **174,19 s** · 2 rodadas de conjunto, 0 de asset |
| tokens | 29.078 entrada · 34.315 saída |
| custo | **`null`** — `VOLC_ADS_PRECO_ENTRADA_MI`/`_SAIDA_MI` não configurados |
| fatos | 6 usados, **4 descartados** |

⚠️ **O tipo de fato do Pautador não é o do prompt.** Dos 6 fatos que o cockpit
devolve, 4 têm `tipo: "afirmacao"` e a seção 2 do `PROMPT.md` só conhece
`numero, prazo, data, mudanca, condicao, orgao, fonte_legal, processo`. Eles são
descartados **e relatados** — remapear seria escolher o que o texto afirma. O
conserto de verdade é o Pautador emitir tipos do inventário.

⚠️ **O juiz do Google é NULO nesta rota, de propósito.** `/provar` julga a mesma
copy dentro do payload inteiro uma linha depois, e a cascata roda até 8 rodadas.

⚠️ **O vocabulário divergia e o desligamento era SILENCIOSO.** A cascata produz
`title/description1/description2` e `values`; o router lia `texto/descricao1/
descricao2/valores`. Toda copy gerada chegaria com **sitelinks e snippet
vazios**, sem exceção — `.get("texto","")` devolve `""` e o Brief aceita. O
engine passou a ter precedência; os nomes em português continuam aceitos.

Testes: `backend/tests/test_trafego.py`, **28 passando** (eram 14).

## Front (`src/`)

| rota | estado |
|---|---|
| `/trafego` | quadro com os funis prontos |
| `/trafego/nova/:opportunityId` | **refeito 18/08/2026** — trilho fixo, 4 cartões, copy no estágio 3, e a ignição |
| `/settings/integrations` | duas abas; **Google Ads é a padrão** — é para cá que o cockpit manda |
| `/trafego/campanha/:id` | **não existe** |

`components/trafego/ReguaDeLeilao.tsx` é o elemento assinatura.
`components/trafego/ListaDeKeywords.tsx` carrega a barra de volume por linha.
`components/settings/google-ads/PainelGoogleAds.tsx` + `hooks/useContasGoogleAds.ts`
são a aba: faixa de escopo, um cartão por projeto, seletor embutido na linha.
Smoke de render em `__tests__/painel-google-ads.test.tsx`, 3 passando — existe
pelo mesmo motivo do smoke do wizard: `tsc` limpo não impede tela branca.

⚠️ `pautadorApi.ts` traduzia **todo** 403 em "confira VITE_PAUTADOR_API_KEY".
Isso engolia a mensagem do portão e mandava o operador mexer na chave certa
procurando um defeito que estava noutro lugar. Agora 403 **com** `detail` mostra
o `detail`; a hipótese da chave ficou para 401 e para 403 sem corpo.

## A CONTA NÃO É MAIS DIGITADA

As colunas `google_ads_customer_id` e `google_ads_manager_id` **já existiam** em
`projects` e estavam vazias. O cockpit deriva por
`pautador_funnel_runs.project_id` → `projects`.

Vinculado e testado ao vivo: **projeto 2 (creditoup.com.br) → `8017851692` via
MCC `6016739364`**. A credencial alcança 12 contas; sob o MCC VOLC há três
anunciáveis (Crédito Up, PMUNDO+, Portal Mundo Mais).

## O QUE FALTA, EM ORDEM

0. ~~A aba Integrações~~ — **entregue em 18/08/2026.** Não há "cadastrar MCC":
   medido, resolver os 12 ids acessíveis em árvore nomeada custa 2,03 s com 6
   threads, então a tela descobre em vez de perguntar. O que sobrou:
   `portalmundomais.com` (projeto 1) segue **sem conta vinculada** — há duas
   candidatas de nome quase igual (`PMUNDO+` e `Portal Mundo Mais`) e a escolha
   é do operador, na tela.
1. ~~O estágio 3 (copy)~~ — **entregue em 18/08/2026**, ver acima. Era ELE que
   mantinha o botão de subir apagado, não a trava: sem headlines a prova
   reprovava sempre.

   O que sobrou dele: `custo_usd` sai `null` porque
   `VOLC_ADS_PRECO_ENTRADA_MI`/`_SAIDA_MI` não estão configurados. Configurar é
   uma linha no `.env` e passa a haver custo medido por lançamento.
2. **`customer.auto_tagging_enabled` é lido mas não consumido.** `contas.detalhe()`
   já o traz; `marcacao.py` precisa dele para a checagem de `marcacao_gclid`
   deixar de depender de um booleano declarado no brief. Medido em 18/08/2026:
   na Crédito Up (`8017851692`) ele vale **`True`** — ou seja, um brief que
   declarasse `marcacao_gclid=True` deveria ser recusado, e hoje não é.
3. `/trafego/campanha/:id` — o que subiu e o veredito de política.
4. **O verificador adversarial nunca rodou.** O workflow que construiu o engine
   foi parado antes da fase 3. Oito classes de defeito seguem sem varredura
   independente: número inventado em comentário, trava violada, escrita no
   Supabase, blocklist ressuscitada, válvula de escape em portão, colisão de id
   temporário, campo de API adivinhado, atomicidade quebrada.

## O QUE NUNCA FOI EXERCITADO

**`subir.py` jamais rodou com a trava aberta.** Por instrução, desde o início.
A rota recusa corretamente com 409 e a mensagem do `EscritaBloqueada` — isso
está testado. O caminho de escrita em si, não.

A campanha nasce `PAUSED` (`comum.py`), então o primeiro disparo custa zero e já
devolve o veredito real de política do Google sobre recurso persistido — a única
coisa que `validate_only` não dá.
