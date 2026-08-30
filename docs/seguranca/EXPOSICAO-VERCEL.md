# Exposição da superfície privilegiada na Vercel

**Data da apuração:** 24/08/2026 · **Classificação:** exposição possível, exploração **indeterminada**

Este documento é o registro de evidência. Ele não conclui que houve exploração,
e não conclui que não houve.

---

## 1. Identidade do projeto — leia antes de qualquer comando

| campo | valor |
|---|---|
| escopo / owner | `tarcisios-projects-2895d85f` |
| project name | `volc-os-campaign` |
| project ID | `prj_tn56w79cDSALjzdqLruqeGYKMaVs` |
| painel | https://vercel.com/tarcisios-projects-2895d85f/volc-os-campaign |
| alias de produção | https://volc-os-campaign.vercel.app |

> **Evidência anterior invalidada.** A primeira apuração foi conduzida contra o
> projeto **`webgo`** (`prj_yjLbJZus5dTTtaY3pBbUDP6uLriX`), porque
> `.vercel/project.json` apontava para ele e os comandos da CLI obedecem esse
> arquivo em silêncio quando não recebem `--scope` e nome de projeto. A
> cronologia que aquela apuração produziu — "produção há 52 dias, deployment
> atual de 11 dias" — **não é deste sistema** e foi descartada. O arquivo bruto
> ficou preservado fora do repositório, marcado como inválido.
>
> `./scripts/guarda-vercel.sh` existe por causa disso e recusa qualquer deploy
> enquanto o vínculo local não for exatamente o ID acima.

**Todo comando da CLI nesta investigação leva escopo e projeto explícitos:**

```bash
npx vercel ls volc-os-campaign --scope tarcisios-projects-2895d85f
npx vercel inspect <url-ou-id>  --scope tarcisios-projects-2895d85f
```

---

## 2. Janela de exposição

| fato | valor | como foi medido |
|---|---|---|
| projeto criado | 13/02/2026 17:26:16 — **192 dias** | `vercel project inspect` |
| produção vigente | `dpl_49TwodSU7GvKGcoAeGFbL9AftB27`, 16/02/2026 16:20:26 — **189 dias** | `vercel inspect` |
| deployments listados | 5 (3 Production, 2 Preview), todos `● Ready` | `vercel ls` |
| origem do build | branch `volc51` (alias `…-git-volc51-…`) | aliases do deployment |

**A janela de exposição é de 189 dias contínuos**, do primeiro deployment de
produção com funções serverless até a apuração. Nenhum deployment intermediário
retirou as rotas: as três produções carregam o mesmo conjunto.

### Aliases que respondem por esse deployment

- `https://volc-os-campaign.vercel.app`
- `https://volc-os-campaign-tarcisios-projects-2895d85f.vercel.app`
- `https://volc-os-campaign-git-volc51-tarcisios-projects-2895d85f.vercel.app`

Os três resolvem para o mesmo build. Fechar um domínio não fecharia os outros.

---

## 3. Superfície publicada

Funções serverless no deployment de produção (`vercel inspect`, seção *Builds*):

```
λ api/health          (2.7KB)     [iad1]
λ api/supabase/rpc    (201.44KB)  [iad1]
λ api/users/query     (201.45KB)  [iad1]
λ api/supabase/query  (201.65KB)  [iad1]
λ api/supabase/insert (201.46KB)  [iad1]
└── 1 output item hidden
```

A listagem resumida da CLI **omite um item**. O painel mostra a lista completa;
o pedido da §5 cobre isso. Pelos arquivos da árvore, o candidato ao item oculto
é `api/supabase/update` ou `api/users/create` — ambos privilegiados.

### O que essas rotas faziam

Todas instanciavam o cliente Supabase com `SUPABASE_SERVICE_ROLE_KEY`, **sem
nenhuma verificação de identidade**, e respondiam `Access-Control-Allow-Origin: *`.

| rota | poder |
|---|---|
| `POST /api/supabase/query` | ler QUALQUER tabela, colunas escolhidas pelo chamador |
| `POST /api/supabase/insert` | escrever em QUALQUER tabela |
| `POST /api/supabase/update` | atualizar QUALQUER tabela — inclusive `users.role` |
| `POST /api/supabase/rpc` | executar QUALQUER função do banco, `SECURITY DEFINER` inclusive |
| `POST /api/users/query` | `select('*')` em `public.users` por e-mail arbitrário |
| `POST /api/users/create` | `auth.admin.createUser` com `role` vindo do corpo |

Como `service_role` **ignora RLS**, esse conjunto é equivalente a um cliente
Postgres administrativo publicado na internet.

**Confirmação de que a credencial estava mesmo lá:** `vercel link` baixou o
`.env.local` do ambiente `development` do projeto, e ele contém `SUPABASE_URL`
e `SUPABASE_SERVICE_ROLE_KEY`. Não é inferência a partir do código — as
variáveis existem no projeto. (O arquivo está coberto por `.gitignore:94`.)

### Agravantes

- `public.users` guarda `password_hash`, `token_primeiro_acesso` e
  `token_expiracao`, e estava com **RLS desabilitada e zero policies**.
- `POST /api/supabase/update {table:'users', data:{role:'ADMIN'}}` promovia
  qualquer conta a administradora, sem login e sem rastro.
- CORS `*` é irrelevante como agravante ou atenuante: `curl` não lê
  `Access-Control-Allow-Origin`. O que expunha era a ausência de autenticação.

---

## 4. Houve exploração? — **indeterminado**

**Não é possível afirmar que não houve.**

`vercel logs <url> --scope …` foi executado contra o deployment de produção.
A saída:

```
Displaying runtime logs for deployment volc-os-campaign-dfns9dweh… (dpl_49Twod…)
starting from Aug Mo 13:12:10.72

waiting for new logs...
```

A CLI **transmite apenas logs novos, a partir do instante da chamada**. Ela não
recupera histórico. Somado a isso, a retenção de logs de runtime da Vercel é
curta e não cobre uma janela de 189 dias em nenhum plano padrão.

Portanto:

- **não há evidência de exploração;**
- **não há evidência de ausência de exploração;**
- a diferença importa: tratar "sem log" como "sem incidente" é o erro que
  transforma uma exposição de seis meses em um caso arquivado sem apuração.

O pedido da §5 é a única via que pode mudar essa classificação.

---

## 5. Pedido formal de logs — para abrir com o suporte da Vercel

> **Assunto:** Retenção e exportação de logs de acesso — projeto
> `volc-os-campaign` (`prj_tn56w79cDSALjzdqLruqeGYKMaVs`)
>
> Identificamos que funções serverless deste projeto expuseram, sem
> autenticação, operações privilegiadas de banco de dados. A exposição vigorou
> de 16/02/2026 a 24/08/2026 (189 dias), no deployment de produção
> `dpl_49TwodSU7GvKGcoAeGFbL9AftB27`.
>
> Precisamos determinar se houve acesso de terceiros. Solicitamos:
>
> 1. **Logs de requisição** (edge/runtime) do deployment
>    `dpl_49TwodSU7GvKGcoAeGFbL9AftB27` no período de 16/02/2026 a 24/08/2026,
>    para os caminhos `/api/supabase/*` e `/api/users/*`, contendo horário,
>    caminho, método, status, IP de origem, user-agent e referer.
> 2. **A lista completa de funções** publicadas nesse deployment — a saída
>    resumida da CLI omite ao menos um item.
> 3. **A política de retenção** aplicável à nossa conta para logs de runtime e
>    de edge, com a data mais antiga ainda recuperável.
> 4. Caso os logs do período não existam mais, **uma confirmação por escrito
>    disso**, com a janela efetivamente retida — precisamos registrar a
>    indeterminação, não presumi-la.
> 5. Se houver **Log Drains** ou integração de observabilidade já ativa na
>    conta, o período que ela cobre.
>
> Não solicitamos alteração de nenhum recurso. O pedido é somente de leitura.

**Onde abrir:** painel da Vercel → projeto `volc-os-campaign` → *Support*, ou
https://vercel.com/help. O CLI não atende este pedido.

---

## 6. Sequência de resposta — e por que rotação não vem primeiro

A ordem é **preservar → fechar → validar → só então decidir sobre rotação.**

| # | passo | estado |
|---|---|---|
| 1 | preservar evidência (leitura apenas) | **feito** — este documento |
| 2 | fechar a superfície no código | **feito** — fatia 1A.1a |
| 3 | validar migrations em banco descartável | **feito** — cluster criado e destruído |
| 4 | aplicar migrations em homologação e produção | pendente — **exige autorização** |
| 5 | publicar o fechamento na Vercel | pendente — **exige autorização** |
| 6 | decidir sobre rotação de `service_role` | pendente — **depende de 4 e 5** |

**Rotacionar antes de fechar não resolve nada.** Enquanto os proxies estiverem
publicados, eles continuam operando — com a chave nova. A rotação só faz
sentido depois que a superfície estiver fechada em produção, e aí ela deixa de
ser contenção e passa a ser higiene: invalidar uma credencial que pode ter
vazado durante a janela.

A **anon key** não entra nessa discussão: ela é pública por desenho, identifica
o projeto e quem protege o dado é a RLS. Rotacioná-la não fecharia nada — o
próprio bundle a publica, corretamente.

---

## 7. Arquivos preservados (fora do repositório)

`/private/tmp/evidencias-vercel/`

| arquivo | conteúdo |
|---|---|
| `LEIA-ME.md` | identidade do projeto correto e aviso de invalidação |
| `01-project-inspect.txt` | criação, framework, root directory |
| `02-deployments.txt` | os 5 deployments com idade, status e ambiente |
| `03-inspect-producao.txt` | aliases e funções do deployment de produção |
| `04-logs-runtime.txt` | prova de que a CLI só transmite logs novos |
| `INVALIDA-projeto-errado-webgo.txt` | ⚠️ coleta do projeto errado, **não é evidência** |
| `project.json.ANTES-webgo.bak` | o vínculo local incorreto, como estava |

Estão fora do git de propósito: são material de apuração com identificadores de
infraestrutura, e o repositório não é o lugar de dado de máquina.
