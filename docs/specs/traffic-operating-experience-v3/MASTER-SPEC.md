# MASTER-SPEC — VOLC Traffic Operating Experience v3

> **Estado:** **15 de 15 artefatos existem.** Veredito em `§9`.
> **Nada foi implementado.** Nenhuma mutação externa foi feita.
> Este documento carrega as travas e o veredito; a prova de cada afirmação está no artefato que a nomeia.
> **Base factual:** `207e91f1da290130e8d02b78c3ba1c8e9a761111` (ancestral de `origin/volc-os-v2`)
> **Linha oficial no momento desta redação:** `origin/volc-os-v2 @ 3331c0c5d63e31e0d068786707c75169231bdad7`
> **Branch:** `sprint/fable-traffic-operating-experience-spec-v3` (worktree isolada)
> **Escopo:** somente documentação em `docs/specs/traffic-operating-experience-v3/`

Este arquivo é a porta de entrada e o contrato de decisões. Ele **não repete** a prova: cada afirmação aponta para o arquivo que a carrega.

| # | Arquivo | O que carrega |
|---|---|---|
| 1 | `MASTER-SPEC.md` | este arquivo: porta de entrada, travas, limites e veredito |
| 2 | `CURRENT-STATE-AUDIT.md` | o retrato medido do que existe, com `arquivo:linha`, e a comparação com `sprint/traffic-operating-cockpit-v2` |
| 3 | `EXPERIENCE-ARCHITECTURE.md` | a topologia, as seis paradas, o Pedido, rotas e estado na URL |
| 4 | `END-TO-END-FLOWS.md` | Search, Display, Demand Gen e Performance Max do início ao fim, com bifurcações e bloqueios |
| 5 | `SCREEN-CONTRACTS.md` | cada superfície: conteúdo, ação dominante, estados, teclado, mobile |
| 6 | `DATA-AND-AUTHORITY-MAP.md` | elemento visual → campo → endpoint → dono → frescor → ausência → ação |
| 7 | `CHANNEL-CAPABILITY-MATRIX.json` | 4 canais × 4 portões, com causa, origem e próximo desbloqueio — legível por máquina |
| 8 | `STATE-MATRIX.md` | os dezesseis estados transversais e o que cada superfície faz em cada um |
| 9 | `VISUAL-DIRECTION.md` | registro `impeccable shape`, auditoria anti-slop, tipografia, superfície, cor |
| 10 | `MOTION-AND-INTERACTION.md` | gramática de movimento, microinterações, teclado, foco, movimento reduzido |
| 11 | `RESPONSIVE-AND-A11Y.md` | contrato em 320/375/414/768/1280/1440/1920 e o alvo WCAG 2.2 AA |
| 12 | `IMPLEMENTATION-SLICES.md` | as fatias A–K, com contraprova vermelha, gates, rollback e risco de conflito |
| 13 | `EXECUTOR-ACCEPTANCE.md` | as contraprovas executáveis e a Definition of Done |
| 14 | `DECISION-LOG.md` | o que foi decidido, o que foi recusado, as correções e as questões em aberto |
| 15 | `CURATION-HANDOFF.json` | **apenas o delta proposto** de curadoria — não aplicado |

**Como ler as citações.** `arquivo:linha` sem sufixo é a base `207e91f`. O sufixo **`@85666da`** marca um blob da sprint `traffic-operating-cockpit-v2`, que **não está integrada nesta base** e cujos arquivos **não existem no disco** — leia com `git show 85666da:<caminho>`. Caminhos sob `src/components/trafego/bancada/` são **propostos**, não existentes.

---

## 1. O problema, dito uma vez

O VOLC O.S. construiu, ao longo de meses, uma quantidade incomum de inteligência sobre compra de tráfego: elegibilidade de keyword com ausência preservada, portão de destino pago com cinco perguntas distintas, sete portões de mensuração, ledger com quatro desfechos que não se colapsam, sentinela com dezesseis estados em ordem causal, matriz de capacidade por canal derivada do manifesto do servidor.

**Quase nada disso chega ao operador no momento em que ele decide gastar.**

A superfície onde o dinheiro passa a ser possível — `/trafego/nova/:opportunityId` — é uma coluna de 1.014 linhas com **dezoito** blocos empilhados, sem ordem obrigatória, com a elegibilidade de lançamento montada no navegador, **duas** definições de "copy pronta" espalhadas por quatro sítios, o canal literal no código, e 235 ocorrências de texto a 11 pixels.

A sprint anterior (`sprint/traffic-operating-cockpit-v2 @ 85666dad16460846eb4077d4c8ff4e98c7bed961`) não tocou nessa superfície: `git diff` sobre `NovaCampanhaPage.tsx` entre a base e aquele commit imprime **0 bytes**, e o blob é literalmente o mesmo objeto nos dois commits. O que ela entregou de visível foi uma lista informativa de treze etapas com `respostas: {}` fixo, montada numa aba de leitura, descrevendo um fluxo que nenhuma tela executa.

**Esta especificação existe para reconstruir aquela superfície e as que a cercam.**

---

## 2. O resultado que o produto precisa entregar

Um operador que lança poucas vezes por semana, não memoriza nada, e está prestes a gastar dinheiro real, precisa conseguir, sem reler documentação:

1. Ver o que existe e o que está gastando.
2. Ver o que pode virar campanha, e o que cada canal permite **agora**.
3. Conferir o destino pago antes de qualquer trabalho.
4. Declarar a política sob a qual o anúncio será julgado.
5. Revisar os termos, as correspondências e as exclusões.
6. Produzir o anúncio.
7. Decidir como a campanha nasce e quanto ela pode custar — **de verdade**, não pelo número que ele digitou.
8. Conferir o pedido inteiro numa tela.
9. Provar contra a conta real sem criar nada.
10. Aprovar, criar **pausada**, e ler o recibo.
11. Acompanhar as primeiras 72 horas e receber alerta acionável quando a entrega não acontece.

E, em dez segundos na frente da tela, responder: **o que estou criando, em qual conta, para qual destino, quanto pode gastar, o que está bloqueado, e qual é o próximo ato.**

---

## 3. A resposta: a Bancada Guiada

**Topologia:** híbrida, decidida em `EXPERIENCE-ARCHITECTURE.md §3`.

- Uma **coluna de decisão** larga, uma parada por vez, com a evidência daquela decisão ao lado dela.
- Um **mapa de seis paradas** fixo no topo — um mapa com estado, não um wizard e não uma terceira linguagem de aba.
- Um **Pedido persistente** que acumula o que será criado, com fonte e frescor em cada linha, e o **teto real de gasto** — que é `2× o orçamento diário`, e que a tela hoje não diz.
- Uma **Ignição** em tela cheia para prova, aprovação e criação: a única superfície teatral do produto, preservada por mérito.
- Um **Recibo** com superfície própria e retornável, porque recibo dentro de modal é recibo que não se volta a ler.

**As seis paradas:** Destino · Política · Termos · Anúncio · Economia · Revisão.

Não são treze porque cinco das treze são degraus da ignição e duas já vêm respondidas. Não são quatro porque o trilho atual esconde a decisão mais consequente da tela ("conta e lance") e deixa o portão de política solto entre cartões. A ordem não é estética: Destino primeiro porque é o único que para tudo sem gastar nada; Política antes de Anúncio porque a copy é escrita e provada sob a vertical.

**A regra que governa o desenho inteiro:** a tela **não decide**. Ela lê o veredito, mostra a evidência, oferece a ação permitida e nomeia quem recusou. Cada afirmação da interface aponta para o campo do servidor que a sustenta — `DATA-AND-AUTHORITY-MAP.md`.

---

## 4. Princípios, e o que cada um proíbe

| # | Princípio | Proíbe |
|---|---|---|
| 1 | **Verdade antes de decoração** | número sem frescor; ausência desenhada como zero; lista vazia lida como "tudo certo" |
| 2 | **Consequência antes da ação** | botão que gasta antes da tela explicar escopo, reversibilidade e aprovação |
| 3 | **Um ato dominante por momento** | duas ações primárias na mesma região; treze decisões numa rolagem |
| 4 | **O servidor decide, a tela mostra** | elegibilidade montada no navegador; severidade classificada por texto; falha de leitura virando permissão |
| 5 | **Ausência é conteúdo** | seção que some quando não há dado; `—` sem dizer quem não foi lido |
| 6 | **Capacidade ausente não vira botão morto** | simetria falsa entre canais; formulário para canal sem construtor |
| 7 | **Identidade na borda** | aurora atrás de tabela, número, alerta ou progresso |
| 8 | **Densidade com ar** | uma pergunta por viewport numa mesa que compara 23 termos |
| 9 | **Movimento comunica estado** | fase fictícia; progresso por tempo; teatro de carregamento em página operacional |

---

## 5. As dezesseis travas que a implementação não pode romper

Cada uma tem prova no repositório e contraprova exigida em `EXECUTOR-ACCEPTANCE.md`.

1. **Toda criação nasce pausada.** `campaign.status` não tem default seguro: a API cria `ENABLED` quando o campo é omitido (`docs/growth-engine/matriz-api/search.md:53-54`).
2. **`validate_only`, criação e ativação são três atos.** Nunca um botão.
3. **Ativação não existe neste sistema.** Não há rota (`grep -rn '"/ativar' backend/` → 0). O portão `ativavel` está `BLOQUEADO` em **4 de 4 canais para as 4 identidades testadas — 16 células**, e a função não tem ramo que produza outro estado (`contrato_canais.py:974-1016`). A tela diz isso com essas palavras e não oferece controle.
4. **O conjunto positivo de keywords que vai para a conta é exatamente o aprovado.** O corpo HTTP não amplia autoridade.
5. **Nenhuma ausência vira zero.** `null` é "ninguém leu"; `0` só quando a consulta voltou zero.
6. **Nenhuma falha de leitura vira permissão.** Falha fecha.
7. **O frontend não recalcula autoridade do backend.**
8. **Search, Display, Demand Gen e Performance Max têm jornadas honestamente distintas** — derivadas do manifesto, não de `if (canal === …)`. São **quatro** canais no contrato de portões; Video e Shopping existem só na gramática do frontend, e a assimetria é declarada no próprio tipo.
9. **Capacidade ausente é escada de portões com causa e origem**, nunca formulário nem botão cinza. As origens são **oito**: `construtor`, `manifesto`, `servidor`, `operador`, `politica`, `mensuracao`, `observabilidade`, `produto`.
10. **A campanha Performance Max não pode expandir para URL fora do destino aprovado** — e o que existe e o que não existe para garantir isso está em `END-TO-END-FLOWS.md §4.1`. ⚠️ `Campaign.url_expansion_opt_out` **não existe na v25** (provado por introspecção do proto em `docs/closure/traffic-creative-operational-closure-v1/verificacao/REVISAO-GEMINI-CONTRATOS.md:74`); o controle real é `asset_automation_settings` — 12 pares, com dependência que gera erro se invertida — mais critério `webpage` negativo, que **não pode excluir a final URL do próprio asset group**.
11. **Não existe loader de fases fictícias.** `POST /provar` é uma requisição sem subfases observáveis.
12. **`prefers-reduced-motion` é respeitado**, e movimento funcional sobrevive.
13. **Sem rolagem horizontal de página** em 320, 375, 414, 768, 1440 e 1920.
14. **Todo alvo interativo tem ao menos 40×40px** (44 no toque).
15. **Nenhum texto que sustenta decisão abaixo de 14px**; nada abaixo de 12px.
16. **A bancada de QA não entra no bundle de produção.** ⚠️ **Correção:** `scripts/gate_bancada_fora_do_bundle.py` **não existe nesta base** — foi criado pela sprint `85666da`, junto de `src/pages/qa/BancadaVisual.tsx`, e não há rota `/qa/trafego/*` em `App.tsx`. Os gates que existem aqui são `src/components/trafego/laboratorio/__tests__/projection.test.ts:82-97` (isolamento do laboratório) e `src/lib/__tests__/seguranca-bundle.test.ts` (segredo no bundle). Se a bancada for reintroduzida, o gate vem junto.

---

## 6. O que muda, superfície por superfície

| Superfície | Veredito | Ver |
|---|---|---|
| `/trafego/nova/:opportunityId` | **reconstruída** — é o objeto desta missão | `EXPERIENCE-ARCHITECTURE`, `SCREEN-CONTRACTS` |
| Ignição (`Lancamento.tsx`) | **preservada e refinada** — a escada de degraus e o horizonte guiado por estado são o melhor que o produto tem; caem o `.reveal` por degrau, o piso de 10–11px e o texto a `white/35` | `SCREEN-CONTRACTS §Ignição` |
| Recibo | **promovido** de estado de modal a região retornável | `SCREEN-CONTRACTS §Recibo` |
| `/trafego?aba=criar` | **reduzida a antessala de canal**: quatro portões, ação dominante, próximo desbloqueio. Sai a prévia de treze etapas | `END-TO-END-FLOWS` |
| `/trafego?aba=canais` | **absorvida** pela antessala. Hoje são dois renderizadores que **discordam de cor** para o mesmo veredito — `canais/PortoesDoCanal.tsx:55-79` (âmbar, sem fundo) × `canais/PainelDaMensuracao.tsx:67-74` (rosa, com fundo) — e é a **única das cinco abas sem guarda de rede** | `CURRENT-STATE-AUDIT` |
| `/trafego?aba=preparar` | mantida; ganha o estado do portão de destino na linha | `SCREEN-CONTRACTS` |
| `/trafego?aba=campanhas` | mantida; volta às abas segmentadas do contrato | `VISUAL-DIRECTION §2` |
| `/trafego/campanhas/:id` | ordem das oito seções mantida; Guardião 72h vira faixa própria — **declarando que é classificação de janela, não processo** | `SCREEN-CONTRACTS §15` |
| `/settings/campaigns` | **fora de escopo, e nomeado como dívida** — segunda lista com botões próprios de pausar/ativar escrevendo direto no Supabase | `IMPLEMENTATION-SLICES §fora de escopo` |

---

## 7. Método, e os limites desta investigação

**O que foi feito**
- Worktree isolada em `207e91f`; **nenhum arquivo tocado fora de `docs/specs/traffic-operating-experience-v3/`**, verificado por `git status --porcelain` no fechamento.
- **Reconstrução da evidência a partir do código**, em 14 eixos paralelos, cada um seguido de uma **passada adversarial de refutação** que abriu os arquivos nas linhas citadas e conferiu trecho a trecho. Nenhuma afirmação desta spec depende de scratchpad efêmero: cada uma aponta para `arquivo:linha` no repositório, e cada ausência tem o comando de busca que voltou vazio.
- **Uma rodada corretiva focal**, aplicada a partir dos relatórios de refutação. Ela mudou conteúdo material — a tabela de desfechos do ledger, a contagem de blocos do cockpit, a definição de "copy pronta", o limiar responsivo do Pedido, a procedência de Video e Shopping — e está registrada em `DECISION-LOG.md §3` e `§9.1`.
- **Validação mecânica**: presença dos 15 artefatos, validade dos 2 JSONs, integridade dos 114 links internos entre artefatos, e resolução de 781 de 823 citações `arquivo:linha` (as 42 restantes são ausências deliberadas, arquivos propostos ou blobs `@85666da`, todos declarados).
- Leitura integral das autoridades: `AGENTS.md`, `CLAUDE.md`, `PRODUCT.md`, `design.md`.
- Leitura das skills obrigatórias antes de qualquer conclusão de desenho: `impeccable` (SKILL + `shape` + `product` + `critique` + `heuristics-scoring` + `cognitive-load` + `interaction-design` + `motion-design` + `responsive-design` + `ux-writing` + `layout`), `hallmark` (SKILL + `verbs/audit` + `anti-patterns` + `motion` + `microinteractions` + `interaction-and-states`), `make-interfaces-feel-better` (SKILL + `surfaces` + `animations` + `typography` + `performance`), `redesign-existing-projects`, `design-taste-frontend`, `ui-ux-pro-max`.
- Investigação paralela sobre a base, com relatórios citando `arquivo:linha`, cobrindo rotas, autoridade, observação, mensuração, destino pago, elegibilidade de keyword, componentes do cockpit, Hub, CSS/tokens, testes, motor por canal e docs de produto.
- Análise separada de `sprint/traffic-operating-cockpit-v2 @ 85666da`, **sem integrar** e sem checkout: leitura por `git log`, `git diff` e `git show`.
- Ambiente local isolado: Vite servido de dentro da worktree, com `.env` apontando para `127.0.0.1:1` em Supabase, API e Pautador — nenhuma chamada externa possível.

**O que NÃO foi observado, e é uma limitação real**
- **As rotas autenticadas não foram vistas em navegador nesta missão.** O ambiente isolado, por construção fail-closed, faz `ProtectedRoute` redirecionar tudo para `/login`; as capturas de `/`, `/trafego` e `/trafego/nova/73` terminam todas em `/login`. O que existe de captura é: a tela de login em 1440 e 375, claro e escuro (produzida agora), e as capturas de bancada de fixtures da sprint anterior, que exercitam apenas `JornadaDoCanal` e `ConversaDeCriacao`.
- Consequência: **o diagnóstico visual desta spec é de código, não de tela renderizada autenticada.** É por isso que `EXECUTOR-ACCEPTANCE.md` exige do executor capturas das rotas reais com sessão, e condiciona a aprovação final à inspeção humana dessas capturas.

**Frescor do Mapa Vivo — declarado, e corrigido**

⚠️ `graphify-out/` **não existe nesta worktree**, e a ausência é **esperada, não regressão**: o diretório inteiro é gitignorado (`.gitignore:72-79`). Rodar `--check` aqui devolveria exatamente `{"current": false, "reason": "UPDATE_STATUS.json ausente"}` com exit 1, por caminho explícito no gerador (`scripts/atualizar_grafo_volc_os.py:185-188`). Qualquer leitura de grafo feita durante a missão foi na **cópia principal** do repositório, que está em outra linha de commits.

O que **pôde** ser verificado nesta base: o grafo gerado está em **sincronia perfeita** com a curadoria humana — os 233 nós e 412 arestas curados aparecem integralmente no snapshot, com zero ausências nos dois sentidos. O que está defasado é a camada técnica/viva, com `snapshot_date` de 22/08/2026 contra `curadoria_atualizada_em` de 03/09/2026.

**O grafo foi consultado como pista e não como autoridade; nenhuma afirmação desta spec depende dele.** O grafo **não foi reconstruído** — a missão proíbe.

**Movimento da base — remedido no fechamento**

`origin/volc-os-v2` avançou de `207e91f` para `3331c0c` (11 commits) durante a missão. A medição foi **refeita no fechamento**, com `fetch` somente de leitura, e o resultado é o mesmo:

| Verificação | Resultado |
|---|---|
| `git rev-parse origin/volc-os-v2` | `3331c0c5d63e31e0d068786707c75169231bdad7` |
| `git merge-base --is-ancestor 207e91f origin/volc-os-v2` | verdadeiro — a base é ancestral da linha oficial |
| `git rev-list --count 207e91f..3331c0c` | `11` |
| `git diff --name-only 207e91f 3331c0c \| grep -iE 'trafego\|traffic\|google_ads\|campanha\|cockpit'` | **vazio** |
| Mesma faixa, filtrada em `docs/volc-os-graph/`, `volc-os-workbook/ROADMAP-VIVO.json`, `docs/architecture/` por termos de tráfego | **vazio** |

Os 11 commits são inteiramente do domínio **Pautador / Validação Psicológica v2**: `backend/app/validacao/oportunidade.py`, seis suítes de teste novas, `src/components/pautador-pro/entity/**`, `src/types/pautadorOportunidade.ts`, `docs/closure/pautador-psychological-validation-v2/**`, e as atualizações de grafo/roadmap que essa lane produziu.

**Conclusão registrada:** não há mudança material nova no domínio de tráfego entre a base e a linha oficial. A base `207e91f` fica preservada como **snapshot factual válido** desta superfície, e nenhuma reconciliação documental foi necessária. Nenhum rebase, merge ou transplante de base foi executado — a missão proíbe.

**Autoria**
A missão especificou Fable 5.1 como writer. A sessão foi trocada pelo usuário para **Opus 5** durante a execução, e é Opus 5 quem escreve estes artefatos. Registrado para que nenhuma leitura futura atribua a autoria errada.

**Base — remedida no fechamento**
`git fetch` somente de leitura. `origin/volc-os-v2` está em `3331c0c`, 11 commits à frente da base, e `207e91f` é **ancestral** dela. A interseção dos 11 commits com o domínio de tráfego é **vazia** — os commits são inteiramente da lane Pautador / Validação Psicológica v2. A base fica preservada como **snapshot factual válido**, e nenhuma reconciliação documental foi necessária. Detalhe abaixo.

**Probes visuais**
Este harness **não tem geração de imagem nativa**. As três direções foram entregues como wireframes semânticos e diagramas de composição em `SCREEN-CONTRACTS.md §Probes`, cobrindo escolha de canal, uma parada de Search, um estado bloqueado, a revisão antes da prova e o recibo de campanha criada pausada.

**Revisão multimodelo**
Codex respondeu e revisou (`DECISION-LOG.md §revisão cruzada`). Gemini **não está disponível** nesta máquina: `gemini -p` responde `Please set an Auth method in your /Users/mac/.gemini/settings.json or specify one of the following environment variables … GEMINI_API_KEY, GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_GENAI_USE_GCA`. A missão proíbe instalar ou consertar harness, então fica registrado literalmente: **CROSS_PROVIDER_REVIEW_NOT_AVAILABLE** (Gemini).

---

## 8. O que esta spec NÃO afirma

- Não afirma que o cockpit está implementado. **Nada foi implementado.**
- Não afirma que qualquer canal além de Search pode criar campanha real.
- Não afirma que Performance Max pode ser criado — ele planeja, e a retenção é decisão de produto registrada.
- Não afirma que a ativação existirá.
- Não afirma que qualquer tarefa do Roadmap está `done`. `CURATION-HANDOFF.json` propõe delta e **não aplica**.
- Não afirma que o redesign foi aceito. A escolha de direção está sujeita a aprovação humana antes de qualquer implementação.
- Não afirma nada sobre o estado ao vivo de nenhuma conta do Google Ads. Nenhuma chamada foi feita.
- Não afirma conformidade WCAG 2.2 AA. Nenhum leitor de tela foi executado; AA é **alvo**, não estado.
- Não afirma que ler `status = ENABLED` prova entrega — `serving_status` e `primary_status` são *Output only*.
- Não afirma que `validate_only` garante a criação: **não existe lista oficial exaustiva do que ele deixa passar**, e a matriz proíbe preencher por memória.
- Não afirma que a campanha criada está sendo observada. O coletor contínuo não alcança PAUSED, e o espelho teve zero linhas para a campanha canário.
- Não afirma que a Google Ads API impede criar campanha de Video ou Shopping: essa verificação **não existe** na `matriz-api`. O que se afirma é sobre o **VOLC**.

---

## 9. Veredito

```
TRAFFIC_OPERATING_EXPERIENCE_V3_SPEC_READY_FOR_HUMAN_REVIEW
```

**Com uma ressalva que o leitor precisa ler antes de qualquer outra coisa:** a revisão independente encontrou um **bloqueio de produto**, e ele está no artefato — não escondido no rodapé.

### 9.1 🔴 O bloqueio, dito primeiro

**O fluxo Search não é executável hoje, e a causa não é de interface.**

`/provar` recusa antes da rede quando o conjunto pago não está aprovado (`portao_conjunto_pago.py:158-163`, `NAO_APROVADO`). E **nada no sistema aprova**: `approved_set_sha256` só é atribuído dentro de `paid_eligibility.aprovar()` (`:1179`), que **não tem chamador de produção**, e `funnel_factory.py:387-391` persiste o conjunto sem aprovar.

Nenhuma fatia de interface conserta isso. A fatia **A0** existe para fechá-lo, **três desenhos possíveis estão nomeados**, e a escolha é **de produto, não desta lane**. `B` a `I` dependem dela.

Esta spec **descreve corretamente** o sistema — inclusive esta lacuna. O que ela não pode fazer é prometer que Search chega ao fim antes de A0.

### 9.2 O que o veredito afirma, e o que não afirma

**Afirma:** os 15 artefatos existem; a evidência foi reconstruída do código e submetida a duas passadas independentes de refutação — uma interna, de 14 eixos, e uma cruzada por Codex; os 12 achados do Codex foram **todos aceitos e corrigidos**; e **a implementação não foi iniciada**.

**Não afirma:** não é aprovação da direção de design; não é conformidade WCAG; não autoriza implementação; e **não afirma que o produto entrega o que a spec descreve** — `§9.1` é a prova de que não entrega ainda.

### 9.3 As condições, verificadas

| # | Condição | Resultado |
|---|---|---|
| 1 | 15 de 15 artefatos existem | ✅ |
| 2 | todo link interno resolve | ✅ 119 referências, zero quebradas |
| 3 | todo JSON é válido | ✅ 2 de 2 |
| 4 | citações `arquivo:linha` resolvem | ✅ 789 de 831; as 42 restantes são ausências deliberadas, arquivos propostos ou blobs `@85666da`, todas declaradas |
| 5 | revisão independente adjudicada no código | ✅ interna (13 relatórios de refutação) **e** cruzada por Codex (**REPROVADO**, 12 achados, **12 corrigidos** — `DECISION-LOG.md §9.1b`) |
| 6 | uma rodada corretiva focal | ✅ uma, sobre os achados do Codex |
| 7 | limitações declaradas | ✅ `§7`, `EXECUTOR-ACCEPTANCE.md §5` |
| 8 | zero implementação | ✅ `git diff-index --quiet HEAD` → árvore rastreada **idêntica** a `207e91f` |
| 9 | zero mutação externa | ✅ só um `git fetch` de leitura |
| 10 | escopo da árvore | ✅ apenas `?? docs/specs/traffic-operating-experience-v3/` |

### 9.4 O que mudou por causa da revisão cruzada

O Codex devolveu **REPROVADO**. Os doze achados foram abertos no código, **nenhum foi refutado**, e a rodada corretiva mudou coisas materiais:

- criou a fatia **A0** e reordenou o grafo de dependências;
- reescreveu **A2**, que prometia "duas expressões" e exigia mudar modelo, projeção e tipos;
- criou **A1b**, porque `bloqueado`/`bloqueios` são globais e não dizem a parada dona;
- corrigiu uma **contradição interna real** no limiar de 1440px — a própria tabela media ~1056px ali, abaixo do mínimo que ela mesma exigia;
- dividiu **J** em três fatias com rollbacks distintos;
- **removeu duas exceções** que a spec se autoconcedia contra `design.md`;
- **decidiu** a persistência em vez de deixar a escolha binária para o executor.

Uma spec que sobrevive a `REPROVADO` sem mudar não foi revisada. Esta mudou.

### 9.5 Ao executor, em três frases

1. **A0 primeiro, e ela é decisão de produto.** Sem o ciclo de aprovação do conjunto, nada de B a I é demonstrável.
2. **Depois A1, A1b e A2** — as três tiram do navegador a autoridade que o servidor já tem ou deveria emitir.
3. **Nenhuma fatia é aceita visualmente sem captura autenticada.** Esta spec não pôde produzi-las, e `EXECUTOR-ACCEPTANCE.md §3.14` as exige.

### 9.6 A recomendação, dita uma vez

Tirando A0, que é de produto, as correções de maior efeito são as mais baratas: a projeção do cockpit **emitir o veredito que o servidor já calcula**; a ponte **parar de coagir ausência a zero**, que ressuscita três ramos de honestidade que a tela já escreveu; o campo motivo **nascer vazio**, que faz três guardas de dez caracteres deixarem de nascer satisfeitas; e o Recibo **oferecer o ato de reconciliar** que o produto já manda o operador executar em texto, sem botão.

Nenhuma delas é um redesign. Todas são a diferença entre uma interface que diz a verdade e uma que apenas parece dizer.
