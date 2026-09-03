# Autorização externa — pedido único

> **Nada aqui foi executado.** Esta lane fechou tudo que é local e parou na
> fronteira que exige decisão de quem responde pela produção. Cada ato traz:
> ação, destino exato, impacto, rollback, prova prévia, comando exato, resultado
> esperado e hard stops.

**Base:** `382c5d4` · **HEAD:** `c72b676` · **Branch:** `sprint/creative-factory-production-go-live-v1`

## Envelope: o que esta lane NÃO fez

| Ato externo | Ocorrências |
|---|---|
| Migration aplicada no Supabase oficial | **0** |
| Escrita no Supabase oficial | **0** |
| Leitura do Supabase oficial | **0** |
| Bucket criado ou configurado | **0** |
| Provider pago chamado | **0** |
| Publicação em qualquer plataforma | **0** |
| Aprovação de peça em nome do usuário | **0** |
| Deploy de worker | **0** |
| `push` · `merge` · alteração de `main` | **0** |

**O PostgreSQL usado em toda esta lane foi DESCARTÁVEL E LOCAL.** Clusters
nascidos de `initdb` dentro de `mktemp -d`, escutando apenas num socket unix
dentro do próprio diretório, destruídos por `pg_ctl stop` na mesma sessão. Houve
**zero** contato com `https://database.agenciavolc.com.br` — nem leitura, nem
escrita, nem migration. Toda afirmação deste pacote sobre o comportamento da
v11_03 em Postgres real foi medida nesses clusters, nunca em produção.

**Rede que HOUVE, e está declarada** — nenhuma é ato de produto:

1. `npm ci` em `deploy/creative-worker/remotion-runtime` (registro público do
   npm, lockfile próprio; grava só em `node_modules`, ignorado pelo git);
2. download do Chrome Headless Shell pelo Remotion na primeira execução
   (`~/.cache/puppeteer`);
3. **2 tentativas de conexão a um endpoint OAuth do Google**, disparadas por
   `backend/tests/test_trafego_canario.py` durante a auditoria. O teste é
   **pré-existente na linha oficial** e escapa das portas herméticas quando
   `~/google-ads.yaml` existe. Não foi introduzido por esta lane, e está no
   backlog nomeado.

---

## 1. Preflight da v11_03 contra o Supabase oficial

**Ação.** Rodar o preflight somente-leitura contra o banco de produção.
**Destino exato.** `https://database.agenciavolc.com.br` (`178.156.196.149`,
container `supabase-db`).
**Impacto.** Nenhuma escrita. A primeira coisa que cada sessão executa, já
conectada, é `set session characteristics as transaction read only` — aplicado
por `SET` **depois** de conectar, justamente para que um `options=` dentro do DSN
não o desfaça. Todas as consultas são de catálogo ou `count(*)`.
**Rollback.** Não se aplica: não há o que reverter.
**Prova prévia.** `scripts/v11_03-provar-preflight.sh` → **30 provas · 0 falhas**:
há prova de que ele acusa quando há o que acusar, e de que é *fail-closed* — o
que não conseguiu conferir sai `NAO CONFERIDO`, que conta como reprovação.

**Comando exato:**
```bash
cd <raiz-do-repo>
# 1. conferir a identidade dos arquivos ANTES de qualquer coisa
shasum -a 256 supabase/migrations/v11_03_execucao_criativa.sql \
              supabase/migrations/v11_03_rollback.sql \
              scripts/preflight-v11_03.sh \
              scripts/provar-ciclo-v11_03.sh \
              scripts/provas-v11_03.sql \
              scripts/provas-papeis-v11_03.sql \
              scripts/v11_03-provar-preflight.sh \
              scripts/v11_03-provar-plano.sh
# esperado: os 8 valores da tabela do passo 0 de braco-a/PACOTE-v11_03.md
#           (corrigidos nesta lane; `pytest backend/tests/test_v11_03_identidades_declaradas.py`
#            confere isso automaticamente e sai 6 passed)

# 2. o preflight. A senha vem de ~/.pgpass (chmod 600), nunca do comando.
scripts/preflight-v11_03.sh "postgresql://USUARIO@HOST:5432/postgres"
```

**Resultado esperado.** Saída `0` com todas as conferências `APTO`: as 5 tabelas
`criativo_render_%` ausentes ou vazias; as 21 tabelas da v11_01/02 existindo
**como tabelas** (`relkind` `r`/`p`, não VIEW); `service_role` com `BYPASSRLS`;
nenhuma das 9 funções existindo com outra assinatura.
Saída `1` = BLOQUEIO. Saída `2` = uso incorreto **ou** algum `NAO CONFERIDO`.

**Hard stops.** Qualquer `sha256` divergente → **pare**, você está prestes a
aplicar arquivo diferente do provado. Saída `1` ou `2` → **pare**; não prossiga
para o item 3.

---

## 2. Conferir que o backup restaura

**Ação.** Tirar um dump e **restaurá-lo** num Postgres descartável.
**Destino exato.** Leitura de `https://database.agenciavolc.com.br`; escrita
apenas no cluster descartável local.
**Impacto.** Leitura no banco de produção (um `pg_dump` completo custa I/O — ver
hard stops). Nenhuma escrita.
**Rollback.** Não se aplica.
**Prova prévia.** Nenhuma — e isto está declarado: **o passo 2 do
`PACOTE-v11_03.md` é roteiro, não evidência.** Nenhum dump foi tirado nem
restaurado por esta lane nem pela anterior.

**Comando exato.** `braco-a/PACOTE-v11_03.md` § 2.1 e § 2.2, integralmente.

**Resultado esperado.** O dump restaura num cluster limpo e a contagem de tabelas
bate com a origem.

**Hard stops.** **Arquivo com data recente NÃO é prova de backup** — um dump
truncado, de outro banco, ou de zero byte têm todos data recente. A única prova é
restaurar e contar. Se a restauração falhar ou a contagem divergir → **pare**, e
não prossiga para o item 3.
⚠️ A máquina tem **4 GB** e é a mesma que serve o produto: não rode o dump em
horário de pico.

---

## 3. Aplicar a v11_03 no Supabase oficial · P17-T03

**Ação.** Aplicar `v11_03_execucao_criativa.sql`.
**Destino exato.** `https://database.agenciavolc.com.br`, schema `public`.
**Impacto.** Cria **5 tabelas** `criativo_render_*`, **9 funções**, **7
gatilhos**, **14 índices** e **27 CHECK**. Não altera nem apaga nada das
v11_01/v11_02. É transacional: aborta inteira ou entra inteira.
**Rollback.** `supabase/migrations/v11_03_rollback.sql` — não é arquivo que nunca
rodou: ele é executado a cada rodada do ciclo. Aceita
`-v v11_03_base_encolhida=confirmo` como escape explícito; **o default continua
abortando**.
**Prova prévia.** `scripts/provar-ciclo-v11_03.sh` → **178 provas · 0 falhas**,
em cluster descartável, cobrindo `aplicar → operar → reverter → reaplicar`.
Reproduzido nesta lane, nesta árvore. Mais `v11_03-provar-plano.sh` → **12 · 0**.

**Comando exato.** `braco-a/PACOTE-v11_03.md` § 3 em diante.

**Resultado esperado.** O `NOTICE` final, literalmente:
```
v11_03 OK: 5 tabelas, RLS forcada, 0 policies, 7 gatilhos, 4 medidas de audio.
```

**Hard stops.** Item 1 tem de ter saído `APTO` e item 2 tem de ter restaurado.
Qualquer `falharam` diferente de 0 nas provas locais encerra o pacote antes daqui.

> ⚠️ **Esta lane consertou dois defeitos que só apareceriam neste momento.** O
> `sha256` que o CHECK `hash_remoto_forma` recusava (`2ffaf5d`, contraprova em
> PostgreSQL 17 com esta migration aplicada) e a tabela de identidades do passo 0
> que estava errada desde que foi escrita (`c8c54c0`). Sem eles, a aplicação
> passaria e a **primeira gravação de artefato** seria recusada — com o sintoma
> longe da causa.

---

## 4. Criar e configurar o bucket `criativos`

**Ação.** Criar o bucket **privado** e trocar `armazenamento_padrao()` para o
adaptador remoto **por configuração**.
**Destino exato.** Supabase Storage em `https://database.agenciavolc.com.br`.
**Impacto.** Passa a existir depósito remoto de peça de cliente.
**Rollback.** Remover o bucket e reverter a configuração. Objetos gravados
precisam ser apagados explicitamente.
**Prova prévia.** `ArmazenamentoSupabase` está escrito e **desarmado**, atrás da
mesma porta `ArmazenamentoConferivel` que o adaptador local cumpre. A máquina de
verificação — upload, releitura, comparação de **bytes e** `sha256` — foi provada
com duas peças reais nesta lane (`VERIFIED_OK` só existe depois da releitura).

**Estado factual.** O bucket **não existe**. Esta lane não consultou o Supabase
oficial; o que se sabe é o que a missão de 27/08/2026 mediu: `select * from
storage.buckets` devolveu zero linhas.

**Hard stops.** **Bucket público por conveniência é a forma mais comum de vazar
peça de cliente** — ele tem de nascer privado. E a troca do adaptador **exige
configuração, não edição de código**: hoje ela obriga a editar
`armazenamento.py:689`, e essa lacuna continua aberta (o ADR exige config).
⚠️ Objeto gravado com a chave antiga (um underscore) está em **outro endereço**.

---

## 5. Um executor remoto para o worker

**Ação.** Decidir onde `python -m app.criativo.bancada.worker` roda, e subi-lo.
**Destino exato.** A definir — é a Decisão 5 de
`docs/architecture/ADR-REMOTION-RUNTIME-STORAGE.md`, deixada ao dono do produto.
**Impacto.** A produção deixa de acontecer dentro do request.
**Rollback.** Derrubar o processo. Trabalho em voo volta para a fila pelo
vencimento do lease — provado.
**Prova prévia.** O worker é processo real: a peça-canário desta lane foi
produzida por `worker-<pid>` com pid **diferente** do processo que enfileirou.
Claim atômico, lease, heartbeat, recolhedor e retomada após crash provados; o
contrato do depósito passa **77 · 0** contra Postgres real.

> ⚠️ **Três defeitos que só apareceriam com MAIS DE UM worker foram fechados
> nesta lane, e é este item que os autoriza.** A cerca contra worker antigo era
> o **nome** do operário, e o nome padrão é `worker-<pid>`, que repete entre
> containers: um zumbi de lease vencido devolvia para a fila, matava com
> `permanente: True`, e renovava o lease do trabalho que o dono vivo estava
> produzindo. E no Postgres — só no Postgres — as guardas de posse eram
> check-then-act: o `select ... for update` soltava o lock antes delas.
> Reproduzidos e corrigidos (`dbf55ad`, `2fe767e`); depois do conserto, 8
> transições concorrentes para um estado terminal dão **1 vencedor e 7 recusas**.

**Hard stops.**
1. ⚠️ **Pré-aquecer o Chrome Headless Shell.** A **primeira** execução de uma
   máquina nova **não é hermética**: o Remotion baixa o Chromium. Sob o sandbox
   `deny network-outbound` o primeiro trabalho **falha**, com a mensagem
   `Node.js v26.5.0`, que não diz por quê. Medido nesta lane: o cache
   `~/.cache/puppeteer/chrome-headless-shell` nasceu durante a execução que deu
   20 erros; depois de existir, tudo passa. Rode um render de aquecimento **antes**
   de dar trabalho ao worker.
2. ⚠️ **Não rode render pesado na mesma máquina do Supabase operacional**
   (`178.156.196.149`, 4 GB): ffmpeg e Chromium concorrem por memória com o
   Postgres que serve o produto inteiro.
3. ⚠️ **Equivalência de pixel macOS ↔ Linux é NÃO PROVADA.** O compositor
   instalado é `darwin-arm64`. Gerar um "hash aprovado" aqui e compará-lo com um
   render de Linux colapsaria local ≠ produção.
4. ⚠️ **Onde não há `sandbox-exec` (Linux), `render_sem_rede` sai `FAIL`
   bloqueante** e o trabalho **não chega a `rendered`**. Ele **nunca** emite
   `SKIPPED` — o texto que dizia isso descrevia o desenho anterior e foi corrigido
   nesta lane. A única saída é `CRIATIVO_PERMITIR_RENDER_COM_REDE`, que emite
   `WARN` e deixa o nome da variável no recibo. Planeje o hermetismo do Linux
   **antes** do deploy.

---

## 6. Persistência real, aprovação humana e validação no destino

Ordem pedida, e só depois de 1–5:

1. um job real atravessa o worker **remoto** e grava em `criativo_render_*`;
2. o artefato sobe ao **bucket** e é relido — `VERIFIED_OK` só depois da releitura;
3. **uma pessoa** aprova a peça-canário, com finalidade escrita;
4. validação no destino: upload **como rascunho, sem ativar**.

**Hard stops.** Aprovar em nome do dono é ato externo e não foi feito. Publicar é
ato **distinto de tudo acima** e exige autorização própria: `PacoteDeDestino.
publicacao_automatica` é `ClassVar` fixo em `False`, e há sentinela que o afirma.

---

## Decisões que continuam pendentes, e não são desta lane

- **Licença do Remotion.** Esta linhagem **acrescentou** um runtime Remotion ao
  repositório (`4.0.479` em lockstep pelo lockfile), o que torna a decisão **mais
  urgente**, não menos. O ADR diz que a Free License cobre organização de até 3
  pessoas e que acima disso exige Company License paga, com **preços NÃO
  CONFIRMADOS**. Enquanto não for verificado em fonte oficial vigente, vídeo por
  Remotion permanece `blocked_by_external_authorization` para faturamento — não
  `unknown`, e muito menos gratuito.
- **D6 de `docs/closure/fable-global-v1/OPEN-DECISIONS.md`** — a autorização da
  v11_03. Nada indica que foi tomada.
- **Credenciais por referência nominal ao Cofre**, nunca por varredura de disco.
  Esta lane respeitou isso numa decisão concreta: a revisão do Gemini **não
  aconteceu** porque o CLI não tem auth nesta máquina, e buscar a chave dentro de
  `.env` de projeto seria exatamente o padrão flagrado.
