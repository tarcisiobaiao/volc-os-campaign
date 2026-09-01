# Creative Factory Production Spine V1 — relatório de entrega

**Status:** `LOCAL_PRODUCTION_SPINE_READY_EXTERNAL_ACTIVATION_PENDING`

A espinha local está fechada e provada. O que falta para chamar de produção —
v11_03 no Supabase oficial, bucket, worker hospedado, peça canário no destino —
depende de autorização externa que esta missão não tem, e está no pacote único
em `AUTORIZACAO-EXTERNA.md`.

## 1. Procedência

| | |
|---|---|
| Base SHA | `b6e226ab2f6d339d2c7c899b83b05ff4a95ebcac` (`origin/volc-os-v2`) — **igual ao esperado pelo prompt, sem divergência** |
| Branch | `sprint/creative-factory-production-spine-v1` |
| Worktree | `/private/tmp/volc-creative-factory-production-spine-v1` |
| Árvore | limpa na criação e na entrega |

## 2. Gates

| Gate | Baseline (medido no SHA base) | Final |
|---|---|---|
| `pytest backend/tests volc_ads` | 2972 passed · 53 skipped | **ver rodapé** |
| `vitest run` | 1208 passed · 5 skipped | ver rodapé |
| `tsc --noEmit -p tsconfig.app.json` | 76 erros herdados | 76 |
| `vite build` | verde | verde |
| `scripts/provar-ciclo-v11_03.sh` | 129 passaram · 0 falharam | 129 · 0 |
| contrato do depósito (novo) | — | 71 (36 SQLite + 35 Postgres) |

⚠️ **Correção de um baseline herdado.** O handoff da bancada registrava
"Frontend completo 902 (7 arq./2 testes falhos)" e tratava as falhas como
herdadas. Elas não eram: `src/lib/supabase.ts:7` lança quando
`VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` não estão no ambiente. Com
placeholders não-credenciais a suíte inteira passa. O baseline antigo colapsava
**ausência de variável** em **falha de teste**.

## 3. Tarefas P17 — estado honesto recomendado

| Tarefa | Antes | Recomendado | Por quê |
|---|---|---|---|
| P17-T04 unificar fila e writer Postgres | `todo` | **`done`** | 36 asserções idênticas passam nos dois depósitos; 7 divergências fechadas |
| P17-T05 executar fora do processo web | `todo` | **`partial`** | worker real provado para IMAGEM; vídeo depende de P17-T07 |
| P17-T06 storage e verificação de bytes | `todo` | **`partial`** | máquina implementada em Python com releitura real; bucket remoto exige autorização |
| P17-T07 Remotion hermético e licença | `todo` | **`partial`** | licença CONFIRMADA na fonte oficial; hermetismo **não provado** — nenhum render executado |
| P17-T08 peça real por destino | `todo` | **`partial`** | 11 elos atravessados com 5 envelopes reais; aprovação humana vive no Postgres |
| P17-T09 contratos HTTP e ownership S0 | `partial` | **`done`** | aceites 3, 4 e 5 provados; 1 e 2 já estavam |

Nenhuma vai a `done` por existir código. P17-T05 fica `partial` porque dizer o
contrário afirmaria vídeo que ninguém produziu aqui.

## 4. Defeitos fechados, todos com contraprova vermelha

**Críticos**

1. `POST /api/criativos/jobs` estourava `anyio.NoEventLoopError` e o job ficava
   preso em `queued` **para sempre**. A rota é `async def` e chamava
   `anyio.from_thread.run` da thread do event loop.
2. O próprio fail-closed explodia com `RuntimeError: Already running asyncio in
   this thread`: o job não virava `failed`, não recebia motivo nem carimbo, e a
   rota devolvia 500 sobre um job órfão.

**Altos**

3. As rotas `/bancada/*` contornavam inteiramente `escolher_despachante()` — a
   porta fail-closed não aparecia em uma linha de `backend/app/routers/`.
4. O render síncrono rodava na thread do event loop: durante ele, nenhuma outra
   requisição do processo era atendida. Parada do servidor, não lentidão.
5. `iniciar_reaper` tinha **zero chamadores** no repositório inteiro.
6. Um loop **por chamada** (minha primeira correção) pendurava o `asyncio.Lock`
   do executor entre loops sob concorrência, e a thread `daemon=False` impedia o
   processo de sair. Achado meu, sobre código meu.

**Sete divergências entre a fila SQLite e o Postgres da v11_03**

7. lease vencido avançava `claimed → running → validating`.
8. `rendered` aceito com recibo de **zero** artefatos.
9. mensagem de falha carregava caminho de disco (lacuna L1 do handoff).
10. sem trilha append-only nem carimbo `terminado_em`.
11. a trilha do Postgres registra o CLAIM; a do SQLite não — claim e devolução
    por lease vencido sumiam.
12. `queued → failed` não existe no mapa, e `reivindicar` escrevia isso por SQL
    cru: o depósito desobedecendo o mapa que ele publica.
13. o CHECK `falha_coerente` proíbe motivo de falha em trabalho `queued`.

**Storage**

14. `existe()` colapsava **falha de rede** em **ausência de objeto** — e a
    cláusula `except (ObjetoNaoEncontrado, Exception)` era, além de perigosa,
    **inerte**.
15. os dois 404 do Storage lidos como um: `Bucket not found` virava "ainda não
    subiu", e o produto tentaria para sempre contra um bucket inexistente.
16. `guardar()` subia e nunca reconferia, devolvendo `None`.
17. 5xx virava `ArquivoRecusado` — servidor acusando o arquivo do operador.
18. falha de rede na releitura podia virar `VERIFIED_MISMATCH` terminal.

**QA e procedência**

19. o gate de dimensão julgava a **declaração** do motor, não os pixels: um PNG
    de 64×64 chegava a `rendered` declarando 1200×628.
20. `MotorTipografico` não declarava `natureza`, então passava no portão de
    produção com aviso onde o `png-local` — que declara — recebia recusa. O
    incentivo estava invertido.

**UI**

21. "A biblioteca tem 0 ativos" com universo **desconhecido**.
22. `canceladoPedidoEm` existia no contrato e nenhum componente o lia.
23. custo `null` (não apurado) desenhado como valor.

## 5. Achados sem correção — registrados, não escondidos

- **O Mapa Vivo descreve outra árvore.** `git merge-base a539dbd b6e226ab` é
  vazio: `main` tem raiz `d767bac`, `volc-os-v2` tem raiz `48a3ad5`. Não é grafo
  defasado — é grafo de outra linhagem, e ele declara `current: true`.
- **Dois padrões de credencial no parque externo**, nenhum deles admissível no
  runtime: um hook carrega o `.env` de um projeto de **cliente** que existe nesta
  máquina; outro colhe chave de API varrendo templates de terceiros por regex.
  Verificado por contagem, sem ler valor: um arquivo casa aqui.
- **`/opt/homebrew/bin/ffmpeg` fixado em 46 arquivos** do parque.
- **Chrome Headless Shell, 193 MB**, é a maior dependência de rede do Remotion —
  não está no `package-lock.json` e o ADR não a registra.
- **Vendorizar fonte pode mudar o pixel sem mudar o sha256**: o Cormorant
  disponível não tem eixo itálico e uma composição pede itálico; o Chrome
  inclinaria o romano, e a assinatura determinista **não acusaria**.
- **Oswald é pedido em peso 800/900** e o Google publica só até 700 — o que se vê
  hoje é negrito sintetizado.
