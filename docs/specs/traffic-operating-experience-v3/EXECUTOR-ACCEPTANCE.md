# EXECUTOR-ACCEPTANCE — contraprovas executáveis e a Definition of Done

Base factual: `207e91f`.

**A regra que governa o arquivo:** uma contraprova só vale se souber **falhar pelo motivo certo**. Um teste que passa hoje e passaria também com o defeito presente não prova nada — foi assim que a rodada anterior de outro módulo "provou" uma mutação apagando uma linha e obtendo `1 error`, que era `SyntaxError` (`scripts/provar-mutacao-bancada.py:1-16`).

---

## 1. Os três tipos de teste, e o que cada um não cobre

| Tipo | Pergunta | **Não** responde |
|---|---|---|
| **mecanismo** | a regra está escrita e é executada? | se a regra é a certa |
| **resultado** | dado este insumo, sai este veredito? | se a tela mostra o veredito |
| **visual** | a tela renderizada mostra isso? | se o dado é verdadeiro |

Uma trava só está fechada quando tem os **três**. Cada contraprova abaixo declara qual é.

---

## 2. As dezesseis travas — contraprova por trava

### T1 · Toda criação nasce pausada

| | |
|---|---|
| **Fato** | `campaign.status` não tem default seguro: a API cria `ENABLED` quando o campo é omitido (`docs/growth-engine/matriz-api/search.md:53-54`; replicado em `display.md:70`) |
| **Mecanismo** | AST sobre `volc_ads/campanha/comum.py` exigindo a atribuição literal `camp.status = …PAUSED` (`:207`). Falha vermelha: trocar por `ENABLED` e a suíte reprova por **asserção**, não por erro de coleta |
| **Resultado** | `SubirEntrada` **não tem campo de status** — teste que envia `{"status": "ENABLED"}` e exige que o modelo o ignore ou rejeite |
| **Visual** | captura do recibo com a palavra **"criada, pausada"** |
| **Prova hoje** | `test_trafego_ledger.py:9-16` já trava que a campanha nasce PAUSED no payload que de fato sai |

⚠️ Complemento obrigatório: `campaign.status` é o **único** dos três campos de estado que é gravável; `serving_status` e `primary_status` são *Output only* (`comum.md:338-344`). **Ler `status = ENABLED` não prova entrega**, e nenhum teste pode usar isso como prova.

### T2 · `validate_only`, criação e ativação são três atos

| | |
|---|---|
| **Mecanismo** | varredura que exige que nenhum componente chame `/provar` e `/subir` no mesmo manipulador |
| **Resultado** | `/provar` devolve `ativacao_incluida: false` (`trafego.py:3182`) — teste de resposta |
| **Visual** | a Ignição mostra os degraus como atos distintos, com a prova antes da aprovação |

### T3 · Ativação não existe

| | |
|---|---|
| **Mecanismo** | `grep -rn '"/ativar\|/despausar' backend/ api/ src/` → **0**; teste que falha se aparecer |
| **Resultado** | `ativavel` é `BLOQUEADO` em **4 de 4 canais para as 4 identidades testadas** — 16 células (`test_trafego_contrato_canais.py:230-236`) |
| **Visual** | a antessala mostra o portão fechado **com as quatro razões e suas quatro origens**, e **nenhum controle** |

### T4 · O conjunto positivo é exatamente o aprovado

| | |
|---|---|
| **Mecanismo** | as três guardas de `portao_conjunto_pago.py:352-364`, a terceira uma pós-condição por **multiconjunto** (`Counter`, não `set`) sobre o brief final; e o teste que **lê o código-fonte da rota** exigindo cada guarda **antes** da chamada de rede (`test_pautador_campaign_birth_wiring.py:512-518, 528-536`) |
| **Resultado** | positiva vinda do corpo é recusada **fechada, não filtrada** (`:259-272`), com código estável no 409 |
| **Visual** | a mesa **não** promete que a seleção vai para o Google |

⚠️ **E a contraprova nova que esta spec acrescenta:** teste que envia positivas em `criterios` e exige **409 com `POSITIVA_DO_CORPO`** — e que a Bancada **nunca** as envie. Hoje ela envia (`NovaCampanhaPage.tsx:367-381, 413`).

### T5 · Nenhuma ausência vira zero

| | |
|---|---|
| **Mecanismo** | `Sinal(0.0, AUSENTE)` **levanta exceção** (`paid_eligibility.py:107-109, 120-121`) |
| **Resultado** | teste sobre a ponte exigindo que `volume=None` e `cpc=None` **atravessem** — hoje `pautador_ponte.py:451-456, 505-506` coage a zero e o teste falha vermelho pelo motivo certo |
| **Visual** | captura da mesa com "volume não medido", e da régua dizendo por que sumiu quando todos os CPCs são zero |
| **Prova hoje** | `canais.test.ts:138-152` trava que `null` vira traço e nunca `0`, e que `0` medido continua `0` |

### T6 · Nenhuma falha de leitura vira permissão

| | |
|---|---|
| **Mecanismo** | `prontidao.ts:400-407` — `status_wp` nulo → `INDETERMINADO`; `tomDaProntidao` (`:182-187`) só a string exata `'APTO'` sai `provado` |
| **Resultado** | `paid_destination_ready` exige papel estrito **E** zero bloqueios **E** zero desconhecidos — e há teste com **desconhecido e zero bloqueios**, o único caso em que os dois divergem (`test_barreira3_destino_de_campanha.py:541-556`) |
| **Visual** | captura do estado indeterminado, com o ato de reauditar |

⚠️ **Quatro contraprovas novas**, uma por ponto de ausência-vira-permissão:

| # | Contraprova | Hoje |
|---|---|---|
| 1 | vertical fora da matriz → `INDETERMINADO`, e a parada **não avança** | nota **verde** (`PortaoDePolitica.tsx:167-172`) |
| 2 | falha de `/politica/verticais` → **erro visível**, parada bloqueada | painel **escondido** sem erro (`NovaCampanhaPage.tsx:155, 702`) |
| 3 | veredito de política **entra** nas pendências | nunca entra (`:332-343`) |
| 4 | vertical desconhecida no servidor → **violação**, não lista vazia | lista vazia (`spec.py:163-168`) |
| 5 | `live_verified` **não** é `true` quando `live_drift` saiu `not_applicable` | é (`recibo.py:160-163`, `contrato.py:73`) |

### T7 · O frontend não recalcula autoridade do backend

| | |
|---|---|
| **Mecanismo** | varredura que reprova, nas superfícies desta spec: `podeLancar` derivado; `cruzar()`; qualquer reimplementação de severidade |
| **Resultado** | teste que injeta `bloqueado: true` no payload e exige a parada bloqueada **sem** contagem local |
| **Visual** | captura com um bloqueio do servidor e a parada fechada |

**A lista fechada do que sai do navegador** está em `DATA-AND-AUTHORITY-MAP.md §8`. A contraprova é uma por item.

### T8 · Jornadas honestamente distintas, derivadas do manifesto

| | |
|---|---|
| **Mecanismo** | varredura que reprova `if (canal === …)` nas superfícies desta spec |
| **Resultado** | teste que remove um canal da resposta de `/canais` e exige que ele **suma da tela** — hoje a bancada monta sobre **6 canais fixos do frontend** (`jornada.ts:879`) |
| **Visual** | os 4 canais, cada um com sua escada |

⚠️ E a autoridade de quem cria e quem prova mora no engine: **2 canais sabem criar** (SEARCH, DISPLAY) e **3 sabem provar** (`volc_ads/subir.py:122-133`). O manifesto é conferido contra eles por teste (`test_trafego_canal_de_criacao.py:821-830`, por árvore sintática, para não depender do SDK instalado).

### T9 · Capacidade ausente é escada de portões, nunca formulário nem botão cinza

| | |
|---|---|
| **Mecanismo** | varredura: todo `disabled` nas superfícies desta spec tem `aria-describedby` apontando para texto **visível** |
| **Resultado** | manifesto `null` ≠ `capacidades: []` — invariante já travado (`capacidades.test.ts:29-44`) |
| **Visual** | captura de cada canal bloqueado, com causa, origem e próximo desbloqueio |

⚠️ **Contraprova nova:** o botão "Criar campanha pausada" é hoje **cinza e mudo** — `disabled` por duas condições e **nenhum texto diz qual falta** (`Lancamento.tsx:561-565`). E abaixo de 640px o botão principal do cockpit fica desabilitado **sem razão nenhuma** (`NovaCampanhaPage.tsx:469-479`), e no ramo `jaLancou` a razão não aparece **em nenhuma largura** (`:454-466`).

### T10 · PMax não expande para fora do destino aprovado

| | |
|---|---|
| **Fato** | ⚠️ `Campaign.url_expansion_opt_out` **não existe na v25** — provado por introspecção do proto (`docs/closure/traffic-creative-operational-closure-v1/verificacao/REVISAO-GEMINI-CONTRATOS.md:74`) e declarado em `docs/architecture/HANDOFF-PMAX-OBSERVABILITY-V25.md:13-16` |
| **Mecanismo** | varredura que reprova qualquer menção ao campo inexistente em código novo |
| **Resultado** | quando PMax passar de `planejavel`, o controle é `asset_automation_settings` (12 tipos, com dependência que **gera erro se invertida**, `performance-max.md:202-215`) **mais** critério `webpage` negativo — que **não** pode excluir a final URL do próprio asset group (`:186-187`) |
| **Visual** | enquanto PMax não passar, **nenhum controle de expansão na tela** |

### T11 · Não existe loader de fases fictícias

| | |
|---|---|
| **Mecanismo** | varredura: nenhuma barra determinada sem denominador real; nenhum `setTimeout` que avance estado |
| **Resultado** | `POST /provar` é **uma** requisição, teto de 120s (`TIMEOUT_PROVA_S`, `trafego.py:111`), **sem streaming, SSE ou campo de etapa** (`grep -rn 'subfase' backend/ src/` → 0) |
| **Visual** | captura durante a prova: spinner funcional + cronômetro real |

### T12 · `prefers-reduced-motion` respeitado, e movimento funcional sobrevive

| | |
|---|---|
| **Mecanismo** | toda animação com deslocamento espacial tem ramo em `prefers-reduced-motion`; nenhum anel de foco dentro de `transition` |
| **Resultado** | `.animate-spin` fica em **1.4s** e `.animate-progress-indeterminate` em **2.4s** — lentas, **não paradas** (`src/index.css:591-592`) |
| **Visual** | captura de **cada parada** em `prefers-reduced-motion: reduce`, legível e completa |

⚠️ E `.card-volc` **não está** no bloco que zera `transform` sob movimento reduzido (`src/index.css:602` lista só `.hover-lift` e `.card-hover`) e **não tem guarda de ponteiro**. Como a Bancada não a usa, a contraprova é `card-volc` = **0** nas superfícies desta spec.

### T13 · Sem rolagem horizontal de página

Larguras: **320, 375, 414, 768, 1280, 1440, 1920**. Contraprova: `document.documentElement.scrollWidth <= clientWidth` em cada uma, nas duas orientações de tema.

⚠️ A tabela rola **dentro do próprio contêiner**, com `overflow-x: auto` declarado ali — **não** herdado da rede de segurança global de `src/index.css:905-913`, que transforma toda `<table>` em bloco abaixo de 768px. Contraprova: abaixo de 768px a mesa de Termos é `<ul>` e **não há `<table>` no DOM**.

### T14 · Alvo mínimo 40×40 (44 no toque)

⚠️ **A presença da classe não é prova.** `src/index.css:250-274` registra que `src/styles/mobile-responsive.css` **nunca foi importado** e que **55 chamadas de `.touch-target` eram no-op** — a sonda mediu alvos de 16×16 em controles que o código supunha protegidos. E `.touch-target` tem **zero consumidores** no escopo de tráfego.

**Contraprova:** medir `getBoundingClientRect()` de cada alvo interativo renderizado. Nenhuma varredura de classe é aceita.

### T15 · Piso tipográfico

`text-[9px]`, `text-[10px]`, `text-[11px]` = **0** nas superfícies desta spec. Hoje: **235 + 19 + 2** no escopo, com 22 `text-[11px]` só em `Lancamento.tsx`.

**Contraste:** calculado sobre os tokens reais, nos dois temas, ≥4.5:1 para texto normal e ≥3:1 para borda/glifo/anel. Hoje **18 das 47** ocorrências de `text-white/NN` da Ignição reprovam: `/30` = 2,58:1, `/35` = 3,12:1, `/40` = 3,76:1, `/45` = 4,49:1 contra `hsl(222 30% 4%)` (`src/index.css:933`).

⚠️ E a contraprova de contraste do repositório tem uma armadilha documentada: o cabeçalho de `acessibilidade-do-inventario.test.tsx:10-14` diz que `--muted-foreground` só passa sobre `--card`. **Isso descreve o estado anterior.** O corpo do teste (`:466-489`) registra que o token foi de 45% para 40% e que a prova **inverteu de sentido**. Vale o corpo.

### T16 · A bancada de QA não entra no bundle de produção

⚠️ **Correção de procedência.** `scripts/gate_bancada_fora_do_bundle.py` **não existe nesta base** — foi criado pela sprint anterior, junto de `src/pages/qa/BancadaVisual.tsx`, e **nenhum dos dois está em `207e91f`**.

Os gates que **existem** aqui:

| Gate | Comando |
|---|---|
| isolamento do laboratório | `npm test -- projection` (`projection.test.ts:82-97`) |
| segredo no bundle | `npm test -- seguranca-bundle` |

Se a bancada de QA visual for reintroduzida, o gate correspondente **vem junto** — não depois.

---

## 3. Contraprovas específicas desta spec

### 3.1 A tela não deriva prontidão

```
✗ VERMELHO HOJE: injetar { bloqueado: true, bloqueios: [...] } no payload do cockpit
                 e exigir a parada bloqueada. Hoje `projecao.cockpit` não emite os campos
                 e a tela conta localmente (NovaCampanhaPage.tsx:332-343).
```

### 3.2 Falha de leitura não vira permissão

Cinco casos, um por ponto de §T6.

### 3.3 Ausência não vira zero

```
✗ VERMELHO HOJE: cockpit com volume=None e cpc=None ⇒ esperar "não medido" na tela.
                 Hoje a ponte coage a zero e os três ramos de ausência são código morto.
```

### 3.4 Canal indisponível não ganha formulário

Remover um canal de `/canais` e exigir que ele suma. Hoje a bancada monta sobre 6 canais fixos do frontend.

### 3.5 Ativação inexistente não vira botão enganoso

`grep` por rota de ativação = 0, **e** varredura de UI: nenhum controle rotulado "ativar", "ligar" ou "publicar" nas superfícies desta spec.

### 3.6 PAUSED continua garantido pelo motor

AST sobre `comum.py:207` **e** ausência de campo de status em `SubirEntrada` **e** o teste de sentinela que substitui `volc_ads.subir` por uma função que chama `pytest.fail`, provando que nenhum caminho bloqueado alcança o mutate (`test_barreira3_destino_de_campanha.py:603-605, 699-734`, seis motivos de recusa parametrizados).

### 3.7 `/reconciliar` tem saída operacional real

```
✗ VERMELHO HOJE: grep -rn 'api/trafego/reconciliar' src/ ⇒ 0.
                 A tela manda reconciliar em texto (Lancamento.tsx:900-902) e não oferece o ato.
```

Depois: o estado `indeterminado` renderiza o botão; `marca` chega ao cliente (hoje `SubidaIndeterminada` não a declara, `types/trafego.ts:799-805`); **nenhum** caminho oferece reenviar (`reenvio_permitido` é `false` fixo no tipo).

⚠️ **Dois bloqueios que o aceite precisa registrar como abertos, não como resolvidos:** `/reconciliar` exige **admin** (`trafego.py:4445`) enquanto o resto exige `exigir_usuario` — o operador não fecha o próprio recibo; e **não existe caixa de entrada de recibos abertos**, então quem perder o `item_id` perde a saída.

### 3.8 O Pedido é projeção do contrato

`FALTA` vem dos bloqueios do servidor. Contraprova: injetar `bloqueios` e exigir que a lista os reflita **sem** somar item local.

### 3.9 O orçamento mostra consequência real

```
✗ VERMELHO HOJE: digitar "10,50" no orçamento ⇒ o pedido carrega 10.5.
                 Hoje MesaDeLance normaliza vírgula e o pedido usa Number(budget) || 0 ⇒ 0.
```

E: o teto do dia aparece **sem** carimbo de frescor, **com** as três ressalvas visíveis (`payment_mode = CONVERSIONS`; limite no nível da conta; `STANDARD` é pacing mensal), e **não** aparece para campanha existente — ali vale `tetoDaCampanha`, que recusa calcular.

E toda leitura de custo diz **"servido"**: `metrics.cost_micros` é custo servido, **não existe métrica de custo cobrado na v25** (`comum.md:504-518`).

### 3.10 Zero mutação em jornadas de preparação

`gate_sem_mutacao_google.py` **mais** a armadilha de import: teste que instala um `MetaPathFinder` que explode se `volc_ads` ou `google.ads` for importado durante a requisição — armadilha no caminho, não asserção sobre intenção (`test_trafego_alertas.py:9-20`).

### 3.11 Prova, aprovação, criação e ativação permanecem atos diferentes

Quatro contraprovas, uma por fronteira. E a de aprovação inclui: **o campo motivo nasce vazio** — hoje ele é pré-preenchido com `lançamento de "${titulo}"` (`Lancamento.tsx:99`), o que satisfaz por construção as três guardas de 10 caracteres.

### 3.12 Responsividade, teclado, contraste, movimento reduzido

Ver T12–T15 e `RESPONSIVE-AND-A11Y.md`. Acrescente:

- a Ignição **rola** (hoje `.ignicao` é `overflow: hidden` sem contêiner de rolagem, `src/index.css:925-928`);
- os blocos da régua são alcançáveis por **teclado** (hoje só `onMouseEnter`/`onMouseLeave`);
- todo valor do recibo tem valor completo acessível e **cópia** (hoje `truncate` sem `title`, `Lancamento.tsx:905-910`).

### 3.13 Build, bundle, segredos

`npm run build` — lembrando que **não pega erro de tipo**; `gate_tsc_ratchet.py` não piora; `npm test -- seguranca-bundle`; `npm test -- projection`.

### 3.14 Capturas autenticadas reais antes do aceite visual

**Esta é a condição que a spec não pôde satisfazer, e que o executor não pode pular.**

`MASTER-SPEC.md §7` registra: nenhuma rota autenticada foi aberta em navegador nesta missão. Todo diagnóstico visual aqui é de **código**.

**O aceite visual exige, com sessão real:**

| Superfície | Larguras | Temas | Movimento |
|---|---|---|---|
| Hub, 4 abas | 375, 768, 1440, 1920 | claro e escuro | normal |
| Bancada, 6 paradas | 375, 768, 1440, 1920 | claro e escuro | normal **e reduzido** |
| Ignição, 10 estados | 375, 1440 | claro e escuro | normal **e reduzido** |
| Recibo, 4 desfechos | 375, 1440 | claro e escuro | normal |
| Página canônica, 8 seções | 375, 1440 | claro e escuro | normal |
| Fila de atenção | 375, 1440 | claro e escuro | normal |

Referência de escala: a sprint anterior produziu **104 capturas** — 13 cenas × 4 larguras × 2 temas, a 2×, mais 13 em `prefers-reduced-motion` (`VISUAL-QA.md:10-12, 77-83` no blob de `85666da`).

**Nenhuma fatia é aceita visualmente com captura de fixture.** Bancada de fixtures prova componente; ela não prova a jornada.

---

## 4. Definition of Done do executor

Uma fatia está pronta quando **todas** forem verdadeiras:

| # | Condição |
|---|---|
| 1 | a contraprova nasceu **vermelha pelo motivo certo** e está verde |
| 2 | os gates de §0 de `IMPLEMENTATION-SLICES.md` passam, com os comandos exatos |
| 3 | `gate_tsc_ratchet.py` **não piorou** |
| 4 | as capturas de §3.14 existem, **com sessão**, nos dois temas |
| 5 | as varreduras mecânicas de `MOTION-AND-INTERACTION.md §8` estão zeradas nas superfícies tocadas |
| 6 | toda ação desabilitada tem razão **visível** ligada por `aria-describedby`, **em todos os breakpoints** |
| 7 | nenhuma afirmação nova da tela sem campo do servidor que a sustente — ou com a derivação declarada em `DATA-AND-AUTHORITY-MAP.md §6.2` |
| 8 | nenhuma tarefa do Roadmap promovida; o delta vai para `CURATION-HANDOFF.json` |
| 9 | zero mutação externa não autorizada; `gate_sem_mutacao_google.py` verde |
| 10 | o handoff cita IDs de tarefa, nós afetados e resultado de frescor (`AGENTS.md`) |

---

## 5. O que o aceite **não** pode afirmar

1. **Não pode afirmar conformidade WCAG 2.2 AA** sem teste com tecnologia assistiva real. Nenhum leitor de tela foi executado nesta spec. O correto é "projetado para AA".
2. **Não pode afirmar que a campanha entrega** por ler `status = ENABLED` — `serving_status` e `primary_status` são *Output only*.
3. **Não pode afirmar que `validate_only` garante a criação.** Ele cobre forma e política, e **não existe lista oficial exaustiva do que ele deixa passar** (`comum.md:114-123`; `fontes.json:946-1130` registra a busca e **proíbe preencher por memória**).
4. **Não pode afirmar que o teto de gasto é garantido.** Há exceção documentada (`payment_mode = CONVERSIONS`), limite no nível da conta que sobrepõe o de campanha e não pode ser aumentado, e `cost_micros` é custo **servido**.
5. **Não pode afirmar que a campanha criada está sendo observada.** O coletor contínuo filtra `ENABLED` e `SEARCH`; o que lê PAUSED não tem rota nem agenda; e o espelho teve **zero linhas** para a campanha canário pausada.
6. **Não pode usar o benchmark Webgo como verdade causal.** Ele é referência de forma, não prova de comportamento.
7. **Não pode declarar `done` nenhuma tarefa do Roadmap** apenas porque a fatia entrou.
