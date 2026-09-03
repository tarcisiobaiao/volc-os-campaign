# STATE-MATRIX — os estados transversais, e o que cada superfície faz em cada um

Base factual: `207e91f`.

**A regra que governa o arquivo:** dois estados que levam a **ações diferentes** nunca compartilham palavra, glifo ou cor. Onde o produto já implementa essa disciplina, este arquivo cita e herda; onde ela quebra, aponta.

---

## 1. Os dezesseis estados

Colunas: **palavra** (o que o operador lê, sempre visível), **glifo**, **de quem depende** (o campo único que o produz), **quem decide**, **persiste?**, **para onde vai**.

| # | Estado | Palavra | Glifo | Dependência exclusiva | Quem decide | Persiste | Transições |
|---|---|---|---|---|---|---|---|
| 1 | **carregando** | "lendo…" | spinner | requisição em voo | navegador | não | → 2,3,4,5,7,8,10 |
| 2 | **vazio confirmado** | "não há nenhum" | círculo vazio | leitura **concluída** com zero linhas | servidor | não | → 1 |
| 3 | **ausência de evidência** | "ninguém leu" | traço | campo `null` **com** leitura declarada ausente | servidor | não | → 1, 2, 4 |
| 4 | **leitura falhou** | "não consegui ler" | alerta | erro da leitura | servidor | não | → 1 |
| 5 | **stale** | "lido há N" + o instante | relógio | carimbo de frescor fora da janela | servidor | sim | → 1 |
| 6 | **parcialmente observado** | "li uma parte" | meio-círculo | contagem lida < contagem esperada | servidor | não | → 1, 5 |
| 7 | **bloqueado** | "bloqueado" | cadeado | ≥1 bloqueador com causa e origem | **servidor** | sim | → 8, 9 (quando a causa cai) |
| 8 | **indeterminado (leitura)** | "não se sabe" | interrogação | ausência de leitura que o portão exige | servidor | sim | → 7, 9 |
| 9 | **pronto para preparar** | "pode montar" | círculo | portão anterior aberto | servidor | não | → 10, 7 |
| 10 | **pronto para provar** | "pode provar" | círculo cheio | pedido completo **e** zero bloqueios | servidor | não | → 11, 7, 12 |
| 11 | **provado** | "provado, nada criado" | selo | selo emitido por `/provar` | servidor | sim (selo) | → 13, 7 |
| 12 | **recusado** | "recusado" | X | `RecusaDeclarada` **com** o rótulo `recusado` | servidor | sim | → 9, 10 |

⚠️ **Um estado que o produto atravessa e a matriz precisa nomear:** `em_voo`. Ele **nasce no ledger**, em `Ledger.despachar()`, e é **commitado antes de o mutate sair** (`ledger.py:19, 275-282`) — **todo lançamento passa por ele**. Ele só vira desfecho *final* quando o próprio fechamento falha, e aí o router o emite com `registrado: false` (`trafego.py:5209, 5235, 5257`). Para a tela, `em_voo` final é o estado **15**; `em_voo` transitório nunca é exibido.
| 13 | **aprovado** | "autorizado" | assinatura | motivo ≥10 + caixa PAUSADA | **operador** | sim (recibo) | → 14, 15, 4 |
| 14 | **criado pausado** | "criada, pausada" | pausa | recibo com `desfecho: sucesso` **e** `id_externo` | servidor | sim | → 16 |
| 15 | **indeterminado (escrita)** | "não sei se criou" | interrogação em losango | `SubidaIndeterminada` (504) | servidor | sim | → 14 ou 12, **só por reconciliação — e hoje só um admin pode chamá-la** |
| 16 | **capacidade inexistente** | "não existe aqui" | traço em círculo | manifesto/contrato declara ausência | servidor | permanente até decisão | → nenhuma pela tela |

⚠️ **Por que dezesseis, e não os treze do briefing.** Três estados que o briefing tratava como um só levam a **ações diferentes** e por isso não colapsam: `vazio confirmado` × `ausência de evidência` × `leitura falhou`; e `indeterminado de leitura` × `indeterminado de escrita` — o primeiro pede uma leitura, o segundo pede uma **reconciliação**, e só o segundo pode ter criado uma campanha. `conflito/reconciliação` **não** ganha linha própria: é o estado **15** visto do outro lado. A contagem é do produto, não do documento.

---

## 2. As sete distinções que o produto se recusa a colapsar

Cada uma existe porque leva a **outra ação**, e cada uma tem prova.

| Distinção | Por quê | Prova |
|---|---|---|
| **2 vazio confirmado** ≠ **3 ausência** | "provei e não há" libera o operador; "não consegui provar" não | `plano_mensuracao.py:68-87` — `nao_coletado` ≠ `vazio_confirmado` ≠ `falhou` |
| **3 ausência** ≠ **zero** | `Sinal(0.0, AUSENTE)` **levanta exceção** | `paid_eligibility.py:107-109, 120-121` |
| **7 bloqueado** ≠ **8 indeterminado** | bloqueado pede que alguém **abra uma permissão ou conserte**; indeterminado pede uma **leitura que ninguém fez** | `contrato_canais.py:86-97`, comentário literal |
| **11 provado** ≠ **13 aprovado** ≠ **14 criado** | três atos, três autoridades: servidor, operador, servidor | `/provar` declara `ativacao_incluida: false` (`trafego.py:3182`) |
| **12 recusado** ≠ **15 indeterminado de escrita** | recusa é **reentrável**; indeterminação **não é** | `ledger.py:32-37`; `SubidaIndeterminada.reenvio_permitido` é `false` **fixo no tipo** (`types/trafego.ts:794-824`) |
| **4 leitura falhou** ≠ **7 bloqueado** | falha de leitura **não é permissão nem recusa** | `prontidao.ts:400-407` — `status_wp` nulo → `INDETERMINADO`, nunca `APTO` |
| **16 capacidade inexistente** ≠ **7 bloqueado** | "o canal não existe aqui" convida a desistir; "o canal planeja e a porta ainda não abriu" convida a **pedir a porta** | `contrato_canais.py:568-572`, comentário literal |

E a assimetria deliberada que fecha o conjunto: `indeterminacaoDeclarada` **rejeita primeiro** qualquer corpo que se nomeie com outro estado e só então aplica a regra frouxa; `recusaDeclarada` é **estrita** (exige o rótulo `recusado`). Documentado como escolha de custo (`lib/trafego/lancamento.ts:59-62`) — na dúvida, o sistema prefere tratar como indeterminado, porque tratar indeterminado como recusa pode criar campanha duplicada.

---

## 3. Como cada superfície se comporta

### 3.1 Bancada — mapa de paradas

| Estado | O mapa mostra | A parada avança? |
|---|---|---|
| 1 carregando | esqueleto do mapa, 6 posições, sem palavra de estado | não |
| 3 ausência | glifo de traço na parada + "ninguém leu \<o quê\>" | **não** |
| 4 falhou | glifo de alerta + "não consegui ler" + tentar de novo | **não** |
| 7 bloqueado | cadeado + palavra + **origem** ("depende de: política") | **não** — `<span aria-disabled>`, nunca botão |
| 8 indeterminado | interrogação + "não se sabe" + o que falta ler | **não** |
| 9/10 pronto | círculo + contagem quando existir | sim |
| 16 inexistente | traço em círculo + "não se aplica a este canal" | **sai do denominador** do progresso |

⚠️ **Nunca "etapa 3 de 12" para um canal sem construtor.** Um canal que não monta não tem progresso: tem escada de portões e o próximo desbloqueio.

### 3.2 Bancada — Pedido

| Estado | A linha do Pedido |
|---|---|
| 3 ausência | `—` **acompanhado de quem não leu**. Nunca `0`, nunca em branco |
| 5 stale | o valor + "lido há 6 min" em tom de atenção |
| 6 parcial | o valor + "li 2 de 3 contas" |
| 7 bloqueado | entra em `FALTA (n)` com link para a parada dona |
| 8 indeterminado | entra em `FALTA (n)` com a leitura que falta |

`FALTA` é do servidor. O navegador não inventa item nenhum. `próximo ato` é frase, não botão — o botão vive na parada dona.

### 3.3 Ignição

| Estado | A escada |
|---|---|
| 7 destino bloqueado | para no degrau `destino`, **antes de qualquer chamada** (`Lancamento.tsx:132-135`) |
| 10 → prova | degrau `prova` com spinner funcional + cronômetro real; **sem subfase fictícia** |
| 11 provado | selo, avisos e o que a prova **não** cobre |
| 12 recusado | código, recibo e item; **mantém** "Voltar e ajustar" (`__tests__/lancamento.test.tsx:252`) |
| 13 aprovado | motivo ≥10 + caixa PAUSADA, ambos escritos ao lado do botão |
| 14 criado | recibo revelado; **"Voltar e ajustar" some** |
| 15 indeterminado | **remove** "Voltar e ajustar" (`:270`) e oferece **reconciliar** — hoje a frase existe sem o ato (`Lancamento.tsx:900-902`) |

⚠️ Correção obrigatória: o degrau `copy` tem hoje veredito **literal `ok`** (`:299`) e pode exibir `copy ✓ —`. Passa a ler o estado real e a poder reprovar.

### 3.4 Recibo

| Estado | A região |
|---|---|
| 14 criado pausado | recibo completo, **incluindo motivo declarado e impressão do pedido** — os dois campos que a ignição hoje omite e que `CartaoDeRecibo.tsx:107-114` já sabe mostrar |
| 15 indeterminado | o que se sabe + **o ato de reconciliar**, com o aviso de que reenvio é proibido |
| — | + a frase de §7.3 do mapa de autoridade: a campanha nasceu pausada e o coletor contínuo não a alcança |

### 3.5 Inventário

Herda o que já existe e funciona:

| Estado | Comportamento hoje |
|---|---|
| 2 vazio | `InventarioVazio` — "o vazio ensina o que aquilo mostraria" |
| 4 falhou | **503, nunca lista vazia** (`trafego_inventario.py:288-293`); 8 motivos fechados |
| 5 stale | `AvisoDeDadoAntigo`; frescor desconhecido **nunca** degrada para `recente` |
| 6 parcial | `AvisoDeLeituraParcial`; falha de uma conta **não contamina** as outras |

Ordem dos avisos declarada como **não estética** (`InventarioDeCampanhas.tsx:256-269`): a barra de filtros vem antes de qualquer estado de dado, inclusive do esqueleto.

### 3.6 Antessala de canal

| Estado do portão | Tom | Glifo | Palavra |
|---|---|---|---|
| `PERMITIDO` | `success` | check | permitido |
| `BLOQUEADO` | `destructive` | cadeado | bloqueado |
| `INDETERMINADO` | `warning` | interrogação em círculo | **não se sabe** |
| `NAO_APLICAVEL` | neutro | traço | não se aplica |

⚠️ `NAO_APLICAVEL` **nunca é emitido para um portão** — só para o eixo `Assets` (`contrato_canais.py:638, 656`). A linha existe para o executor não inventar um quinto tom quando encontrá-la em `Assets`.

Regra inegociável: **só `PERMITIDO` pinta positivo** (`canais.ts:485-496`). Para os sete portões de mensuração, só `PRONTO` (`portoes.ts:119-124`) — `PARCIAL` e `INDETERMINADO` caem no default `ignorado`.

### 3.7 Página canônica e fila de atenção

| Estado | Comportamento |
|---|---|
| diagnóstico ausente | quatro ramos de não-resposta, **nenhum devolve `null`** (`CampanhaCanonPage.tsx:457-473`) |
| histórico/recibos | ausência de **capacidade**, declarada com negação explícita de que algo mudou (`:292-299`) |
| estrutura do canal | ⚠️ **a única seção que hoje simplesmente não renderiza** (`:274-283`) — **corrigir**: toda seção declara ausência |
| `HEALTHY` | exige zero causas **E** evidência `apurada`; parcial → `DATA_UNAVAILABLE` (`sentinela.py:2036-2043`) |
| `CAMPAIGN_OFF` | **filtra** as candidatas: cala os degraus internos e deixa de pé só conta e destino (`:2011-2018`) |
| `LOW_DEMAND` | ⚠️ **não tem produtor**. Declarado em `PRECEDENCIA`, `ESTADOS_DE_INCIDENTE` e `SEVERIDADE`, com verbete no frontend, e **nada o emite**. A tela **não** o lista como possível até existir produtor |

---

## 4. O vocabulário fechado — palavra por estado

Uma palavra por estado, em toda a superfície. Nenhuma sinonímia.

| Estado | Palavra canônica | **Proibido** |
|---|---|---|
| 2 | "não há nenhum" | "vazio", "0 resultados", "nada encontrado" |
| 3 | "ninguém leu" | "sem dados", "N/A", "—" sozinho |
| 4 | "não consegui ler" | "erro", "falha", "algo deu errado", "Ops!" |
| 5 | "lido há \<N\>" | "desatualizado", "antigo" |
| 6 | "li uma parte" | "parcial" sozinho |
| 7 | "bloqueado" | "indisponível", "não permitido" |
| 8 | "não se sabe" | "pendente", "aguardando", "indeterminado" sozinho |
| 11 | "provado, nada criado" | "validado", "aprovado", "ok" |
| 13 | "autorizado" | "confirmado", "pronto" |
| 14 | "criada, pausada" | "criada", "sucesso", "no ar" |
| 15 | "não sei se criou" | "falhou", "erro", "tente de novo" |
| 16 | "não existe aqui" | "em breve", "indisponível", "não suportado" |

Nenhuma dessas frases usa exclamação. Nenhuma culpa o operador. Cada uma das de falha carrega um **próximo passo** — regra que `erros.ts:46-54` já impõe com oito motivos fechados.

⚠️ **Um sexto estado inventado a resolver:** `hub/contrato.ts:63-72` cria um estado visual `pendente` na frente Preparar que **não existe no vocabulário canônico do backend** — e o próprio arquivo declara isso como recusa de inventar estado. Ou o backend passa a emiti-lo, ou ele sai.

---

## 5. Combinações, e qual vence

Estados coexistem. A precedência é fixa.

**Ordem de precedência (o primeiro que casar vence):**

```
4 leitura falhou  >  7 bloqueado  >  8 indeterminado  >  5 stale  >  6 parcial  >  3 ausência  >  2 vazio  >  9/10 pronto
```

Justificativa, item a item:

- **4 antes de tudo:** se a leitura falhou, nada do que veio é confiável.
- **7 antes de 8:** um bloqueio medido é mais informativo que uma leitura ausente — e mais acionável.
- **8 antes de 5:** não saber é pior que saber com atraso.
- **3 depois de 5 e 6:** ausência de um campo não deve esconder que a leitura inteira está velha ou parcial.
- **2 por último entre os negativos:** "não há nenhum" só é dizível quando a leitura foi completa, recente e bem-sucedida.

A sentinela aplica a mesma disciplina no seu domínio: `PRECEDENCIA` é aplicada **uma vez sobre o conjunto inteiro** de causas candidatas, depois de todas as sete famílias serem coletadas (`sentinela.py:2002-2024`) — nunca na ordem de avaliação.

**Regra de exibição:** um estado dominante por região (`design.md`, "One Dominant Signal"). Os subordinados viram **uma frase de evidência**, nunca uma pilha de chips.

---

## 6. Estados que a tela nunca inventa

| Nunca | Porque |
|---|---|
| "tudo certo" por lista vazia | vazio ≠ saudável |
| `0` para ausência | `Sinal(0.0, AUSENTE)` levanta exceção no servidor; a tela não pode ser mais frouxa |
| "pronto" por ausência de bloqueio conhecido | `paid_destination_ready` exige **zero desconhecidos**, não só zero bloqueios (`portao.py:92-96`) |
| "sucesso" por `registrado: false` | proibição explícita no contrato (`types/trafego.ts:727-742`) |
| um quinto tom de portão | quatro estados, quatro tons |
| "em breve" para capacidade inexistente | ou existe próximo desbloqueio nomeado, ou é "não existe aqui" |
| barra determinada sem denominador real | se o total é desconhecido, há um contador do que já foi lido |

---

## 7. O que persiste, e onde

| Estado | Persiste em | Sobrevive a F5? |
|---|---|---|
| 5 stale | carimbo do servidor | sim |
| 7 bloqueado | contrato do servidor | sim |
| 11 provado | selo (`preparo.selo.impressao`) | sim, enquanto o selo valer |
| 13 aprovado | recibo | sim |
| 14/15 | ledger | sim |
| **escolhas do operador** (marcadas, exclusões, lance, orçamento, estratégia, certificações) | ⚠️ **nada** | **não** |

`grep -c 'localStorage\|sessionStorage' src/pages/trafego/NovaCampanhaPage.tsx` → **0**. Não há escrita na URL (`grep 'setSearchParams\|useNavigate'` → 0). Não existe rota de rascunho (`grep 'rascunho_da_campanha\|/escolha'` → 0).

**Consequência hoje:** um F5 desfaz a triagem inteira — e as `marcadas` voltam repostas pela **pré-marcação automática** (`:164-167` marca **todas**), não pela escolha do operador. O operador pode não perceber que perdeu a curadoria.

**Contrato alvo — decidido, não deixado para o executor.** A parada atual vive na URL (`?etapa=`). As escolhas vivem em **`sessionStorage`**, chaveadas por `opportunityId` + `run`, e a tela **declara** que são locais e não foram salvas.

**Por que `sessionStorage` e não rascunho de servidor:** rascunho de servidor exige rota, armazenamento, identidade e política de concorrência — quatro decisões de arquitetura que esta lane não pode tomar e que nenhuma fatia dimensiona. `sessionStorage` é reversível, não cria contrato novo e resolve o caso real (o F5 acidental). O rascunho de servidor **fica como tarefa própria** no handoff, com o custo nomeado; ele não é pré-requisito de nada.

**O que isso implica, e a tela diz:** as escolhas **não** sobrevivem a outra máquina, outro navegador ou aba anônima, e **não** são vistas por mais ninguém. E a assimetria de reposição hoje (`vertical` é reposta, `certificacoes` salvas na mesma linha **nunca são lidas de volta** — `:254-261`) é corrigida: ou repõe as duas, ou nenhuma.
