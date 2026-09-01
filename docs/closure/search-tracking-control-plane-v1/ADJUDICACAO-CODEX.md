# Adjudicação — revisão adversarial Codex `gpt-5.6-sol` (effort high)

**Data:** 2026-09-02 · **Uma rodada, como mandado.**
**Veredito:** **REPROVOU** com 2 BLOQUEANTES, 7 IMPORTA e 1 MENOR.
**Minha adjudicação: os dez procedem.** Todos corrigidos, com prova que falhava
antes em `backend/tests/test_trafego_revisao_adversarial.py` (23 provas).

A regra dada ao revisor foi "achado sem contraprova executável é descartado".
Ele devolveu contraprova que roda para os dez, e conferi cada uma reproduzindo
por conta própria antes de mexer no código.

---

## Os dois BLOQUEANTES, e o que eles tinham em comum

Os dois eram **a mesma família**: conferir a **COLUNA** e devolver o **PAYLOAD**.

A linha do banco tem `customer_id` como coluna consultável e o plano inteiro em
`payload`. Eu conferia a coluna — que é o que a consulta filtrou — e devolvia
(ou regravava) o payload, que ninguém tinha olhado.

**Uma consulta é uma INTENÇÃO; a conferência é um FATO.** Eu estava conferindo a
intenção e chamando isso de portão. A ironia é que o comentário que escrevi na
própria guarda dizia a frase certa ("um filtro é uma intenção e a conferência é
um fato") sobre a metade errada do problema.

### Achado 9 — `GET /plano-de-mensuracao` devolvia payload de outra conta

```
coluna 5478096539 · payload_devolvido 4820015411 · persistido True
```

Reproduzi por conta própria antes de aceitar. **Conserto:** depois de
`pm.do_json`, o plano reconstruído é confrontado com `cid` **e** `mid` — o MCC
entra junto porque um plano do MCC errado descreve outra hierarquia, e é a
hierarquia que decide de quem é a ação de conversão. Recusa 409, e a conta
alheia **não aparece** na mensagem: recusar não é vazar.

### Achado 10 — a reconciliação regravava payload alheio

```
vinculado True · documento_customer_id 4820015411
volc_campaign_id d596aba4-585e-5d0c-abd6-7e3c72d48434
```

Pior que o 9: aqui o `volc_campaign_id` era derivado da conta **pedida** e o
documento gravável ficava na conta **alheia**. A linha apontaria uma campanha de
uma conta para o plano de outra — e, sendo append-only, ficaria lá.

**Conserto:** conferência de `customer_id` do payload reconstruído antes de
`_gravar_plano`.

⚠️ **O portão de conta que EU tinha acrescentado nesta mesma missão foi o que
criou a falsa sensação de cobertura.** Ele fechava a porta certa pelo lado
errado, e sem a revisão eu teria entregue achando que estava fechada.

---

## Os oito restantes

| # | severidade | achado | veredito |
|---|---|---|---|
| 1 | IMPORTA | `activation_ready=PRONTO` com `campaign_birth=NAO_PRONTO` | **procede** |
| 2 | IMPORTA | `Prontidao(smart_bidding_eligible=True)` → `smart_bidding_ready=PRONTO` sem evidência | **procede** |
| 3 | IMPORTA | estratégia desconhecida atravessava quando a medição estava PRONTA | **procede** |
| 4 | MENOR | `RegraDeValor` aceitava valor negativo/não finito | **procede** |
| 5 | IMPORTA | `_slug` prometia canonicalizar `BPC/LOAS` e não canonicalizava | **procede** |
| 6 | IMPORTA | moeda do evento não validada — `💩` passava como `currencyCode` | **procede** |
| 7 | IMPORTA | consentimento fora da impressão do envelope | **procede** |
| 8 | IMPORTA | mesmo instante em dois fusos → impressões diferentes | **procede** |

### 1 — ativação pronta para campanha que não nasceu

```
NAO_PRONTO PRONTO ()
```

A resposta afirmava, ao mesmo tempo, que a campanha não nasceu e que despausá-la
era seguro — com a lista de bloqueadores **vazia**. Meu próprio fixture
(`_pronta()`) passa `recibo_registrado=True`, então eu nunca tinha visto o ramo.

**Conserto:** `campaign_birth == PRONTO` entra na propriedade, e um bloqueador
não material nomeia a ausência do nascimento.

### 2 — derivar não basta se a fonte da derivação for escrevível

Eu tinha trocado os dois portões de campo para propriedade justamente para tornar
a contradição inexpressável. Funcionou para o par estado/estado — e o
**booleano continuou sendo campo**. `Prontidao(smart_bidding_eligible=True)`
produzia `PRONTO` com medição e observabilidade indeterminadas.

**Conserto:** `__post_init__` recusa elegibilidade sem as duas provas.

Isso quebrou duas fixtures existentes que afirmavam `eligible=True` com estados
indeterminados — combinações que `avaliar` nunca produz. Eu as corrigi em vez de
afrouxar a invariante, e a razão está escrita dentro de cada uma.

### 3 — o fail-closed que só valia no caso já fechado

```
ATRAVESSOU PRONTO
```

`ESTRATEGIA_INVENTADA` com `measurement_ready=PRONTO` passava, porque o
desconhecido caía no ramo "aprende de conversão" — que só recusa quando a
medição já recusa. Ou seja: nunca.

⚠️ E a defesa "o `Brief` de Search intercepta antes" é exatamente o arranjo que
esta missão existe para desfazer: **depender da guarda de outro módulo para
cumprir o contrato deste**.

**Conserto:** `ESTRATEGIAS_CONHECIDAS` como união fechada
(`SEM_APRENDIZADO` + `POR_CONTAGEM` + `EXIGEM_VALOR`), e o desconhecido é
recusado **antes** de qualquer avaliação de medição. `TARGET_ROAS` e
`TARGET_CPA` entraram na classificação — `TARGET_ROAS` é por VALOR, e antes ele
era tratado como por contagem.

### 5 — a docstring prometia o que o código não fazia

```
bpc/loas bpc-loas False
```

Minha própria docstring dizia que `BPC/LOAS` e `bpc-loas` eram a mesma oferta.
`strip().lower()` não faz isso.

Havia duas saídas, e **não escolhi a sugerida**. O revisor propôs canonicalizar
separadores; eu recusei e **recuso o não canônico**:

- **fundir** `/` em `-` é um *merge silencioso*. `x/y` e `x-y` podem ser ofertas
  genuinamente diferentes, e a fusão **some** com uma delas — que é o defeito
  oposto ao que o módulo combate, e mais caro, porque duplicata se vê e
  desaparecimento não;
- **recusar** faz o erro aparecer no primeiro uso, com o campo e o caractere
  ofensor, e não seis meses depois num relatório que não fecha.

A docstring foi corrigida para dizer o que o código faz.

### 7 e 8 — a impressão do envelope repetindo a lição do plano

Os dois são a mesma família do defeito que a impressão do PLANO já tinha
corrigido **duas vezes** (frescor de fora; estados de leitura de fora): **o que
decide o veredito tem de entrar na identidade**, ou o segundo é lido como retry
do primeiro.

- **7:** consentimento muda o item de `valido` para `recusado` e não entrava na
  impressão — dois lotes com vereditos opostos colidiam.
- **8:** `2026-09-01T12:00:00-03:00` e `...15:00:00Z` são o mesmo instante e
  davam impressões diferentes. O conserto canonicaliza para UTC **e devolve o
  texto cru quando não dá para interpretar** — a impressão não pode depender de
  o evento ser válido, senão falha parcial vira falha total pela porta dos
  fundos. Há prova disso (`test_hora_ilegivel_nao_derruba_a_impressao`).

---

## O que ele NÃO achou, e disse em voz alta

- **Área 3 (ordem em `/subir`):** *"O portão está antes de `ledger.abrir`,
  `ledger.despachar`, persistência do plano e `sb.subir`; `PortaoFechado` vira
  409. Não encontrei mutação material nem caminho reproduzível para 500."*
- **Área 5 (impressão do plano):** o hash congelado da base foi confirmado —
  `test_plano_sem_perfil_mantem_a_impressao_anterior_byte_a_byte: PASS`. *"Não
  consegui provar outra colisão de decisão no plano."*
- **Vazamento de dado de usuário:** *"o teste com valor `SEGREDO` imprimiu
  `segredo_no_recibo False`, e o valor também não entra no corpo da impressão. O
  caminho `enviar()` continua recusando estruturalmente."*

---

## Gates depois da rodada corretiva

| gate | antes da revisão | depois | veredito |
|---|---|---|---|
| `pytest backend/tests volc_ads -q` | 2859 · 30 · 0 | **2882 · 30 · 0** | +23 = as provas da revisão |
| `npx vitest run` | 1208 · 5 · 0 | **1210 · 3 · 0** | as duas `skipIf(semBuild)` passaram a rodar porque `dist/` existe |
| `npx tsc --noEmit -p tsconfig.app.json` | 76 | **76** | igual ao baseline |
| `npm run build` | verde | **verde** | |
| `scripts/gate_sem_mutacao_google.py` | 3/3 | **3/3** | |
| `git diff --check` | limpo | **limpo** | |

**Nenhuma segunda rodada foi aberta.** O contrato era uma revisão focal e uma
rodada corretiva, e é isso que está aqui.
