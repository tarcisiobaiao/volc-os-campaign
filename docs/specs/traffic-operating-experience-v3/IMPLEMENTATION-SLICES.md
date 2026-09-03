# IMPLEMENTATION-SLICES — a sequência atômica de execução

Base factual: `207e91f`. **Nada aqui foi implementado.**

**A regra que governa o arquivo:** nenhuma fatia é grande o bastante para ser irreversível, e nenhuma entra sem **contraprova vermelha antes** — um teste que falha pelo motivo certo hoje e passa depois. Uma fatia que não sabe como falhar não sabe o que entrega.

---

## 0. Os gates reais deste repositório

Citados por nome, com a armadilha de cada um. Toda fatia referencia esta tabela.

| Gate | Comando | Armadilha registrada |
|---|---|---|
| tipos | `npx tsc --noEmit -p tsconfig.app.json` | ⚠️ `npx tsc --noEmit` **puro não checa nada** — o `tsconfig.json` da raiz é solution-style (`"files": []`), e sem `-p` o compilador roda sobre **zero arquivos** e sai 0 (`CLAUDE.md`). E `TS2688` de pastas `@types/* 2` duplicadas **para a checagem semântica antes** dela começar |
| ratchet de tipos | `python3 scripts/gate_tsc_ratchet.py` | mede e compara: passa enquanto o número **não piora**. `BASELINE_ERROS` é medição, não meta — subi-lo para passar é desligar o gate com passos extras |
| unidade/DOM | `npm test` (`vitest run`) | baseline da sprint anterior: **1.513 passed / 6 skipped** |
| backend | `bash scripts/gates-backend.sh` | ⚠️ `pytest` direto dá **três resultados diferentes** e nenhum avisa: sem `PYTHONPATH` falha em `volc_ads`; sem `-p no:randomly` duas falhas ficam intermitentes; venv errado roda 716/744. **Use o script** |
| build | `npm run build` | ⚠️ **não pega erro de tipo** — esbuild não checa tipos |
| lint | `npm run lint` | — |
| sem mutação Google | `python3 scripts/gate_sem_mutacao_google.py` | — |
| ledger v10.03 | `python3 scripts/gate_provar_ledger_v10_03.py` | — |
| agenda única GAds | `python3 scripts/gate_agenda_unica_gads.py` | — |
| vitest do lançamento | `python3 scripts/gate_vitest_lancamento.py` | — |
| isolamento do laboratório | `npm test -- projection` | `projection.test.ts:82-97` |
| segredo no bundle | `npm test -- seguranca-bundle` | — |

⚠️ **Falha herdada esperada.** `GATES.md:21-25` da sprint anterior registra uma falha de pytest que **reproduz na árvore intocada no SHA da base** — logo, esperada também aqui. Ela **não** é regressão desta lane, e nenhuma fatia deve "consertá-la" de passagem.

---

## 1. O grafo de dependências

```
A0 (aprovação do conjunto) ──► A (contratos de servidor) ──► tudo o mais
```

🔴 **A0 é pré-requisito de todo o resto.** Sem ela, `/provar` termina em 409 e nenhuma fatia de B a I é demonstrável.

```
A (contratos de servidor)  ─┬─► B (fundação da Bancada) ─┬─► C (Destino+Política)
                            │                            ├─► D (Termos)
                            │                            ├─► E (Anúncio)
                            │                            └─► F (Economia+teto)
                            │                                     │
                            └─────────────────────────────────────┴─► G (Revisão+Pedido)
                                                                        │
                                                                        ▼
                                                         H (Ignição) ─► I (Recibo+reconciliação)
                                                                        │
J (multicanal) ◄────────────────────────────────────────────────────────┘
K (hardening) — atravessa todas, e fecha
```

**Regra de sequência:** C, D, E e F são **independentes entre si** e podem ser feitas em qualquer ordem, ou em paralelo por pessoas diferentes. Tudo o mais é sequencial.

---

## A0 · 🔴 O ciclo de aprovação do conjunto pago

**Objetivo.** Fazer existir o estado que o portão exige. **Sem esta fatia, nada abaixo é demonstrável.**

| Campo | Valor |
|---|---|
| **O bloqueio** | `portao_conjunto_pago.py:158-163` recusa com `NAO_APROVADO` quando `conjunto.approved_set_sha256` é falsy — **antes de qualquer rede** |
| **Por que ele nunca é satisfeito** | `approved_set_sha256` só é atribuído em `paid_eligibility.py:1179`, dentro de `aprovar()`, ou reidratado de dicionário em `:883`. **`aprovar()` não tem chamador de produção.** E `funnel_factory.py:387-391` persiste o conjunto **sem aprovar** |
| **Arquivos** | `backend/app/agents/mining/paid_eligibility.py`, `funnel_factory.py`; uma rota nova em `backend/app/routers/`; superfície de aprovação no front |
| **Autoridade** | servidor — e a aprovação é **ato humano**: `aprovar()` exige `aprovado_por` e `hash_conferido`, e a docstring diz que o hash "é o que impede aprovar uma tela e exportar outra coisa" |
| **Dependências** | nenhuma |
| **Contraprova vermelha** | teste que percorre o caminho normal — minerar → persistir → `/provar` — e exige **200**. Hoje falha com **409 `NAO_APROVADO`**, que é exatamente o motivo certo |
| **Implementação mínima** | ⚠️ **não é decidível por esta lane.** São três desenhos possíveis, com custos e donos diferentes: (a) aprovação explícita numa superfície de curadoria de keywords, com `aprovado_por` do token; (b) aprovação implícita no momento em que o operador confirma a parada Termos; (c) aprovação no `funnel_factory`, tornando a mineração autoaprovada — **que anula o portão**. A opção (c) é desaconselhada aqui: o portão existe para separar "lista minerada" de "conjunto de campanha", e autoaprovar apaga a distinção |
| **Gates** | `gates-backend.sh` |
| **Rollback** | a rota e a superfície saem; o portão volta a recusar |
| **Integração** | **antes de tudo** |
| **Risco de conflito** | **alto** — toca o motor de mineração |

**Dono:** produto decide o desenho; servidor implementa. Está em `DECISION-LOG.md §8 Q5`, promovida a **bloqueante**.

---

## A · Contratos de servidor faltantes

**Objetivo.** Tirar do navegador a autoridade que o servidor já tem, e emitir o que ele já calcula.

**Por que primeiro.** Cinco das oito derivações de navegador de `DATA-AND-AUTHORITY-MAP.md §8` só saem se A existir. Fazer B antes de A significa construir a Bancada sobre a mesma mentira.

### A1 · `projecao.cockpit` serializa `bloqueado` e `bloqueios`

| Campo | Valor |
|---|---|
| **Arquivos** | `backend/app/trafego/projecao.py:157-177`; `src/types/trafego.ts` (o tipo `Cockpit`) |
| **Autoridade** | servidor |
| **Dependências** | nenhuma. `volc_ads/pautador_ponte.py:266-272` **já calcula** |
| **Contraprova vermelha** | teste que chama a projeção com um cockpit cujo `avisos` tem `severidade == 'bloqueio'` e exige `resultado["bloqueado"] is True` e `len(resultado["bloqueios"]) == 1`. Hoje falha com `KeyError` |
| **Implementação mínima** | duas chaves no dict de retorno. Não mexer na regra de severidade |
| ⚠️ **O que A1 NÃO resolve** | `bloqueado`/`bloqueios` são **globais**. Cada aviso carrega `codigo`, `severidade`, `titulo` e `detalhe` (`pautador_ponte.py:125-137`) e **não diz a que parada pertence**. Sem isso, transformar um bloqueio global nos seis estados de parada exigiria o cliente inventar uma tabela `codigo → parada` — que é exatamente a derivação que A1 existe para eliminar. **A1 precisa de A1b** |
| **Gates** | `gates-backend.sh`; `tsc -p tsconfig.app.json` |
| **Evidência visual** | nenhuma — é contrato |
| **Rollback** | remover as duas chaves; nenhum consumidor obrigatório ainda |
| **Integração** | pode entrar sozinha, sem tocar em nada do front |
| **Risco de conflito** | **baixo.** É a dependência M1 que a sprint anterior nomeou como o próximo ato de maior valor e não fez |

⚠️ **Decisão embutida.** Servidor e cliente hoje **discordam**: o servidor barra só em `severidade == 'bloqueio'`; o cliente barra em tudo que não for `informacao`/`atencao`. A1 **não** resolve isso — ela **expõe** a regra do servidor. Qual das duas vale é decisão de produto, registrada em `DECISION-LOG.md §D9`.

### A1b · O servidor declara a parada dona de cada bloqueio

| Campo | Valor |
|---|---|
| **Arquivos** | `volc_ads/pautador_ponte.py` (o aviso ganha um campo), `backend/app/trafego/projecao.py`, `src/types/trafego.ts` |
| **Contraprova vermelha** | teste que exige, para cada aviso, um campo `parada` dentro de um vocabulário fechado de seis. Hoje `KeyError` |
| **Implementação mínima** | um campo por aviso. O mapeamento `codigo → parada` vive **no servidor**, onde o código é emitido |
| **Alternativa declarada** | se o servidor não puder mapear, a regra alternativa é **explícita e única**: um bloqueio global fecha **a parada Revisão**, e só ela — nunca as seis. A tela **não** distribui bloqueios por adivinhação |
| **Risco de conflito** | baixo |

Sem A1b **ou** a regra alternativa, o mapa de paradas volta a derivar estado no navegador.

### A2 · A ponte para de coagir ausência a zero

| Campo | Valor |
|---|---|
| **Arquivos** | `volc_ads/pautador_ponte.py:451-456` (`_cpc`), `:505-506` (volume) |
| **Autoridade** | servidor |
| **Contraprova vermelha** | teste que monta um cockpit com `volume=None` e `cpc=None` e exige que a projeção devolva `None` nos dois. Hoje devolve `0` e `0.0` |
| **Implementação mínima** | ⚠️ **NÃO são "duas expressões".** Remover `or 0.0` faz `float(None)` cair no `except`, que **continua atribuindo `0.0`**; remover `or 0` faz `int(None)` levantar `TypeError`. E os modelos são **não-anuláveis**: `Cpc.valor` e `KeywordCandidata.volume` em `pautador_ponte.py:115-145`, e `volume: number` em `src/types/trafego.ts:23-36`. A fatia é: **(1)** tornar os dois campos `Optional` no dataclass; **(2)** trocar coerção por `None` explícito, sem `except` que reintroduza zero; **(3)** propagar `\| null` na projeção e no tipo TS. O front não muda — os ramos de ausência já existem e hoje são código morto |
| **Gates** | `gates-backend.sh`; `npm test` |
| **Evidência visual** | captura da mesa com um termo sem volume medido, mostrando "volume não medido" em vez de `0` |
| **Rollback** | reverter os dois `or` |
| **Integração** | sozinha |
| **Risco de conflito** | **médio** — a ponte é compartilhada. Confirmar que nenhum consumidor faz aritmética assumindo número |

**É a fatia de maior razão efeito/custo do plano inteiro:** duas expressões, e três ramos de honestidade que a tela já escreveu passam a executar.

### A3 · Carimbo de frescor na resposta do cockpit

| Campo | Valor |
|---|---|
| **Arquivos** | `backend/app/trafego/projecao.py:157-177`; `volc_ads/pautador_ponte.py` |
| **Contraprova vermelha** | teste que exige `lido_em` na resposta. Hoje `KeyError` — nem o servidor emite |
| **Implementação mínima** | um instante ISO-8601 |
| **Gates** | `gates-backend.sh` |
| **Rollback** | remover a chave |
| **Risco de conflito** | baixo |

Sem A3, a Bancada carimba **"sem carimbo de leitura"** — e não inventa relógio local.

### A4 · `spec.py` fecha por ausência

| Campo | Valor |
|---|---|
| **Arquivos** | `volc_ads/policy/spec.py:163-168` |
| **Contraprova vermelha** | teste com vertical fora da matriz exigindo **violação de indeterminação**, não lista vazia |
| **Implementação mínima** | alinhar com `landing_policy/contrato.py:455-464`, onde código não classificado **bloqueia** |
| **Gates** | `gates-backend.sh` |
| **Risco de conflito** | **médio** — muda comportamento de política. Confirmar com o dono antes |

### A5 · `GET /canais` passa `prontidao_por_canal` e `prontidao_pmax`

| Campo | Valor |
|---|---|
| **Arquivos** | `backend/app/routers/trafego.py:5512-5516` |
| **Contraprova vermelha** | teste que exige `medicao.lida is True` para um canal com leitura disponível. Hoje é **sempre `false`** |
| **Custo** | **médio** — exige leitura viva, e é a única fatia de A que gasta rede |
| **Risco de conflito** | médio |

⚠️ **Não é pré-requisito de nada.** Sem A5, a antessala diz "não se sabe" — que é a verdade de hoje.

### A6 · `response_model` nos handlers de tráfego

Opcional, e recomendada. `grep -rn 'response_model' backend/app/routers/trafego.py trafego_inventario.py` → **0**. O único do eixo está em `trafego_diagnostico.py:51`. Sem contrato tipado de saída, o executor programa contra dicionários montados à mão.

**Fora de A, e deliberadamente:** rota de ativação; rota de recibos; agenda do coletor que alcança PAUSED. As três estão em `DATA-AND-AUTHORITY-MAP.md §9` com dono, e **nenhuma é desta lane**.

---

## B · Fundação da Bancada

**Objetivo.** A moldura: rota, estado na URL, mapa de paradas, Pedido, e a coluna de decisão vazia.

| Campo | Valor |
|---|---|
| **Arquivos** | `src/pages/trafego/NovaCampanhaPage.tsx` (reescrita), novos em `src/components/trafego/bancada/` |
| **Autoridade** | servidor para estado de parada (via A1); navegador para navegação |
| **Dependências** | **A1** (senão o mapa continua derivado no navegador) |
| **Contraprova vermelha** | (a) teste que abre `?etapa=termos` e exige a parada Termos aberta — hoje o parâmetro não existe; (b) teste que recarrega e exige a mesma parada; (c) teste que exige que `bloqueado` venha do payload e **não** de contagem local |
| **Implementação mínima** | rota com `?canal=` e `?etapa=`; mapa `<nav><ol>` com `aria-current="step"`; Pedido como projeção; **nenhuma parada implementada ainda** |
| **Gates** | `tsc -p`; `npm test`; `npm run lint`; `gate_tsc_ratchet.py` |
| **Evidência visual** | capturas em 375/768/1440/1920, claro e escuro, com o mapa e o Pedido vazios |
| **Rollback** | a rota antiga permanece atrás de flag até B passar no aceite |
| **Integração** | **não remover `NovaCampanhaPage` antiga até G** |
| **Risco de conflito** | **alto** — é o arquivo mais tocado do módulo. Fazer B em uma passada, sem intercalar C–F |

**Sai nesta fatia:** `.reveal` de `/trafego/nova` (8 aplicações), `.card-volc` (7), `backdrop-blur` da barra fixa, o Trilho de 4 âncoras, o componente morto `Campo` (`:987-995`), e o `Esqueleto` genérico (`:997-1012`) — que hoje mostra 3 cartões para uma tela de 4 mais barra, faixa e painel.

---

## C · Destino e Política

| Campo | Valor |
|---|---|
| **Arquivos** | `src/components/trafego/bancada/paradas/Destino.tsx`, `bancada/paradas/Politica.tsx`; `src/components/trafego/PortaoDePolitica.tsx`; `src/components/landing-policy/PainelDoDestinoPago.tsx` |
| **Autoridade** | servidor |
| **Dependências** | B; **A4** para o ponto 4 de política |
| **Contraprova vermelha** | **quatro**, uma por ponto de ausência-vira-permissão: (1) vertical fora da lista exige `INDETERMINADO`, não nota verde; (2) falha da rota de verticais exige **erro visível**, não painel escondido; (3) veredito de política **entra** nas pendências; (4) `live_verified` **não** pode ser `true` quando `live_drift` saiu `not_applicable` |
| **Implementação mínima** | duas paradas; ligar a prop `reauditoria` (existe e **nenhum chamador a passa**) |
| **Gates** | `npm test`; `gates-backend.sh` (para A4) |
| **Evidência visual** | capturas dos 5 estados do portão + o estado indeterminado com o ato de reauditar |
| **Rollback** | por parada |
| **Risco de conflito** | **médio** — `landing-policy` é compartilhado com o Redator |

⚠️ **Um achado que C precisa resolver e que não é de tela:** `limitacao` significa coisas **opostas** nos dois lados. `PortaoDePolitica.tsx:159-165` escreve que a campanha **sobe**; `volc_ads/campanha/conteudo.py:56, 266-269` põe `limitacao` na lista de severidades que **barram**. Adjudicar antes de escrever a parada.

E: duas das quatro verticais reais (`saude`, `jogos_azar`) **não têm o campo `nota`** em `spec.json`, e a rota preenche `descricao` com `regra.get("nota", "")` (`trafego.py:320`) — a descrição sai vazia e o componente não a renderiza.

---

## D · Termos

| Campo | Valor |
|---|---|
| **Arquivos** | `bancada/paradas/Termos.tsx`; `MesaDeCriterios.tsx`; `ListaDeKeywords.tsx`; `ReguaDeLeilao.tsx` |
| **Autoridade** | servidor para elegibilidade e conjunto; operador para correspondência e exclusões |
| **Dependências** | B; **A2** (senão os ramos de ausência continuam mortos) |
| **Contraprova vermelha** | (a) termo com `volume: null` renderiza "volume não medido", não `0`; (b) o pedido **não** carrega positivas; (c) a régua com todos os CPCs zero **diz por quê** em vez de sumir; (d) bloco da régua alcançável por teclado |
| **Implementação mínima** | mesa + exclusões + régua; render de `cockpit.procedencia.aviso` e `cockpit.descartadas` (hoje nunca lidos) |
| **Gates** | `npm test` — ⚠️ **não existe teste para `ReguaDeLeilao` nem `ListaDeKeywords`**; D cria os primeiros |
| **Evidência visual** | mesa em 768/1440/1920 + a lista em 375 com o aviso de desktop |
| **Rollback** | por componente |
| **Risco de conflito** | médio |

**A frase que muda nesta fatia.** Sai *"o que você vê é o que vai para o Google"* (`MesaDeCriterios.tsx:497-501`). Entra: *"o conjunto positivo é o aprovado na mineração. Aqui você define correspondência e exclusões."* Porque em `/provar` a `Escolha` é montada com `keywords_por_grupo(<conjunto aprovado>)` (`trafego.py:2977-2981`) — **a marcação do operador não entra na conta.**

⚠️ **Achado de servidor que D expõe e não resolve:** nada no sistema **aprova** o conjunto pago que o portão exige — `funnel_factory.py:391` grava sem aprovar e `paid_eligibility.py:1166-1181` tem função de aprovação **sem chamador**. O portão pode recusar por um estado que nenhum caminho produz. Vai para `CURATION-HANDOFF.json` como tarefa nova.

---

## E · Anúncio

| Campo | Valor |
|---|---|
| **Arquivos** | `bancada/paradas/Anuncio.tsx`; `CartaoCopy.tsx` |
| **Dependências** | B, D (a copy ancora nos termos) |
| **Contraprova vermelha** | (a) **uma** definição de "copy pronta" — teste que exige o mesmo veredito nos quatro sítios de hoje; (b) `perdida` é estado próprio com ato de reescrever; (c) o botão desabilitado expõe **as duas** razões |
| **Implementação mínima** | uma parada; unificar a definição; exibir `atualizado_em` (hoje só `criado_em` aparece) |
| **Gates** | `npm test` (existem `cartao-copy-real` e `cartao-copy-vocabulario`) |
| **Rollback** | por parada |
| **Risco de conflito** | baixo |

⚠️ **Trava dura a respeitar:** `AdGroupAd.ad` é **Immutable** (`search.md:66, 73-75`). A parada **não** oferece "editar anúncio publicado" — oferece *substituir e aposentar*, e diz o que fica no histórico.

E `copyDesatualizada` compara **só os textos** das keywords ordenados (`:221-225`): mudança de match type ou negativa nova **não** marca a copy como desatualizada. Ou o critério cresce, ou a tela declara o que ele cobre.

---

## F · Economia e teto

| Campo | Valor |
|---|---|
| **Arquivos** | `bancada/paradas/Economia.tsx`; `MesaDeLance.tsx`; `canais/PainelDaMensuracao.tsx` |
| **Autoridade** | servidor para os 7 portões; operador para lance/orçamento; **navegador para o teto do dia**, sob as 5 condições de `DATA-AND-AUTHORITY-MAP.md §6.2` |
| **Dependências** | B |
| **Contraprova vermelha** | (a) `"10,50"` no orçamento chega ao pedido como `10.5`, não `0`; (b) o teto do dia aparece **sem** carimbo de frescor e **com** as três ressalvas; (c) o teto **não** aparece para campanha existente; (d) os 7 portões renderizam com `PARCIAL` em amarelo, não verde; (e) toda leitura de custo diz **"servido"** |
| **Implementação mínima** | trazer `PainelDaMensuracao` para cá; uma função de parse de dinheiro; o bloco de teto |
| **Gates** | `npm test` (existe `mesa-de-lance`) |
| **Evidência visual** | o bloco de teto com as três ressalvas visíveis, não em tooltip |
| **Rollback** | por bloco |
| **Risco de conflito** | médio |

**Três frases que mudam nesta fatia:**

1. A graduação **para** de dizer que o "motor de gestão" a executa (`MesaDeLance.tsx:219-223`). `graduacao_em_conversoes` é aceito pelo modelo HTTP e **nunca lido, persistido ou executado**. Passa a: *"registrada como intenção. Nenhum processo deste sistema a executa hoje."*
2. ⚠️ As constantes de dinheiro são **BRL fixas enquanto a moeda é da conta**: `TETO_CPC_BRL = 0.5` e `PISO_VERBA_GRADUACAO = 30` são comparados com os números digitados **sem conversão**, e o prefixo cai para `'R$ '` (`MesaDeLance.tsx:51-70`). Ou converte, ou declara que a régua é BRL.
3. As três estratégias sem caminho de escolha (`TARGET_CPA`, `MAXIMIZE_CONVERSION_VALUE`, `TARGET_ROAS`) **não** ganham controle — a tela declara que a casa opera com duas. ⚠️ E existem **quatro** conjuntos fechados divergentes de estratégia no repositório (front 2, `dominio` 2, `prontidao` 5, brief); F não os unifica, mas **declara** qual está usando.

---

## G · Revisão, Pedido e a troca da rota

| Campo | Valor |
|---|---|
| **Arquivos** | `bancada/paradas/Revisao.tsx`; `bancada/Pedido.tsx`; `src/App.tsx` |
| **Dependências** | B–F, **A1** |
| **Contraprova vermelha** | (a) `FALTA` vem do servidor — teste que injeta `bloqueios` e exige que a lista os reflita **sem** somar item local; (b) a rota antiga **não** é mais alcançável; (c) o Pedido não mostra número medido sem frescor |
| **Implementação mínima** | a parada 6 + o Pedido completo; remover a página antiga |
| **Gates** | todos |
| **Evidência visual** | o Pedido em coluna (≥1100px de conteúdo) e em digest+gaveta |
| **Rollback** | **o ponto de não retorno.** Rollback = reverter G inteira e voltar a rota antiga |
| **Risco de conflito** | **alto** — toca `App.tsx` |

---

## H · Ignição

| Campo | Valor |
|---|---|
| **Arquivos** | `src/components/trafego/Lancamento.tsx` |
| **Dependências** | G |
| **Contraprova vermelha** | **oito**: (1) foco preso no diálogo; (2) `Esc` durante `escrevendo` **diz por que não fecha**; (3) o botão de fechar é **desabilitado**, não desmontado; (4) o degrau `copy` **reprova** quando não há copy; (5) o campo motivo nasce **vazio**; (6) o horizonte **não recua** numa reprovação; (7) `indeterminado` e `escrevendo` têm valores distintos; (8) todo texto ≥14px e todo `text-white/NN` ≥ AA |
| **Implementação mínima** | portal + `inert` + armadilha de foco; `aria-live` na escada; `role="alert"` no erro; `useMemo` no pedido; cronômetro só enquanto há chamada |
| **Gates** | `npm test`; `gate_vitest_lancamento.py`; `gate_sem_mutacao_google.py` |
| **Evidência visual** | os 10 estados, claro e escuro, **e em `prefers-reduced-motion`** |
| **Rollback** | a Ignição é isolada — reverter o arquivo |
| **Risco de conflito** | baixo |

**Preservar sem tocar:** o portão de destino nos dois pontos; as três travas (com o campo vazio); recusa × indeterminação com saídas opostas.

---

## I · Recibo e reconciliação

| Campo | Valor |
|---|---|
| **Arquivos** | `bancada/Recibo.tsx`; `recibos/CartaoDeRecibo.tsx`; `src/lib/pautadorApi.ts`; `src/types/trafego.ts` |
| **Autoridade** | servidor |
| **Dependências** | H |
| **Contraprova vermelha** | (a) o recibo **sobrevive** ao fechamento da Ignição; (b) o estado `indeterminado` renderiza o **botão** de reconciliar; (c) **nenhum** caminho oferece reenviar; (d) o request id é **copiável e completo**, não `truncate` mudo; (e) `marca` chega ao cliente |
| **Implementação mínima** | região com `id="recibo"`; unir os campos das duas superfícies (`motivo`, `impressao`, `estado`, `explicacao`); `reconciliarLancamento()` em `pautadorApi.ts` |
| **Gates** | `npm test` (existe `recibo.test.ts`); `gates-backend.sh` |
| **Evidência visual** | os quatro desfechos, e o `indeterminado` com o ato |
| **Rollback** | o botão de reconciliar sai; o recibo permanece |
| **Risco de conflito** | baixo |

⚠️ **Três bloqueios que I encontra e não resolve sozinha:**

| # | Bloqueio | Dono |
|---|---|---|
| 1 | `SubidaIndeterminada` (`types/trafego.ts:799-805`) **não declara `marca`** — a chave do caminho alternativo de `/reconciliar`. **I corrige o tipo**; é a única parte que é dela |
| 2 | `POST /reconciliar` exige **`exigir_admin`** (`trafego.py:4445`) enquanto o resto exige `exigir_usuario`. **O operador não pode fechar o próprio recibo.** Decisão de produto — vai para o handoff |
| 3 | **não existe caixa de entrada de recibos abertos.** Quem perder o `item_id` perde a saída. Tarefa nova |

Enquanto 2 e 3 estiverem abertos, a tela mostra o ato **e diz quem pode executá-lo**.

---

## J · Multicanal — **três fatias, não uma**

⚠️ **Correção:** a redação anterior agregava quatro mudanças independentes (autoridade, navegação, tokens e estrutura do Hub) sobre seis arquivos que somam ~3.690 linhas, com rollbacks diferentes. "Rollback por componente" era a admissão de que não havia unidade reversível. Fica dividida:

| Fatia | Objetivo | Contraprova única | Rollback |
|---|---|---|---|
| **J1 · autoridade** | tirar `cruzar()` do navegador e iterar a lista de canais do servidor | remover um canal de `/canais` ⇒ ele **some da tela**; varredura: `cruzar()` não existe mais | reverter `canal/jornada.ts` |
| **J2 · um renderizador de portão** | consolidar `PortoesDoCanal` e `PainelDaMensuracao` num só, com um tom por veredito | `BLOQUEADO` tem **um** tom em toda a superfície | reverter os dois componentes |
| **J3 · tokens e abas do Hub** | zero paleta crua nas superfícies de canal; Hub de 5 para 4 abas, segmentadas | varredura de paleta crua = 0; `<TabsList>` do Hub usa o primitivo | reverter `HubDeTrafegoPage` e `canais/*` |

J1 → J2 → J3, nesta ordem: J2 depende do vocabulário que J1 fixa, e J3 é cosmética sobre o que J1 e J2 deixaram.

| Campo | Valor (comum às três) |
|---|---|
| **Arquivos** | `canais/PainelDeCanais.tsx`, `PortoesDoCanal.tsx`, `PainelDaMensuracao.tsx`; `canal/jornada.ts`; `estudio/*`; `HubDeTrafegoPage.tsx` |
| **Autoridade** | servidor |
| **Dependências** | G |
| **Contraprova vermelha** | (a) `cruzar()` **não existe mais** — varredura de código; (b) a antessala itera a resposta de `/canais` e um canal removido do servidor **some da tela**; (c) `BLOQUEADO` tem **um** tom em toda a superfície; (d) zero classes de paleta crua nos três arquivos; (e) a aba `canais` não existe mais |
| **Implementação mínima** | um renderizador de portão; a antessala; Hub de 5 para 4 abas; abas segmentadas |
| **Gates** | `npm test`; `tsc -p`; varredura de paleta crua |
| **Evidência visual** | os 4 canais, cada um com sua escada, claro e escuro |
| **Rollback** | por componente; a aba `canais` volta se preciso |
| **Risco de conflito** | **alto** — o Hub é compartilhado |

**A dívida concentrada:** **216** ocorrências de paleta crua em **6 arquivos**, e `PainelDeCanais.tsx` sozinho responde por cerca de metade. É uma fatia, não uma varredura.

⚠️ **J não pode dar CTA de Bancada a canal que não cria.** Enquanto `NovaCampanhaPage` montar pedido com `canal: 'SEARCH'` literal (`:414`), o CTA "Preparar por Search" é o comportamento correto.

---

## K · Hardening, responsivo, a11y e QA visual

Atravessa todas. **Não é uma fatia final que conserta o que as outras deixaram** — é o gate de cada uma. O que fica para K é só o que só faz sentido no conjunto.

| Item | Contraprova |
|---|---|
| tipografia | `text-[9px]`, `text-[10px]`, `text-[11px]` = **0** nas superfícies desta spec |
| faixa lateral | `border-l-2` **colorida** = 0 (as 5 neutras permanecem) |
| movimento | `.reveal`, `.card-volc`, `backdrop-blur` = 0; `transition-all` continua em 0 |
| paleta | zero cor crua nas superfícies desta spec |
| uppercase | só em `.kicker` |
| responsivo | sem rolagem horizontal de página em 320/375/414/768/1280/1440/1920 |
| a11y | todo `disabled` com `aria-describedby` para texto **visível**; alvos medidos no retângulo renderizado, **não** pela presença de `.touch-target` |
| contraste | calculado sobre os tokens, nos dois temas |
| reduzido | captura em `prefers-reduced-motion` de cada parada |
| bundle | `npm test -- seguranca-bundle`; `npm test -- projection` |
| tipos | `gate_tsc_ratchet.py` **não piora** |

⚠️ **K não pode ser o único lugar onde a a11y aparece.** Cada fatia de B a J entrega suas próprias contraprovas de foco, nome acessível e estado — K só confere o conjunto.

---

## 2. Fora de escopo, e nomeado

| Item | Por quê | Dono |
|---|---|---|
| `/settings/campaigns` (`App.tsx:105`) | segunda lista de campanhas com botões próprios de pausar/ativar. Enquanto existir, **duas telas podem discordar** sobre se uma campanha está rodando. **Dívida nomeada**, não item deste redesign | produto |
| `/dashboard/campaign/:campaignId` (`:101`) | terceira superfície sobre o mesmo objeto | produto |
| rota de ativação | não existe, e **não deve ser criada por esta lane** | produto |
| agenda do coletor que alcança PAUSED | exige decidir a autoridade de agenda, nunca escolhida (`alvo.py:19-23`) | plataforma |
| unificar os 4 conjuntos de estratégia de lance | atravessa engine, backend e front | arquitetura |
| `GET .../recibos` | rota nova | servidor |
| a falha herdada de pytest | reproduz na árvore intocada da base | — |

---

## 3. O que nenhuma fatia pode fazer

1. **Nenhuma mega-implementação sem checkpoint.** Cada fatia entra com contraprova vermelha antes e gates depois.
2. **Nenhuma fatia mistura reorganização estrutural ampla com mudança funcional ampla** (`CLAUDE.md`): preserve a capacidade de provar equivalência e reverter.
3. **Nenhuma fatia marca tarefa do Roadmap como `done`.** A lane emite delta em `CURATION-HANDOFF.json`; o integrador aplica.
4. **Nenhuma fatia toca `docs/volc-os-graph/curadoria-operacional.json` nem `volc-os-workbook/ROADMAP-VIVO.json`.**
5. **Nenhuma fatia faz chamada real ao Google Ads** sem a trava de dois fatores e sem estar dentro da janela do canário.
6. **Nenhuma fatia declara conformidade WCAG** sem teste com tecnologia assistiva.
