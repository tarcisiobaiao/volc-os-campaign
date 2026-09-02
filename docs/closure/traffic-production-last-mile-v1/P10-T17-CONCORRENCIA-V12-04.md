# P10-T17 — a concorrência da RPC v12_04, provada

> Documento exigido pelo próprio `acceptance` da tarefa: *"O aceite exige teste
> automatizado vermelho antes da correção, verde depois, ciclo
> apply→operate→rollback→reapply verde e **documentação da semântica** antes de
> aplicar v12_04 em produção."*

| | |
|---|---|
| Branch | `sprint/traffic-production-last-mile-v1` |
| Base | `c8ca8628e83742dd7da5242f0a015f76292aafe7` (`origin/volc-os-v2`) |
| Commits | `48d9fc0` (precedência, idempotência, recibo) · `79770a5` (projeção legada) · `c299274` (espera circular da trava) |
| Arquivo | `supabase/migrations/v12_04_gads_fato_canonico_dia.sql` |
| sha256 depois | `daad5a56d571521e5a4d690ecd1786d7ab4a04b3dd13ad0851ac0fc588911008` |
| Rollback | `supabase/migrations/v12_04_rollback.sql` · `583a2f7189db739feeed944cb3bd51e4a333a878cadbaa366ec9511cb95cbee3` |
| Aplicada no Supabase oficial? | **NÃO.** Medido em leitura read-only: 0 de 3 relações e 0 de 4 funções existem |

---

## Por que 107 provas verdes não provavam nada disto

`scripts/provar-ciclo-v12_04.sh` roda 107 contraprovas e passa inteiro. Todas
rodam em **uma sessão**, uma chamada de cada vez.

Todas as invariantes da v12_04 que dependem de "ler, decidir, escrever" eram
defendidas por um `SELECT` que roda **antes** do `INSERT`, sobre um snapshot que
pode ter mudado quando a escrita acontece. Em série isso nunca aparece — o
`SELECT` sempre enxerga o que a chamada anterior já commitou. É por isso que uma
prova serial de precedência passa e a precedência mesmo assim não existe.

O defeito não estava nas provas. Estava no eixo que elas não tinham.

## O harness: por que a corrida é determinística, e não sorteada

`scripts/provar-concorrencia-v12_04.sh` mantém **duas sessões psql vivas**,
alimentadas por FIFO, para controlar as fronteiras de transação. Nada nele dorme
esperando dar sorte:

- **fim de comando** — sentinela `\echo` no stdout daquela sessão;
- **bloqueio real** — `pg_stat_activity.wait_event_type = 'Lock'` para o
  `application_name` da sessão, lido por uma **terceira** conexão.

Se o bloqueio esperado não acontece, o degrau **falha** em vez de passar. Uma
corrida que não foi encenada não pode ser reportada como corrida vencida.

O cluster nasce e morre no script (`postgres:16-alpine` em docker). **Nunca fala
com `database.agenciavolc.com.br`.**

---

## O vermelho, medido

Contra o código de `c8ca862`: **16 de 23 degraus falharam.** (O roster cresceu para 35
degraus ao longo da missão: C8/C9 vieram de uma revisão adversarial do preflight, e
C10 de revisar a correção de C8.)

Os 7 que passaram importam tanto quanto os 16: eles provam que o harness mede
estado real e não reprova tudo por construção. Uma prova que fica vermelha em
tudo não distingue defeito de arranjo quebrado.

### C1 · a precedência não existia

```
FALHOU  C1.2 a precedência que sobreviveu é a de D-1 (2) — obtido [1], esperado [2]
FALHOU  C1.3 a origem que sobreviveu é D-1 — obtido [D0], esperado [D-1]
FALHOU  C1.4 a janela continua FECHADA — obtido [f], esperado [t]
FALHOU  C1.5 o D0 preterido contou como PRETERIDA — obtido [0], esperado [1]
FALHOU  C1.6 o D0 preterido NÃO contou linha aceita — obtido [1], esperado [0]
```

Um D0 intradia sobrescreveu um D-1 de **janela fechada**, e `janela_fechada`
voltou de `true` para `false`. A invariante 3 do cabeçalho da migration —
*"Janela fechada nunca é rebaixada por leitura intradia"* — não valia.

E o segundo dano é pior que o primeiro: a degradação foi contada como
`linhas_aceitas`. O recibo registrava como sucesso o ato de destruir o dado bom.

**Causa:** o `ON CONFLICT ... DO UPDATE` não tinha `WHERE`. As duas sessões leem
"a linha não existe", as duas decidem gravar, a primeira commita, e o `UPDATE`
da segunda aplica uma decisão tomada sobre um snapshot que já morreu.

### C2 · o desempate por `colhida_em` também não

```
FALHOU  C2.1 a leitura MAIS NOVA sobreviveu (impressoes=99) — obtido [7]
FALHOU  C2.2 a colhida_em preservada é a de 18:00 — obtido [06:00]
```

Mesma causa, mesmo posto: venceu quem commitou por último.

### C7 · nem o backfill

```
FALHOU  C7.1 o backfill sobreviveu (impressoes=555) — obtido [1]
FALHOU  C7.2 a precedência final é 3 (backfill) — obtido [2]
```

### C3/C4 · a idempotência devolvia o índice cru

```
FALHOU  C3.1 ... contém [duplicate key value]:
        ERROR: duplicate key value violates unique constraint "trafego_coleta_execucao_pkey"
FALHOU  C4.1 a recusa é NOMEADA pelo contrato — não contém
        [CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE]
```

A checagem de idempotência morava num `SELECT` no topo da função. Duas sessões
de mesma chave o atravessam antes de qualquer commit, e a segunda só descobria a
verdade no índice único. O chamador recebia uma violação de constraint sem o nome
do contrato — que um retry de n8n lê como falha de infraestrutura. No caso
divergente era pior: a recusa que devia se chamar
`CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE` chegava disfarçada de erro de banco.

### C6 · a execução superada nunca mais fechava

```
FALHOU  C6.2 ... contém [RECIBO_NAO_RESOLVE_FATOS]:
        ERROR: RECIBO_NAO_RESOLVE_FATOS: ledger diz 1 aceitas e a tabela tem 0
FALHOU  C6.3 o recibo de fechamento de X existe — obtido [0], esperado [1]
```

O fechamento comparava uma alegação **histórica** ("aceitei 1") contra o estado
**vivo** ("hoje você não possui nenhuma"). Quando uma execução de posto maior
legitimamente superava a linha, a execução superada não conseguia mais fechar —
e o deadman ficava olhando uma corrida eternamente aberta. Um alarme falso
nascido de um sucesso.

### C8/C9 · a projeção legada escolhia um número

Estes dois vieram de uma revisão adversarial do preflight, **depois** da primeira
correção. São o único caminho de escrita cujo dano é permanente: o rollback da
v12_04 não desfaz projeção.

```
FALHOU  C8.2 ao menos um recibo recusou a projeção por ambiguidade — obtido [0]
FALHOU  C8.3 NÃO existem dois recibos dizendo 'aplicada' — obtido [2]
FALHOU  C9.2 a projeção NÃO declara ter aplicado duas linhas — obtido [2]
FALHOU  C9.3 a projeção recusa por ambiguidade — obtido [aplicada]
FALHOU  C9.4 a legada NÃO recebeu número de segmento arbitrário — obtido [20]
```

`daily_campaign_metrics` é endereçada por `(campaign_id, date)` e mais nada; a
chave canônica tem quatro partes. A projeção é uma redução **com perda**, e a
v12_04 já sabia disso: recusa por ambiguidade. Só que a ambiguidade era um
`EXISTS` num snapshot — em série ele sempre enxerga a linha anterior (é o que
CP-19 mede), e com as duas transações abertas nenhuma enxerga a outra, porque as
chaves canônicas são **diferentes** e não bloqueiam uma à outra em lugar nenhum.

E C9 nem precisa de corrida: a guarda comparava só `customer_id`, ignorando
`segments_hash`. Duas linhas legítimas da mesma conta com segmentos diferentes
caem na mesma linha legada — as duas projetavam, a segunda sobrescrevia a
primeira, e o recibo contava **duas aplicadas numa tabela que tem uma linha**.
A legada ficou com `impressions=20`, o segmento DESKTOP, escolhido porque veio
por último. Passou despercebido porque nenhuma contraprova enviava dois segmentos.

---

## A semântica nova, item a item

### 1. A precedência é avaliada NO MOMENTO DA ESCRITA

```sql
ON CONFLICT (customer_id, campaign_id, metric_date, segments_hash)
DO UPDATE SET ...
WHERE EXCLUDED.precedencia > g.precedencia
   OR (EXCLUDED.precedencia = g.precedencia
       AND EXCLUDED.colhida_em >= g.colhida_em);
GET DIAGNOSTICS v_escritas = ROW_COUNT;
```

A condição é a **negação exata** da regra antiga (`pretere quando o posto é
menor, ou quando empata no posto e a colheita é mais velha`), então empate exato
de posto **e** de relógio continua escrevendo: releitura idêntica não é
rebaixamento.

A contagem passou a vir do `ROW_COUNT` real. Contar antes de escrever era
exatamente como a degradação silenciosa entrava no recibo como sucesso.

### 2. A colisão de chave responde pelo contrato

```sql
INSERT INTO public.trafego_coleta_execucao (...) VALUES (...)
ON CONFLICT (chave_idempotencia) DO NOTHING;
GET DIAGNOSTICS v_gravou = ROW_COUNT;
IF v_gravou = 0 THEN
  SELECT * INTO v_existente FROM ... WHERE chave_idempotencia = v_chave;
  IF NOT FOUND OR v_existente.payload_sha256 <> v_payload THEN
    RAISE ... 'CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE ...';
  END IF;
  RETURN <recibo guardado>;
END IF;
```

`execucao_id` é derivado da `chave_idempotencia` por `volc_gads_uuid_da_chave`,
então PK e unique colidem juntas e a mesma guarda cobre as duas.

No caminho divergente o `RAISE` derruba a transação inteira — inclusive o fato
que aquele lote escreveu antes. **Payload divergente não deixa rastro.**

Um efeito colateral que vale nomear: a guarda `FATO_DUPLICADO_NA_EXECUCAO`
deixou de disparar quando `v_atual.execucao_id = v_exec_id`. Igualdade ali
significa que a **mesma chave** já escreveu — retry idempotente cuja corrida
passou por baixo da checagem do topo, não duplicata de execução. Lotes diferentes
da mesma `execucao_chave` têm chaves diferentes, e continuam pegos.

### 3. Supersessão legítima fecha como `parcial`, com nome

```sql
v_superadas := v_soma.aceitas - v_fatos;
IF v_superadas > 0 THEN
  v_resultado := 'parcial';
  motivo := 'LINHAS_SUPERADAS_POR_PRECEDENCIA: N de M ...';
END IF;
```

`v_fatos > v_soma.aceitas` continua sendo recusa dura — é impossível por
construção e portanto é corrupção.

**Isto não abre porta para mentira.** `v_soma.aceitas` não vem do chamador: vem
do `ROW_COUNT` que a própria RPC gravou lote a lote, e nada além dela escreve no
fato (RLS forçada, zero policies, `service_role` sem escrita direta).

### 4. A projeção trava pela chave legada antes de olhar

```sql
PERFORM pg_advisory_xact_lock(
  hashtext(f.campaign_id || '|' || f.metric_date::text)::bigint);

IF EXISTS (SELECT 1 FROM public.google_ads_campanha_dia o
            WHERE o.campaign_id = f.campaign_id
              AND o.metric_date = f.metric_date
              AND (o.customer_id <> f.customer_id
                OR o.segments_hash <> f.segments_hash)) THEN ...
```

Travar pela chave legada serializa exatamente onde a colisão acontece, e faz o
caso concorrente terminar **igual ao caso serial** — que é a definição de
correção aqui, já que o serial é o que CP-19 declara correto. A trava é de
transação: solta sozinha no COMMIT.

Ambíguo passou a ser *"outra linha canônica cai nesta linha legada"*, venha de
outra conta ou de outro segmento.

**Pressuposto declarado:** `READ COMMITTED`, o default do PostgREST. É ele que dá
snapshot novo a cada instrução, permitindo que o segundo enxergue o primeiro
depois da trava. Sob `REPEATABLE READ` a trava ainda serializa, mas a releitura
seria cega — e nesse caso a projeção deve ser desligada
(`projetar_compat: false`) até haver prova sob a isolação em uso.

---

### C10 · a trava do C8 podia travar duas execuções uma na outra

Defeito **introduzido pela própria correção do C8**, e encontrado ao revisá-la.
A trava consultiva é tomada DENTRO de um laço, uma por linha legada — por
`(campaign_id, metric_date)`. Trava dentro de laço só é segura se todas as
transações a adquirirem na MESMA ordem global, e o laço ordenava por
`(customer_id, campaign_id)`. As duas ordens não coincidem: bastam duas execuções
com contas diferentes tocando as mesmas campanhas.

```
FALHOU  C10.1 nenhuma projeção falhou por espera circular (40P01) — obtido [1], esperado [0]
```

A corrida não é sorteada: uma terceira sessão segura a linha legada da campanha
maior, prendendo a primeira execução DEPOIS de ela já ter a trava dessa campanha;
só então a segunda pega a menor e vai buscar a maior. Quando a terceira solta, o
ciclo se fecha.

O sintoma não é travar para sempre — o Postgres detecta, aborta uma, e o
`EXCEPTION` da projeção vira `projecao_estado='falhou'`,
`projecao_erro_codigo='40P01'`. O fato canônico sobrevive, e a contenção funciona.
Mas a projeção falharia de forma **intermitente**, que é pior de diagnosticar que
um erro constante, porque some quando alguém vai olhar.

**Correção:** ordenar o laço pela própria chave da trava —
`ORDER BY g.campaign_id, g.metric_date, g.customer_id, g.segments_hash`.

---

## O verde, medido

```
concorrência v12_04:  35 ok   0 falharam        (scripts/provar-concorrencia-v12_04.sh)
ciclo serial       :  107 ok   0 falharam       (scripts/provar-ciclo-v12_04.sh)
  incluindo CP-19a/b/c/d, intactas
  CICLO v12_04 COMPLETO: aplicar → operar → reverter → reaplicar
```

O ciclo `apply → operate → rollback → reapply` foi **executado**, não descrito:
o rollback é recusado sem declaração de perda, aceito com ela, as tabelas somem,
a v9_01 fica intacta, `daily_campaign_metrics` sobrevive, e a terceira aplicação
é recusada com nome.

## Cobertura contra o `acceptance`

| Exigência | Onde | Estado |
|---|---|---|
| duas conexões/sessões simultâneas | harness FIFO + `pg_stat_activity` | ✅ |
| D0 < D-1 < backfill | C1, C7 | ✅ |
| empate por `colhida_em` | C2 | ✅ |
| mesma chave idempotente repetida | C3 | ✅ |
| mesma chave com payload divergente | C4 | ✅ |
| fechamento depois da escrita | C5 | ✅ (já estava correto) |
| duas execuções concorrendo pela mesma chave de fato | C1, C2, C6, C7 | ✅ |
| preservação do recibo | C6 | ✅ |
| vermelho antes, verde depois | 16/23 → 32/32 | ✅ |
| ciclo apply→operate→rollback→reapply | 107/0 | ✅ |
| documentação da semântica | este documento | ✅ |
| _(além do aceite)_ projeção legada sob corrida | C8, C9 | ✅ |
| _(além do aceite)_ ausência de espera circular na trava | C10 | ✅ |

## O que este trabalho NÃO faz

- **Não aplica a v12_04 no Supabase oficial.** Isso exige autorização externa
  explícita e está no pacote único do checkpoint.
- **Não prova nada sob isolação diferente de `READ COMMITTED`.**
- **Não prova a v12_03**, que também segue não aplicada.
- **Não testa concorrência entre a RPC e um `TRUNCATE`/`DELETE` administrativo** —
  não existe caminho autorizado para isso, e a RPC nunca apaga.
