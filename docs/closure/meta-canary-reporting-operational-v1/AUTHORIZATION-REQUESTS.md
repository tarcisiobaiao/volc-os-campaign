# Pedidos de autorização — Meta, canário e coleta

Cada pedido abaixo é **separado** e não implica os outros. Nenhuma autorização
histórica, de outro plano, de outra conta ou de outro SHA foi reutilizada nesta
sessão. Nada aqui foi executado.

O código a que estes pedidos se referem é o desta linha operacional:

- worktree `/private/tmp/volc-os-operacao-80-20`
- branch `execution/volc-os-operacao-80-20`
- base desta sessão `546ac50910583901d6d24611c7f37f66672bcdfa`

Para autorizar, responda citando **o identificador do pedido e o SHA exato** que
está autorizando. Um "pode seguir" genérico não é suficiente para atravessar
nenhuma destas fronteiras.

---

## CP2 — aplicar o perfil de schema no Supabase oficial

**Estado:** NÃO SOLICITADO AINDA COMO APLICAÇÃO. O que se pede primeiro é a
**leitura do catálogo**, que é um ato menor e separado.

### CP2-a — ler o catálogo oficial (leitura, sem escrita)

- **Alvo:** `https://database.agenciavolc.com.br` (única autoridade operacional,
  confirmada por `python3 scripts/verificar_autoridade_supabase.py`).
- **Ato:** executar `docs/closure/traffic-operational-closure-v2/ler-catalogo-meta.sql`
  como leitura, para descobrir **quais** dos perfis já existem no catálogo real.
- **Por que é necessário:** o manifesto declara `authority.current = LOCAL_ONLY`
  e afirma explicitamente que **não** sabe se qualquer perfil está aplicado.
  Sem esta leitura, qualquer `apply` é um palpite sobre um banco com dados.
- **Limitação conhecida deste script, a corrigir antes de usar:** ele usa
  `::regclass` sobre literais, então **aborta com erro** quando as tabelas do
  perfil não existem — exatamente o caso `NAO_APLICADO` que ele precisa
  distinguir. Uma leitura que falha fica indistinguível de um perfil ausente.
  Corrigir para `to_regclass(...)` antes de rodar.
- **Não autoriza:** nenhuma escrita, nenhum `apply`, nenhum `DDL`.

### CP2-b — aplicar o perfil escolhido

- **Perfil:** a decidir entre `CREATE_ONLY` (nascimento pausado) e
  `META_READ_MODEL` (leitura/relatório). São perfis diferentes com arquivos
  diferentes; autorizar um **não** autoriza o outro.
- **Arquivos, ordem e checksums:** exatamente os de
  `docs/closure/traffic-operational-closure-v2/SCHEMA-DEPLOY-MANIFEST.json`,
  mais a migration incremental nova desta sessão
  (`supabase/migrations/20260907210000_meta_read_model_consistency.sql`), que
  precisa ser adicionada ao manifesto com seu checksum antes da janela.
- **Executor obrigatório:** `psql`. As migrations usam meta-comandos de barra
  invertida (`\set ON_ERROR_STOP on`); um driver que envie o arquivo como SQL
  puro falha na primeira linha ou, pior, ignora o `ON_ERROR_STOP` e segue
  depois de um erro.
- **Proibição absoluta:** nunca aplicar `supabase/migrations/*.sql` por glob.
  20 dos 48 arquivos SQL do diretório são **rollbacks** que dropam tabelas e
  funções, e tanto a ordenação alfabética quanto a por timestamp intercalam
  apply e rollback na mesma passada.
- **Backup e recuperação:** ponto de recuperação antes da janela; plano forward
  e rollback preservando recibos de operação. Nenhum rerun destrutivo para
  limpar um estado parcialmente aplicado.
- **Verificação depois:** reler catálogo, funções, grants, roles, constraints e
  versão; conferir que as janelas de create continuam fechadas.
- **Diferenças já conhecidas que a janela precisa resolver:**
  - `SCHEMA-DEPLOY-MANIFEST.json` → `/local_cycle_evidence/sequence[0]` ainda
    descreve o apply de **três** arquivos, enquanto o perfil `CREATE_ONLY` tem
    **cinco**. O runbook já registra cinco. A fonte precisa concordar consigo
    mesma antes de guiar uma janela real.
  - `/produced_on_commit` aponta para `d54e100`, um commit em que três dos cinco
    arquivos declarados **não existiam**. Os checksums estão corretos; o carimbo
    de procedência não.
  - O perfil `META_READ_MODEL` não declara `catalog_probe` em nenhum passo, então
    `scripts/verificar_perfil_schema_meta.py::classificar` só consegue devolver
    `NAO_APLICADO` para ele, qualquer que seja o catálogo.

---

## CP3 — leitura e `validate_only` reais na Meta

- **Conta:** uma única conta, nomeada no ato da autorização.
- **Page, destino e peça:** exatos, nomeados no ato.
- **Janela:** período e horário nomeados.
- **Ato:** `GET` de leitura e, se autorizado explicitamente,
  `execution_options=validate_only` das raízes do plano vigente.
- **Não autoriza:** criar, editar ou ativar qualquer objeto; nem persistir no
  Supabase oficial.
- **Nota de escopo:** a prova remota histórica cobre leitura de contas e
  validação das raízes Campaign/Creative. Ela **não** comprova AdSet nem Ad, e
  **não** cobre um hash de plano novo.

---

## CP4 — um único canário Meta PAUSED

- **Escopo exato:** uma Campaign, um AdSet, um Ad e o Creative correspondente.
  Nada além disso.
- **Estados:** Campaign, AdSet e Ad nascem e permanecem `PAUSED`. O Creative
  **não** recebe um `status: PAUSED` fictício — ele tem estado de biblioteca.
- **Pré-condições:** CP1 satisfeito, o perfil de schema de CP2 aplicado e
  verificado, e CP3 tendo provado conta/Page/destino/peça e as raízes do plano
  **vigente** (não de um plano histórico).
- **Disciplina:** ledger aberto **antes** do despacho; identidades registradas
  imediatamente após a confirmação do provedor; read-back conferindo conta,
  orçamento, destino, vínculos e estados críticos.
- **Sem atomicidade prometida:** são quatro objetos independentes. Falha parcial
  **preserva** recibos e objetos conhecidos; ambiguidade **impede** reenvio
  automático; nenhum cleanup ou delete sem autorização própria.
- **Não autoriza:** ativação, segundo canário, orçamento maior, upload de mídia
  nova, nem qualquer edição posterior.

---

## Coleta operacional — Meta READ → Supabase → dashboards

Três atos **distintos**, que precisam de autorização separada:

### C-1 — leitura Meta autorizada
- Contas permitidas e datas permitidas, nomeadas.
- Somente `GET` de Insights no grão declarado em `REPORTING-CONTRACT.json`.

### C-2 — persistência no Supabase oficial
- Depende de CP2-b (o schema precisa existir).
- Requer `META_READ_MODEL_WRITE_ENABLED=1` no backend, que é um ato deliberado.
- **Atenção:** autorização de leitura **não** cobre persistência. Um `reconcile`
  pode escrever no ledger mesmo fazendo apenas `GET` na Meta.

### C-3 — n8n
São três atos diferentes e **não** se implicam:
1. **importar desativado** — o JSON entra no n8n com `active: false`;
2. **executar manualmente** — uma execução única, sob observação;
3. **ativar a agenda** — o cron passa a disparar sozinho.

Autorizar (1) não autoriza (2), e autorizar (2) não autoriza (3).

---

## Provisionamento de credencial Meta para o servidor — BLOQUEIO CONCRETO

Este é o item que **impede** a coleta agendada hoje, e ele não se resolve com
autorização: precisa de provisionamento.

**O problema, exatamente:**

- O token Meta operacional vive hoje no **Chaveiro do macOS** do operador, lido
  por `backend/app/trafego/meta/credenciais.py` através de rotas que exigem
  `darwin` + `localhost` + papel ADMIN.
- Um servidor n8n **não tem** esse Chaveiro. Ele também não deve depender de
  sessão de navegador nem de endpoint administrativo em `localhost`.
- O fluxo Google resolve o equivalente com um **tipo de credencial predefinido
  do n8n** (`googleAdsOAuth2Api`), referenciado por `nodeCredentialType`. **Não
  há evidência** neste repositório de que a instalação n8n em uso ofereça um
  tipo equivalente para a Meta, nem qual é a versão do n8n.

**O que precisa ser provisionado (contrato, não implementação):**

| item | requisito |
|---|---|
| tipo de credencial | um tipo de credencial n8n capaz de resolver um token de usuário de sistema Meta, referenciado por `nodeCredentialType`; **ou** um resolvedor de segredo server-side que o backend consulte por referência autorizada |
| permissões | somente leitura: `ads_read`. Nunca `ads_management` para esta trilha |
| escopo de contas | limitado às contas explicitamente autorizadas para coleta; a credencial não deve alcançar outras |
| titularidade | usuário de sistema do Business, não token pessoal de um operador |
| rotação | rotação e revogação previstas, sem alterar a identidade dos snapshots já gravados |
| transporte | o token **nunca** em JSON de workflow, argumento de CLI, log, prompt, variável de ambiente literal ou `Config` node |

**O que NÃO foi feito, deliberadamente:** não inventamos um nome de tipo de
credencial, não colocamos token em lugar nenhum, e não fingimos que o fluxo
autentica. O workflow gerado referencia a credencial por indireção e **não
funciona** até que este provisionamento exista — o que é a resposta honesta,
não uma pendência escondida.

---

## Achados de segurança encontrados de passagem (fora do escopo desta missão)

Registrados porque são reais e o operador precisa saber. **Nada foi alterado.**

1. `n8n/gerar_joinads_day_before_simplificado.py:7` contém um **bearer token de
   terceiro em texto puro**, emitido também para
   `n8n/joinads_day_before_simplificado.json:138` e `:199`. Não verifiquei se
   ainda é válido; deve ser tratado como comprometido e rotacionado.
2. `scripts/gate_agenda_unica_gads.py` **allowlista pelo nome** justamente esse
   arquivo (`ESPERADOS`), então a varredura não apenas deixa de barrá-lo: ela o
   abençoa explicitamente.
3. `n8n/pautador_kw_mining_webhook.json` silencia toda falha de escrita no
   Supabase — os três nós de escrita carregam `"onError":
   "continueRegularOutput"`, o padrão que o próprio validador do GAds proíbe.
4. `tools/agent-harness/gate-catalog.json` → o gate `backend-unit` roda a suíte
   **sem isolamento de rede** sobre testes documentados como capazes de tocar o
   Supabase real. Uma execução de gate rotineira faz chamadas ao projeto oficial.
5. `tools/agent-harness/gate-catalog.json` → o gate `tipos-frontend` declara
   `project_targets: []`, então compila **zero** arquivos: é estruturalmente
   verde e não prova nada.
