# Meta Operations V1 — fechamento local

**Veredito: `META_OPERATIONS_V1_LOCAL_PARTIAL`.**

O grão financeiro, o tracking de nascimento, o read model candidato e a
superfície do dashboard fecharam localmente com prova. CP5 e CP6 não fecharam, e
a razão não é código: não existe schema Meta na base oficial, não existe bucket
privado, não houve geração nem upload real, a ficha de canário não sai completa
por uma lacuna nomeada de schema, e não houve QA visual em navegador.

Declarar `COMPLETE` com esses buracos seria exatamente a afirmação que esta
missão existe para não fazer.

---

## 1. A decisão que mudou tudo, e a prova que a forçou

O sistema declarava, em código e em documentação, que

```
GAM.utm_campaign_value = Meta campaign_id
```

A operação real nunca foi assim. Os anúncios que rodaram carregam

```
utm_source={{site_source_name}}
utm_medium=paid_social
utm_campaign={{adset.id}}      ← o CONJUNTO, não a campanha
utm_term={{adset.id}}
utm_content={{ad.id}}
placement={{placement}}
```

O join por `campaign_id` casava **zero linhas** contra o dado real. A tela
mostrava receita `—` para sempre — sem errar uma conta, porque não chegava a
fazer nenhuma.

A prova tem 64 linhas campanha/dia de operação real: **62 com receita atribuída
via conjunto e 2 sem UTM de conjunto no GAM**, ambas sem entrega.
**R$ 1.029,41** investidos, **R$ 1.140,73** de receita, ROAS **1,1081**.

O grão canônico passou a ser:

```
account_ref + campaign_id + adset_id + date + metric_scope + metric_version
```

`metric_scope` entra na **identidade** da linha de propósito: é o que torna
impossível somar a leitura campaign-level às leituras adset-level. As duas medem
a mesma despesa por caminhos diferentes; somá-las dobra o gasto. A leitura de
campanha virou **reconciliação**, nunca parcela.

---

## 2. Git

| | |
|---|---|
| branch | `execution/volc-os-operacao-80-20` |
| base | `d8067053e3774e06d300e8129ed82d066be4a6e6` |
| HEAD | ver §9 |
| `d54e100` é ancestral | sim |
| `d806705` é ancestral | sim |
| worktree nova | **não** |
| branch nova | **não** |
| stash / reset / clean / rebase / merge / amend / push | **nenhum** |
| checkout principal (`main`) | **intocado**, com as 879 entradas de terceiros |

### O incidente que quase virou blocker

A worktree operacional estava **registrada**, mas quebrada: o coletor de `/tmp`
do macOS apagou o arquivo `.git`, o `pyvenv.cfg` do venv, o conteúdo de
`site-packages`, o `node_modules` e **2.372 arquivos rastreados**.

O que tornou a recuperação segura foi a medição, não a intenção: as 2.372
entradas eram **100% deleções**, com zero `M`/`A`/`R`/`C`. Não havia trabalho de
ninguém para perder. A recuperação usou `git worktree repair` (repara uma
worktree já registrada; não cria nenhuma) e `git checkout-index --all`, que **por
desenho não sobrescreve arquivo existente** — só materializa o que está ausente.

---

## 3. O que foi entregue, por checkpoint

**CP0 — raio-x.** 12 agentes read-only em paralelo, um por subsistema, cada um
citando `arquivo:linha`. 254 linhas de matriz em `AS-IS-MATRIX.json`.

**CP1 — contrato de atribuição.** `backend/app/trafego/meta/atribuicao.py`, o
grão canônico com suas recusas nomeadas. `financeiro.py` reescrito: resolve os
conjuntos filhos, lê gasto em `nivel=adset`, lê receita por
`utm_campaign_value IN (<conjuntos>)`, e deixa `totalizar` somar. Golden
sanitizado derivado do CSV real, com 33 testes.

**CP2 — tracking de nascimento.** `TRACKING_GAM_ADSET_ID`. `campaign_id`
continua na URL porque a instrumentação do site o lê — mas o contrato **não**
declara atribuição por ele: a campanha de uma receita é resolvida pelo read
model, do conjunto para o pai. O guarda da URL de destino cresceu junto
(`utm_term`, `utm_content` e `placement` entraram na lista recusada).

**CP3 — read model.** Duas views mais uma condicional, como **migration
candidata**. A pergunta obrigatória foi respondida antes de escrever DDL: o fato
do gasto por conjunto/dia **já cabia inteiro** na tabela existente, e o elo
conjunto→campanha **já era persistido**. Faltava o JOIN. Por isso o delta é
view, e não tabela — uma tabela nova duplicaria o gasto em dois lugares.

**CP4 — dashboard.** A seção "Conjuntos de anúncios" com o financeiro por
conjunto e a **prova aritmética escrita** de que o total é a soma. Divergência é
mostrada, nunca resolvida escolhendo um lado. Cinco métricas que o servidor já
calculava e o frontend jogava fora entraram na tela.

**CP5 e CP6 — bloqueados por fatos externos**, detalhados em §7.

**CP7 — pacote portável.** Contrato de empacotamento em
`WEBGO-PORTABILITY.json`, mais a correção que o torna possível: os três nós de
**escrita** do fluxo n8n carregavam a URL absoluta do Supabase enquanto a
releitura já lia `Config.SUPABASE_URL`. Trocar o Config movia a leitura e
deixava as escritas no destino antigo, **sem erro nenhum**.

---

## 4. Revisão adversarial

Revisor: `codex exec` (Codex CLI 0.153.4), sandbox read-only, esforço alto.

> ⚠️ A missão pedia `gpt-5.5-codex`. A conta recusa esse modelo — *"not supported
> when using Codex with a ChatGPT account"* — e a revisão rodou no padrão da
> conta, `gpt-6-astra`. Registrado em vez de silenciado.

**12 achados. Nenhum refutado.** 11 `CONFIRMED_FIXED`, 1 parcial com o resto
nomeado. Os dois que mexiam em dinheiro:

**Truncamento silencioso.** `financeiro.py` pedia `limit=4000` e conferia
`len(linhas) >= 4000`. O PostgREST corta em `db-max-rows` (1000) e **ignora** um
limit maior — o próprio `supabase_service.py:75-78` documenta isso. A guarda
nunca disparava: com 1.200 linhas disponíveis vinham 1.000, e as 200 que faltavam
eram classificadas como `SEM_UTM_ADSET_NO_GAM`. Leitura truncada virava "este
conjunto/dia não tem receita".

**Fan-out do GAM.** A view fazia `LEFT JOIN` por `(adset_id, date)` contra uma
tabela chaveada por `(gam_accounts_id, utm_campaign_value, date)`. Duas contas
GAM com o mesmo conjunto no mesmo dia duplicavam a linha — e portanto duplicavam
o **gasto**, que não depende do GAM para existir.

Consertar o achado 11 revelou algo maior: as "limpezas" por `DELETE` nos testes
falhavam **em silêncio**, porque o schema instala gatilhos `BEFORE DELETE` que
recusam remoção nas tabelas de insight. O schema estava certo; os testes é que
supunham poder desfazer o que gravaram.

Adjudicação por achado: `ADVERSARIAL-ADJUDICATION.json`.

---

## 5. Portões

| portão | antes da missão | depois |
|---|---|---|
| `pytest backend/tests volc_ads` | 18 failed · 5333 passed | **2 failed · 5419 passed · 75 skipped** |
| `tsc -p tsconfig.app.json` | 76 erros | **76 erros** (nenhum nos arquivos tocados) |
| vitest (serial) | 7 arquivos · 22 testes falhando | **7 arquivos · 22 testes** — o mesmo conjunto |
| vite build | ok | **ok** |
| `git diff --check` | limpo | **limpo** |
| scanner de segredos | limpo | **limpo**, com 4 padrões novos |
| validador n8n Meta | 293/0 | **293/0** |
| gerador n8n `--check` | bate | **bate** |
| ciclo PostgreSQL descartável | — | **17 testes**: apply → uso → replay → concorrência → rollback → reapply |

As 16 falhas de backend que sumiram **não foram consertadas uma a uma**: elas
eram configuração ausente. O `rootdir` do pytest é escolhido pelo ancestral comum
dos argumentos, e o comando que o próprio `pytest.ini` documenta
(`pytest backend/tests volc_ads`) lia um arquivo sem `asyncio_mode`, caindo em
`STRICT`. `test_meta_supply_bytes.py` inteiro falhava — e passa 19/19 sozinho.

**As 2 falhas restantes** (`test_canario_pedido_aprovado`) são anteriores a esta
missão e falham também em isolamento, no commit base.

**QA visual em navegador: NÃO REALIZADO.** Não há afirmação sobre 375/768/1440 px
nem sobre tema claro/escuro. O que existe é jsdom.

---

## 6. Migrations

Nenhuma foi aplicada oficialmente. `database.agenciavolc.com.br` não foi tocado.

A nova (`20260908120000` + rollback) é **candidata**, provada em cluster
PostgreSQL 16 descartável. Continuam candidatas as onze anteriores listadas em
`SCHEMA-MANIFEST.json`.

`gam_metrics` e `gam_accounts` — de onde a receita sai — **não têm DDL neste
repositório**. É schema legado. Por isso a view de receita é condicional e
separada do núcleo: amarrar o núcleo a ela o tornaria indeployável na instalação
portável que o pacote Webgo prevê.

---

## 7. O que falta, e é externo

- leitura Meta real no grão adset — **nenhuma chamada foi feita**;
- `validate_only` cobrindo adset e ad (estrutural: dependem do pai real);
- criação PAUSED de qualquer objeto;
- read-back remoto de `url_tags` com a macro expandida;
- uma linha de `gam_metrics` real casando com um `adset_id` nascido deste compilador;
- bucket privado, bytes reais, `image_hash` real;
- schema oficial: **17 tabelas e 4 RPCs ausentes**;
- QA visual autenticado.

Riscos abertos, com forma de correção: `OPEN-RISKS.json` (12 entradas).

Dois merecem destaque:

**R-06.** Uma coleta em `nivel=adset` produz linhas **órfãs** se a hierarquia não
estiver corrente: o fato não guarda o `campaign_id` pai, e o único elo é
`trafego_meta_adset`, populado por outro fluxo. Publicar o fluxo de insights sem
a hierarquia em dia é um ato incompleto — registrado no próprio gerador.

**R-01.** Uma peça gerada pelo Estúdio pode ser registrada como patrimônio na
conta do cliente **sem nenhuma avaliação de política**. O que foi feito aqui: a
afirmação falsa de que o gate havia rodado foi **corrigida no código**. Escrever
que o gate rodou é pior do que a ausência do gate — a próxima pessoa confiaria na
frase e pararia de procurar.

---

## 8. Memória operacional

`ROADMAP-VIVO.json` — `updated_at: 2026-09-08`. **P10-T16, P11-T02, P11-T03,
P11-T04, P11-T05, P11-T06** continuam `partial`. Nenhuma foi promovida: o
`done_when` da iniciativa P11 pede um primeiro lançamento seguro, e nada foi
lançado.

Achado do raio-x que precisou de conserto antes do fechamento: **P11-T02, T03 e
T04 não tinham o campo `acceptance`**. O protocolo exige provar critérios de
aceite, e sem o campo isso era literalmente inexequível. O campo foi **criado**
nas três.

`curadoria-operacional.json` — `curadoria_atualizada_em: 2026-09-08`. Nós
alterados: `cap_meta_ads`, `concept:meta_direct_traffic`, `cap_revenue_ingestion`,
`cap_attribution`. As duas primeiras afirmavam por escrito o grão errado.

Grafo reconstruído uma vez, no fim, por `scripts/atualizar_grafo_volc_os.py`.
`--check` responde `current: true`, com `input_sha256` **novo**
(`c933404e…`, contra o `ff31e7f4…` que estava stale na entrada da missão) e
`EXIT=0`. 477 nós operacionais, 739 arestas; 33.818 nós híbridos, 78.513 arestas.

---

## 9. Confirmação literal

**zero push · zero deploy · zero Meta real · zero criação · zero ativação · zero
Supabase oficial · zero migration oficial · zero n8n remoto · zero Google Ads ·
zero geração paga · zero upload de mídia · zero leitura de token · zero
`.env_webgo` · zero segredo commitado.**

`.env_webgo` **não existe** neste worktree — confirmado sem ler conteúdo.
Nenhuma URL ou chave Webgo está hardcoded no repositório.

O SHA para eventual push posterior está em `EXECUTION-RESULT.json`, campo `head`,
junto da lista completa de commits.
