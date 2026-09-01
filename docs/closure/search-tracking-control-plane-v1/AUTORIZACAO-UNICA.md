# Pacote único de autorização — o que esta missão NÃO fez e precisa de dono

**Data:** 2026-09-02 · **Branch:** `sprint/search-tracking-control-plane-v1`
**Base:** `26a58c444f20af547b6e4e01267c9f746cf9e438` (`origin/volc-os-v2`)

Tudo o que segue exige uma decisão que não é de implementação. Nada aqui foi
executado, tentado ou preparado no ambiente vivo. Cada item traz **operação
exata**, **destino**, **impacto**, **rollback** e **verificação posterior**.

Eles estão em ordem de dependência: A destrava B, B destrava C. Autorizar C sem
A e B não produz nada.

---

## A. O primeiro plano real durável — um `/subir` autorizado na conta canário

### Operação exata

Um `POST /api/trafego/subir` com `estrategia_lance="MANUAL_CPC"`,
`confirmar_criacao_pausada=true` e motivo descritivo, na conta canário, com
`FORGE_PERMITIR_ESCRITA=1` armada no processo.

### Destino

- Google Ads, conta **5478096539** (Portal Mundo Mais), MCC 6016739364 —
  a **única** que `canario.exigir` aceita (`routers/trafego.py:2930`).
- Supabase oficial `database.agenciavolc.com.br`, tabela
  `public.trafego_campanha_plano_de_mensuracao`, via a RPC governada
  `public.volc_registrar_plano_de_mensuracao`.

### Impacto

- **Cria uma campanha Search de verdade**, PAUSED por literal em `comum.py`.
  Custo de veiculação: **zero** enquanto pausada.
- Grava **uma linha** de plano de mensuração (append-only) e, no sucesso, uma
  **segunda** linha com o `campaign_id` — as duas são a mesma decisão antes e
  depois de ela ter endereço, e não duplicata.
- Abre e fecha um recibo no ledger.
- ⚠️ **É este ato, e só ele, que tira a tabela do zero.** Enquanto ele não
  acontecer, P05-T12 continua `partial` pelo primeiro critério de aceite.

### Rollback

- Campanha: `POST /api/trafego/remover` (`CampaignOperation.remove`), ou remoção
  manual no painel. Campanha removida não gasta e não volta ao leilão.
- Plano: **NÃO removível pela aplicação.** A tabela é append-only por gatilho, e
  `service_role` não tem `DELETE` nem `TRUNCATE`. Uma linha errada só sai por
  `postgres` no SQL editor do Studio — e o rollback da v12_02 declara a tabela
  **não reconstruível**. Isto não é um defeito: é o ponto do append-only.
- Recibo: reconciliável por `POST /api/trafego/reconciliar`.

### Verificação posterior

```
GET /api/trafego/plano-de-mensuracao?customer_id=5478096539&login_customer_id=6016739364
```
Deve responder `persistido: true`, com `plano_id`, `impressao`, os sete portões
e — se o vínculo tiver acontecido — a segunda linha com `campaign_id`.
Esta rota **não toca o Google**: ela lê o Supabase e nada mais.

---

## B. O envio `validateOnly` real contra a Data Manager API

### Operação exata

Uma chamada `validateOnly=true` de ingestão de eventos, com um envelope montado
por `data_manager.montar_envelope` e aprovado por `data_manager.validar`.

⚠️ **O código para fazer isso NÃO EXISTE nesta entrega, e a ausência é
deliberada.** `data_manager.enviar()` levanta `EnvioNaoAutorizado`, não há
cliente HTTP no módulo, e um teste estrutural lê o próprio fonte para provar que
não há `httpx`, `requests`, `urllib` nem `googleapis.com` nele. Autorizar B é
autorizar **escrever** esse caminho, não apenas acioná-lo.

### Destino

`datamanager.googleapis.com`, operating account = a conta **DONA** da
`ConversionAction` eleita (que numa hierarquia com conversão centralizada **não
é** a conta que roda a campanha), `productDestinationId` = o **id numérico** da
ação.

### Impacto

- `validateOnly=true` **não cria conversão** e não altera dados. Gasta quota.
- Prova o que hoje é a maior lacuna do contrato: que o envelope que este sistema
  monta é aceito pela API real, e que o destino resolvido por dono + id numérico
  é o destino certo.

### O que falta ANTES de B, e por que

Três coisas, nesta ordem:

1. **Credencial e escopo** da Data Manager API para a conta dona. A API está
   habilitada no Google Cloud e **nunca foi exercitada** — habilitada não é
   provada.
2. **Uma fila durável.** `conversion_queue` e `conversion_batches` existem vivas
   (as duas com 0 linhas) e **não servem** — ver item C.
3. **Um lugar para o recibo assíncrono.** O recibo da Data Manager é por lote e
   chega depois. Sem onde guardá-lo, um envio aceito e um envio perdido ficam
   indistinguíveis — que é exatamente o estado que o sistema inteiro existe para
   não produzir.

### Rollback

`validateOnly` não tem o que reverter. O que precisa de rollback é o **código de
envio** que B obriga a escrever: ele deve nascer atrás da mesma trava de dois
fatores de `gads/modo.py` (`destravar()` no código **e** variável no ambiente).

### Verificação posterior

O recibo de `data_manager.validar` (local) comparado com a resposta da API: os
mesmos itens aceitos e recusados, pelas mesmas causas. Divergência aqui é a
prova de que a validação local está errada — e é a única forma de descobrir isso
sem enviar nada.

---

## C. A migration da fila de conversão — **NÃO PREPARADA, e a razão está dita**

### O que foi auditado

`conversion_queue` (viva, 0 linhas, leitura de 22/08/2026):

```
batch_id · bucket_weight · conversion_time · conversion_value · created_at ·
currency_code · gclid · google_error · id · original_bucket · sent_at ·
status · visit_id
```

Faltam **cinco** coisas sem as quais um envio governado não existe:

| # | falta | por que é fatal |
|---|---|---|
| 1 | destino | nenhuma coluna diz conta DONA nem id NUMÉRICO da ação |
| 2 | conta | não há `customer_id`; a fila foi desenhada para UMA conta |
| 3 | `wbraid`/`gbraid` | só `gclid` — e é o tráfego de app e o de iOS que mais dependem dos outros dois |
| 4 | consentimento | nenhuma coluna; consentimento viaja COM o evento |
| 5 | chave de dedup | `id` é surrogate; surrogate novo a cada tentativa não deduplica nada do lado do Google |

E as duas tabelas **não têm DDL no repositório**: `grep` em
`supabase/migrations/` não as encontra. Elas existem no banco e não são
governadas por este código.

### Por que nenhuma migration foi escrita

O briefing autoriza "uma migration nova **somente se for indispensável**". Ela
não é indispensável para esta entrega — a fronteira `validateOnly` está fechada
sem banco. E escrevê-la agora seria decidir, sozinho, três coisas de dono:

- **estender** as tabelas vivas ou **aposentá-las** por novas (elas têm 0 linhas,
  então aposentar é barato — mas há um produtor legado presumido em n8n que
  ninguém desta missão auditou);
- se a fila é **por conta** ou **global com `customer_id`**;
- se o consentimento por evento é **coluna** ou **payload** (a v12_02 escolheu
  coluna para o que se consulta e payload para o que se audita, e a mesma
  pergunta se repete aqui).

**O que eu recomendo, se me for pedido:** tabelas novas
(`trafego_conversao_fila` / `trafego_conversao_lote`) no padrão da v12_02 —
append-only, RPC única como porta de escrita, `service_role` sem `INSERT`
direto, destino por par (dono, id numérico) com CHECK, e as duas velhas
declaradas legado com condição de aposentadoria. Não escrevi porque é decisão
sua, e uma migration escrita "para o caso de" vira dívida no dia em que a
decisão for outra.

### Rollback

Não se aplica: nada foi escrito.

---

## D. `MAXIMIZE_CONVERSION_VALUE` — a porta que ficou fechada de propósito

### O fato

O portão `pr.exigir_para_criacao` recusa `MAXIMIZE_CONVERSION_VALUE` **sempre**
que não há regra de valor declarada no perfil — e como `/subir` ainda não recebe
os eixos de negócio no corpo, na prática ele recusa **sempre**.

### Por que não abri

Este sistema **não lê** `conversion_action.value_settings` em nenhuma das cinco
leituras GAQL (verificável por `grep` no repositório). Sem essa leitura e sem
uma regra declarada, otimizar pelo valor é perseguir um número que pode ser zero
em todas as linhas — e o erro é silencioso: a campanha entrega, o relatório mostra
conversões, e o ROAS que ninguém consegue explicar aparece semanas depois.

### As duas formas de abrir, e o que cada uma custa

1. **Declarar** a regra de valor no perfil de mensuração — exige acrescentar os
   eixos de negócio (`negocio`, `intencao`, `funil`, `evento`, regra de valor) ao
   corpo de `/provar` e `/subir`. ⚠️ Isso muda `chave_intencao` para todo mundo,
   a menos que o campo entre em
   `CAMPOS_QUE_SO_ENTRAM_NA_IDENTIDADE_QUANDO_EXISTEM` — a mesma armadilha que
   `assets_display` disparou em 01/09/2026 e que está documentada em
   `routers/trafego.py:1930`.
2. **Ler** `conversion_action.value_settings` — uma sexta consulta GAQL, com o
   custo de quota já declarado em `_plano_de_mensuracao` (o teto de 30 s não
   cancela a thread, e dez cliques em cinco minutos deixam dez threads órfãs).

Nenhuma das duas é difícil. As duas são decisão de escopo.

---

## E. Aplicar o delta de curadoria e reconstruir o Mapa Vivo

Depois do merge, e **uma vez só**:

```bash
python3 scripts/atualizar_grafo_volc_os.py
python3 scripts/atualizar_grafo_volc_os.py --check
```

O delta está em `delta-curadoria.json`: 7 nós, 10 arestas, P05-T12 **segue
`partial`** e P06-T07 vai de `todo` para `partial`.

⚠️ **Não rodado nesta missão de propósito.** Trabalho em branch não integrada não
marca a fonte compartilhada, e Roadmap, curadoria e grafo estão fora do
ownership declarado.

---

## O que esta missão NÃO fez — a lista fechada

- ❌ nenhum `mutate` no Google Ads
- ❌ nenhum envio pela Data Manager, nem `validateOnly`
- ❌ nenhuma escrita no Supabase oficial
- ❌ nenhuma migration aplicada, e nenhuma escrita
- ❌ nenhum n8n tocado
- ❌ nenhum deploy, push, merge ou ativação
- ❌ nenhuma meta de conversão ou `ConversionAction` alterada ou criada
- ❌ nenhum gasto
