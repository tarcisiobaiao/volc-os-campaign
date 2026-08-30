# HANDOFF — VOLC OS / motor de tráfego (Google Ads) — 20/08/2026

Você está assumindo uma sessão em andamento no repositório **VOLC OS**
(`/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign`), branch `sync/webgov6`.
Este documento existe porque a sessão anterior (Claude Code) ficou sem
créditos no meio do trabalho. Leia inteiro antes de tocar em qualquer coisa —
tem decisão de arquitetura, erro já cometido e corrigido, e número medido que
não pode virar chute de novo.

## 0. As quatro regras, e elas são absolutas

O usuário (Tarcisio, `tarcisio@agenciavolc.com.br`) as declarou no início da
sessão e elas **não se negociam**:

1. **Trava de escrita fechada.** Nunca chame `destravar()`, nunca defina
   `FORGE_PERMITIR_ESCRITA=1`. Só leitura e `validate_only` (que É leitura: a
   API valida e descarta, não cria nada). **Só execute escrita com autorização
   explícita do usuário, na hora** — não vale autorização de uma mensagem
   anterior para uma ação nova.
2. **Não altere nada em conta de terceiro.** A credencial do MCC alcança 39
   contas anunciáveis; só 3 são da casa (ver seção 3). `escopo.py` recusa no
   servidor, não só esconde na tela — não contorne isso.
3. **Português do Brasil** em comentário, docstring, nome de variável e
   mensagem de commit/PR.
4. **Todo número citado é MEDIDO e diz onde foi medido.** Se você não mediu,
   não cite. Nunca invente estatística, benchmark ou limiar — e se herdar um
   número de código existente, ele já vem com a procedência escrita ao lado;
   preserve isso.

Além disso, do estilo de trabalho que o usuário validou nesta sessão:
"entregue, não audite" — não pare para descrever o que vai fazer, faça e
mostre o resultado medido. E: "só chame de pronto o que você viu rodar" —
separe sempre o que ficou de pé do que ninguém conseguiu provar.

## 1. O que é o VOLC OS, rapidamente

Sistema de arbitragem de display: compra clique barato de Google Ads Search →
funil próprio (landing pages via WordPress) → monetiza com display/AdSense.
Pipeline: **PAUTA → FUNIL → CAMPANHA → RESULTADO**. Sete países (BR MX CO CL
PE AR ES), hoje só BR está em operação real.

Stack: Vite + React 18 + TS + shadcn/ui + Tailwind + React Query no front;
FastAPI (`backend/`, porta 8010) atrás; `volc_ads/` é um pacote Python própio
(venv separado do `backend/.venv`, mas o backend importa dele) que fala com o
SDK oficial `google-ads` (v25) via gRPC.

Rodar localmente:
```bash
./start-dev.sh          # front :8080 + api Express :3001
# o backend FastAPI roda à parte, via uvicorn (ver processos abaixo)
backend/.venv/bin/uvicorn app.main:app --reload --reload-dir app --reload-dir ../volc_ads --port 8010
```

**Armadilha do `npx tsc --noEmit`**: sem `-p tsconfig.app.json` ele checa
zero arquivos e sempre passa (gate falso-verde). Use sempre
`npx tsc --noEmit -p tsconfig.app.json`. Hoje ele acusa **76 erros herdados
do webgo** (não relacionados a este trabalho) — qualquer trabalho novo deve
manter esse número, não reduzi-lo nem aumentá-lo, a menos que seja pedido.

## 2. A saga desta sessão, na ordem — leia antes de mexer no motor de copy

Isto importa porque **cada correção anterior nasceu de uma hipótese errada
que os dados refutaram**. Se você não souber essa história, vai repetir o
mesmo erro com uma cara nova.

### 2.1 — `RemoteProtocolError` na geração de copy (RESOLVIDO)

A escrita de copy (`volc_ads/copy/cliente.py`, `TransporteGemini`) morria com
`RemoteProtocolError: Server disconnected without sending a response.`
Diagnóstico errado #1: "é o endpoint não-streaming que corta aos 60s" →
trocamos para `streamGenerateContent`. **Continuou caindo.** Diagnóstico
correto, medido: o corte é no **tempo até o PRIMEIRO BYTE**, não no tempo
total. Enquanto o modelo "pensa" (`thinkingConfig`), não sai nenhum byte na
linha, e o servidor do Gemini fecha a conexão aos ~60s mesmo em streaming.

Medido (payload real de 77KB, mesma chamada, variando o teto de pensamento):
```
sem teto / medium / 32768 / 24576 / 16384  → NUNCA emite 1º byte, cai aos ~61s
orçamento  8192  → 1x passou (44s), 1x caiu   (cara ou coroa — NÃO USAR)
orçamento  2048  → 1º byte em 1,7-4,0s, 3/3 sucesso
nível      low   → 1º byte em 1,6-3,7s, 3/3 sucesso
```

Fix em `volc_ads/copy/cliente.py`:
- `TuboMudo(FalhaDeTransporte)` — exceção própria para "caiu com ZERO bloco
  recebido" (queda antes do 1º byte), distinta de queda no meio do stream
  (essa é rede de verdade, retenta normal).
- `ESCADA_DE_PENSAMENTO = ({"thinkingBudget": 2048}, {"thinkingLevel": "low"})`
  — só os dois degraus medidos como 3/3. **Não adicione 8192 nem nada entre
  2048 e "livre" sem medir de novo com o prompt real.**
- Quando um degrau dá `TuboMudo`, desce pro próximo automaticamente. Não
  retenta o MESMO degrau (`_transitorio()` retorna `False` para `TuboMudo`).
- Telemetria carrega `Chamada.pensamento` (qual degrau produziu a resposta).

### 2.2 — Ad Strength `AVERAGE`/"Ruim": a hipótese da REPETIÇÃO DE RAIZ (REFUTADA)

O Google devolve, via `ad_group_ad.action_items`:
```
"Try including more keywords in your headlines."
"Try including more keywords in your descriptions."
```
Hipótese #1 (errada, cara e cara demais): "isso quer dizer repetir o termo
dominante (`fgts`/`saque`/`aniversario`) em mais títulos". Fizemos uma régua
proporcional (`C9.cobertura_do_termo`) e testamos ao VIVO, subindo campanha
pausada (custo zero, R$0 gasto):

```
campanha 24156134066: raiz em  4/15 títulos, 2/4 descrições → AVERAGE
campanha 24161105437: raiz em 15/15 títulos, 4/4 descrições → AVERAGE
                       (OS MESMOS DOIS ITENS, palavra por palavra)
```

**Levar a repetição ao teto não mudou nada.** "More keywords" não quer dizer
"repita mais o termo" — quer dizer **mais keywords DISTINTAS do grupo de
anúncio**. Medido: das 82 keywords do grupo, a copy de raiz-no-teto espelhava
só 7; das 64 palavras de conteúdo das keywords, só 15 apareciam no anúncio.

### 2.3 — A correção certa: C11 "variedade de keywords" (MEDIDA, funcionou)

Reescrevemos a régua e o prompt para exigir **cobertura de keywords
distintas**, não repetição de raiz. `fracao_titulos_com_termo` do `Pedido`
foi **zerada** (era 0.6 — chute meu, refutado). Nova checagem
`volc_ads/copy/contrato.py::_c11_variedade_de_keywords` mede duas coisas:

1. **Keywords espelhadas** — quantas keywords do grupo têm TODAS as palavras
   de conteúdo presentes num mesmo título/descrição.
2. **Vocabulário recorrente** — % de palavras que aparecem em **≥2 keywords**
   (não ≥1: palavra que só uma pessoa digita, tipo `1331`/`www`/`meu`/`tenho`,
   não cabe em título de 30 chars e tornava a régua insatisfazível — mesmo
   erro que a cota de dígitos do C8 já tinha cometido antes).

Subimos campanha pausada com a copy nova (`24156373085`) e medimos:
```
7/82 keywords, 13/36 vocabulário  → AVERAGE (a de repetição no teto)
16/82 keywords, 16/36 vocabulário → BOM (primeiro Bom desta operação)
```

**Isto é o número medido que vale hoje.** Está documentado com procedência em
`volc_ads/forca.py` (topo do docstring) e em
`_c11_variedade_de_keywords` (docstring). Não é limiar publicado pelo Google
— é o que ESTA conta aceitou, nesta data, neste nicho. E não é o teto: o item
"Inclua palavras-chave bastante usadas nos títulos" ainda estava DESMARCADO
no painel quando a nota virou Bom — ou seja, existe folga acima ligada a
**volume de busca** (`cluster.keywords[].volume: high|medium|low`, que já
vem do Pautador e a C11 ainda ignora). Ver seção 6, item aberto.

### 2.4 — Bug lateral pego pela C10 (CORRIGIDO)

Ao criar `_c10_portao_do_lancamento` (roda o MESMO `Validador` de
`policy/spec.json` que `campanha/search.py` usa no `/provar`, só que DENTRO
da cascata de copy, antes de custar), apareceu `IndexError: list assignment
index out of range` em `Alvo.escrever` quando o alvo (ex.: um valor de
snippet) já tinha sido cortado por outra correção antes de esta rodar.
Corrigido em `contrato.py::Alvo.escrever` (não estoura mais, ignora em
silêncio) e `ciclo.py::_regenerar` (confere se a escrita realmente pegou
antes de anotar sucesso no diário — "a pior forma de sucesso é a que não
deixa rastro").

### 2.5 — O laço de teste ponta-a-ponta, autorizado e executado

Sequência que RODOU de verdade, contra a conta real (`8017851692`, MCC
`6016739364`), na ordem: `/remover` campanha antiga (PAUSED, R$0, sem risco)
→ regenerar copy → `/provar` (`validate_only`, selo emitido) → `/subir`
PAUSADA → ler `ad_strength` via `forca.py`. Campanha final:
**`24156373085`**, PAUSED, nota **Bom** confirmada no painel do Google pelo
usuário (screenshot). A API (`ad_group_ad.ad_strength`) **atrasa em relação
ao painel** — chegou a ficar `PENDING` por 40 minutos depois de o painel já
mostrar Bom. Isso está documentado no `forca.py`: trate `PENDING` sempre como
"ainda não avaliei", nunca como reprovação.

### 2.6 — Diagnóstico "campanha ligada sem gastar" — pedido do usuário, feito

O usuário perguntou por que duas campanhas `ENABLED` gastavam R$0,00.
Investigado com GAQL ao vivo: **lance de R$0,12 contra CPC de mercado
medido de R$10,54** (maquininha) — 88x abaixo. E: **o próprio usuário tinha
baixado o lance e o orçamento no painel** minutos depois de o motor subir a
campanha (achado via `change_event`, GAQL). O usuário pediu explicitamente
**para NÃO usar o CPC do DataForSEO no alerta** ("pode ser inflado... apenas
a diretriz óbvia"). Construímos:

- **`volc_ads/entrega.py`** (novo) — módulo de leitura pura, irmão do
  `forca.py`. Regra: campanha `ENABLED` + ligada há ≥24h (constante
  `HORAS_ATE_ALERTAR`, **não medida, é escolha de operação, declarada como
  tal**) + custo R$0,00 → alerta. Dois sintomas com remédios opostos:
  `SEM_IMPRESSAO` (não entrou no leilão → olhar lance/orçamento) e
  `SEM_CLIQUE` (entrou o bastante e ninguém clicou → olhar anúncio). O corte
  entre os dois é `IMPRESSOES_PARA_CULPAR_O_ANUNCIO = 100` (também não
  medido, declarado) — **bug real que pegamos rodando contra a conta real**:
  com corte em `impressoes > 0`, uma campanha com 1 impressão em 24h recebia
  "revise o texto do anúncio", conselho errado. Corrigido para exigir volume
  mínimo antes de culpar o texto.
- Única conta derivada: `teto_de_cliques = orçamento ÷ lance` — divisão de
  dois fatos da própria conta, **nunca** estimativa de terceiro. Há um teste
  (`test_o_modulo_nao_conhece_cpc_de_terceiro`) que quebra por AST se alguém
  importar `pautador_ponte`/`motor_pautas`/`dataforseo` para este módulo —
  **não remova essa prova, ela guarda uma decisão explícita do usuário**.
- **Fonte é a CONTA, não a tabela `campaigns`** — descoberto medindo: a
  tabela tinha `customer_id` VAZIO nas 4 linhas, campanhas da véspera
  ausentes, `status_source: auto` (o fluxo n8n antigo também escreve nela —
  dois donos = cache, não verdade). `entrega.verificar(cid, campaign_ids=None,
  ...)` pergunta à conta via GAQL `campaign.status = 'ENABLED'` quando não
  recebe lista.
- **`GET /api/trafego/alertas`** (nova rota, `backend/app/routers/trafego.py`,
  fim do arquivo) — varre as 3 contas da casa via `escopo.mapa()`, sem
  tabela, sem cron, recalcula na hora (custo: ~5 consultas GAQL por conta).
  Decisão explícita: **não faz alerta persistido/lido-não-lido** — se a
  campanha voltar a gastar, o alerta some sozinho no próximo GET.
- **Front**: `src/components/trafego/AlertaDeEntrega.tsx` (cartão),
  `src/components/layout/SinoDeAlertas.tsx` (sino — só renderiza quando
  `alertas.length > 0`, polling a cada 10min), ligados em
  `src/pages/trafego/TrafegoPage.tsx` e `src/components/layout/Navigation.tsx`
  (linha ~222, dentro do header da sidebar).

**⚠️ ITEM ABERTO E NÃO VERIFICADO NO NAVEGADOR**: o usuário reportou "não vi o
sino no front". Medido por mim: a rota `/alertas` retorna 1 alerta agora (a
campanha maquininha cruzou 24h durante a sessão), o componente e o import
estão corretos no código, o Vite está servindo (`curl` 200). A hipótese mais
provável é cache de navegador / HMR não pegou o componente novo — **peça para
o usuário dar um hard refresh (Cmd+Shift+R) antes de investigar mais fundo**.
Se persistir depois do refresh, comece por: (1) console do navegador por erro
JS, (2) confirmar que `Navigation.tsx` realmente recarregou (HMR do Vite às
vezes falha silenciosamente em edição de import no topo do arquivo — pode
precisar reiniciar o `npm run dev`).

## 3. Contas e campanhas reais (Google Ads)

- **MCC da casa**: `6016739364` ("VOLC Negócios Digitais") —
  `escopo.MCC_DA_CASA` em `backend/app/trafego/escopo.py`.
- **3 contas da casa** (as únicas em que `/provar`/`/subir` aceitam operar):
  - `8017851692` — Crédito Up (onde está toda a ação desta sessão)
  - `3849678045` — PMUNDO+
  - `5478096539` — Portal Mundo Mais
- A credencial (`gads/client.py`) **alcança 39 contas anunciáveis** no total
  — as outras 36 são de terceiro. `escopo.exigir_escopo()` recusa no
  servidor; a rota `GET /api/trafego/contas` é a ÚNICA leitura que não passa
  por esse portão (é diagnóstico, mede o alcance, não opera).
- **Campanhas vivas hoje na conta `8017851692`**:
  - `24156373085` — FGTS Saque-Aniversário, **PAUSED**, nota **Bom** medida.
    Usuário disse que vai decidir ligar depois de ver o alerta funcionando.
    Nasceu com orçamento R$10/dia, MANUAL_CPC, lance R$0,12 (alterado pelo
    usuário no painel de um valor maior que o motor tinha subido).
  - `24155134757` — Maquininha de Cartão, **ENABLED**, nota **POOR** (não
    refeita ainda com a C11 nova — está na lista de pendências, seção 6).
    Lance R$0,12 contra CPC de mercado medido ~R$10,54 (mediana). R$0,00
    gasto, e o alerta de `entrega.py` vai/já pode estar disparando para ela
    (cruzou 24h durante esta sessão).
  - Campanhas antigas removidas nesta sessão (histórico, não tocar):
    `24156134066` (FGTS, versão de raiz-no-teto, AVERAGE),
    `24161105437` (FGTS, teste da hipótese refutada, AVERAGE).

## 4. Como rodar as provas

```bash
# backend + volc_ads (Python) — venv do backend, NÃO o da raiz
cd /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign
backend/.venv/bin/python -m pytest volc_ads backend/tests -q
# esperado: 601 passed, 20 skipped (medido em 20/08/2026, fim da sessão)

# front
npx vitest run
# esperado: 228 passed (21 arquivos)

npx tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS"
# esperado: 76 (herdados do webgo — NÃO deste trabalho, ver CLAUDE.md)
```

Para rodar consultas GAQL ao vivo contra a conta real e ver dado fresco (ex.:
reler o `ad_strength`, ver alertas), use o cliente direto:
```bash
cd /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign
backend/.venv/bin/python - <<'PY'
import sys; sys.path.insert(0,"."); sys.path.insert(0,"backend")
from volc_ads import forca, entrega
for v in forca.ler("8017851692", "24156373085", login_customer_id="6016739364"):
    print(v.resumo())
for d in entrega.alertar(entrega.verificar("8017851692", None, login_customer_id="6016739364")):
    print(d.campaign_name, d.horas_ligada, d.custo)
PY
```
Isto é LEITURA (`search()`), sem risco — mas ainda assim é rede de verdade,
não abuse em loop apertado (a API do Google Ads tem quota).

## 5. Rotas principais do backend (`backend/app/routers/trafego.py`)

Todas sob `/api/trafego`. As que só LEEM: `/quadro`, `/copy/{id}` (GET),
`/candidatos/{id}`, `/contas`, `/escopo`, `/politica/verticais`, `/trava`,
`/alertas` (nova, seção 2.6). As que ESCREVEM (passam pela trava de dois
fatores + `escopo.exigir_escopo`): `/copy` (POST, gera copy — não mexe no
Google Ads, é LLM), `/provar` (`validate_only`, tecnicamente não cria nada
mas passa pelo caminho de escrita), `/subir` (mutate real, cria campanha
PAUSED sempre — doutrina P7), `/remover` (mutate real).

`_no_escopo(customer_id, login_customer_id)` em `trafego.py:133` é o portão
que toda rota de escrita chama antes de tocar na conta.

## 6. O que está pendente — nenhum item aqui foi autorizado a mexer

Ordem sugerida, mas a decisão é do usuário:

1. **Verificar o sino no navegador** (ver seção 2.6, item aberto) — provável
   só precisar de hard refresh, mas confirme antes de reportar como certo.
2. **Priorizar keywords de ALTO VOLUME na C11.** O cluster do Pautador já
   traz `volume: high|medium|low` por keyword
   (`pautador_ponte.carregar().cluster["keywords"]`). A C11 hoje trata todas
   as 82 keywords como iguais; o item "palavras-chave **bastante usadas**"
   ainda aparecia desmarcado quando a nota virou Bom, então há sinal de que
   ponderar por volume pode fechar esse último item. **Não fizemos isso —
   é hipótese, não medição.** Se for tentar, meça de novo subindo campanha
   pausada, não assuma.
3. **Refazer a copy da Maquininha (`24155134757`, ENABLED, POOR)** com o
   motor já corrigido (C11 + streaming + escada de pensamento). É campanha
   ATIVA — mexer nela precisa de autorização explícita na hora, não vale a
   autorização geral do laço de teste do FGTS.
4. **Girar 3 credenciais**, pendente desde o início da sessão, nunca
   avançado: developer token do Google Ads, WordPress Application Password,
   Supabase `SERVICE_ROLE_KEY`. A última é pesada — self-hosted, girar
   implica trocar `JWT_SECRET` e reassinar `anon`+`service_role` juntos, ver
   `CLAUDE.md` seção Supabase. Não fazer sem o usuário presente.
5. **`VOLC_ADS_PRECO_ENTRADA_MI`/`VOLC_ADS_PRECO_SAIDA_MI`** não configurados
   — a tela mostra "preço não configurado" em vez de custo real de LLM. O
   usuário precisa trazer os valores da própria conta de billing do Gemini;
   não invente.
6. **Decisão do usuário, não técnica**: ligar `24156373085` (FGTS) é gasto de
   mídia real — só ele decide quando.

## 7. Coisas que já erraram e foram corrigidas — não refaça

- ❌ Achar que `RemoteProtocolError` no streaming é problema de rede →
  retentar. **É tubo mudo por corte de 60s no 1º byte.** Ver 2.1.
- ❌ Achar que "more keywords in headlines" = repetir o termo dominante.
  **É variedade de keywords distintas.** Ver 2.2/2.3, refutado com dado real.
- ❌ Cobrar 100% (ou até 50%) do vocabulário BRUTO das keywords — palavra que
  só uma keyword usa (`1331`, `www`, `tenho`) não cabe em título e torna a
  régua insatisfazível. **Corte é ≥2 keywords por palavra.**
- ❌ Achar que qualquer impressão > 0 já significa "o texto é o problema".
  **Precisa de volume mínimo (100) antes de culpar o anúncio, não o lance.**
- ❌ Ler a tabela `campaigns` do Supabase como fonte de verdade sobre estado
  de campanha — ela tem dois escritores e fica desatualizada/incompleta. A
  fonte é sempre a API do Google Ads.
- ❌ Usar `severidade == "erro"` direto do `policy/spec.json` sem checar
  `_SO_AVISO`/`_SEVERIDADE_BARRA` de `campanha/search.py` — uma regra
  (`editorial.maiusculas.tudo_caixa_alta`) é rebaixada a aviso de propósito
  (sigla vs. grito não dá pra distinguir sem dicionário por idioma). Ver
  `contrato.py::_barra_o_lancamento`, importa de `search.py`, não duplica.

## 8. Estilo do usuário, resumido

Prefere respostas objetivas com o número medido em vez de prosa. Gosta de
código auto-documentado com o "porquê" no docstring/comentário (esta base
inteira tem esse padrão — comentários longos explicando decisão e a medição
que a sustenta, em vez de explicar o óbvio). Pediu explicitamente para nunca
usar CPC/estimativa de terceiro em alertas. Autoriza escrita real na conta
quando pedido claramente, e espera que você pare e confirme antes de agir
fora do escopo pedido. Está sem créditos no Claude Code agora, por isso este
handoff — trate isso como continuação direta da mesma sessão, não como
projeto novo.
