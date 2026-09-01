# Critérios de aceite — o texto literal, e o que esta missão precisa provar

*Worker 4 · verification · read-only sobre código*
*Branch `sprint/traffic-creative-operational-closure-v1` · base `3462b14`*
*Fontes lidas: `volc-os-workbook/ROADMAP-VIVO.json`, `docs/closure/search-production-closure-v1/**`,
`docs/closure/fable-global-v1/**`, e o código da árvore.*

---

## 0. Como este documento deve ser usado

**Ele não inventa critério.** Para cada tarefa há duas seções bem separadas:

- **CRITÉRIO LITERAL** — texto copiado do `ROADMAP-VIVO.json`, sem paráfrase.
- **O QUE A MISSÃO PRECISA PROVAR** — derivação minha, explicitamente rotulada
  como derivação. Um worker pode discordar dela; não pode discordar do literal.

⚠️ **Só três das nove tarefas têm array `acceptance` no Roadmap: P04-T09, P05-T11
e P05-T12.** As outras seis (P03-T04, P04-T04, P04-T05, P04-T06, P04-T07, P05-T05)
têm apenas `title` + `proof`. Nelas, o mais próximo de um critério literal são as
cláusulas **"FALTA…"** escritas dentro do próprio `proof` — e elas são literais,
porque foram escritas por quem mediu. Nenhum worker deve apresentar critério
derivado como se o Roadmap o exigisse.

### A escada que nunca se colapsa (`fable-global-v1/DEFINITION-OF-DONE.md` §1)

`código presente` → `teste existente` → `teste executado (contagem exata)` →
`commit existente` → `commit alcançável pela main` → `funcionalidade integrada` →
`disponível em localhost` → `migration escrita` → `migration aplicada` →
`dado sintético` → `shadow com dado real` → `produção operacional`.

Regra dura, e ela vale como critério de reprovação nesta missão:
**ausência ≠ zero medido ≠ falha ≠ indisponível ≠ não aplicável ≠ vazio confirmado.**

E o anti-padrão que reprova automaticamente: *"verde" sem contagem*. Todo gate
citado nesta missão precisa de **comando exato + números antes/depois**.

---

## 1. Baseline factual medido nesta árvore (para ninguém redescobrir)

| Fato | Onde | Consequência |
|---|---|---|
| Há **duas** portas de canal, não uma | `volc_ads/subir.py:122` e `:127` | `CONSTRUTORES_POR_CANAL` = {SEARCH, DISPLAY} (mutate). `PROVADORES_POR_CANAL` = {SEARCH, DISPLAY, DEMAND_GEN} (validate_only). Demand Gen **prova e não cria, por estrutura** |
| A divergência entre vista e perfil derruba o import | `volc_ads/subir.py:133-148` | Registrar canal novo sem construtor completo é erro na hora, não na tela |
| PMax não está em nenhuma das duas | idem | Não existe `volc_ads/campanha/pmax.py`; PMax hoje não tem builder nenhum |
| Canais reconhecidos na taxonomia | `volc_ads/campanha/marcacao.py:74` | SEARCH, DISPLAY, DEMAND_GEN, PERFORMANCE_MAX, VIDEO |
| `ProvarEntrada` **não tem campo de imagem de Display** | `backend/app/routers/trafego.py:1311-1400` | O elo HTTP da linhagem Display continua aberto (F031 vale para Display) |
| Demand Gen **já alcança** a ponte por HTTP | `backend/app/routers/trafego.py:1915`, `:2054` | `criativo_ponte.imagens_de_demand_gen(...)` é chamada na rota |
| Display continua sem alcançar | `backend/app/routers/trafego.py:2086` | `imagens_display=None` literal |
| `src/types/trafego.ts` conhece `linhagem_declarada` | `src/types/trafego.ts:217` | É um membro de união de string, **não** o objeto `Preparo.linhagem` |
| Contrato de prontidão existe | `backend/app/trafego/prontidao.py:13-16, 217-249` | G0..G3; `smart_bidding_eligible` fail-closed; G2 governa G3 junto com G1 |
| `/criativos` tem 10 rotas montadas | `src/App.tsx:136-145` | A superfície existe; o que se prova é **procedência nela**, não existência dela |

---

## 2. As nove tarefas

### P04-T04 — Implementar builder e validate_only do primeiro canal
*status atual: `partial`*

**CRITÉRIO LITERAL** (não há array `acceptance`; isto é o `proof`):

> "Construtor completo em volc_ads/campanha/display.py: budget → campanha → geo →
> idioma → ad group → responsive display ad, num mutate. […] O caminho de
> `validate_only` está implementado e testado com cliente falso; **FALTA a prova
> contra a conta real, que exige autorização — e é só ela que separa esta tarefa
> de `done`**."

**O QUE A MISSÃO PRECISA PROVAR** (derivação):

1. O plano Display serializa em objetos **v25 reais**, offline, sem rede.
2. `validate_only` executado — e aqui a missão tem de declarar **qual dos dois**:
   (a) contra cliente falso → não move a tarefa, porque isso já existe;
   (b) contra a conta-laboratório real → é o único ato que a fecha.
3. Zero `mutate`. O caminho de escrita de Display existe em
   `CONSTRUTORES_POR_CANAL`, então Display **pode** mutar — a prova de que não
   mutou precisa ser positiva, não presumida.
4. Contagem de testes antes/depois de `volc_ads` e do arquivo próprio
   (`testes_display.py`), com comando exato.

⚠️ **Armadilha declarada pelo próprio Roadmap:** a distância entre `partial` e
`done` aqui é **uma autorização**, não código. Entregar mais testes com cliente
falso não move a tarefa. Se a autorização não vier, o honesto é `partial` com a
lacuna nomeada — não `done` por volume de prova sintética.

---

### P04-T05 — Integrar assets de imagem e vídeo ao contrato de canal
*status atual: `partial`*

**CRITÉRIO LITERAL** — o `proof` enumera as lacunas com letra. Cópia literal:

> "(a) o caminho HTTP não alcança a ponte […] `ProvarEntrada` em
> `backend/app/routers/trafego.py` NÃO TEM CAMPO DE IMAGEM […] e `Preparo.linhagem`
> chega ao JSON de /provar e /subir como CHAVE EXISTENTE E VALOR SEMPRE VAZIO;
> (b) a TELA não mostra: `src/types/trafego.ts` não declara `linhagem` em `Preparo`
> e nenhum componente a renderiza;
> (c) o construtor de Display AVISA quando falta linhagem, não recusa — deliberado;
> (d) validate_only real e upload real na conta, que exigem autorização;
> (e) reuso de asset já na conta com linhagem preservada, recusado com motivo
> nomeado dentro da própria ponte;
> (f) adapters de imagem e vídeo, runtime portável e persistência do CreativeJob."

Invariantes literais já provadas, que **não podem regredir**:

> "reconcilia por BYTES e não por nome: hash falso, mime falso ou dimensão falsa
> rebaixam o registro a `Linhagem.desconhecida`" · "`ImagemParaSubir.procedencia:str`
> foi REMOVIDA" · "`subir.py` deriva a linhagem DO PAYLOAD (`_linhagem_do_payload`),
> não do brief" · "`confirmada` derivada e nunca gravada".

**O QUE A MISSÃO PRECISA PROVAR** (derivação):

1. **(a) e (b) são o alvo desta missão.** Medido hoje: Demand Gen já atravessa
   (`trafego.py:2054`), **Display não** (`trafego.py:2086` passa `imagens_display=None`).
   Fechar (a) para Display significa `ProvarEntrada` ganhar campo e o campo chegar
   ao builder — não basta o objeto existir no response.
2. `Preparo.linhagem` precisa ser provado **não-vazio** num caminho HTTP real, e a
   prova precisa distinguir *vazio confirmado* de *chave ausente*. Hoje o valor é
   sempre vazio e a chave sempre existe: um teste que só asserta "a chave existe"
   passa com o defeito presente.
3. **(c) é decisão mantida, não lacuna.** Um worker que fizer Display *recusar*
   por falta de linhagem está mudando produto sem mandato — CL-06 registra
   "Display AVISA (não recusa) […] decisão deliberada mantida".
4. Nenhum caminho pode promover linhagem: divergência de bytes/MIME/dimensão só
   **rebaixa** para `desconhecida`. Contraprova obrigatória (G4 do DoD).
5. (d), (e), (f) permanecem fora salvo autorização explícita; declarar por item.

---

### P04-T06 — Adicionar inventário e H0 específicos sem duplicar o Hub
*status atual: `partial`*

**CRITÉRIO LITERAL:**

> "manifesto existe; **seções específicas ainda vazias**. […] `EstruturaDoCanal`
> passou a separar as três ausências — canal não operado, canal operado sem leitura
> das filhas, e leitura que ainda não chegou. 12 provas."

**O QUE A MISSÃO PRECISA PROVAR** (derivação):

1. Qualquer canal novo (Display, Demand Gen, PMax) precisa aparecer no inventário
   com **a ausência certa das três** — e não caindo no `default` do switch, que foi
   exatamente o defeito corrigido em `8684420..6f4072a` (Vídeo/Shopping recebiam o
   perfil do Search).
2. Regra dura do CL-06: *"nenhum canal novo sem `EstruturaDoCanal` distinguindo as
   três ausências"*. Isto é gate, não recomendação.
3. O perfil declarado do canal não pode contradizer a capacidade real — foi assim
   que Display ficou `integrado: false` depois de ganhar construtor.
4. **H0 tem uma lacuna medida que esta missão não fecha sozinha:** o recibo do
   canário registra `espelho_h0: 0` porque *"o coletor contínuo lê apenas ENABLED e
   uma campanha PAUSED some da observabilidade (P09-T14)"*. Se a missão tocar H0,
   precisa dizer se atacou isso ou não. Não atacar é aceitável; alegar
   observabilidade sem isso, não.

---

### P04-T07 — Definir observabilidade PMax antes de autorizar criação
*status atual: `todo` — a única das nove que ainda é `todo`*

**CRITÉRIO LITERAL:**

> "pMaximizer foi aceito como referência de consultas, cobertura de asset groups e
> qualidade de assets; **não existe coleta PMax nem painel VOLC específico**."

O título é o critério: observabilidade **ANTES** de autorizar criação.

**O QUE A MISSÃO PRECISA PROVAR** (derivação):

1. A ordem é normativa. Entregar builder PMax **antes** de observabilidade
   inverte a tarefa. Se a missão entregar contrato/plano PMax, ele tem de ser
   inalcançável por mutate — hoje PMax não está em `CONSTRUTORES_POR_CANAL`
   nem em `PROVADORES_POR_CANAL`, e sair desse estado é uma decisão, não um efeito
   colateral.
2. "Coleta PMax" e "painel VOLC" são os dois objetos nomeados como ausentes.
   Um plano offline serializável em v25 **não é** coleta nem painel — é insumo.
3. `todo → partial` exige prova nova executada; `todo → done` exige coleta e
   painel operando. Promover a `done` sem os dois contradiz o texto literal.
4. Se a missão declarar "mensuração inadequada bloqueia PMax", a prova é um teste
   que **falha fechado**, não um campo que reporta status.

---

### P04-T09 — Fechar a prova segura do builder Demand Gen
*status atual: `partial`, prioridade 2 · **tem `acceptance` literal***

**CRITÉRIO LITERAL — os cinco aceites, verbatim:**

1. "Demand Gen relabelado como Search é recusado antes de trava, recibo e cliente"
2. "Troca de canal, `login_customer_id`, hash ou tipo de operação invalida o selo"
3. "Asset remoto sem recibo tipado e campos não operados falham fechado"
4. "Objetos v25 são instanciados e serializados offline sem rede"
5. "A rota produtiva de Demand Gen permanece recusada e o estado máximo é `partial`"

**Estado literal registrado na `evidencia` (commit `e0f05a1`, 30/08):**

> "Aceite 1 PROVADO […] Aceite 5 PROVADO […] **PENDENTE: aceites 2, 3 e 4 não foram
> exercitados nesta entrega.**"

**O QUE A MISSÃO PRECISA PROVAR** (derivação):

1. **Os alvos são exatamente 2, 3 e 4.** 1 e 5 já estão provados; reprová-los é
   trabalho repetido — mas uma regressão neles é bloqueador crítico.
2. Aceite 2 tem quatro eixos e cada um é uma contraprova separada: canal,
   `login_customer_id`, hash, tipo de operação. Um teste que só troca o canal
   cobre um quarto do aceite.
3. Aceite 5 é **teto declarado**: o próprio aceite proíbe promover P04-T09 a
   `done` nesta missão. Qualquer delta de curadoria propondo `done` para P04-T09
   contradiz o texto que a tarefa carrega.
4. Aceite 4 diz "**offline sem rede**": a prova precisa ser executável com socket
   bloqueado, e a missão deve mostrar o mecanismo, não afirmar a propriedade.

---

### P05-T11 — Primeiro canário Search pausado na Portal Mundo Mais
*status atual: `partial`, prioridade 1 · **tem `acceptance` literal***

**CRITÉRIO LITERAL — os sete aceites, verbatim:**

1. "Pauta publicada e vinculada à Portal Mundo Mais"
2. "Plano efetivo mostra URL, grupos, keywords positivas e negativas, RSA, orçamento e CPC"
3. "V10_01 registra intenção, lote, item, validações, aprovação e recibo `em_voo` antes do Google"
4. "A API cria exatamente uma campanha PAUSED"
5. "Timeout nunca oferece reenvio"
6. "Inventário e H0 reconciliam o ID externo"
7. "Ativação permanece impossível neste ato."

**Estado medido (recibo `RECIBO-CANARIO-V10-24195821946.json`, 01/09/2026):**

| Aceite | Estado | Evidência literal |
|---|---|---|
| 1 | **NÃO** | `vinculo_funil_campanha: 0`; "o vínculo editorial Portal Mundo Mais × pauta/LP NÃO foi satisfeito […] EXCEÇÃO AUTORIZADA DE TESTE DE INFRAESTRUTURA" |
| 2 | **PROVADO** (parcial de origem) | dossiê traz URL, 1 grupo, 2 keywords PHRASE, RSA 15+4, budget 10 BRL, CPC 1 BRL. **Negativas = 0, e por decisão declarada**: "Nenhuma negativa foi inventada" |
| 3 | **PROVADO** | recibo `5526a821…` desfecho `sucesso`, `operacoes_consumidas: 34`, item `criada_pausada`, `aprovado_em` preenchido |
| 4 | **PROVADO** | campanha `24195821946` PAUSED; `campanhas_com_a_marca: 1`; `conta_antes: 6 → conta_depois: 7`, `delta: 1` |
| 5 | **PROVADO em código, NÃO exercido em produção** | o desfecho foi `sucesso` direto; `verificacoes_reconciliacao: 0` — o caminho de timeout não ocorreu |
| 6 | **NÃO** | `espelho_h0: 0` — "o coletor contínuo lê apenas ENABLED e uma campanha PAUSED some da observabilidade (P09-T14)" |
| 7 | **PROVADO** | `ativacao_incluida: false`; `inclui_ativacao=false` na política; nenhuma operação altera status |

**O QUE A MISSÃO PRECISA PROVAR** (derivação):

1. **P05-T11 não pode ir a `done` nesta missão**: os aceites 1 e 6 estão medidos
   como zero, e o 1 é uma exceção autorizada — o que a mantém honestamente
   `partial`, não o que a fecha.
2. Aceite 6 é o gancho real desta missão para tráfego: reconciliar o ID externo
   no inventário/H0 é o que P04-T06 e P09-T14 tocam.
3. **Qualificação obrigatória em qualquer texto:** o canário `24195821946` é o
   primeiro **com ledger v10**; o primeiro canário histórico foi `24183717006`, em
   28/08/2026, sem ledger. O Roadmap marca isso como "⚠️ QUALIFICAÇÃO HISTÓRICA
   OBRIGATÓRIA". Escrever "primeiro canário Search" sem a qualificação é defeito
   de relatório — e já houve um: `CAMPAIGN_BIRTH_READY` declarado sem campanha.
4. O achado de mensuração (`biddable=true` só em DOWNLOAD/APP, com oito ações
   PURCHASE na conta) **não é** um problema de P05-T11; é o que cria P05-T12.

---

### P05-T12 — Fechar o plano canônico de mensuração no nascimento Search
*status atual: `partial`, prioridade 1 · **tem `acceptance` literal — dez itens***

**CRITÉRIO LITERAL — verbatim:**

1. "`campaign_measurement_plan` persistido no Supabase oficial, com migration e rollback provados"
2. "conversion customer e `ConversionAction` owner resolvidos e gravados"
3. "goals efetivos lidos da conta E da campanha (`customer_conversion_goal`, `campaign_conversion_goal`, `conversion_goal_campaign_config.goal_config_level`)"
4. "reutilização de ação canônica por semântica de evento, e não por nicho ou campanha"
5. "nenhuma `ConversionAction` criada automaticamente por nicho ou campanha"
6. "ação nova nasce Secondary (`primary_for_goal=false`), salvo aprovação independente e explícita"
7. "GTM/GA4, auto-tagging, click IDs (gclid/gbraid/wbraid) e consentimento inventariados por conta"
8. "destino Data Manager resolvido por owner + numeric action ID, nunca por nome"
9. "front mostrando meta efetiva, fonte do sinal, frescor da última conversão e bloqueadores"
10. "ativação e Smart Bidding impossíveis enquanto G1 e G2 não estiverem PRONTO"

**Doutrina literal fixada** (`docs/architecture/evidence/GOOGLE-ADS-DOCS-2026-09-01.md`,
citada no `proof`): *"a API só ATUALIZA goals, nunca cria nem remove, e
`selective_optimization` é de campanha de APP"*.

**O QUE A MISSÃO PRECISA PROVAR** (derivação):

1. **O item 3 é a lacuna nomeada como causa do `partial`**: "a leitura hoje é de
   `conversion_action`, e não dos recursos que decidem o efetivo". Ler
   `conversion_action` e chamar de meta efetiva é exatamente o defeito. O dossiê
   já rotula isso: `conversion_goal_status: PARCIAL`, com a nota "Isso não é a
   meta EFETIVA".
2. O item 10 já tem contrato em `backend/app/trafego/prontidao.py` (G0..G3,
   `smart_bidding_eligible` fail-closed, G2 governando G3 junto com G1). O que
   falta é a **leitura correta alimentando esse contrato**, não o contrato.
3. O item 1 exige **Supabase oficial** — degrau 9 da escada. Migration escrita não
   satisfaz; cluster descartável não satisfaz.
4. O item 9 é frontend e é onde mora o risco desta missão: uma tela que mostre
   "meta efetiva" a partir de `conversion_action` estaria **afirmando prontidão
   falsa**. É bloqueador, não cosmético.
5. Itens 5 e 6 são proibições: a contraprova é um teste que **falha** quando o
   caminho proibido é tentado.

---

### P03-T04 — Catalogar engines de imagem e vídeo por contrato
*status atual: **`done`***

**CRITÉRIO LITERAL:**

> "pacote vivo em `docs/creative-engines` […] Imagem: 856 arquivos, 443
> fontes/contratos hasheados, 18 specs, 7 skins e 64 renders classificados. Vídeo:
> 17 formatos, 15 skins, 15 nichos, 14 vozes e 38 MP4s 1080x1920 observados; 20 com
> QA técnico, 4 com QA visual e 2 snapshots congelados. **Os dois parques continuam
> externos ao runtime do VOLC O.S.**"

**O QUE A MISSÃO PRECISA PROVAR** (derivação):

1. Esta tarefa **já é `done`** e é catálogo, não runtime. O papel dela nesta
   missão é servir de **fronteira**: os parques são externos.
2. **O risco a vigiar é o inverso do usual** — não "está incompleta?", e sim
   *"alguém apresentou um artefato do catálogo como se fosse produção?"*. Uma
   fixture de `docs/creative-engines` exibida em `/criativos` como peça produzida
   é exatamente o anti-padrão "fixture-como-produção" que a missão manda caçar.
3. Nenhum worker deve rebaixar P03-T04 sem prova nova; nenhum deve usá-la como
   evidência de que o motor criativo **produz**.

---

### P05-T05 — Levar recibo de lançamento ao cockpit existente
*status atual: `partial`*

**CRITÉRIO LITERAL** (o `proof` inteiro, e ele é curto):

> "jornada ainda tem rotas e identidades históricas"

**O QUE A MISSÃO PRECISA PROVAR** (derivação):

1. Este é o `proof` **mais fraco das nove** — uma frase, sem comando, sem
   contagem, sem caminho. Ele não sustenta promoção nem rebaixamento.
   **Recomendação:** esta missão deveria devolver um `proof` medido para P05-T05,
   mesmo que o estado continue `partial`. Isso é entrega, não burocracia.
2. "Rotas e identidades históricas" tem um caso medido e citável: o recibo do
   canário registra que a gravação legada em `campaigns` **falhou com HTTP 400**
   ("a tabela exige `project_id` NOT NULL"), e que por desenho isso vira aviso.
   Ou seja, o cockpit histórico e o ledger v10 **discordam sobre a mesma campanha**,
   e o canônico é o ledger.
3. O recibo do canário existe em disco
   (`docs/closure/search-production-closure-v1/RECIBO-CANARIO-V10-24195821946.json`)
   e **não** no cockpit. Levar o recibo ao cockpit é mostrar
   `intencao/lote/item/recibo/identidade` numa tela — com os estados de ausência
   renderizados (CL-E: "estado de ausência renderizado explicitamente").

---

## 3. `fable-global-v1` — o que está SUPERADO

O pacote é **biblioteca de specs, não fila literal**. Ele foi escrito em
29/08/2026, sobre `e858651`. Três dias e um canário real depois, estes fatos
mudaram. **Um worker que cite qualquer item da coluna esquerda como estado atual
está citando um fato morto.**

| Fato / doc | O que ele afirma | Situação hoje | Prova da superação |
|---|---|---|---|
| **F006** | "O canário Search real existe: campanha **24183717006** […] Restam 5 gates: ledger v10_01, persistir intenção, vínculo, reconciliação, veredito de política" | **SUPERADO em parte** | Existe um segundo canário, `24195821946`, **com ledger v10 completo**. Ledger, intenção e recibo deixaram de ser gates abertos. Continuam abertos: vínculo (`0`), reconciliação (`0`) e política (`REVIEW_IN_PROGRESS`) |
| **F009** | "O ledger decisório v10 […] **NÃO está aplicado**; lote.py/intencao.py importados APENAS por testes; a aprovação da UI não tem caller de produção" | **SUPERADO** | v10_01/03/04 aplicadas e exercidas em produção; `POST /api/trafego/subir` abriu recibo `em_voo` antes da rede e fechou com `sucesso`; a aprovação humana (`tarcisio-dono`) está gravada e vinculada ao plano |
| **F005** | "o builder Demand Gen […] **não existe na main hoje**" | **SUPERADO** | `volc_ads/campanha/demand_gen.py` (31.786 bytes) e `testes_demand_gen.py` estão na árvore; `perfil.DEMAND_GEN.validador` está em `PROVADORES_POR_CANAL` |
| **F031** | "ProvarEntrada não tem campo de imagem […] o consumidor real é o CLI offline" | **PARCIALMENTE SUPERADO** | **Demand Gen** já atravessa por HTTP (`trafego.py:2054`). **Display continua exatamente como F031 descreve** (`trafego.py:2086`: `imagens_display=None`). Citar F031 como verdade geral é errado; citar para Display é correto |
| **CL-02 / CL-06** | "Display: […] falta SÓ a prova contra conta real (**D5**)" | **VIGENTE** | Nada mudou: nenhum `validate_only` real de Display foi executado |
| **CL-06** | "Demand Gen […] na main o canal falha por design (sem construtor no registry)" | **VIGENTE, e é desenho, não defeito** | `volc_ads/subir.py:122` — a ausência em `CONSTRUTORES_POR_CANAL` é a garantia estrutural do aceite 5 de P04-T09 |
| **CL-06** | "PMax: candidato read-only de observabilidade `5eb6b38` nunca revisado" | **VIGENTE** | P04-T07 continua `todo` |
| **CL-07 / F030** | "v11_03 provada 129/129 em cluster descartável, **NÃO aplicada** (D6); sem writer Postgres; sem worker remoto; Remotion não-hermético" | **VIGENTE** | Nada nesta missão indica D6 resolvido. O motor criativo continua com fila local |
| **README §"Estado do grafo"** | "`current: true` […] gerado em `a539dbd`" | **SUPERADO** | O grafo foi reconstruído após o canário (commit `3462b14`, "Mapa Vivo após o canário real") |
| **CL-02 (regra dura)** | "Timeout NUNCA oferece reenvio (lição do canário de 28/08)" | **VIGENTE e provado em código** | Mas **não exercido em produção**: o canário v10 teve `sucesso` direto |

### O que continua valendo integralmente, e é o que interessa

- **`DEFINITION-OF-DONE.md` inteiro** — a escada de 12 degraus, os 14 gates
  G1..G14 e os anti-padrões. Nada nele foi superado; o canário real, ao
  contrário, o confirmou.
- **CL-F (regra dura)**: "Linhagem por bytes (sha256), nunca por nome; divergência
  rebaixa a `desconhecida`, jamais promove. Peça só é 'verificada' após releitura
  dos bytes no destino."
- **CL-E (regra dura)**: "Estado de ausência renderizado explicitamente (nunca
  'tudo certo' por falta de dado)."
- **G12**: worker paralelo **propõe** delta de curadoria; não aplica.

---

## 4. O que reprova, independentemente de qual worker entregou

Derivado do DoD §4 e da Definição de Pronto desta missão. Isto é a lista que a
`MATRIZ-DE-FECHAMENTO.md` vai aplicar:

1. **Ausência tratada como zero.** `espelho_h0: 0` significa "a campanha não está
   no espelho", não "zero impressões". Toda tela e todo contrato precisa manter os
   dois distintos.
2. **Readiness verde sem prova.** Um campo `PRONTO` derivado de leitura errada
   (ex.: meta efetiva vinda de `conversion_action`) é pior que `INDETERMINADO`.
3. **Fixture apresentada como produção.** Renders de `docs/creative-engines`
   (P03-T04, catálogo externo ao runtime) não são peças produzidas.
4. **Qualquer caminho que possa mutar Google Ads** fora do envelope autorizado —
   inclusive PMax ou Demand Gen entrando em `CONSTRUTORES_POR_CANAL`.
5. **Identidade frouxa.** Reconciliar por nome, não por bytes/ID. Selo que
   sobrevive a troca de canal, MCC, hash ou tipo de operação (P04-T09 aceite 2).
6. **Teste que passa com qualquer entrada.** Assert sobre existência de chave
   quando o defeito é o valor; `try/except` engolindo o gate; prova de
   concorrência que passa sem concorrência (defeito já cometido e corrigido em
   `c6b6a86`).
7. **"Verde" sem contagem.** Comando exato + números antes/depois, sempre.
8. **Marcar fonte compartilhada a partir de worktree não integrada.** Nenhum
   worker escreve `ROADMAP-VIVO.json` nem a curadoria; o integrador único aplica.

---

*Este documento é read-only sobre código. Nenhum arquivo de produto foi tocado
para produzi-lo.*
