# DATA-AND-AUTHORITY-MAP — elemento visual → campo → endpoint → dono → frescor → ausência

Base factual: `207e91f`. Este arquivo responde, para **cada coisa que a tela afirma**, cinco perguntas: de onde veio, quem é o dono, quando foi lido, o que aparece quando não veio, e o que o operador pode fazer.

**A regra que governa o arquivo:** a tela **não decide**. Se uma coluna "autoridade" disser `navegador`, isso é um defeito a corrigir ou uma derivação autorizada com regra escrita — nunca um acidente.

---

## 1. As três autoridades, e o que cada uma pode

| Autoridade | Pode | Não pode |
|---|---|---|
| **servidor** | emitir veredito, severidade, bloqueio, estado de portão, frescor | — |
| **navegador — projeção** | formatar, agrupar, traduzir vocabulário fechado, ordenar **pela ordem que o servidor mandou** | inventar veredito, calcular elegibilidade, reclassificar severidade |
| **navegador — entrada do operador** | guardar o que o operador digitou e **explicar a consequência dele sob regra publicada** | apresentar isso como medida, carimbar frescor, tratar como leitura |

A terceira linha é a que resolve a tensão de §6.2. Fora dela, **toda derivação no navegador é defeito**.

---

## 2. Hub de Tráfego — inventário (`/trafego?aba=campanhas`)

Endpoint: `GET /api/trafego/inventario` (`backend/app/routers/trafego_inventario.py:235`), 12 parâmetros de query, paginação por cursor opaco.

| Elemento visual | Campo | Autoridade | Frescor | Ausência | Erro | Ação |
|---|---|---|---|---|---|---|
| ordem das campanhas | ordem do array | **servidor** | — | — | — | nenhuma. `__tests__/ordem-do-servidor.test.tsx:92-104` prova ausência de qualquer primitiva de ordenação no cliente |
| nome, canal, estratégia | `CampanhaNoInventario` | servidor | — | `—`; `estrategia` nula devolve `AUSENTE`, nunca vazio | — | abrir a linha |
| custo, cliques, impressões | `entrega.*` | servidor | `entrega.leitura` | **sem o carimbo o número não sai do backend** (`types/trafego.ts:1623-1638`); a tela recusa exibir as três colunas juntas (`LinhaDeCampanha.tsx:204-212`) | — | — |
| **teto estimado** | `teto_de_cliques` | **servidor** | — | **quatro ramos de retorno**, três respostas visíveis: a contagem, `não se aplica` (lance automático) e `—` por **dois motivos diferentes** — falta lance/orçamento, ou o teto não veio e a tela recusa calcular (`LinhaDeCampanha.tsx:151-163`) | — | — |
| moeda | `entrega.moeda` | servidor | — | `(sem moeda declarada)` — nunca assume BRL (`types/trafego.ts:23-31`) | — | — |
| frescor da conta | `Frescor` (6 valores) | servidor | é o próprio | `nunca_lido` ≠ `vazio_confirmado` (`types/trafego.ts:1589-1613`); frescor desconhecido **nunca degrada para `recente`** (`InventarioDeCampanhas.tsx:271-272`) | — | releitura read-only |
| presença | `EstadoDePresenca` (7 valores) | servidor | — | fallback tolerante nomeia o valor desconhecido (`Selos.tsx:126-139`) | — | — |
| totais | `Inventario.totais` (5 contadores) | servidor | — | `geral` **não é o universo do banco**: respeita os filtros (`types/trafego.ts:1799-1817`) | — | — |
| falha de leitura | — | servidor | — | **503, nunca lista vazia** (`trafego_inventario.py:288-293`) | vocabulário fechado de 8 motivos, cada um com próximo passo (`erros.ts:46-54`) | tentar de novo |

⚠️ **Dois defeitos de autoridade nesta superfície:**

1. `InventarioDeCampanhas.tsx:263` passa apenas a frase ao `FalhaDoInventario`, que **sorteia um código novo**. O código `VOLC-XXXXXX` que o operador copia **não é** o registrado no console. Quem receber esse código não acha nada.
2. `GrupoDeConta.tsx:219-223` imprime `conta.motivo` — **texto livre do servidor** — sem passar pelo vocabulário, enquanto o mesmo campo é deliberadamente descartado no aviso de leitura parcial. Duas políticas para o mesmo campo.

---

## 3. Antessala de canal (`/trafego?aba=criar`)

Endpoint: `GET /api/trafego/canais` (`trafego.py:5493`).

| Elemento | Campo | Autoridade | Ausência |
|---|---|---|---|
| estado de cada portão | `canais[].portoes[]` — 4 portões, 4 estados | **servidor** | invariante recusa `BLOQUEADO` sem bloqueador (`contrato_canais.py:207-219`) |
| causa e origem da recusa | `bloqueadores[].{codigo, causa, origem}` | servidor | 8 origens fechadas; a origem diz **a quem pedir** (`canais.ts:530-539`) |
| contagem de portões abertos | campo `aberto` emitido pelo servidor | servidor | a tela **audita** o contrato em vez de recalcular (`canais.ts:549-574`) |
| leitura viva do Google | `fontes.leitura_viva_do_google` | servidor | declarado **`false`** em toda resposta (`trafego.py:5519-5531`) |
| mensuração por canal | `medicao.lida` | servidor | ⚠️ **sempre `false`**: a rota não passa `prontidao_por_canal` (`trafego.py:5512-5516`) |
| observabilidade de PMax | `observacao.estado` | servidor | ⚠️ **sempre `INDETERMINADO`**: a rota não passa `prontidao_pmax` |

### 3.1 ⚠️ A derivação que precisa migrar

`src/components/trafego/canal/jornada.ts:645-646` — `escritaLiberada`, dentro de `cruzar()` (que começa em `:616`), combina **API + backend + `sabe_criar` + permissão + trava** no navegador para decidir se a escrita sai. A aba `canais` recusa explicitamente fazer isso (`PainelDeCanais.tsx:10`) e a aba `criar` faz.

**Contrato alvo:** a antessala consome **apenas** `canais[].portoes[]`. A interseção sai do cliente. Onde o servidor não emite o suficiente, a tela diz `INDETERMINADO` — não completa a conta.

E `jornada.ts:879` monta sobre **6 canais fixos do frontend**, não sobre a lista que o servidor devolve. **Contrato alvo:** iterar a resposta do servidor; canal que o servidor não devolve não aparece.

---

## 4. A Bancada — parada a parada

Endpoint principal: `GET /api/trafego/candidatos/{opportunity_id}` (`trafego.py:782`) → `projecao.cockpit` (`projecao.py:157-177`, **oito chaves**).

### 4.1 Destino

| Elemento | Campo | Autoridade | Ausência |
|---|---|---|---|
| as 5 perguntas | `volc`, `publicacao`, `ao_vivo`, `campanha`, `google` | **servidor** (recibo) → traduzido por `prontidao.ts:100-114` | 5 estados; `NAO_AVALIADO` ≠ `INDETERMINADO`, declarados **não sinônimos** (`:93-98`) |
| veredito do portão | `readiness.volc_gate` | servidor | `paid_destination_ready` exige papel estrito **E** zero bloqueios **E** zero desconhecidos (`portao.py:92-96`) |
| verificação ao vivo | `readiness.live_verified` | servidor | qualquer valor ≠ `true` → `INDETERMINADO` (`prontidao.ts:605-627`). ⚠️ **Mas `live_verified` fica `true` quando `live_drift` sai `not_applicable`**, porque `STATUS_NAO_APLICAVEL` está dentro de `STATUS_CONCLUSIVOS` (`recibo.py:160-163`, `contrato.py:73`, `varredura.py:2014-2019`) — uma verificação que não observou nada conta como observada |
| **aprovação do Google** | `readiness.google_approval` | **ninguém** | literal `"unknown"`, fixo no código, **sem nenhuma entrada que o mude** (`recibo.py:164-170`). A tela devolve `DESCONHECIDA_POR_CONTRATO` e a frase diz que **nenhuma leitura da tela muda isso** |
| completude da evidência | `evidence_completeness` | servidor | razão de conclusivas sobre as dez — existe para que poucos achados não pareçam página limpa (`recibo.py:135-147`) |
| deriva ao vivo | comparação de impressão canônica, ou sha256 do byte | servidor | sem HTML ao vivo → `not_applicable`; sem hash aprovado → `unavailable` (`varredura.py:2014-2025`) |
| janela de frescor | ⚠️ **duas janelas diferentes** | servidor **e** navegador | no **backend** o `freshness_window_s` do recibo é ignorado e vale a janela de 24h do contrato — evidência não escolhe a própria validade (`trafego.py:2638-2645`). Na **tela**, `prontidao.ts:538-543` **usa** `recibo.freshness_window_s` quando ele é número finito positivo, e só cai nos 24h quando o campo está ausente. **Contrato alvo: uma janela só, a do contrato.** |
| origem da evidência | `evidence_origin` | — | ⚠️ o front lê o campo (`prontidao.ts:684`) e **nenhum código do backend o escreve** (`grep -rn 'evidence_origin' backend/` → 0) |

⚠️ **Frescor calculado no navegador.** `prontidao.ts:434, 547` usa `Date.now()`, memoizado em `[cockpit]` (`NovaCampanhaPage.tsx:324-330`). O relógio é amostrado **uma vez por carga** e nunca reavaliado. **Contrato alvo:** o servidor emite `vencido: bool` junto do recibo, ou a tela reavalia por intervalo e **diz** que reavaliou.

### 4.2 Política

| Elemento | Campo | Autoridade | Ausência |
|---|---|---|---|
| lista de verticais | `volc_ads/policy/spec.json → habilitacao` | servidor (`GET /politica/verticais`, `trafego.py:279-326`) | ⚠️ ver os quatro defeitos abaixo |
| severidade por país | `bloqueio` / `limitacao` por par vertical×país | servidor | — |
| certificação | **auto-declaração do operador** (checkbox) | **operador** | não há leitura de verificação real: `grep 'advertiser_verification\|identity_verification'` em `backend/ volc_ads/` → **0** |
| veredito do anúncio | `ad_group_ad.policy_summary` | servidor (`GET /veredito/{customer}/{campaign}`, `:5584`) | "em revisão" é estado próprio, exibido **antes** de qualquer cor de aprovação (`VereditoDePolitica.tsx:111-119`); fallback fail-closed (`:41-58, 125-127`) |

⚠️ **Quatro pontos onde ausência vira permissão.** Todos precisam inverter:

| # | Hoje | Contrato alvo |
|---|---|---|
| 1 | `atual === undefined` → nota **verde** "Sem portão de habilitação" (`PortaoDePolitica.tsx:167-172`) | vertical fora da matriz → **`INDETERMINADO`**, e a parada não avança |
| 2 | falha da rota → `{verticais: []}` → painel **escondido** sem erro (`NovaCampanhaPage.tsx:155, 702`) | falha de leitura → estado de erro **visível**, parada bloqueada |
| 3 | o `barra` **nunca entra** em `podeLancar` (`:332-343`); não existe callback | o veredito de política é uma das pendências que o **servidor** emite |
| 4 | servidor: vertical fora da matriz → **lista vazia** de violações (`spec.py:163-168`) | alinhar com `contrato.severidade()` (`landing_policy/contrato.py:455-464`), onde não classificado **bloqueia** |

### 4.3 Termos

| Elemento | Campo | Autoridade | Ausência |
|---|---|---|---|
| conjunto de keywords | `production_ads_queue` do cluster | **decidido antes do backend** — `montar_cockpit` apenas lê (`pautador_ponte.py:878-879, 917`) | — |
| volume por termo | `KeywordCandidata.volume` | servidor | ⚠️ **coagido a 0** (`pautador_ponte.py:505-506`) |
| CPC por termo | `Cpc` (4 campos) | servidor | ⚠️ **coagido a 0.0** com `medido_na_conta=False` (`:451-456`) |
| ressalva do CPC minerado | `medido_na_conta` | servidor | é literal `False` — a ressalva **sempre** aparece (`ReguaDeLeilao.tsx:225-232`) |
| correspondência | 3 tipos; BROAD só sob `MAXIMIZE_CONVERSIONS` | operador, sob regra | no servidor `propor_match_type` **nunca propõe BROAD** (`paid_eligibility.py:519-524`) |
| negativas | escritas pelo operador | **operador** | **nada as sugere** — declarado em três lugares (`paid_eligibility.py:1241-1242`) |
| selo "medida na conta" | `evidencia.tipo === 'MEDIDO'` | — | ⚠️ **nenhum caminho de produção cria essa evidência**; o selo nunca aparece (`MesaDeCriterios.tsx:402-410`) |
| aviso de procedência (fator 7,4×) | `cockpit.procedencia.aviso` | servidor | ⚠️ viaja no payload e **não é renderizado** (`grep 'procedencia.aviso' src/` → 0) |
| descartadas | `cockpit.descartadas` (texto, volume, cpc, motivo, destino) | servidor (`projecao.py:164-166`) | ⚠️ **nunca lido** |

⚠️ **A doutrina quebrada no meio.** O tipo `Sinal` recusa `Sinal(0.0, AUSENTE)` (`paid_eligibility.py:107-109`); a tela sabe renderizar ausência; **a ponte coage**. Resultado: três ramos de ausência são código morto (`MesaDeCriterios.tsx:201-202`, `ListaDeKeywords.tsx:140-142`, `ReguaDeLeilao.tsx:78,92,230`).

**Contrato alvo:** a ponte **para de coagir**. `volume: null` e `cpc: null` atravessam, e os ramos que a tela já escreveu passam a executar. É a mudança de menor custo e maior efeito de todo o mapa.

⚠️ **A colisão do conjunto positivo.** A tela envia positivas em `criterios` (`NovaCampanhaPage.tsx:367-381, 413`); o portão **recusa positiva vinda do corpo, fechada** (`portao_conjunto_pago.py:259-272`). **Contrato alvo:** a Bancada envia **apenas negativas e correspondências**; o conjunto positivo é do servidor, e a mesa diz isso em vez de "o que você vê é o que vai para o Google" (`MesaDeCriterios.tsx:497-501`).

### 4.4 Anúncio

| Elemento | Campo | Autoridade | Ausência |
|---|---|---|---|
| copy | `EscritaDaCopy` | servidor (`GET /copy/{id}`, `POST /copy` assíncrono) | `CopyPersistida.perdida` existe porque `status === 'running'` **não prova** que algo roda: um reinício deixa a linha running para sempre (`types/trafego.ts:1329-1348`) |
| carimbos da copy | `criado_em`, `atualizado_em` | servidor | `criado_em` **é exibido** (`CartaoCopy.tsx:96, 422-428`); `atualizado_em` não. A tela diz quando a copy nasceu, não quando mudou |
| "copy pronta" | — | ⚠️ **navegador, com três definições** (`NovaCampanhaPage.tsx:335, 442, 652`) | **contrato alvo: uma só**, `status === 'done'` |

⚠️ **Trava dura da API que a parada precisa respeitar:** `AdGroupAd.ad` é **Immutable** — editar o criativo de um RSA existente é impossível pela API. O caso de uso é *replace-and-retire*, com dois `AdGroupAd` distintos no histórico (`docs/growth-engine/matriz-api/search.md:66, 73-75`). A tela **não** pode oferecer "editar anúncio publicado" como se fosse edição.

### 4.5 Economia

| Elemento | Campo | Autoridade | Ausência |
|---|---|---|---|
| moeda da conta | `customer.currency_code` | servidor, via `contas.py:63-64` | ⚠️ caminho **separado** do fuso; a GAQL do plano de mensuração lê `time_zone` e **não** lê `currency_code` (`metas_efetivas.py:150-163`) |
| fuso da conta | `customer.time_zone` | servidor | decide a data de HOJE; quando não lido, resultado é `None` — nunca o relógio do servidor (`metas_efetivas.py:677-690`) |
| os 7 portões | `Prontidao.portoes()` | **servidor** (`prontidao.py:256-283`) | `INDETERMINADO` é o default dos campos de portão (`:59-76`) — **exceto** `smart_bidding_eligible`, que tem default próprio |
| meta efetiva | 3 recursos (`customer_conversion_goal`, `campaign_conversion_goal`, `goal_config_level`) | servidor | objeto explícito `meta_efetiva_nao_lida` com 7 estados de leitura; `metas_que_mandam` devolve `None` e **nunca tupla vazia** (`plano_mensuracao.py:478-498`) |
| estratégia | 2 valores no front, **5 famílias no backend** | operador (2), servidor (classificação) | o backend recusa string fora da união **antes** de avaliar medição (`prontidao.py:772-784`; as três famílias fechadas estão em `:720-752`) |
| **orçamento e lance** | entrada do operador | **operador** | `MANUAL_CPC` atravessa o portão sem prova de medição (`prontidao.py:784-798`) |
| **teto do dia** | derivado: `2 × orçamento` | **navegador — entrada do operador** (§6.2) | ver §6.2: regra publicada, **sem** carimbo de frescor |
| graduação | `graduacao_em_conversoes` | ⚠️ **ninguém** | aceito pelo modelo HTTP e **nunca lido, persistido ou executado** (`grep` → 3 hits, todos definição/repasse) |
| teto do canário | `POLITICA` | servidor | R$ 20,00/dia e CPC R$ 1,00, **por pedido** — nunca acumulado (`canario.py:25-34, 153-163`) |

### 4.6 Revisão / Pedido

O Pedido é **projeção**. Nenhuma linha dele nasce de cálculo do navegador exceto as de §6.2.

| Linha | Fonte |
|---|---|
| conta, moeda, fuso | `cockpit.conta` — **"a conta vem do PROJETO, não do operador"** (`types/trafego.ts:150`) |
| destino | recibo de landing policy |
| canal | manifesto do servidor |
| conjunto | contagem do que veio, **não do que a tela montou** |
| **o que falta** | ⚠️ **hoje o navegador inventa**; contrato alvo: `bloqueado`/`bloqueios` do servidor |
| próximo ato | frase derivada dos bloqueios do servidor |

---

## 5. Ignição, Recibo e Reconciliação

| Elemento | Endpoint | Autoridade | Ausência |
|---|---|---|---|
| degrau `destino` | nenhuma chamada | **prop** `LeituraDoDestinoPago` | para antes de gastar (`Lancamento.tsx:132-135`) |
| degrau `copy` | nenhuma chamada | ⚠️ **literal `estado="ok"`** (`:299`) | **contrato alvo:** o degrau lê o estado real da copy e pode reprovar |
| degrau `prova` | `POST /provar` | servidor | **uma** requisição, teto de 120s (`TIMEOUT_PROVA_S`, `trafego.py:111`), **sem subfase observável** |
| resultado da prova | 5 chaves: `preparo`, `avisos`, `grupos`, `autorizacao`, `destino`, `prontidao` | servidor | `ativacao_incluida: false` explícito (`:3182`); selo retido quando destino inelegível (`:3147-3149`) |
| degrau `escrita` | `POST /subir` | servidor | recusa sem selo (409) e recusa impressão divergente (409) (`:3620-3645`) |
| **status PAUSED** | — | **`volc_ads/campanha/comum.py:207`**, literal do construtor | o payload HTTP **não tem campo de status**: não há como pedir outro (`SubirEntrada`, `:3398-3431`) |
| recibo | chave `recibo` da resposta | servidor | ⚠️ vive só em `useState`; sem persistência, sem rota, sem histórico |

### 5.1 O ledger — quatro desfechos que não colapsam

| Desfecho | Como nasce | Reentrável? |
|---|---|---|
| `sucesso` | `ledger.fechar_sucesso` | — |
| `erro` | `ledger.fechar_erro` → item `falhou` | **sim** |
| `sem_resposta` | `ledger.fechar_sem_resposta` → item `indeterminado` | **não** |
| `em_voo` | **nasce no próprio ledger**, em `Ledger.despachar()`, **commitado ANTES de o mutate sair** (`ledger.py:19, 275-282`) — **todo lançamento passa por `em_voo`**. Ele *permanece* como desfecho final quando o fechamento falha, e aí o router o emite com `registrado: false` (`trafego.py:5209, 5235, 5257`) | — |

E um quinto estado: `registrado: false` significa "não há recibo nenhum", com proibição explícita de lê-lo como sucesso (`types/trafego.ts:727-742`).

`fechar_sem_resposta` **não aceita** `resposta_bruta`, e a omissão é deliberada (`ledger.py:341-347`).

### 5.2 ⚠️ `/reconciliar` — a saída que existe e não tem porta

`POST /api/trafego/reconciliar` (`trafego.py:4442`, admin) lê a conta e fecha o mesmo recibo, **nunca reenvia**. Aceita `marca` como alternativa a `campaign_id` — o que a torna utilizável pelo item que mais precisa dela, o que **nunca teve id externo** (`:4186-4195`). Protege contra três coisas que o banco não protege: item inexistente (**404**, `:4476-4479`), item de outra conta (**409**, `:4480-4486`) e duplicidade consumada (**409 sem carimbar nada**, `:4520-4533`). Quando a leitura da conta está indisponível, `achou=None` registra a ignorância, **não move o item, e nada reagenda a tentativa** (`:4497-4502, 4536-4537`).

⚠️ **É a única rota admin numa jornada de operador.** `POST /reconciliar` exige `exigir_admin` (`:4445`); o restante do router exige apenas `exigir_usuario` (`:101`). **O operador que caiu no indeterminado não pode fechar o próprio recibo.**

⚠️ **Não existe caixa de entrada de recibos abertos.** Nenhuma rota lista itens em `indeterminado`/`em_voo`. A reconciliação só é possível para quem **ainda tem o `item_id`** da resposta HTTP que falhou — e essa resposta some quando o modal fecha.

⚠️ **E o tipo do front descarta a chave da porta de saída.** O corpo do 504 leva `marca`, `chave_intencao` e `plano_de_mensuracao_id` de propósito — para o item que nunca teve id externo. `SubidaIndeterminada` (`types/trafego.ts:799-805`) declara apenas cinco campos e **não inclui `marca`**. Sem ela, o caminho alternativo de `/reconciliar` fica inalcançável pela tela.

E o próprio código registra que, **até ela existir, `indeterminado` era terminal na prática, com saída documentada de "alguém com psql"** (`:4174-4180`).

**Consumidor no frontend: nenhum.** `grep -rn 'api/trafego/reconciliar' src/ api/` → **0**.

Enquanto isso, `proximoAtoSeguro` devolve `reconciliar_na_conta` **por padrão** (`lib/trafego/lancamento.ts:141-147`) e `Lancamento.tsx:900-902` **manda o operador reconciliar o recibo aberto — em texto, sem botão e sem chamada.**

**Contrato alvo:** a região Recibo, no estado `indeterminado`, oferece o ato. O corpo do erro `SubidaIndeterminada` traz `reenvio_permitido: false` **fixo no tipo** (`types/trafego.ts:794-824`) — a tela nunca oferece reenvio; oferece **reconciliação**, que é outra coisa.

### 5.3 Por que o indeterminado é inevitável

`docs/growth-engine/matriz-api/comum.md:151-154`: **a API não oferece chave de idempotência.** Varredura por `idempot` em 70 páginas oficiais retornou zero ocorrências.

Sem idempotência, um timeout depois do envio é genuinamente ambíguo: a campanha pode existir ou não. `/reconciliar` não é conveniência — é a **única** forma correta de fechar essa ambiguidade.

---

## 6. Duas derivações autorizadas, e por que

### 6.1 A regra geral

Nenhuma. Toda afirmação da tela aponta para campo do servidor.

### 6.2 A exceção: o teto de gasto do que o operador está digitando

Há uma tensão real. `tetoDaCampanha` (`inventario/LinhaDeCampanha.tsx:135-164`) **recusa** dividir orçamento por lance mesmo tendo os dois números, porque "calcular aqui um número que a leitura não trouxe seria inventá-lo com aparência de medido". E o Pedido quer mostrar `teto do dia = 2 × orçamento`.

**As duas não são o mesmo caso, e a diferença é o que torna uma segura:**

| | `tetoDaCampanha` | `teto do dia` no Pedido |
|---|---|---|
| Sobre o quê | uma campanha **que já existe** | um número que o operador **está digitando agora** |
| Insumo | campos **lidos** da conta | entrada do operador |
| O que seria | uma **medida** que ninguém mediu | uma **consequência** sob regra publicada |
| Frescor | teria de ter, e não tem | **não tem, e não deve ter** |

**Condições que autorizam a derivação — todas obrigatórias:**

1. O insumo é **exclusivamente** o valor que o operador digitou nesta sessão. Nenhum campo lido entra na conta.
2. A linha é rotulada com a regra e a fonte: *"regra do Google: 2× o orçamento diário médio"*, com link para `docs/growth-engine/matriz-api/comum.md:459`.
3. **Nenhum carimbo de frescor.** Frescor é para medida.
4. A linha **desaparece** quando a Bancada mostra uma campanha existente. Ali vale `tetoDaCampanha`.
5. As **três ressalvas** de §6.3 aparecem junto, não em tooltip.

### 6.3 As três ressalvas que precisam viajar com o número

| Ressalva | Fonte |
|---|---|
| campanhas com `Campaign.payment_mode = CONVERSIONS` **não têm limite diário**, só mensal | `comum.md:471-474` |
| existe **limite de gasto diário no nível da CONTA** que sobrepõe o orçamento de campanha — comum em contas novas ou pendentes de verificação, e **não pode ter aumento solicitado** | `comum.md:603-614` |
| `STANDARD` **não** é trava diária de 1×: é pacing mensal (`comum.md:560`). `ACCELERATED`, presente no enum v25, está sunsetado desde abril/2020 e retorna `ACTION_NOT_PERMITTED` (`comum.md:533-536, 543, 550-552`) | — |

E a regra que vale para toda leitura de gasto na tela: **`metrics.cost_micros` é custo SERVIDO, não cobrado**, e **não existe métrica de custo cobrado na v25** — verificado por introspecção do proto (`comum.md:504-518`). Hoje ele é apresentado como "gasto" e "custo" sem marcação (`AlertaDeEntrega.tsx:90`). **Contrato alvo:** toda exibição de custo diz "servido" e nunca promete a fatura.

---

## 7. Campanha canônica e vigilância

| Elemento | Endpoint | Autoridade | Ausência |
|---|---|---|---|
| identidade | `GET /campanhas/{volc_campaign_id}` | servidor | **só a identidade interna endereça a página**: o id externo do Google não é único no VOLC O.S. (`types/trafego.ts:1750-1758`) |
| manifesto do canal | `CampanhaCanonica.manifesto` | servidor | `null` (canal sem manifesto) ≠ manifesto vazio (`:1777-1784`) |
| diagnóstico | `GET /campanhas/{id}/diagnostico` | servidor — **única rota do módulo com `response_model`** (`trafego_diagnostico.py:51`) | quatro ramos de não-resposta, **nenhum devolve `null`** (`CampanhaCanonPage.tsx:457-473`) |
| veredito da sentinela | 16 estados por `PRECEDENCIA` | servidor (`sentinela.py:133-150`) | `HEALTHY` exige zero causas **E** evidência `apurada`; parcial → `DATA_UNAVAILABLE` (`:2036-2043`) |
| severidade | mapa fechado de 5 graus | servidor | `POLICY_REVIEW` é deliberadamente **média** — nem crítica, nem aprovação (`:168-187`) |
| mutação externa | `mutacao_externa` | servidor | **campo constante `False`**, e o texto disso vai para a tela em vez de ser deduzido da ausência de botão (`:39-43`) |
| histórico e recibos | — | — | **ausência de CAPACIDADE**, declarada na própria seção (`CampanhaCanonPage.tsx:292-299`) |
| estrutura do canal | — | servidor | ⚠️ **a única das 8 seções que simplesmente não renderiza** quando falta o dado (`:274-283`) — sem frase de ausência |

### 7.1 O sino e a fila

| Elemento | Autoridade | Nota |
|---|---|---|
| nascimento de um alerta | `dominio.merece_alerta` (`backend/app/trafego/dominio.py:761-767`) | exige campanha **LIGADA** + custo **MEDIDO e igual a zero** + idade conhecida **≥24h** |
| severidade do quadro de alertas | ⚠️ **não existe** | `alertas.py` (569 linhas) **não tem campo de severidade** |
| ordem da fila | `SINTOMAS[].ordem` (`atencao/projecao.ts:680-684`) | — |
| **cor** do item | ⚠️ **segunda tabela escrita à mão** (`atencao/visual.ts:40-53`) | não deriva de `ordem` |
| contador da aba | `useAtencao.ts:150` | ⚠️ conta só escopo de campanha; a fila exibe também escopo de conta |
| ação concreta | `ordem_de_revisao` (`backend/app/trafego/dominio.py:717-732`) | lista o que conferir e **recusa sugerir valor** por ADR-11 |
| tipo de `AlertaDeEntrega` | ⚠️ **o tipo mente** | TS declara `impressoes`, `cliques`, `custo` **não-nuláveis**; a dataclass do backend os declara `Optional` e os zera para `None` sem carimbo (`types/trafego.ts:1490-1492`) |

### 7.2 ⚠️ O Guardião 72h é uma classificação, não um processo

- `janela_do_guardiao` é calculada **por requisição**, dentro de `avaliar`, a partir de `horas_ligada` (`diagnostico_persistido.py:1343-1354`).
- `horas_para_incidente = 24.0` (`sentinela.py:338`); a amarração a `dominio.HORAS_ATE_ALERTAR` é **só prosa** (`:325-327`) — `sentinela.py` não importa nada de `app.`, então nada mecânico impede as duas divergirem.
- `None` e `NaN` são tratados como "idade desconhecida" — **nunca** como zero nem como campanha madura (`:384-398`).

Mas:

| Ausência | Prova |
|---|---|
| **não há agendador** no backend | `grep -rn 'APScheduler\|celery\|@repeat_every' backend/app/` → **0** |
| `Incidente`, `consolidar`, `incidente_do_veredito` **não têm chamador de produção** | só definição e testes |
| **não há tabela de incidentes** no schema | `grep -rn 'trafego_incidente' sql/ supabase/` → **0** |
| `LOW_DEMAND` **não tem produtor** | declarado, em `PRECEDENCIA`, em `ESTADOS_DE_INCIDENTE`, em `SEVERIDADE`, com verbete no frontend — e **nada o emite** |
| `CaixaDePropostas` é renderizada **sem** `aoSubmeter` | o próprio componente desabilita o botão; a fila de mudanças recomendadas não tem para onde ir (`CampanhaCanonPage.tsx:506-510`) |
| `AlertaDeEntrega` (o cartão rico) **não é renderizado em produção** | único import default está no próprio teste |

### 7.3 ⚠️ A campanha recém-criada é invisível

- O coletor **contínuo** filtra `estado_externo = ENABLED` **e** `canal = SEARCH`, com instrução explícita de não ampliar (`volc_ads/inteligencia_google/persistencia.py:77-90`).
- O coletor que **lê PAUSED existe** — `campanha_por_identidade`, sem filtro de estado, protegido pela identidade completa (`:111-119`) — e **não tem rota HTTP**: só CLI.
- `alvo.py:19-23` declara que a autoridade de agenda **ainda não foi escolhida** e que o pacote systemd versionado **nunca foi instalado**.
- **Consequência medida:** o espelho tinha **zero linhas** para a campanha canário nascida PAUSED (`contrato_canais.py:492-504`).

O ciclo fecha assim: a campanha nasce pausada por segurança, e a pausa a torna invisível para a vigilância. **A Bancada precisa dizer isso no Recibo** — não como falha, como fato: *"esta campanha nasceu pausada e o coletor contínuo não a alcança; a releitura é por identidade e ainda não tem agenda."*

---

## 8. O que sai do navegador — a lista fechada

| # | Derivação | Onde | Substituto |
|---|---|---|---|
| 1 | `podeLancar` / `pendencias` | `NovaCampanhaPage.tsx:332-343` | `bloqueado`/`bloqueios` em `projecao.cockpit` |
| 2 | filtro de severidade de aviso | `:91, 309-310` | o servidor emite o que barra |
| 3 | interseção de escrita por canal | `canal/jornada.ts:645-646` | `canais[].portoes[]` |
| 4 | frescor do recibo por `Date.now()` | `prontidao.ts:434` | `vencido: bool` do servidor, ou reavaliação declarada |
| 5 | "copy pronta" (3 definições) | `NovaCampanhaPage.tsx:335, 442, 652` | uma definição: `status === 'done'` |
| 6 | montagem do conjunto positivo | `:367-381, 413` | o servidor é dono do conjunto |
| 7 | lista de canais fixa | `canal/jornada.ts:879` | iterar a resposta de `GET /canais` |
| 8 | etapa `origem` literal | `:440` | `destino.apto_para_campanha` |

**Continua no navegador, autorizado:** formatação, agrupamento, tradução de vocabulário fechado, e a derivação de §6.2 sob as cinco condições.

---

## 9. Mudanças de backend realmente necessárias

Ordenadas por razão custo/efeito. Detalhamento em `IMPLEMENTATION-SLICES.md`.

| # | Mudança | Por quê | Custo |
|---|---|---|---|
| B1 | `projecao.cockpit` serializa `bloqueado` e `bloqueios` | mata a derivação nº 1, a mais consequente. **O servidor já calcula** (`pautador_ponte.py:266-272`); é só emitir | baixo |
| B2 | a ponte **para de coagir** volume e CPC a zero | ressuscita três ramos de ausência que a tela já escreveu | baixo |
| B3 | carimbo de frescor na resposta do cockpit | hoje nem o servidor emite (`projecao.py:157-177`) | baixo |
| B4 | `GET /canais` passa `prontidao_por_canal` e `prontidao_pmax` | destrava mensuração e observabilidade, hoje sempre não lidas | médio |
| B5 | `spec.py` alinha vertical desconhecida com `contrato.severidade()` | fecha o quarto ponto de ausência-vira-permissão | baixo |
| B6 | `response_model` nos handlers de tráfego | dá contrato tipado para programar contra | médio |
| B7 | rota que exponha o recibo por identidade | hoje o recibo morre no fechamento do modal | médio |
| B8 | agenda para a coleta por identidade (alcança PAUSED) | fecha §7.3 | alto — **exige decisão de autoridade de agenda** |

⚠️ **Fora da lista, e deliberadamente:** rota de ativação. Não existe, o portão está fechado por quatro razões de quatro origens, e **não deve ser criada por esta lane**.

---

## 10. Cinco superfícies que a documentação já declara sem rota

`docs/growth-engine/frontend.md:241-249` publica uma tabela "Rotas que ainda não existem". Confirmadas nesta base:

| Rota declarada inexistente | Ainda inexistente? |
|---|---|
| `GET /api/trafego/campanhas/{id}/recibos` | **sim** |
| `GET /api/trafego/lotes/{id}`, `POST .../retomar`, `POST .../cancelar` | **sim** — apesar de `backend/app/trafego/lote.py` existir |
| `POST /api/trafego/propostas/{id}/aprovar` | **sim** — e o documento já declara a regra: o autor sai do **token**, nunca do corpo |
| `GET /api/trafego/criativos` | **sim** |
| diagnóstico persistido | **não** — passou a existir depois do documento, em router próprio (`trafego_diagnostico.py:31-52`) |
