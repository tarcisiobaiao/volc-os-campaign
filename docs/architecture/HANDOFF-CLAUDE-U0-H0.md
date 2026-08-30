# Handoff — Claude · Sprint U0 + fundação H0

**Data:** 26/08/2026 · **Branch:** `feat/hub-trafego`
**Escopo entregue:** backend, domínio, persistência, migrations, contratos em `src/types/` e testes.
**Fora do escopo, e não tocado:** `src/components/**`, `src/pages/**`, `src/hooks/**`, curadoria e artefatos do grafo.

Contrato de referência: [HUB-MULTICANAL-CONTRATO-U0-H0.md](./HUB-MULTICANAL-CONTRATO-U0-H0.md).

---

## 1. Commits

| SHA | o quê |
|---|---|
| `c494621` | **fix** · a busca sumia na página 2 e o total encolhia a cada avanço |
| `6a63c1c` | **feat** · histórico sai do padrão e ativas sobem na lista (v9_03) |
| `1494b97` | **feat** · o adaptador de canal passa a colher a URL de destino (v9_04) |
| `76f0fd6` | **feat** · a conta decide se o funil já tem campanha, não o cadastro legado |
| `3593fa9` | **feat** · manifesto de canal e vocabulário canônico, sem `PMAX` no contrato |
| `8b906a5` | **test** · o manifesto passa a ser conferido contra o registro do engine |
| `178287a` | **docs** · este handoff |
| `43b6dc5` | **test** · prova que o grupo de conta não é fatiado entre páginas |
| `ec5f51a` | **fix** · "não tive como provar" deixa de passar por "provei e não há" |
| `530c823` | **fix** · sete defeitos que a auditoria adversarial pegou |
| `10db206` | **fix** · cursor forjado não reescreve a consulta, e o tipo `Canal` para de mentir |

Zero push. Zero deploy. Zero migration aplicada em produção. Zero mutação no Google Ads.

---

## 2. Contrato de inventário — **versão 2**

`VERSAO_INVENTARIO` subiu de `1` para `2` nos dois lados. Três mudanças que um
cliente v1 não sobrevive em silêncio:

1. **o padrão passa a excluir histórico removido** — um cliente v1 contando a
   resposta acharia que 79 campanhas sumiram do banco;
2. **`totais` troca de forma** — `campanhas` sai, entram `operacionais`,
   `historicas` e `geral`;
3. **o cursor passa a carregar o degrau de ordenação** — um cursor v1 colado numa
   chamada v2 é **recusado com mensagem**, nunca reinterpretado.

### `GET /api/trafego/inventario`

| parâmetro | tipo | default | nota |
|---|---|---|---|
| `busca` | `string` | — | casa nome **ou** id externo. Higienizada na fronteira |
| `conta` | `string[]` | — | `customer_id`, repetível |
| `projeto` | `number[]` | — | |
| `canal` | `string[]` | — | vocabulário canônico; `PMAX` e `DISCOVERY` traduzidos |
| `estado_externo` | `string[]` | — | `ENABLED`, `PAUSED`, … |
| `presenca` | `string[]` | — | os seis estados de presença |
| `frescor` | `string[]` | — | ⚠️ **aceito, validado e ignorado** — ver §7 |
| `procedencia` | `string[]` | — | |
| `atencao` | `bool` | — | |
| `vinculado` | `bool` | — | |
| **`incluir_historico`** | `bool` | **`false`** | **novo** |
| `limite` | `int` | 55 | |
| `cursor` | `string` | — | opaco; nunca offset |

**A regra do filtro explícito.** Filtrar por `estado_externo=REMOVED` ou
`presenca=removida` **liga o histórico sozinho**, sem precisar de
`incluir_historico=true`. Nomear exatamente o que o padrão esconde e receber
lista vazia seria mentira. A regra em uma frase: *o padrão só decide quando o
operador não decidiu*.

> **Para o Grok:** `hub/adaptacao.ts:136-141` pede o histórico com
> `estado_externo=['REMOVED']`. **Isso continua funcionando** — a faixa de
> histórico não fica vazia. Você pode manter como está ou trocar por
> `incluir_historico=true`; as duas formas valem.

### Envelope

```jsonc
{
  "versao": 2,
  "frescor": "recente",
  "leitura": { "lido_em": "2026-08-26T…", "idade_s": 120 },
  "parcial": false,
  "faltou": [],
  "contas": [ { "customer_id": "…", "nome": "…", "frescor": "…",
                "leitura": …, "ultima_leitura_boa": …, "motivo": null,
                "quantidade": 5, "campanhas": [ … ] } ],
  "proximo_cursor": "eyJ…",
  "totais": {
    "contas": 3,
    "operacionais": 5,   // NÃO é histórico
    "historicas": 79,    // sob os MESMOS filtros
    "geral": 84,         // a soma — NÃO é o universo do banco
    "atencao": 2
  }
}
```

⚠️ **`geral` não é o universo.** Com `busca=FGTS`, `geral` é quantas campanhas de
FGTS existem contando história — não 84. O rótulo da aba Campanhas usa
`operacionais`.

### Ordenação padrão

`customer_id` → `ordem_operacional` → `volc_campaign_id`.

| degrau | o quê |
|---|---|
| 0 | pede atenção |
| 1 | ligada |
| 2 | pausada |
| 3 | demais estados presentes |
| 4 | histórico |

A conta vem **primeiro** porque o envelope agrupa por conta: uma ordem global
partiria cada conta em pedaços espalhados por várias páginas, e o cabeçalho de
grupo apareceria três vezes com três fatias da mesma conta.

**Atenção é o eixo primário, e isso é deliberado.** Uma pausada que a conta não
confirma sobe na frente de uma ligada que está bem: a primeira é divergência
aberta, a segunda não é nada.

> **Divergência a resolver com o Grok:**
> `src/components/trafego/hub/ordenarCampanhas.ts:11-19` implementa outra ordem
> (`atenção+ENABLED=0`, `ENABLED=1`, `atenção sozinha=2`, `PAUSED=3`). O servidor
> agora ordena; reordenar no cliente sobre uma página paginada produz ordem
> local dentro de fatia global — e as duas discordam a partir da página 2.
> **Sugestão: remover a reordenação do cliente.**

---

## 3. Reconciliação — `GET /api/trafego/quadro`

Cada item de `prontos[]` ganha:

```jsonc
{
  "opportunity_id": 65,
  "run_id": 9,
  "project_id": 2,                    // novo
  "urls_publicadas": ["https://…"],   // novo — as URLs REAIS, não só quantas
  "campanhas_lancadas": 1,            // number | null — NÃO é mais a autoridade
  "reconciliacao": {
    "opportunity_id": 65,
    "run_id": 9,
    "estado": "correspondencia_provavel",
    "candidatas": [
      { "volc_campaign_id": "gads-…",
        "externa": { "customer_id": "…", "campaign_id": "…" },
        "nome": "…", "estado_externo": "ENABLED", "canal": "SEARCH",
        "historico": false, "vinculo_id": null,
        "sinais": [ { "regra": "url_no_nome_declarado", "forca": "medio",
                      "evidencia": { "url": "…", "lida_de": "nome_da_campanha" } } ] }
    ],
    "sinais_ausentes": [ { "regra": "linhagem_declarada", "motivo": "…" } ],
    "acao_permitida": "confirmar_vinculo",
    "exige_confirmacao_humana": true,
    "pode_montar": false,
    "pode_relancar": false
  }
}
```

### Estados e ações

| estado | ação | `pode_montar` | `pode_relancar` |
|---|---|---|---|
| `vinculada` | `abrir_o_que_existe` | false | false |
| `correspondencia_provavel` | `confirmar_vinculo` | false | false |
| `conflito` | `abrir_revisao` | false | false |
| `somente_historico` | `relancar_declarado` | false | **true** |
| `sem_campanha` | `montar` | **true** | false |

### Regras e força

| regra | força | de onde vem |
|---|---|---|
| `url_final_da_conta` | forte | lida do **anúncio** pela varredura — observação |
| `linhagem_declarada` | forte | intenção registrada e imutável (ADR-02) |
| `url_no_nome_declarado` | médio | terceiro campo da taxonomia — declaração nossa, espelhada |
| `lancamento_declarado` | médio | `campaigns.funnel_run_id` — a tabela legada, agora como **sinal** |

`forte` é o que foi **observado** na conta; `medio` é o que foi **declarado** por
nós. Uma declaração pode estar desatualizada: alguém renomeia a campanha no
painel do Google e ela deixa de ser verdade sem que nada perceba.

### Três decisões que o dado real forçou

**Histórico não gera conflito.** Um funil tem três campanhas na conta, duas
removidas. Contá-las todas daria conflito, e conflito bloquearia o operador por
causa da própria história de relançamento (E-05). O que disputa o leilão é o que
está no ar.

**URL da conta e URL do nome não somam.** A segunda é a **origem** da primeira:
nosso lançador escreveu a URL no nome, e a conta a espelhou de volta. Somá-las
contaria o mesmo fato duas vezes.

**`sem_campanha` não pode significar duas coisas.** "Provei e não há" libera a
montagem; "não consegui provar" não deveria. `sinais_ausentes` nomeia cada regra
que não pôde correr, e a prova que falha devolve `reconciliacao: null` com
`campanhas_lancadas: null` — nunca zero.

> **Para o Grok:** `preparar/estados.ts:29` faz
> `if ((c.campanhas_lancadas ?? 0) > 0) return 'vinculada'`. Com o contrato novo,
> leia `c.reconciliacao.estado` direto, e trate `reconciliacao: null` como
> "não foi possível provar" — **não** como `sem_campanha`. O `?? 0` transforma
> "não apurado" em "não há", que é o defeito que esta rodada fecha.

### Rotas de vínculo

```
POST /api/trafego/vinculos
  { volc_campaign_id, opportunity_id?, project_id?, funnel_run_id?,
    regra, evidencia, vinculo_anterior? }          → 201 { vinculo: {…} }

POST /api/trafego/vinculos/{vinculo_id}/desfazer
  { motivo? }                                      → 200 { vinculo: {…} }
```

Portão `exigir_usuario` nas duas. `confirmado_por` e `desfeito_por` saem do
**token**, nunca do corpo — aceitar do corpo deixaria qualquer um assinar com o
nome de outro, numa tabela cujo propósito é dizer quem decidiu o quê.

Desfazer é `UPDATE`, nunca `DELETE`: a linha é o rastro de que houve um vínculo.

---

## 4. Vocabulário de canal e manifesto

`Canal` passa a ser `'SEARCH' | 'DISPLAY' | 'DEMAND_GEN' | 'PERFORMANCE_MAX'`.

`PMAX` **saiu do contrato**. Ele não existe no enum do Google nem no engine;
persistir, filtrar ou devolver esse valor era uma string que só existia entre
nós. O apelido continua **aceito na entrada** e traduzido numa fronteira só —
`canalCanonico()` em `src/types/trafego.ts` — porque um link antigo com
`?canal=PMAX` precisa abrir. `DISCOVERY` entra junto: é o nome anterior de
Demand Gen e a conta ainda o responde.

`GET /api/trafego/inventario/vocabulario` passa a publicar:

```jsonc
{
  "plataformas": ["GOOGLE_ADS", "META_ADS"],
  "manifestos": [ { "plataforma": "GOOGLE_ADS", "canal": "SEARCH",
                    "rotulo": "Search",
                    "hierarquia": ["campanha","grupo","anuncio","keyword"],
                    "paineis": [...], "campos_do_pedido": [...],
                    "capacidades": ["ler","propor"],
                    "provas_obrigatorias": ["politica","duplicidade","selo"],
                    "indisponibilidades": [], "sabe_criar": true }, … ],
  "estados_de_reconciliacao": ["vinculada", …]
}
```

**A tela deriva cada CTA daqui, e não da lista de canais.** Quatro canais não são
quatro botões de "criar": existe um único construtor, e oferecer os outros por
simetria visual faz o operador descobrir a ausência depois de montar o pedido
inteiro. `indisponibilidades` é a frase que a tela mostra — a diferença entre um
botão cinza sem explicação e uma recusa que ensina.

**Meta declara `capacidades: []`** — nem ler. Não há credencial, adaptador nem
conta ligada. É o que impede a tela de mostrar "0 campanhas" para o Meta, que
afirmaria uma leitura que ninguém fez. O nível 2 dele chama-se **`conjunto`**, e
traduzi-lo para "grupo de anúncios" faria o operador procurar no painel do Meta
uma palavra que não existe lá.

---

## 5. Migrations — **validadas, NÃO aplicadas**

| arquivo | o quê | risco |
|---|---|---|
| `v9_03_historico_e_ordem_operacional.sql` | publica `historico` e `ordem_operacional` na view | substitui **uma view**; sem dado, sem tabela, sem RLS |
| `v9_04_url_final_preservada.sql` | põe `url_final` entre os rótulos preservados | substitui **o corpo de uma função** de gatilho |
| `v9_03_rollback.sql` | **reverte** a v9_03 (DROP + CREATE + grants) | o rollback "óbvio" não funciona — ver §8c |

Ambas validadas em cluster descartável (`initdb` → v9_01 → v9_02 → v9_03 →
v9_04), com provas dentro da própria transação: colunas publicadas, `service_role`
com `SELECT`, `anon` recusado.

**Rollback.** v9_03 → **`v9_03_rollback.sql`, e só ele**. Reaplicar a v9_02
**não** reverte: `CREATE OR REPLACE VIEW` sabe trocar expressão e acrescentar
coluna no fim, mas não sabe remover — devolve `cannot drop columns from view` e
aborta. Medido. O ciclo aplicar → reverter → reaplicar foi provado ponta a ponta
em cluster descartável.

v9_04 → reaplicar a definição da função como está na seção 5 da v9_01 (difere em
uma linha).

⚠️ **Reverter o schema exige reverter o código junto.** A U0 filtra por
`historico` e ordena por `ordem_operacional`; sem as colunas, toda leitura do
inventário responde erro do PostgREST.

⚠️ **A U0.1 não funciona em produção antes da v9_03.** Sem as colunas, o filtro
`historico=is.false` e o `order=ordem_operacional.asc` devolvem erro do PostgREST.

⚠️ **`supabase/migrations/README.md` se contradiz** sobre v9_01: a tabela do topo
diz APLICADA em 25/08 07:26:41-03 e a seção "Série v9" diz não aplicada. Eu não
editei o README (não é meu ownership nesta rodada). **Codex: resolver antes de
aplicar qualquer coisa.**

---

## 6. Arquivos alterados

**Criados**
```
backend/app/trafego/reconciliacao.py
backend/app/trafego/plataforma.py
backend/tests/test_trafego_reconciliacao.py
backend/tests/test_trafego_plataforma.py
supabase/migrations/v9_03_historico_e_ordem_operacional.sql
supabase/migrations/v9_04_url_final_preservada.sql
docs/architecture/HANDOFF-CLAUDE-U0-H0.md
```

**Modificados**
```
backend/app/trafego/dominio.py            e_historico, ordem_operacional, PAUSADA
                                          + ordem dos termos de pede_atencao
backend/app/trafego/inventario.py         incluir_historico, cursor de 3 chaves,
                                          VERSAO 2, totais por natureza
backend/app/trafego/persistencia.py       and único, contagem sem cursor, order,
                                          keyset de 3 chaves, FonteDeReconciliacao
backend/app/trafego/sincronizador.py      grava url_final quando o perfil a declara
backend/app/trafego/adaptador_search.py   colhe url_final de ad_group_ad
backend/app/routers/trafego.py            /quadro usa reconciliação
backend/app/routers/trafego_inventario.py incluir_historico, rotas de vínculo,
                                          manifesto no vocabulário
src/types/trafego.ts                      VERSAO 2, totais, Canal canônico,
                                          Reconciliacao, ManifestoDeCanal
backend/tests/test_trafego_inventario.py  dublê deriva as colunas da view
backend/tests/test_trafego_persistencia.py 8 provas novas contra Postgres real
backend/tests/test_trafego_sincronizador.py duas entidades filhas
backend/tests/test_trafego_alertas.py     declara as rotas novas no portão
```

---

## 7. Incompatibilidades e pendências verdadeiras

### ⚠️ O que o Grok precisa mudar — **duas linhas, e uma prova**

O tipo `Canal` passou a declarar **seis** valores, porque é isso que a API emite:
`SEARCH`, `DISPLAY`, `DEMAND_GEN`, `PERFORMANCE_MAX`, **`VIDEO`** e
**`SHOPPING`**. A conta pode ter campanha de Vídeo, e escondê-la seria mentir
sobre o que está gastando.

Isso tem duas consequências no front, e **as duas apontam para o mesmo
conserto**:

1. **`formato.tsx:163`** — `PALAVRA_DO_CANAL: Record<Canal, string>` ficou
   incompleto. Faltam `VIDEO` e `SHOPPING`. O `tsc` acusa `TS2739`.

2. **`onze-estados.test.tsx`, 2 provas vermelhas** — elas usam `VIDEO` como
   exemplo de "canal que o servidor conhece e este pacote não". `VIDEO` deixou
   de ser desconhecido: `canalCanonico('VIDEO')` agora devolve `'VIDEO'`, e
   `PALAVRA_DO_CANAL['VIDEO']` devolve `undefined` — que é pior que a frase que
   o teste protegia.

   **Sugestão de exemplo novo:** `'HOTEL'`. É um enum real do Google que o
   espelho pode gravar (a CHECK da v9_01 aceita quinze) e que a API **não**
   emite (o contrato emite seis). É exatamente o caso que o teste descreve.

O erro de tipo e a falha de teste são a mesma pressão, no lugar certo: a tela
precisa ter uma palavra para todo valor que o servidor pode mandar.

**Estado ao entregar:** frontend **554 passa · 2 falham** por este motivo, e
nada mais.

### Como ficou a colisão anterior (resolvida)

`npx tsc --noEmit -p tsconfig.app.json`: **81 erros**, sendo **76 o baseline
herdado do webgo** e **5 a colisão de contrato**, todos em arquivos em voo:

| arquivo | erro | conserto |
|---|---|---|
| `hub/contrato.ts:47` | `'PMAX'` não é `CanalDoHub` | trocar por `'PERFORMANCE_MAX'` |
| `hub/contrato.ts:69` | `CandidatoPreparar` estende mal | `reconciliacao` agora é objeto, não string |
| `hub/adaptacao.ts:30-31` | `'PMAX'` | idem |
| `hub/perfilDeCanal.ts:98,101` | `'PMAX'` | idem |
| `hub/__tests__/adaptacao.test.ts` | `'PERFORMANCE_MAX'` não cabe em `CanalDoHub` | resolve junto |
| `preparar/__tests__/reconciliacao.test.tsx:22` | `RECONCILIACAO_PENDENTE` não existe | do próprio front |

### Dívidas que continuam abertas

1. **`filtros.frescor` é filtro fantasma** — aceito, validado e nunca consumido
   (`inventario.py:284`, `:340`). Nenhum leitor em `montar_inventario` nem em
   `params_de_campanhas`. Ou vira filtro real, ou sai do contrato.
2. **`presenca=presente` devolve zero linhas** — o vocabulário aceita
   (`ESTADOS_DE_PRESENCA` o publica), mas no banco "presente" é `NULL` e
   `presenca.in.(presente)` não casa nada.
3. **`nao_espelhada` não é filtrável** — a view a emite, `presenca_projetada` a
   traduz para `conta_nao_identificada`, e nenhum filtro a alcança.
4. **`estado_externo` aceita qualquer texto**, sem vocabulário nem recusa —
   diferente de canal, presença, frescor e procedência, que recusam com a lista.
5. **`atencao` e `pede_atencao` divergem num caso**: `impressoes > 0` e
   `cliques = NULL`. Em SQL, `cliques = 0` avalia NULL e cai no `ELSE false`; em
   Python, `sintoma_de_entrega` decide outra coisa. O teste de paridade não cobre
   essa linha porque nenhuma fixture a produz.
6. **`IMPRESSOES_PARA_CULPAR_O_ANUNCIO = 100` continua duplicado** entre
   `dominio.py` e `projecao.ts`. A direção decidida é a API devolver o sintoma já
   classificado; não entrou nesta fatia.
7. **`test_mesmos_query_params_da_fonte_antiga` está morto** — `skipif` sobre uma
   classe que já foi removida. Sempre pula, e ninguém foi avisado.
8. **Orçamento de contagem**: `contagem()` faz um `HEAD` por conta e
   `contagem_por_natureza` faz mais dois. Com 3 contas são ~6 requisições; a
   credencial alcança **39 contas anunciáveis**. A partir de ~20, vale trocar por
   uma RPC de agregação.
9. **`campaign_lineage_id` é `NULL` em 100% das campanhas** — a regra
   `linhagem_declarada` existe e nunca dispara. Ela aparece corretamente em
   `sinais_ausentes`.
10. **Nenhuma superfície de proposta/escrita** — nenhum canal declara `escrever`,
    e a escada (fato → proposta → antes/depois → validação → autorização →
    execução idempotente → recibo → releitura → verificação) tem só os dois
    primeiros degraus declarados.

---

## 8. Testes executados

```
backend    691 passed · 17 skipped · 3 failed (herdados, ver abaixo)
frontend   556 passed · 42 arquivos · zero falha
tipos      77 erros = 76 do baseline + 1 de um arquivo que não devia existir
build      verde (vite, 5,2 s)
bundle     zero token privilegiado
```

**A colisão de contrato com o front SE RESOLVEU.** Ela existiu enquanto o Grok
tinha os arquivos em voo; na última medição, `hub/` e `preparar/` acusam **zero**
erros — ele já convergiu para `PERFORMANCE_MAX` e para `reconciliacao` como
objeto. A tabela da §7 fica como registro do que foi negociado, não como
pendência.

⚠️ **O 77º erro vem de `src/components/trafego/inventario/formato 2.tsx`** — um
dos quatro arquivos com sufixo `" 2"` que são cópia de Drive/Finder (o `npm`
nunca cria nome com espaço). Ele é **não rastreado**, tem **zero imports**, e o
arquivo real (`formato.tsx`) já está correto. Mas o `tsc` varre `src/` inteiro, e
a cópia velha ainda declara `PMAX` — então ela agora **polui o gate de tipos**.

Não removi: remover arquivo fora do meu escopo é proibido nesta rodada. **Codex:
esta é a hora de decidir.** Os quatro são
`EstadosDoInventario 2.tsx`, `Selos 2.tsx`, `formato 2.tsx` e `useInventario 2.ts`.

**Sobre o bundle.** O único JWT que chega ao navegador tem `role: anon` — pública
por construção. Nenhum papel privilegiado. Duas observações que não são desta
fatia mas ficam registradas:

- o bundle contém o **texto-fonte** de uma Edge Function do Meta CAPI, que lê
  `Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")`. É o CÓDIGO da função, não a chave
  — nenhum valor de segredo viaja. Ainda assim, código de servidor no bundle do
  cliente é superfície que ninguém pediu;
- os testes do frontend passam apesar dos 5 erros de tipo, porque o `vitest` não
  faz checagem de tipos. O gate real é o `tsc`.

As **3 falhas herdadas** são de ambiente, não da fatia — a máquina não tem
`google-ads` instalado:
`test_seguranca_hub.py::test_a_trava_esta_fechada_e_recusa_escrita`,
`test_seguranca_hub.py::test_nem_um_admin_autenticado_abre_a_trava`,
`test_trafego.py::test_o_selo_e_pre_requisito_de_subir`.
Medidas iguais no baseline (`3 failed, 631 passed`) antes de qualquer mudança
minha.

⚠️ **`test_notificacoes.py` e `test_trafego_canal_de_criacao.py` não coletam**
nesta máquina (`ModuleNotFoundError: google.ads`). Foram excluídos das rodadas;
**Codex precisa rodá-los num ambiente com o SDK.**

⚠️ **A suíte usa `pytest-randomly`.** Sem `-p no:randomly` a ordem varia e duas
falhas herdadas ficam intermitentes. Todas as medidas acima usam ordem fixa.

---

## 8b. Prova contra o dado real de produção — somente leitura

Rodei a reconciliação contra os funis e as 84 campanhas reais, lidos do Supabase
oficial. Nenhuma escrita, nenhuma chamada ao Google.

| run | funil | estado | `pode_montar` | `exige_confirmacao` | candidatas |
|---|---|---|---|---|---|
| 6 | permalink de rascunho | `sem_campanha` | **true** | **true** | 0 |
| 7 | maquininha | `correspondencia_provavel` | false | true | 2 (1 no ar) |
| 9 | fgts | `correspondencia_provavel` | false | true | 3 (1 no ar) |

- **run 9 é o caso que motivou a rodada.** `campaigns` não tem linha nenhuma para
  ele, e a regra antiga respondia `campanhas_lancadas: 0` → "montar campanha".
  Agora as três campanhas dele aparecem: uma ENABLED e duas no histórico. E a
  história **não virou conflito**.
- **run 7 continua reconhecido**, por dois caminhos independentes:
  `url_no_nome_declarado` e `lancamento_declarado`.
- **run 6 é o caso honesto**: montar continua liberado — quase todo funil novo
  começa em rascunho —, mas com confirmação, porque não houve como comparar.
- A regra que disparou nos dois foi `url_no_nome_declarado`. `url_final_da_conta`
  aparece corretamente em `sinais_ausentes`: a coluna ainda é nula porque a
  varredura que a colhe (v9_04 + uma sincronização) não rodou.

---

## 8c. Auditoria adversarial

Cinco lentes independentes (paginação/cursor, SQL, reconciliação, segurança,
contrato) sobre o diff da fatia, com Postgres descartável e execução real.
**46 achados brutos.** Os que se sustentaram com prova viraram conserto:

| # | achado | gravidade |
|---|---|---|
| 1 | a v9_04 **apagou uma guarda da v9_01** — "nenhum número sem carimbo", a regra A do schema | grave |
| 2 | o **rollback da v9_03 não executava** (`cannot drop columns from view`) | grave |
| 3 | **UTM na URL do anúncio derrubava a regra mais forte** → `sem_campanha`, que libera a montagem | grave |
| 4 | **universo vazio virava prova de ausência** — "conta nunca varrida" e "conta vazia" chegavam idênticos | grave |
| 5 | **dois runs da mesma oportunidade trocavam de veredito** (`reconciliar_muitos` chaveava só por `opportunity_id`) | grave |
| 6 | `int(None)` em `project_id` derrubava `/quadro` inteiro | média |
| 7 | `projects` com `limit: 200` sem ordem — teto silencioso que liberava a montagem | média |
| 8 | **cursor forjado reescrevia a árvore booleana** do PostgREST | média |
| 9 | o tipo `Canal` declarava 4 e a API emitia 6 | média |

O achado 1 é o mais instrutivo: `CREATE OR REPLACE FUNCTION` substitui o **corpo
inteiro**, e reescrever a função para acrescentar uma linha apagou oito que não
foram copiadas de volta — em silêncio, com a migration reportando sucesso. A
v9_04 agora difere da v9_01 em exatamente uma linha, recusa-se a aplicar se a
guarda sumir, e há teste contra Postgres real.

### O que a auditoria levantou e **não** virou conserto

- **A `anon key` do bundle tem `iss: supabase-demo`** — e a verificação foi
  feita: **`DEFAULT_INSEGURO`**. O `JWT_SECRET` vivo é idêntico ao segredo
  público de demonstração, e as duas chaves são assinadas por ele. Incidente
  crítico aberto em [`docs/INCIDENTE-JWT-SECRET.md`](../INCIDENTE-JWT-SECRET.md),
  com plano de rotação **não executado**. **A série v9 está parada por causa
  dele.**
- **`atencao=false` apaga a conta que falhou inteira**, inclusive o histórico que
  a própria view diz não pedir atenção (`_familia_falha` devolve `None`). É
  anterior a esta fatia.
- **URL preservada era apresentada como observação FORTE.** ✅ Fechado em
  `fe29d80`: a força passou a ser `historica` — sustenta a candidata e não fecha
  o vínculo sozinha. Volta a `forte` quando existir `url_final_lida_em`.
- **O canal não entra na decisão da reconciliação.** Uma campanha Display para a
  mesma URL bloqueia a montagem de uma Search. Deliberado por ora — a pergunta do
  quadro é "este funil tem campanha?", e tem —, mas o canal viaja em cada
  candidata para a tela poder dizer qual é.

### A refutação fechou: **138/138**

3 céticos por achado × 46 achados, cada um com viés de refutar e instruído a
marcar "refutado" na dúvida. **12 sobreviveram** à maioria.

| # | achado | gravidade | votos | estado |
|---|---|---|---|---|
| 1 | a chave do keyset se movia — varredura no meio da paginação engolia campanhas | **alta** | 3/3 | **corrigido** `c49cf30` |
| 2 | `sem_campanha` quando nenhuma regra pôde comparar | **alta** | 2/3 | **corrigido** `ec5f51a` |
| 3 | `atencao=false` apagava a conta que falhou inteira | média | 3/3 | **corrigido** `fc7c946` |
| 4 | o sino divergia da coluna `atencao` da view | média | 3/3 | **corrigido** `fc7c946` |
| 5 | cursor forjado reescrevia a árvore booleana | média | 2/3 | **corrigido** `10db206` |
| 6 | `frescor` aceito, validado e ignorado | média | 3/3 | **corrigido** `f763120` |
| 7 | índice único de vínculo virava 502 | média | 3/3 | **corrigido** `fc7c946` |
| 8 | `POST /vinculos` não conferia a campanha | média | 2/3 | **corrigido** `fc7c946` |
| 9 | o motivo do sinal ausente afirmava comparação que não houve | média | 3/3 | **corrigido** `fc7c946` |
| 10 | vincular liberado a papel revogado | média | 2/3 | **corrigido** `fc7c946` |
| 11 | `desfazer` com id inválido devolvia 502 | baixa | 3/3 | **corrigido** `fc7c946` |
| 12 | detalhe de erro vazava estrutura do banco | baixa | 3/3 | **corrigido** `fc7c946` |

**Nenhum virou pendência.** A instrução permitia que os médios virassem, desde
que não comprometessem autorização, rollback, reconciliação ou integridade do
inventário — e os seis médios tocavam exatamente esses quatro.

#### O achado 1 merece ser lido

Foi **regressão minha**, do commit `6a63c1c`, e a auditoria a provou contra
Postgres real com o código de verdade.

`ordem_operacional` virou a segunda chave do keyset, e eu a calculava incluindo
`tentativa_resultado` — que vem de `trafego_snapshot_conta`, é da **conta**. Uma
única gravação de snapshot reescrevia o degrau de todas as campanhas dela ao
mesmo tempo, e o cursor emitido antes passava a apontar para um ponto que não
existia mais.

```
conta com 6 campanhas saudáveis, limite 3
  página 1                    → C-1, C-2, C-3   (cursor no degrau 1)
  varredura falha entre elas  → as seis vão ao degrau 0
  página 2                    → LISTA VAZIA, proximo_cursor: null
```

C-4, C-5 e C-6 sumiam da listagem enquanto `totais.operacionais` continuava 6.
Sem erro, sem aviso, sem "carregar mais" — a tela ficava coerente consigo mesma
e errada.

O degrau agora depende só de colunas do espelho. Uma varredura que **falha** nem
toca no espelho: os degraus não se movem. A falha da conta continua em `atencao`
(o sino conta) e no cabeçalho do grupo (`frescor: falhou`); o que saiu foi só a
**ordem**, porque ordem precisa de chave estável.

---

## 9. Para o Codex, na integração

1. **Resolver a contradição do `supabase/migrations/README.md`** sobre v9_01
   antes de aplicar qualquer coisa.
2. **Aplicar v9_03 e v9_04** com preflight/postflight, e registrar no README com
   data, ambiente, executor, hash, `security_invoker`, ACLs, `anon` recusado e
   rollback — no mesmo formato de v9_01/v9_02.
3. **Rodar uma varredura real** depois da v9_04 para popular `url_final`. Só
   então a regra `url_final_da_conta` sai de `sinais_ausentes` e passa a ser o
   sinal forte que a doutrina promete. Somente leitura.
4. **Validar no navegador** com as 84 campanhas: padrão sem histórico, "carregar
   mais" atravessando degraus, os cinco totais, e o quadro de Preparar mostrando
   os funis reais sem oferecer duplicação.
5. **Rodar `test_notificacoes.py` e `test_trafego_canal_de_criacao.py`** num
   ambiente com `google-ads`.
6. **Curadoria e grafo** — a reconciliar depois da convergência:
   `cap_inventario_trafego=implemented` contra `wave:P0-T`,
   `concept:multichannel_inventory`, `wave:P0-R` e `concept:reconciliation`,
   todos ainda `todo`.
