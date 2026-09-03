# Gates — creative-factory-production-go-live-v1

Todos os números abaixo foram **medidos nesta worktree**, com o comando escrito
ao lado. Nenhum vem de relatório anterior, e onde o ambiente muda o resultado
isso está dito.

**Base:** `382c5d4c67fc521d5e6739f8e76d1c36a96fdb53` (`origin/volc-os-v2`)
**Feature integrada:** `5235f0c6d8a6c526b42bf64342373471cd14ebe4`
**Merge:** `87cfcef` · **HEAD:** ver `README.md`
**Worktree:** `/private/tmp/volc-creative-factory-production-go-live-v1`

## 1. Baseline e delta

O baseline foi medido **no mesmo ambiente**, numa worktree separada em
`382c5d4`, porque comparar contra o número de outro relatório mede a diferença
entre duas máquinas e não a diferença entre dois commits.

| Gate | Base `382c5d4` | Merge `87cfcef` | HEAD | Comando |
|---|---|---|---|---|
| backend | **3332** passed · 87 skipped · **0 failed** | **3370** · 87 · **0** | **3405** · 90 · **0** | `PYTHONPATH=$PWD backend/.venv/bin/python -m pytest backend/tests volc_ads -q -p no:randomly` |
| frontend | **1256** passed · 5 skipped | **1262** · 5 | **1262** · 5 | `npx vitest run` |
| TypeScript | **76** erros herdados | **76** | **76** | `npx tsc --noEmit -p tsconfig.app.json` |

**Zero falhas nos três pontos.** O `+38` do merge é exatamente o conjunto de
testes que a feature acrescenta; o `+35` do HEAD são as provas das cinco
correções desta lane, mais a sentinela de invariante do gate de MIME.

⚠️ **Os 87 `skipped` são do ambiente, não do código.** Esta worktree não tem
`.env`, então tudo que exige `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` pula —
e pula **igual** no base e no merge, que é o que torna o delta legível. Copiar
segredo para dentro da worktree para "melhorar" o número seria trocar uma
medição honesta por uma bonita.

⚠️ **O relatório da feature mediu `3358 → 3396`**, e a diferença para os meus
`3332 → 3370` é a mesma constante 26 nos dois lados: outro ambiente, mesmo
delta. Um delta que se reproduz em dois ambientes é o que sobrou de fato.

## 2. Gates da fábrica criativa

| Gate | Resultado | Comando |
|---|---|---|
| ciclo v11_03 (aplicar→operar→reverter→reaplicar) | **178 · 0** | `bash scripts/provar-ciclo-v11_03.sh` |
| preflight v11_03 acusa quando há o que acusar | **30 · 0** | `bash scripts/v11_03-provar-preflight.sh` |
| o plano descreve a v11_03 que existe | **12 · 0** | `bash scripts/v11_03-provar-plano.sh` |
| render hermético, determinístico e medido | **17 · 0** | `bash scripts/provar-render-hermetico.sh` |
| golden de imagem | **23 passed** | `pytest backend/tests/test_criativo_golden_imagem.py` |
| golden de vídeo | **22 passed** | `pytest backend/tests/test_criativo_golden_video.py` |
| runtime Remotion | **13 passed** | `pytest backend/tests/test_criativo_runtime_remotion.py` |
| identidades declaradas × arquivos (**nova**) | **8 passed** | `pytest backend/tests/test_v11_03_identidades_declaradas.py` |
| o registro de storage cabe no banco (**nova**) | **12 passed** | `pytest backend/tests/test_criativo_storage_registro_cabe_no_banco.py` |
| o MIME é medido, não declarado (**nova**) | **8 passed** | `pytest backend/tests/test_criativo_mime_medido.py` |
| contrato do depósito, **os dois adapters** | **77 passed · 0 skipped** | `VOLC_EXIGIR_POSTGRES=1 <python-com-psycopg> -m pytest backend/tests/test_criativo_deposito_contrato.py` |
| higiene do diff | **limpo** | `git diff --check origin/volc-os-v2 HEAD` |
| segredos | **nenhum padrão forte** | `python scripts/verificar_segredos.py` |

## 3. O gate de vídeo exigiu instalar o runtime, e isso é declarado

`deploy/creative-worker/remotion-runtime/node_modules` não é versionado. Sem
ele, `test_criativo_golden_video.py` **pula 22** e `provar-render-hermetico.sh`
sai sem rodar nenhum degrau — e nenhum dos dois fica vermelho.

Rodei `npm ci` nesse diretório (registro público do npm, lockfile próprio,
16 pacotes `@remotion/*` em **4.0.479** exatos conferidos contra o lockfile) e o
Remotion baixou o Chrome Headless Shell na primeira execução. As duas são
**instalação de dependência local**, escrevem apenas dentro de diretórios
ignorados pelo git, e estão no envelope de atos externos do `README.md`.

Sem isso o número de vídeo seria `22 skipped` — e um verde que não executou o
motor é pior que um vermelho, porque afirma cobertura que não existe.

### Um defeito de ambiente que o gate expôs, e que importa para o deploy

Na primeira execução depois do `npm ci`, rodar golden de imagem e de vídeo
**juntos** deu `25 passed · 20 errors`. Em isolado, cada um passa (23 e 22), e
nas duas ordens juntos passa 45. A causa está medida: o diretório
`~/.cache/puppeteer/chrome-headless-shell` foi **criado durante aquela execução**
(carimbo 19:46–19:47), e os renders que caíram na janela do download falharam.

Não é defeito do código, e é fato operacional com consequência direta:
**o primeiro render de uma máquina nova NÃO é hermético — ele baixa o
Chromium.** O hermetismo provado pelos 17 degraus vale a partir do segundo. Um
worker que suba em container limpo e receba trabalho imediatamente falha o
primeiro job, e a mensagem que ele emite (`Node.js v26.5.0`) não diz por quê.
Está no pacote de autorização como pré-aquecimento obrigatório.

## 4. O que NÃO foi medido, e por quê

- **Preflight contra o Supabase oficial** (`https://database.agenciavolc.com.br`):
  não executado. O script é somente-leitura e fail-closed, mas exige DSN, e esta
  lane não tem credencial — buscar uma dentro de `.env` de projeto é exatamente
  o padrão que a missão anterior flagrou. Virou item do pacote de autorização.
- **Equivalência de pixel macOS ↔ Linux:** NÃO PROVADA. O determinismo dos 17
  degraus é na mesma máquina, com compositor `darwin-arm64`.
- **`DepositoPostgres` sob concorrência de PROCESSOS:** o teste de contrato usa
  threads. `FOR UPDATE SKIP LOCKED` é a garantia correta e passa, mas a prova
  com processos separados não foi feita.
- **Revisão factual do Gemini:** `PROVIDER_NOT_AVAILABLE` (§ `README.md`).


## 5. O contrato do depósito, e por que ele exige outro interpretador

`test_criativo_deposito_contrato.py` roda a **mesma** bateria contra os dois
depósitos, e o de produção é o Postgres. `psycopg` não estava declarado em
requirements nenhum, então no interpretador que `scripts/gates-backend.sh`
escolhe (`backend/.venv`) toda a parametrização `[postgres]` sai como skip:

| Interpretador | Resultado |
|---|---|
| `backend/.venv` (sem o driver) | **40 passed · 37 skipped** |
| um com `psycopg`, `VOLC_EXIGIR_POSTGRES=1` | **77 passed · 0 skipped** |

Os 37 que somem são exatamente o adapter que serve a produção — e a fila local
já divergiu do Postgres uma vez, no P17-T04, por essa cobertura assimétrica.
`psycopg[binary]` foi **declarado** em `backend/requirements-dev.txt` nesta lane;
**instalar** ficou de fora porque `backend/.venv` é compartilhado com a árvore
principal (item BL-2 do handoff, com o comando exato).

Os números de Postgres deste documento vieram do interpretador **com** o driver,
contra um cluster descartável com a v11_03 aplicada.

## 6. Revisão adversarial — Codex `gpt-5.6-sol`

Read-only, sobre os commits desta lane. **Dois BLOQUEANTES, dois ALTOS e uma
hipótese** — e todos os cinco eram sobre correções que eu tinha acabado de fazer.
Todos fechados em `2fe767e`.

| O que ele derrubou | Como |
|---|---|
| A cerca tinha dois buracos que eu não vi | `motor_desconhecido` escrevia `FAILED` sem cerca nenhuma; `bater()` deixava o zumbi renovar o lease do dono vivo |
| O gate de MIME tinha o buraco que veio fechar | `image/webp` → dois `SKIPPED` não-bloqueantes somam um caminho verde sem abrir o arquivo |
| A canário podia dizer "conferido" sem os fatos | `_sem_publicacao` só olhava domínio; o veredito ignorava 5 dos fatos que promete |
| Minhas guardas podiam passar sem conferir nada | linha malformada sumia em silêncio; um CHECK **comentado** contava como proteção |

**A hipótese que ele não pôde testar, e eu pude.** Ele viu que
`DepositoPostgres.transicionar` faz `select ... for update` **antes** de
`con.transaction()` com `autocommit=True`, e registrou como hipótese porque "não
havia Postgres local disponível". Medido aqui, com duas conexões:

```
c1: select ... for update            (autocommit)
c2: select ... for update NOWAIT  -> SUCESSO      ← o lock de c1 já caiu
dentro de `with con.transaction()`:  c2 -> LockNotAvailable
```

Em autocommit o `for update` roda na própria transação implícita e ela fecha ao
terminar. As guardas de posse eram check-then-act com janela real, e o `UPDATE`
final não repete a condição no `where`. O SQLite nunca teve o problema
(`begin immediate` cobre tudo) — mais uma divergência SQLite/Postgres, a mesma
família que o P17-T04 fechou no lease.

Depois do conserto: **8 concorrentes disputando `validating → failed` dão
`1 venceu / 7 TransicaoProibida`.** Antes, todos passavam.

**O que ele confirmou correto:** o token de cerca dentro de `transicionar`, a
normalização de `sha256:` nos casos exercitados (hash válido cabe no CHECK,
mismatch real continua recusado, valor malformado continua fora), e as 16 provas
que rodou.


## 7. A fragilidade do reconhecimento de MIME — risco futuro, não defeito de hoje

A revisão adversarial levantou que `mime_de` conhece **três** assinaturas e a de
JPEG tem **dois bytes**. A pergunta certa é se isso é defeito executável agora ou
risco de amanhã, e ela se responde executando. Cinco ataques ao contrato atual:

| Ataque | `mime_declarado_confere` | `dimensao` | Resultado |
|---|---|---|---|
| bytes Mach-O declarados `image/webp` | **FAIL** | SKIPPED | bloqueado |
| lixo iniciado por `\xff\xd8` como `image/jpeg` | PASS | **FAIL** | bloqueado |
| PNG 64×64 com pedido de 1200×628 | PASS | **FAIL** | bloqueado |
| PNG real declarado `image/gif` | **FAIL** | PASS | bloqueado |
| bytes arbitrários declarados `video/mp4` | SKIPPED | **FAIL** | bloqueado |

**Nenhum passou. Não há defeito executável, e por isso não houve mudança de
comportamento.** Os dois gates são complementares: onde a assinatura rasa deixa
passar, o leitor profundo — o mesmo que mede a dimensão — recusa; e onde a
assinatura não existe, o outro instrumento mede.

**O risco futuro é concreto, e é de arranjo.** A complementaridade é
**emergente**: vale pela relação entre três conjuntos (`FORMATOS_RECONHECIDOS`,
`_MIMES_MENSURAVEIS`, `_MIMES_VERIFICADOS_POR_OUTRO_INSTRUMENTO`), e nenhum deles
sabe dos outros. Acrescentar `image/webp` a `_MIMES_MENSURAVEIS` — gesto razoável,
para o gate de dimensão passar a cobrar webp — sem ensinar a assinatura ao
`mime_de` faz o par voltar a somar dois `SKIPPED`, que foi exatamente o bloqueante
que a revisão pegou.

Uma propriedade que ninguém afirma é uma propriedade que a próxima edição remove
sem querer. `c72b676` diz as três invariantes, sem tocar em comportamento.
Contraprova executada: com `image/webp` acrescentado e a assinatura não ensinada,
a invariante 2 fica vermelha **nomeando o formato**.
