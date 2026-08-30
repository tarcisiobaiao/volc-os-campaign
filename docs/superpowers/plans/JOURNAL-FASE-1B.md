# Journal — Fase 1B (execução contínua)

Ponto de retomada exato. Atualizado a cada checkpoint.

## Onde estamos

HEAD ao iniciar esta execução: `953a466`
Workflow em curso: `wf_2c667175-ed5` (task `w5obgviqj`)
Workflow anterior, concluído: `wf_204bbc96-2ed` — 3 implementações + 3 auditorias

## O defeito estrutural que esta execução fecha

A camada de acesso consulta tabelas que nenhum schema cria:

| código consulta | canônico em `v9_01` |
|---|---|
| `volc_trafego_conta` | `trafego_snapshot_conta` |
| `volc_trafego_campanha` | **split**: `trafego_campanha` (identidade) + `trafego_campanha_espelho` (espelho) |
| `volc_trafego_sincronizacao` | `trafego_evento` (append-only; chave de idempotência em `chave_de_agrupamento`) |

Ocorrências: `inventario.py:874-875`, `sincronizador.py:968,975,983,993,1003,1014`.

O split não é rename: `trafego_campanha` guarda o que o VOLC **declara**
(procedência, linhagem) e `trafego_campanha_espelho` guarda o que a conta
**respondeu**. Separadas para que nenhum gatilho de espelho alcance uma
declaração — é o conserto de E-08 em forma de schema.

## Ownership desta rodada

| frente | arquivos exclusivos |
|---|---|
| A | `supabase/migrations/*`, `scripts/testar_migration_descartavel.sh`, `backend/app/trafego/persistencia.py` (novo), seu teste |
| B | `inventario.py`, `sincronizador.py`, `dominio.py`, `alertas.py` (novo), `routers/trafego_inventario.py`, seus testes |
| C | `HubDeTrafegoPage.tsx`, `components/trafego/inventario/**`, `hooks/useInventario.ts` |
| integrador | `routers/trafego.py`, `main.py`, `App.tsx`, `types/trafego.ts`, `lib/pautadorApi.ts`, `layout/*`, `useNotificacoes.ts`, commits |

## Feito antes desta rodada

- `9c827ee` domínio + migration v9_01/v9_99 (6 tabelas, RLS, provadas em cluster descartável)
- `fffd23f` API + sincronizador + router (`registrar()` inclui os dois routers)
- `0ba6fde` Hub de 3 abas, contrato com o 7º estado `presente`, sino → `?aba=atencao&foco=`
- `6a084e9` `docs/DESIGN.md` (produto)
- `56f4dbe` curadoria: `cap_inventario_trafego=partial`, `risk:alertas_gaql_no_render`
- `953a466` 4 achados altos da auditoria: zero inventado na origem, frescor falhando aberto, idempotência memorizando fracasso, mapa sem reserva

## Aberto ao iniciar

1. **Camada de acesso × schema** — o item acima. Frente A + B.
2. **`/api/trafego/alertas` gasta cota no render.** Frente B entrega `alertas.py`
   como projeção; o rewire em `routers/trafego.py` é do integrador.
   Dificuldade real: `horas_ligada`, `razoes`, `aprovacao_do_anuncio` e
   `alteracoes` não têm coluna. A saída é **estender o snapshot**, não reduzir a
   tela nem inventar o dado.
3. **`?atencao=true`** dependia de coluna gerada que só existia na DDL removida.
4. **Gatilho de preservação** cobre só as 4 colunas de entrega: leitura parcial
   apaga `nome`/`estado_externo`/`canal` e a linha fica sem nome.
5. **`_prova_recusa` aceita qualquer erro** como prova.
6. **`dominio.py` sem consumidor de produção**, e suas regras de frescor
   contradizem `inventario.py` para a mesma entrada.
7. **`docs/DESIGN.md` não é achado pelo loader** (raiz tem `PRODUCT.md`).
   Ler explicitamente.

## CHECKPOINT — 25/08, workflow `wf_2c667175-ed5`

**Critério 1 ATENDIDO.** Nenhuma referência de produção às tabelas fantasma.
Verificado por AST (constantes string do módulo), não por grep: as únicas
menções restantes estão em docstring de `persistencia.py`, explicando a
migração. Os quatro módulos usam as canônicas:

| módulo | tabelas |
|---|---|
| `persistencia.py` (novo, 692 linhas) | as 6 + as 2 views |
| `inventario.py` | as 6 |
| `sincronizador.py` | campanha, espelho, snapshot_conta, evento |
| `alertas.py` (novo, 562 linhas) | campanha, espelho, snapshot_conta, evento |

**Duas VIEWs** na migration para o join no schema (evita N+1 no cliente):
`trafego_inventario_conta` e `trafego_inventario_campanha`, ambas com
`security_invoker = true` — sem isso a view rodaria com privilégio do dono e
passaria por cima da RLS. Isso eleva o piso para PG15; produção é 15.8, e a
migration aborta em versão menor.

**Frente C entregue:** 385 provas, 30 arquivos, 0 falhas. Um `describe` por
estado numerado (os onze) e um por achado da auditoria, nomeado com
`arquivo:linha`.

**Frentes A e B ainda rodando** quando este checkpoint foi escrito.

### Pedidos ao integrador, já registrados

1. `src/App.tsx`: montar `<HubDeTrafegoPage oportunidades={...}
   contadorDeOportunidades={...} />` — hoje monta sem prop e o cabeçalho
   aparece duas vezes.
2. `src/pages/trafego/TrafegoPage.tsx`: extrair o corpo sem o cabeçalho da
   página (kicker "compra de tráfego" + `<h1>Tráfego</h1>`), porque o Hub já
   desenha o dele.
3. `src/types/trafego.ts`: as uniões são fechadas e a tela agora degrada com
   segurança — decidir se o tipo passa a admitir valor desconhecido em vez de
   mentir que a união cobre tudo que o servidor emite.
4. `routers/trafego.py`: reapontar `/alertas` para `alertas.py` quando a
   Frente B entregar.

## Retomada

1. `python3 scripts/atualizar_grafo_volc_os.py --check`
2. Ler os `result` de `journal.jsonl` do workflow em curso
3. Integrar A → B → C, commitando cada fatia verde
4. Auditoria adversarial sobre o conjunto; corrigir achados altos
5. Grafo **sem** `--reuse-technical`; `built_at_commit` == HEAD final

---

## Congelamento para validação de produto — 2026-08-26

Fase 6 aceita como **checkpoint técnico**, não como aceite de produto. O dono
inspeciona `localhost:8080` como operador. Enquanto isso: **nenhuma alteração de
interface**. Árvore em `43130af`, grafo `current: true` no mesmo commit.

P0-R **não** começa. Sem push, sem deploy, sem mutação no Google Ads.

### Pendências que a Fase 6.1 fecha

| # | Dívida | Onde nasce |
|---|---|---|
| 1 | "Carregar mais": o cursor existe no hook, o botão não. Sem filtro a página 1 mostra 55 de 84 | `useInventario.ts` expõe `carregarMais`; nenhuma superfície chama |
| 2 | Ordenação não prioriza ativas. Hoje é `customer_id, volc_campaign_id` — histórico removido se mistura com o que está no ar | `persistencia.py`, `order` do PostgREST |
| 3 | Feedback visual do dono | a coletar |
| 4 | Consistência `cap_inventario_trafego` × `wave:P0-T` na curadoria | `curadoria-operacional.json` |

### Dívida de autoridade: o limiar de 100 impressões

`IMPRESSOES_PARA_CULPAR_O_ANUNCIO = 100` decide se a causa é **"ninguém viu"** ou
**"viram e não clicaram"** — dois diagnósticos que mandam o operador a lugares
opostos: um é lance/orçamento, o outro é criativo. Hoje esse número vive em dois
lugares:

- `backend/app/trafego/dominio.py` — `sintoma_de_entrega()`
- `src/components/trafego/atencao/projecao.ts` — `sintomaDaCampanha()`

Há teste comparando os dois lados, o que **detecta** a divergência mas não a
**impede**: continuam sendo duas regras que por acordo estão iguais. Um ajuste
aplicado num lado e esquecido no outro faz a mesma campanha receber diagnósticos
diferentes na fila e no relatório — e o operador não teria como saber qual acreditar.

**Direção decidida (rodada de blindagem, não agora):** a API devolve o sintoma **já
classificado**; o frontend fica responsável só pela apresentação. O limiar deixa de
ser constante duplicada e passa a ser regra de um dono só, versionada com a migration
que a introduziu. Enquanto isso não acontece, tratar qualquer mudança no número como
mudança nos **dois** arquivos, no mesmo commit.

---

## Onde isto ficou — 26/08/2026, fim da rodada U0+H0

O congelamento acima terminou: o dono aceitou a Fase 6 como checkpoint técnico e
a frente seguiu para **U0 + fundação H0**, com Grok no frontend e Codex na
integração.

### As quatro pendências da 6.1

| # | estado |
|---|---|
| 1 · "Carregar mais" | **do lado do servidor, pronto** — cursor de 3 chaves, e o `historico` fora do padrão reduz a página 1 de 55/84 para as 5 operacionais. O botão é do Grok |
| 2 · ativas antes do histórico | **fechado** — `ordem_operacional` na view, resolvido no banco |
| 3 · feedback visual do dono | não chegou; a validação foi substituída pela missão U0 |
| 4 · `cap_inventario_trafego` × `wave:P0-T` | **continua aberto** — curadoria é do Codex |

### A dívida de autoridade do limiar

`IMPRESSOES_PARA_CULPAR_O_ANUNCIO = 100` **continua duplicado** entre
`dominio.py` e `projecao.ts`. A direção decidida — a API devolver o sintoma já
classificado — não entrou na U0, e o motivo é escopo: a U0 fechou a verdade
operacional (histórico, ordem, reconciliação) e a H0 o chassi multicanal. O
limiar entra na rodada de blindagem, como estava previsto.

### O que a U0+H0 acrescentou a esta lista

- **incidente de credenciais aberto** com risco aceito temporariamente
  (`docs/INCIDENTE-JWT-SECRET.md`) — 13 segredos públicos, gate obrigatório antes
  de qualquer operação externa;
- **v9_03 e v9_04 prontas e não aplicadas**, com rollback executável e ciclo
  provado (`scripts/provar-ciclo-migrations.sh`);
- **`url_final_lida_em` não existe** — enquanto isso, a URL do anúncio viaja como
  `historica` e não `forte`;
- **`ordenarCampanhas()` do cliente precisa sair** — a ordem agora é do servidor.
