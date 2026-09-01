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
| `pytest backend/tests volc_ads` | 2972 passed · 53 skipped | **3195 passed · 53 skipped** |
| `vitest run` | 1208 passed · 5 skipped | **1243 passed · 3 skipped** |
| `tsc --noEmit -p tsconfig.app.json` | 76 erros herdados | 76 |
| `vite build` | verde | verde |
| `scripts/provar-ciclo-v11_03.sh` | 129 passaram · 0 falharam | 129 · 0 |
| contrato do depósito (novo) | — | **71** (36 SQLite + 35 Postgres) |

Medidos em série, num único HEAD (`2733715`), árvore limpa.

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

## 6. O recibo: onze campos presentes, onze ausentes

A missão pede que o recibo registre modo, provider, modelo, versão, seed,
dimensão alvo, dimensão nativa, resize/crop, brand pack, hashes de inputs,
prompt sanitizado, output hash, custo, duração, tentativas, gates, aprovação e
destino. **Metade não existe**, e a espinha estar fechada não apaga isso.

| Presentes | Ausentes |
|---|---|
| versão do motor e das dependências | modo (`modo_slug` existe na Encomenda, não no Recibo) |
| seed (sem default, por decisão) | provider externo — o mais próximo é `motor_slug` |
| dimensão alvo (na `Validacao`) | modelo |
| output hash (sha256 **medido do disco**) | dimensão nativa antes do resize |
| bytes do artefato (conferidos) | resize / crop / enquadramento |
| campos de custo (estimado e real) | brand pack |
| duração do artefato e do trabalho | hashes de input |
| gates e validações | prompt sanitizado — e o **oposto** acontece: o insumo cru viaja em `parametros` e sai pela API |
| assinatura determinista | tentativas (vivem só na linha do trabalho) |
| `produzido_por` (autor permanente) | aprovação humana (só no Estúdio, em tabela Postgres) |
| chave de idempotência | destino / entrega · storage remoto · medida de áudio |

Três merecem nome próprio, porque não são só ausência:

- **O insumo cru viaja no recibo e sai pela API.** O caminho do Estúdio decidiu o
  contrário e gravou o motivo (`"insumo_sanitizado": None`, com o comentário
  dizendo que duplicá-lo num campo que a API lê seria mais um caminho de
  vazamento). A bancada não seguiu a mesma decisão.
- **Os campos de custo não têm produtor.** São literais `None` no construtor, e
  nenhum ponto do caminho os escreve. Está correto como "não apurado" para motor
  local gratuito — e no dia em que entrar um motor pago, ligar o provider sem
  ligar a apuração faria todo trabalho nascer com custo nulo permanente.
- **`MedidaDeAudio` é estrutura morta.** Nenhum motor implementa `medir_audio`,
  e a v11_03 reservou três colunas numéricas que nascerão permanentemente nulas
  — exatamente o "null permanente que parece lacuna de preenchimento" que o
  `PLANO-v11_03.md` diz querer evitar.

## 7. Revisões externas

Codex `gpt-5.6-sol` fez a revisão adversarial sobre o SHA integrado, e ela pagou
o preço da rodada inteira num achado só.

### Vazamento entre inquilinos no Estúdio — CONFIRMADO E FECHADO

`GET /api/criativos/jobs/{job_id}` e `GET /api/criativos/jobs` ligavam a
identidade a `_` — literalmente descartavam — e serviam só para exigir "algum
usuário autenticado". O repositório também não ajudava: `buscar_job` consultava
`id=eq.<uuid>` e nada mais, e `listar_jobs` **não tinha nem parâmetro de dono**.

Reproduzido por mim contra as funções reais
(`contraprovas/contraprova_leitura_cruzada.py`):

```
--- B pede o job de A pelo UUID ---
   VAZOU: B recebeu o job de A -> projetoTitulo='BRIEFING CONFIDENCIAL DO USUARIO A'
--- B lista os jobs ---
   B viu 2 job(s) · VAZOU: a listagem atravessa inquilino
```

A listagem é a pior das duas: não era preciso nem conhecer um UUID.

O comentário da rota **irmã**, na bancada, já tinha escrito a regra: *"O UUID não
é autorização: buscar sem o filtro faria esta rota diferir das rotas de
leitura/listagem"*. A bancada aplicou; o Estúdio não. Agora a leitura filtra pelo
**mesmo campo que a criação grava** (`criado_por = identidade.sub`), e o 404 é o
mesmo de "não existe" — responder diferente confirmaria a existência de job
alheio.

**Pendência declarada:** o mesmo padrão existe em `obter_asset` e
`listar_assets`, que também ligam a identidade a `_`. Fechá-las exige resolver a
posse *através* do job (o asset não carrega dono próprio), o que é mudança maior
do que cabe nesta rodada corretiva. Fica registrada aqui e no handoff de
curadoria como achado reproduzido e **não corrigido**.

⚠️ **A revisão do Gemini 3.7 Flash NÃO aconteceu, e a fronteira é esta:** o CLI
não tem método de auth configurado nesta máquina — sem `~/.gemini/settings.json`
e sem `GEMINI_API_KEY` no ambiente. A chave existe dentro de arquivos `.env` de
projeto, e ler segredo de arquivo para alimentar um CLI é **exatamente o padrão
que esta missão flagrou como risco R1/R2 no parque externo**. O eixo factual foi
coberto por um segundo passe do Codex, que continua sendo revisor de outro
modelo, e isso está declarado em vez de a entrega afirmar uma revisão Gemini que
não houve.
