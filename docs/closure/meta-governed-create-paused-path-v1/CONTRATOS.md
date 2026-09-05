# Contratos — aprovação, recibo e reconciliação do nascimento Meta PAUSED

Três contratos novos, e cada um existe porque sem ele uma afirmação da tela
seria indistinguível de uma promessa. Este documento é a referência normativa:
o código o implementa, os testes o exercitam, e um leitor que discorde de algo
aqui deve discordar antes de mudar o código.

---

## 1. Contrato do recibo durável de `validate_only`

### O problema

Até esta missão, `POST .../criacao/validar` devolvia a prova ao navegador e a
esquecia. `ResultadoValidacaoMeta` é uma dataclass congelada que virava JSON e
morria. Uma rota de aprovação construída sobre isso teria exatamente uma fonte
para "este plano foi validado": **o cliente dizendo que sim**.

Um navegador que afirma o próprio recibo verde não é uma falha teórica. É o
caminho mais curto entre uma aba aberta e uma campanha criada sem que a Meta
tenha olhado o payload.

### A tabela

`public.trafego_meta_validation_receipt`

| Coluna | Regra |
|---|---|
| `validation_id` | uuid, chave. A **única** coisa que o navegador recebe. |
| `plan_sha256` | `^[a-f0-9]{64}$`. Identidade canônica do plano compilado. |
| `account_ref` | referência **opaca**, nunca o id da conta. |
| `actor_id` | quem clicou. |
| `api_version` | fixo em `v26.0`. |
| `coverage` | `CHECK (coverage = 'INDEPENDENT_ROOTS_ONLY')` |
| `steps_validated` | não vazio. Um recibo que não validou nada não prova nada. |
| `steps_pending` | pode ser vazio. |
| `operations_total` | `= cardinality(validated) + cardinality(pending)` |
| `objects_created` | `CHECK (objects_created = 0)` |
| `accepted` | `CHECK (accepted)` |
| `validated_at` | carimbo do servidor. |

**Por que `coverage` é literal.** `INDEPENDENT_ROOTS_ONLY` é a única cobertura
que `validar_raizes` sabe produzir — AdSet e Ad carregam marcadores de
dependência e a Meta não aceita filho antes do pai. Gravar qualquer outra
palavra faria uma aprovação futura acreditar numa validação mais ampla do que a
que aconteceu. O `CHECK` transforma isso em impossibilidade.

**Por que `objects_created` existe.** A afirmação "zero objetos" precisa estar
gravada como número, não subentendida pelo nome da tabela.

### Quem escreve

Só `trafego_meta_create_record_validation`, chamada pelo backend **depois** de a
Meta responder `success`. `anon` e `authenticated` não têm grant nenhum; nem
`service_role` tem `INSERT`.

### Falha fechada

Se `META_CREATE_LEDGER_WRITE_ENABLED` estiver fechada, a gravação falha e a
resposta declara `prova_duravel.registrada = false` com o motivo. A validação
**continua verdadeira** — a Meta respondeu, nada foi criado — e o que fica
impossível é aprovar. Apagar o resultado da validação porque o ledger está
fechado seria mentir na direção oposta.

---

## 2. Contrato da aprovação

`public.trafego_meta_create_approval`

Uma aprovação existe **se e somente se** todos estes vínculos forem verdadeiros
ao mesmo tempo:

| Vínculo | Coluna / verificação | Recusa |
|---|---|---|
| ator | `actor_id` = o ator do recibo de validação | `META_VALIDATION_ACTOR_DIVERGED` |
| conta opaca | `account_ref` = a do recibo | `META_VALIDATION_ACCOUNT_DIVERGED` |
| plano | `plan_sha256` = o do recibo | `META_VALIDATION_PLAN_DIVERGED` |
| manifesto ordenado | `steps_expected`, derivado do plano compilado | `META_VALIDATION_MANIFEST_DIVERGED` |
| orçamento diário | `daily_budget_minor`, minor units, `> 0` | — |
| moeda | `currency`, `CHECK = 'BRL'` | `META_CURRENCY_UNSUPPORTED` |
| operações | `operations_expected = cardinality(steps_expected)` | `META_VALIDATION_MANIFEST_DIVERGED` |
| expiração curta | `expires_at ≤ approved_at + 1h` no `CHECK`; 15 min na rota | `META_APPROVAL_EXPIRY_TOO_LONG` |
| timestamp | `approved_at`, `clock_timestamp()` do servidor | — |
| nascimento PAUSED | `paused_birth_confirmed`, `CHECK (paused_birth_confirmed)` | `META_PAUSED_BIRTH_NOT_CONFIRMED` |
| validação viva | `validation_id` NOT NULL, UNIQUE, FK, e idade ≤ 30 min | `META_VALIDATION_RECEIPT_NOT_FOUND` / `_STALE` |
| pedido do operador | `plan_request` jsonb, objeto, ≤ 60 kB | `META_APPROVAL_PLAN_REQUEST_INVALID` |

### Por que `validation_id` é UNIQUE

Um recibo autoriza uma aprovação e **só uma**. Reaprovar depois de expirar exige
validar de novo — e isso é correto, não incômodo: a conta pode ter mudado de
saldo, de Página ou de biblioteca de imagens entre uma tentativa e outra. O
`UNIQUE` também mata o replay de uma prova antiga.

### Por que `plan_request` é armazenado

Porque a criação recebe **apenas** `approval_id` e `plano_sha256_esperado`. Sem o
pedido gravado, o servidor não teria como reconstruir o payload e teria que
aceitá-lo do navegador — que é exatamente o que a missão proíbe.

O que é gravado são as **referências opacas** e o texto do operador. Nenhum
identificador bruto da Meta, nenhum `image_hash`, nenhum token: esses vivem só
em `ReferenciasMetaResolvidas`, dentro do processo, e são re-resolvidos a cada
recompilação. Se a Página ou a imagem mudarem de identidade entre a aprovação e
a criação, o hash recompilado diverge e a criação para — que é a propriedade
desejada.

### Uma aprovação viva por plano

`pg_advisory_xact_lock(hashtextextended(plan_sha256, 1602))` mais uma sonda por
`EXISTS`. **Não** é um `UNIQUE`: expiração e falha precisam liberar o plano,
ambiguidade precisa prendê-lo. Provado com duas conexões simultâneas em
PostgreSQL descartável, e cada sessão traz o seu próprio recibo — senão o que
barraria a segunda seria o `UNIQUE(validation_id)`, e a prova do lock não
existiria.

---

## 3. Contrato do recibo da saga

`public.trafego_meta_create_step`, um passo por operação do manifesto.

### A ordem, e o que ela garante

Para cada passo, **nesta ordem**:

1. resolver dependências (ids reais dos passos anteriores);
2. exigir `status == "PAUSED"` no payload, para todo objeto veiculável;
3. `validate_only` do degrau já resolvido;
4. **preparar o recibo** — `INSERT` commitado — e só então;
5. `POST` de criação;
6. interpretar a resposta;
7. read-back por `GET`;
8. validar pertencimento (conta), estado e campos;
9. fechar o passo;
10. só então avançar.

O passo 4 antes do 5 é o contrato inteiro: um objeto que nasce sem recibo é um
objeto que ninguém consegue reconciliar.

### Estados e transições

```
                    prepare_step
                         │
                         ▼
                    IN_FLIGHT ──── close_step ────► CREATED
                         │                             ▲
                         ├──── fail_step ────► FAILED  │
                         │   (recusa PROVADA da Meta)  │
                         │                             │
                         └──── mark_ambiguous ──► AMBIGUOUS
                                                   │   │
                            resolve_absent ────────┘   │
                            (ausência PROVADA,         │
                             passo com ≥120 s)         │
                                   ▼                   │
                                FAILED      close_step ┘
                                            (presença PROVADA)
```

⚠️ `fail_step` recusa `AMBIGUOUS` de propósito. Uma recusa escrita da Meta prova
que nada nasceu; um silêncio não prova nada. Só a leitura da conta desempata, e
`resolve_absent` é o registro dessa leitura.

⚠️ **`resolve_absent` também recusa um passo jovem demais.** Um passo vira
`AMBIGUOUS` assim que uma segunda chamada reentra nele — e isso pode acontecer
com a primeira ainda dentro do `await` do `POST`, antes de a Meta receber
qualquer coisa. Fechar como ausente nesse instante gravaria "não existe" sobre
um objeto prestes a nascer, e liberaria uma nova aprovação sobre ele. O piso é
de 120 s contra um cliente HTTP de 20 s; a RPC recusa qualquer janela abaixo de
60 s.

### A identidade do objeto, e não a do plano

`UNIQUE (approval_id, step_name)` protege **uma saga contra si mesma**. A
aprovação única por `plan_sha256` protege **um plano contra si mesmo**. Nenhum
dos dois protege a **conta**, e o buraco entre eles era concreto:

1. o operador aprova P1 e a campanha nasce;
2. o AdSet falha — o que **libera** o plano para nova aprovação;
3. o operador corrige a headline de um anúncio;
4. mudar um filho muda o `plan_sha256` do plano inteiro, e o payload da Campaign
   continua **byte a byte o mesmo**;
5. P2 é aprovado, o ledger novo começa em `campaign`, responde `DESPACHAR` — e a
   mesma campanha nasce pela segunda vez.

`trafego_meta_create_prepare_step` passou a sondar por **(conta, nome do passo,
`payload_sha256`)** antes de despachar, sob lock consultivo (salt 1603):

| Gêmeo encontrado | Resultado |
|---|---|
| `CREATED` | a saga nova **adota** o objeto: grava a própria linha `CREATED` com o mesmo id externo e segue **sem um único POST** |
| `IN_FLIGHT` ou `AMBIGUOUS` | `META_STEP_DUPLICATE_IN_FLIGHT` — pode existir objeto do outro lado, e só a reconciliação desempata |

### O read-back divergente fica gravado

O recibo fecha **antes** do read-back, e essa ordem é deliberada: o id que a Meta
acabou de devolver precisa estar gravado antes de qualquer outra coisa, senão uma
queda entre o `POST` e o `INSERT` perde para sempre a única prova de que o objeto
nasceu.

O preço dessa ordem é que uma divergência de leitura deixava o livro dizendo
apenas `CREATED`. `readback_error` é o conserto desse preço, sem inverter a
ordem que protege o id: a resposta HTTP diz 502, e o recibo passa a dizer o
mesmo.

### O que o recibo nunca devolve

`external_object_id`. O recibo diz `has_external_id: true|false` e nada mais.
O identificador da Meta não entra em nenhum corpo JSON que possa acabar num log.

---

## 4. Contrato da ambiguidade

Depois de um despacho, se o transporte for incerto:

- estado do passo: **AMBIGUO**;
- `retry_permitido`: **false**, sempre;
- o lote **para**: nenhum filho é preparado ou criado;
- nenhum reenvio automático, em nenhuma circunstância;
- HTTP **502**, nunca 422 (que significaria "a Meta olhou e recusou") e nunca
  504 retentável.

### Reconciliação — as três conclusões

| Leitura da conta | Conclusão | Efeito no ledger |
|---|---|---|
| exatamente um objeto, read-back completo confere **e** `created_time` posterior ao `prepared_at` | `FECHADO_COMO_CRIADO` | `close_step` com o id lido |
| listagem completa, nenhum objeto com aquele nome, passo com ≥120 s | `FECHADO_COMO_NAO_ENCONTRADO` | `resolve_absent` |
| listagem incompleta, dois homônimos, read-back divergente, erro de leitura, **objeto anterior ao despacho**, **tipo sem `created_time`** | `PERMANECE_AMBIGUO` | nada |

**Não conseguir provar a ausência não é prová-la.** Fechar um passo por
"provavelmente não nasceu" autorizaria um reenvio sobre um objeto que existe.

### Nome igual não prova nascimento

A unicidade de nome que o contrato garante vale **dentro do lote**, nunca dentro
da conta. Uma campanha antiga, homônima e com a mesma receita passaria por todo
o read-back — e fechar o passo com o id dela penduraria o AdSet novo numa
campanha de outra semana.

A identidade tem três camadas, e as três precisam passar:

1. **nome** — encontra exatamente um candidato na aresta certa da conta certa;
2. **`_validar_read_back` completo** — o mesmo do executor, sem afrouxar nada;
3. **correlação temporal** — o `created_time` do objeto tem de ser posterior ao
   `prepared_at` do recibo, com 5 minutos de folga de relógio.

⚠️ `AdCreative` **não expõe `created_time`** na Marketing API. A consequência é
deliberada: **um criativo nunca é fechado por leitura**. Ele permanece ambíguo,
porque a leitura não consegue prová-lo — e inventar a prova seria pior do que
não tê-la.

A reconciliação percorre o manifesto **inteiro**, em ordem, porque os ids dos
passos anteriores são o que prova o pertencimento dos seguintes — e o ledger,
de propósito, nunca os devolve.

Nenhum `POST` sai da rota de reconciliação. Reenviar continua sendo uma decisão
humana, tomada depois de o recibo estar fechado.

---

## 5. As autorizações

| Variável | O que autoriza |
|---|---|
| `META_CREATE_PAUSED_ENABLED=1` | o ato de criar objetos reais |
| `META_CREATE_LEDGER_WRITE_ENABLED=1` | a escrita do recibo durável |

As duas, sempre. Com qualquer uma fechada: HTTP 409
`META_CREATE_PAUSED_BLOCKED`, zero Keychain, zero Supabase, zero HTTP para a
Meta — medido por armadilhas nos testes, não suposto.

⚠️ `META_VALIDATE_ONLY_ENABLED` **não** entra nessa lista e nunca deve entrar.
Ela autoriza uma chamada que não cria nada. Reaproveitá-la como autorização de
criação faria a licença de olhar virar licença de gastar.

A saga chama `validate_only` internamente antes de cada degrau. Essa validação
pertence ao ato de criar e é autorizada por `META_CREATE_PAUSED_ENABLED` — não
pela flag da rota de validação.

---

## 6. Os três status HTTP, e por que são três

| Status | Significado | `retry_permitido` |
|---|---|---|
| **409** | uma guarda local ou durável recusou. Nada foi despachado. | — |
| **422** | a Meta olhou o pedido e o reprovou. Está **provado** que nada nasceu. | conforme o erro |
| **502** | houve despacho e o resultado é **desconhecido**. | sempre `false` |

A diferença entre 422 e 502 é a diferença entre reenviar e duplicar. Um único
status para os dois ensinaria o operador a ler silêncio como reprovação.

⚠️ **Quem classifica é a saga, não a rota.** A primeira versão tinha uma lista de
códigos no mapeador de erros, e a lista errava: um 500 da Meta depois do `POST`
levanta `META_REMOTE_CREATE_FAILED` com `criacao_descartada=False`, o executor
marca o passo `AMBIGUOUS` no banco — e a resposta dizia 422 com
`reconciliacao_necessaria=false`. O ledger e o protocolo contavam histórias
diferentes sobre o mesmo despacho.

`ErroRemotoMeta.exige_reconciliacao` é marcada no ponto exato em que a saga
deixa um passo ambíguo, e viaja com a exceção — inclusive através do
reempacotamento que acrescenta `objetos_criados`.
