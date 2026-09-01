# Gates — P10-T16

**Lane:** `sprint/hermes-p10-t16-n8n-ledger-v12-v1`
**Base:** `b6e226ab2f6d339d2c7c899b83b05ff4a95ebcac` · **Data:** 01/09/2026
**Máquina:** Linux 6.8.0-124, Python 3.11.15, Node v22.23.1, Docker com
`postgres:16-alpine`, `google-ads` 31.4.0, sem `psql`/`initdb` locais.

Todos os comandos abaixo foram **executados**. Nenhum fala com
`database.agenciavolc.com.br`, com a Google Ads API, com o n8n ou com o servidor
Hetzner.

---

## 1. Ciclo SQL — aplicar → operar → reverter → reaplicar

```bash
bash scripts/provar-ciclo-v12_04.sh
```

```
passaram 107 · falharam 0
CICLO v12_04 COMPLETO: aplicar → operar → reverter → reaplicar
```

Quatro degraus, num container Postgres 16 que nasce e morre no comando:

| Degrau | O que mede |
|---|---|
| 1 — aplicar | duas tabelas, view de saúde, RPC única `SECURITY DEFINER` com `search_path` fixo, RLS `ENABLE + FORCE`, zero policies, zero grant `anon`/`authenticated`, `service_role` sem escrita direta, nenhuma métrica com DEFAULT, chave canônica com a CONTA, FK `DEFERRABLE INITIALLY DEFERRED`, e `daily_campaign_metrics` **não criada nem alterada** |
| 2 — comportamento | `scripts/provas-v12_04.sql`: 65 provas de contrato (CP-01 a CP-24) |
| 2-bis — contenção | `service_role` recusado fora da RPC e **aceito** por ela; zero medido chega zero, ausência chega NULL |
| 3 — reverter | rollback recusado sem declaração de perda; com declaração, reverte; `trafego_campanha` e a legada continuam de pé, com receita intacta |
| 4 — reaplicar | tudo volta, a RPC volta a aceitar ingestão, e uma terceira aplicação é recusada com nome |

⚠️ O degrau 2 tem guarda contra degrau mudo: se produzir menos de 45 provas, ele
**falha** em vez de anunciar "0 falharam" — que foi como as provas da v12_02
quase passaram sem medir nada.

### Dois defeitos que o próprio arranjo de prova tinha

Estabilidade foi medida, não suposta: o ciclo rodou **três vezes seguidas** e
devolveu `passaram 107 · falharam 0` nas três. Chegar lá exigiu consertar o
harness duas vezes.

**1. Contador que oscilava entre 104 e 107 na mesma árvore.** As provas de
comportamento falam só por `NOTICE`, que sai pelo **stderr**; o stdout do `psql`
leva uma linha **vazia** para cada `select pg_temp.tenta(...)`, porque a função
devolve `void`. Com `2>&1`, as 65 linhas vazias corriam com as 65 notices e volta
e meia se interpolavam no meio de uma linha, quebrando a âncora `^  ok`. Um
degrau que às vezes não conta o que rodou é pior do que um degrau que falha. A
captura passou a ser `2>&1 >/dev/null` — só stderr.

**2. Duas de três execuções seguidas morriam sem conectar.** A imagem oficial do
Postgres sobe um servidor **temporário** no mesmo socket para rodar o `initdb`, e
o `pg_isready` responde verde para *ele*; logo depois o entrypoint derruba esse
servidor e sobe o definitivo. A espera passou a ser pelo marcador
`PostgreSQL init process complete` **e** por um `select 1` que responde.

## 2. Validação n8n — nó a nó, workflow completo, expressões e varreduras

```bash
python3 scripts/validar_workflows_n8n_gads.py
```

```
passaram 339 · falharam 0 · pulados 0
workflows n8n VALIDADOS nó a nó, com topologia e varreduras
```

Sete camadas, sobre os dois workflows:

- **estrutura**: chaves obrigatórias, nomes e ids únicos, zero conexão órfã, zero
  nó ilhado, `active: false`, fuso e `executionOrder` declarados;
- **round trip de import/export**: sobrevive à ida e volta por JSON; o payload
  público (`name`/`nodes`/`connections`/`settings`) está completo; nenhum nó
  carrega campo interno de execução;
- **nó a nó**: Code (modo declarado, formato `[{ json }]`, sem `{{ }}` no JS, sem
  `require`, sem `$env`, sem credencial literal, sem `$('No').all()` dentro do
  laço), HTTP (credencial e não header manual, timeout, retry com teto, sem
  `continueOnFail`/`continueRegularOutput`, `neverError: false`, Content-Type
  coerente), Merge (combina por POSIÇÃO, duas entradas), If (duas saídas,
  operador declarado), SplitInBatches (typeVersion 3, batchSize 1, duas saídas);
- **expressões e referências**: `={{ }}` bem formado fora de Code; toda
  referência `$node["Nome"]` / `$('Nome')` aponta para nó existente, com
  maiúsculas e minúsculas conferidas — inclusive dentro dos Code nodes;
- **sintaxe real**: `node --check` em cada `jsCode`, embrulhado como o n8n
  embrulha (senão `return` no topo daria falso vermelho);
- **topologia**: a ordem obrigatória do contrato conferida elo a elo, `done` em
  `main[0]`, lote em `main[1]`, `Limit 1` no fechamento, alerta só na saída
  verdadeira, e prova de alcançabilidade de que **erro de autenticação não tem
  caminho de volta ao pedido**;
- **segurança**: seis padrões de segredo, `*.supabase.co`, hosts fora da
  allowlist, cinco padrões de mutação Google, quatro de ativação n8n,
  `LOGIN_CUSTOMER_ID`/`CONTAS_PERMITIDAS` vazios no artefato versionado, e os 27
  campos GAQL conferidos contra os *descriptors* do SDK v25.

## 3. Simulação offline D0/D-1 — o JavaScript real, com relógio injetado

```bash
node scripts/simular_gads_ledger_v12.mjs
```

```
passaram 65 · falharam 0
SIMULAÇÃO OFFLINE COMPLETA (rpc=fake) — zero rede, relógio injetado
```

Blocos: janela/identidade/disparo (10) · NULL ≠ 0 na normalização (6) ·
identidade devolvida e conta compartilhada (2) · validação, parcial e linha verde
(4) · paginação, lotes e acumulado (9) · várias contas e o `done` (5) · falha não
vira vazio (10) · vazio confirmado ≠ falha (2) · recibo, releitura e batimento
(8) · falha fechada antes de qualquer leitura (4) · idempotência (5).

### O defeito que este gate encontrou

A primeira versão lia o contexto da iteração com
`$('Pagina: preparar pedido').first()`. O simulador derrubou: `$()` resolve pelo
**índice da rodada do nó que pergunta**. Uma conta que falha faz o nó de pedido
rodar mais vezes que o de normalização, e a partir dali cada iteração lia o
contexto de **outra conta** — silenciosamente, com a resposta certa colada na
conta errada. A correção foi trocar `$()` por dois `Merge` por posição, e a
regressão virou contraprova nomeada em três lugares.

## 4. Ponta a ponta — o documento do fluxo contra a RPC real

```bash
bash scripts/provar-ponta-a-ponta-gads.sh
```

```
passaram 12 · falharam 0
PONTA A PONTA COMPLETA — documentos do n8n aceitos pela RPC v12_04
```

O dublê some do lado do banco: os documentos que o JavaScript monta vão para a
RPC de verdade, num Postgres descartável com a v12_04 aplicada. É a costura onde
dois artefatos costumam discordar em silêncio. Google Ads continua dublê.

Uma das 12 provas nasceu vermelha e apontou um erro **da prova**, não do código
(esperava NULL onde a fixture media zero) — o que confirma que ela discrimina.

## 5. Gate de agenda única

```bash
python3 scripts/gate_agenda_unica_gads.py
```

```
passaram 14 · falharam 0 · pulados 1
UMA autoridade de agenda escolhida (n8n) e NENHUMA ligada
```

O pulado é declarado, e é o achado mais importante desta lane:

```
PULADO  agenda única CONFIRMADA na instância viva — REAL_N8N_READ_NOT_PROVEN —
o inventário de 19/08 registra 5 workflow(s) da família com agenda ATIVA:
criacao-gads-factory-v3 (criação); custo-gads-placements-display (custo);
custo-gads-placements-display-d1 (custo); custo-gads-report (custo);
custo-gads-report-d1 (custo).
```

## 6. Suíte Python

### Focal (o que esta lane acrescenta)

```bash
python3 -m pytest backend/tests/test_gads_workflows_n8n.py -q
# 18 passed
```

### Completa, com baseline medido no commit base

```bash
python3 -m pytest backend/tests volc_ads -q
```

| | passaram | falharam | pulados |
|---|---:|---:|---:|
| base `b6e226a` (worktree limpa) | 2904 | 20 | 101 |
| HEAD desta lane | 2922 | 20 | 101 |
| **delta** | **+18** | **0** | **0** |

As 20 falhas são **herdadas e isso foi provado, não suposto**: a mesma suíte
rodou numa worktree limpa em `b6e226a` e as mesmas 20 falham lá. São
`test_criativo_execucao.py` (18, por ausência de `pytest-asyncio` no ambiente) e
`test_criativo_rotas_equivalentes.py` (2, *golden* de OpenAPI e faixa de
toolchain). Nenhuma toca `n8n/`, `supabase/migrations/` ou `scripts/`, e esta
lane não editou `backend/app/**`.

> ⚠️ **Nota de execução.** A primeira tentativa de rodar a suíte baseline em
> segundo plano foi **morta pelo limite de turnos do executor** (task `bodd94q1l`
> devolveu apenas `[killed]`). A medição acima é de uma reexecução completa, em
> primeiro plano, na worktree destacada `b6e226a` — que foi removida ao final
> (`git worktree remove` + `prune`).

## 7. Gates de segurança e autoridade

```bash
python3 scripts/verificar_autoridade_supabase.py
# ✓ Supabase oficial: https://database.agenciavolc.com.br

python3 scripts/gate_sem_mutacao_google.py
# ok · 1/3 FORGE_PERMITIR_ESCRITA não está armada
# ok · 2/3 a trava de escrita está fechada
# ok · 3/3 as 5 contraprovas focais da rota passaram

python3 scripts/verificar_segredos.py
# Secret scan: nenhum padrão forte encontrado no working tree.

git diff --check
# (sem saída)
```

## 8. Determinismo do artefato gerado

```bash
python3 n8n/gerar_flows_gads_ledger_v12.py --check
# ok · os 2 workflows em disco batem com o gerador (contrato 9566b7b3a609…)
```

---

## O que NÃO foi executado, e continua não sendo

- ❌ migration aplicada no Supabase oficial;
- ❌ workflow importado, atualizado ou ativado no n8n;
- ❌ chamada real à Google Ads API (leitura ou mutação);
- ❌ canário, primeira janela automática ou heartbeat em produção;
- ❌ instalação, habilitação ou start de qualquer unit/timer systemd;
- ❌ `git push`, merge, rebase ou cherry-pick de outra lane;
- ❌ edição de `volc-os-workbook/ROADMAP-VIVO.json`,
  `docs/volc-os-graph/curadoria-operacional.json` ou `graphify-out/**`.

## Limitações declaradas

| Sigla | O que significa |
|---|---|
| `REAL_N8N_READ_NOT_PROVEN` | não havia credencial de n8n no ambiente; a instância viva não foi lida. IDs, versões e estado ativo vêm de documento e inventário versionados, não de medição |
| `REAL_GOOGLE_ADS_READ_NOT_PROVEN` | zero chamada à API. Os 27 campos existem nos *descriptors* v25; isso não prova que o par (recurso, campo) é selecionável em GAQL |
| `CREDENCIAL_DEVELOPER_TOKEN_NAO_EXERCITADA` | `={{ $credentials.developerToken }}` não foi resolvido contra um n8n real. Se falhar, a correção é outro caminho de injeção — nunca o token no JSON |
| `RETRY_DO_MOTOR_NAO_EXERCITADO` | `retryOnFail`/`maxTries` são do motor do n8n. Provada está a declaração do teto e a classificação da falha depois dele |
| `SERVIDOR_HETZNER_NAO_INSPECIONADO` | o gate de systemd mede esta máquina, não o servidor oficial |
