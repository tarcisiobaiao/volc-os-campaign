# Meta — canário pausado, dados reais e dashboards operacionais

Entrega local sobre a base `546ac50910583901d6d24611c7f37f66672bcdfa`, na branch
`execution/volc-os-operacao-80-20`, worktree `/private/tmp/volc-os-operacao-80-20`.

**Isto não é aceite de produção.** Nenhuma conta Meta foi consultada, nenhum
objeto foi criado, nenhum schema oficial foi aplicado, nenhum workflow foi
importado ou ativado, e nenhum dado real atravessou a cadeia. O que existe é
implementação local provada com a rede bloqueada, mais os pedidos de autorização
prontos para os atos que faltam.

## Preflight — o que foi confirmado antes de editar

- HEAD igual ao SHA declarado, árvore limpa, sem divergência.
- `546ac509` e `0c2723e5` são ancestrais; nenhum reset, rebase, merge, amend,
  stash ou limpeza destrutiva. Escritor único.
- Processos próprios da worktree: Vite em `:8080`, API Node em `:3001`, uvicorn
  `--reload` em `:8010`, todos filhos de `./start-dev.sh`.
- `python3 scripts/verificar_autoridade_supabase.py` → `✓ Supabase oficial:
  https://database.agenciavolc.com.br`. Isso confirma a configuração; **não** é
  autorização de acesso, e nenhum acesso foi feito.

### O watcher foi desligado de propósito

`backend/app/main.py::_reconciliar_runs_orfaos` roda no `startup` e, quando o
Supabase está habilitado, faz `supa.select("pautador_funnel_runs", …)` **e**
`_atualizar(...)` — uma leitura **e uma escrita** no Supabase oficial. Não existe
flag que a desligue. O uvicorn rodava com `--reload`, e autoreload reexecuta o
startup.

Editar Python com o watcher no ar produziria uma reconciliação oficial **por
save** — dezenas de efeitos externos não autorizados. Então o uvicorn foi parado
antes da primeira edição de Python, e Vite (`:8080`) e a API Node (`:3001`)
ficaram no ar o tempo todo. O backend é reiniciado uma única vez no fim, e esse
único startup é declarado como efeito.

## O que mudou, e por quê

Quatro commits lineares. Nada foi corrigido "porque um spec antigo mandava": a
adjudicação foi feita contra o HEAD, e ela mostrou que **T05 e T07 estavam byte
a byte iguais à base do spec** — os commits `21fb1f2..546ac509` tocaram só a
trilha de criação/fencing. Nenhum defeito deste marco tinha sido corrigido antes.

### T05 — perguntar a coisa certa aos Insights (`91bab53`)

O número que a Meta devolve depende inteiramente do que foi pedido, e o pedido
não existia como contrato.

| defeito medido | antes | agora |
|---|---|---|
| LPV somava ViewContent | LPV=4 + VC=7 → **11** | **4** |
| action presente sem valor | **0** | **NULL** |
| `time_increment` | nunca enviado (30 dias voltavam como 1 linha agregada, guardada como série) | enviado, e parte do grão |
| `action_report_time` | nunca enviado | enviado, e parte do grão |
| janela de atribuição | carimbada sem ter sido pedida | o **tipo recusa** rótulo que não corresponda ao pedido |
| "hoje" | `date.today()` do host | fuso real da conta |
| `campaign_id` ausente no nível campaign | virava o **id da conta** | erro tipado |
| `action_values` | nunca pedido | pedido e guardado separado de `actions` |

O carimbo falso deixou de ser possível **por construção**: `InsightMeta` recusa
um fato cuja etiqueta de janela não corresponda às janelas solicitadas.

### T07 — o filtro de conta precisa chegar aos conjuntos e anúncios (`552349a`)

```python
if conta_opaca and entidade in {"campanhas", "criativos", "insights"}:
    params["ad_account_ativo_id"] = f"eq.meta_account_{conta_opaca}"
```

Conjuntos, anúncios e mensuração caíam no `else` implícito e o parâmetro era
descartado em silêncio: pedir os conjuntos da conta A devolvia também os da B.
As duas tabelas não têm coluna de conta — penduram-se em campanha e conjunto —
então escopá-las exige caminhar os pais, com teto declarado.

`detalhe` não recebia conta nenhuma: **um id era a própria autorização**.

`limit: 500` com `order: observado_em.desc` se apresentava como inventário
completo. Não era paginação e nem era ordem total — todas as linhas de um
snapshot compartilham `observado_em`, então o corte em 500 era arbitrário.

### Rodada corretiva sobre o próprio delta (`c339764`, `8089eab`)

Uma revisão adversarial encontrou sete defeitos **no trabalho desta sessão**:
completude calculada e descartada na fronteira; grão não chegando à linha;
`action_values` lido e descartado; chave de idempotência dependendo do instante
da leitura; `/recibo/ultimo` devolvendo o recibo de outra conta;
`object_story_id` (`<page_id>_<post_id>`) vazando para o navegador; e linha sem
dia próprio ganhando o dia pedido. Todos corrigidos com contraprova.

### T09 — o vocabulário de retorno (`METRIC-CONTRACT.json`)

`calculateROAS` não devolve ROAS: devolve o **excedente** sobre o gasto. Para
receita 200 e gasto 100 ela responde `100`, enquanto ROAS vale `2`.

**Decisão (O02): a função legada fica byte a byte como está**, marcada como
deprecated. Dez arquivos a consomem, cinco deles painéis do Google, e as faixas
de cor estão calibradas na escala do excedente. Trocar a fórmula global
recoloriria cinco páginas e reescreveria relatórios históricos em silêncio.

O que passou a existir são os nomes certos, com unidade no nome e ausência que
continua ausência: `roasRatio` (razão), `retornoExcedentePct` (%), `lucroBruto`,
`roiLiquidoPct`. Um teste prova que a razão `2` cairia na faixa "laranja"
enquanto o excedente `100` é "verde" — é exatamente esse o risco de unificar
nomes sem unificar escalas.

### Marco C — n8n (`7084995`)

Gerador, workflow e validador espelhando a trilha do Google. Nascido `active:
false`. O dia é o da **conta**: às 02:00Z de 07/09 uma conta em São Paulo pede
2026-09-05 e uma em Tóquio pede 2026-09-06 — se a janela viesse do servidor as
duas seriam iguais. Conta sem fuso é recusada, nunca cai em UTC.

**Paridade provada, não prometida:** o fluxo e `persistencia.linhas_de_insights`
calculam o `meta_insight_daily_id` cada um do seu lado, um em JS e outro em
Python. Se divergirem, o mesmo fato entra duas vezes com duas chaves e a
projeção `latest` expõe duas "revisões correntes" — sem nenhum dos dois lados
reclamar. Existe um teste que refaz a identidade pelo lado Python a partir do
que o fluxo gravou e exige o mesmo id.

### Schema — migration candidata (`85eebb3`)

Delta **incremental** sobre v15_02, correto exista ou não v15_02 no catálogo
oficial. Fecha nove defeitos, entre eles: ausência que nunca era marcada;
snapshot antigo sobrescrevendo o novo; falta de projeção `latest`; custódia de
Cofre gravada como `verified` por uma **leitura**; identidade de credencial vinda
do payload do chamador; e `service_role` mantendo DELETE e TRUNCATE porque o ACL
padrão nunca foi revogado.

## Provas

| gate | resultado | isolamento |
|---|---|---|
| testes Meta (Python) | **290 passaram** | TCP bloqueado |
| testes n8n Meta | **31 passaram** | TCP bloqueado |
| suíte backend inteira | **4108 passaram**, 38 falharam, 13 erros | TCP bloqueado |
| SQL do read model | **145 asserções, 0 falhas** | PostgreSQL descartável, loopback |
| validador n8n Meta | **264 provas, 0 falhas** | local |
| validador n8n Google | **337 provas, 0 falhas** (não regrediu) | local |
| gate de agenda única | **12 provas** · "UMA autoridade escolhida e NENHUMA ligada" | local |
| geradores `--check` | Meta ok, Google ok | local |

**Sobre as 38 falhas da suíte inteira:** estão confinadas a seis arquivos —
`test_adspower_broker_hermetico`, `test_trafego`, `test_quadro`,
`test_publicar_pagina`, `test_reler_wordpress`, `test_canario_pedido_aprovado` —
e **nenhum deles importa qualquer módulo do delta**. A causa visível é
`AssertionError: NETWORK BLOCKED DURING REVIEW`: são testes que precisam de rede
ou de Supabase real e falham **porque** o isolamento foi mantido. O isolamento
não foi retirado para deixá-los verdes. Não afirmo que passariam sem ele: não
testei sem ele, de propósito.

## O que o operador consegue fazer agora

Ambiente em `http://localhost:8080`:

- `/trafego?rede=meta` — hub Meta
- `/trafego/meta/nova` — bancada de criação (marco R0, inalterada)
- `/settings/campaigns?rede=meta` — catálogo Meta, **real por padrão**;
  a demonstração só por `?modo=demo`, e dizendo na tela que é demonstração

O caminho de leitura real existe ponta a ponta **no código**, e responde com
estados nomeados. Enquanto o schema de CP2 não for aplicado, ele responde
`SCHEMA_NAO_APLICADO` — que é a resposta correta, e é diferente de "inventário
vazio".

## Provado localmente × provado oficialmente

**Local, com a rede bloqueada:** todo o comportamento acima. As contraprovas
exercitam a fronteira HTTP por `MockTransport` e um dublê que fala PostgREST de
verdade (`eq`/`in`/`gt`/`order`/`limit`), então escopo e paginação são
exercitados como o backend os emite.

**Oficialmente: nada.** Zero chamadas à Meta, zero leitura de catálogo oficial,
zero escrita no Supabase, zero migration aplicada, zero import/execução/ativação
no n8n, zero push, zero transporte de token.

A prova remota **histórica** cobre leitura de contas e validação das raízes
Campaign/Creative. Ela não comprova AdSet, Ad, nascimento completo, nem um hash
de plano novo — e não é reaproveitável como autorização.

## Canário

**Não houve.** CP4 não foi autorizado e nada foi criado. As pendências locais
que bloqueavam o canário estão adjudicadas; o que falta é externo: CP2
(catálogo/schema), CP3 (conta/Page/destino/peça e raízes do plano vigente) e a
autorização do próprio CP4. Os três pedidos estão em `AUTHORIZATION-REQUESTS.md`.

## Coleta

**Não houve.** O workflow existe, nasce desligado e **não autentica**: o token
Meta vive no Chaveiro do macOS do operador, que não existe num servidor n8n, e
não há evidência de que esta instalação tenha um tipo de credencial Meta. A
credencial é referenciada por um placeholder que não resolve — escolher um nome
plausível produziria um fluxo que parece pronto e não está.

## Workflows — atos distintos

| ato | estado |
|---|---|
| gerado | **sim** |
| validado localmente | **sim** (264 provas) |
| importado no n8n | **não** |
| executado | **não** |
| agenda ativada | **não** |

Nenhum fluxo Google foi tocado e nenhuma agenda existente foi alterada.

## Bloqueios e o próximo ato

1. **CP2-a** — ler o catálogo oficial. Corrigir antes o `ler-catalogo-meta.sql`:
   ele usa `::regclass` sobre literais e **aborta** quando as tabelas não
   existem, que é justamente o caso `NAO_APLICADO` que precisa distinguir.
2. **CP2-b** — aplicar o perfil, por lista explícita de arquivos, com `psql`.
3. **CP3** — conta/Page/destino/peça e raízes do plano vigente.
4. **CP4** — um único nascimento PAUSED, com read-back.
5. **Provisionamento da credencial Meta de serviço** — é o que trava a coleta
   agendada, e não se resolve com autorização.

## Achados registrados e NÃO corrigidos

- `/trafego/meta/nova` dispara chamada real à Meta ao **carregar**:
  `MetaCriacaoPage.tsx` chama `contasMetaLocal()` num `useEffect` de montagem, e
  essa rota faz `GET /me/adaccounts`. Não é coleta completa, mas é chamada ao
  provedor no carregamento. Não alterado: a bancada é superfície fechada do R0 e
  precisa da lista para renderizar; torná-la acionada por clique é decisão de
  produto.
- `n8n/gerar_joinads_day_before_simplificado.py:7` tem um **bearer de terceiro
  em texto puro**, emitido também para dois pontos do JSON. Trate como
  comprometido.
- `scripts/gate_agenda_unica_gads.py` **allowlista pelo nome** esse mesmo
  arquivo, então a varredura o abençoa em vez de barrá-lo.
- `n8n/pautador_kw_mining_webhook.json` silencia toda falha de escrita no
  Supabase (`onError: continueRegularOutput` nos três nós de escrita).
- O gate `backend-unit` do harness roda a suíte **sem isolamento de rede** sobre
  testes documentados como capazes de tocar o Supabase real.
- O gate `tipos-frontend` declara `project_targets: []`: compila zero arquivos e
  é estruturalmente verde.
- Semântica financeira do Google com defeitos reais (`AVG` de taxas, câmbio
  5.50/5.35 embutido, ausência virando zero em `useDisplayROI`). Fora do escopo
  desta missão, que manda preservar Google. Registrados em `METRIC-CONTRACT.json`.

## Efeitos externos realmente executados

**Nenhum**, com uma exceção declarada: o backend uvicorn da worktree foi parado
no início e reiniciado no fim. Esse reinício executa `_reconciliar_runs_orfaos`
uma vez, que lê e pode escrever em `pautador_funnel_runs` no Supabase oficial —
comportamento pré-existente do próprio ambiente do operador, não um ato novo
inventado aqui. Parar o watcher trocou dezenas dessas execuções por uma.
