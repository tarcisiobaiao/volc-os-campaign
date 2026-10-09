# Google Ads — fechamento sniper (09/10/2026)

Card 106 (Gás do Povo), conta 547-809-6539, MCC 601-673-9364. Nenhuma campanha
criada, ativada ou com orçamento alterado. Nenhuma chamada paga nesta rodada.

## 1. Três estados que não se confundem

| canal | builder aceito pela API | fluxo cockpit validado | pronto para lançar |
|---|---|---|---|
| SEARCH | sim — 15 ops, `xUsAh6AUPU_1FrNlaKXfvw` (Codex, mídia de ensaio) | **sim, com dado real**: card 106, conjunto aprovado (cluster 10), copy registrada, 44 ops, `validate_only` aceito, `pNVi5pBJHo5K-w48h7rNdQ` | **não** — destino sem permalink publicado, recibo de aprovação ausente, política de benefícios (§4), canário/escrita fechados |
| DISPLAY | sim — 9 ops, `EqfdKLSt8Rq9Ne8alvKYEg` | não — sem mídia aprovada para Google | não |
| DEMAND_GEN | sim — 9 ops, `evcTANUKWqQckLlytFXcig` | não — sem mídia aprovada | não; teto do canário (R$ 20/dia) abaixo do mínimo do Google (US$ 5/dia) |
| PERFORMANCE_MAX | sim — 25 ops, `yMAhcaR7LNAAkf_AG0Rm0A` (ramo técnico) | não — sem mídia; `construir`/`planejar` recusam por mensuração | não — conversões fora da métrica |

Os quatro recibos do Codex ficam intactos em
`canarios/google-quatro-canais-real-20261009/resultado-google.json`. Só o
Search foi revalidado, porque só o payload dele mudou (copy editada). Recibo:
`/tmp/volc-gads-blindagem/operacao-20261009/recibo-search-106-v3.json`
(pedido sha256 `9bc372dd…a949a3`, 44 operações, `validate_only=true`,
`partial_failure=false`, gRPC OK).

`validate_only` aceito **não** é aprovação de política, não é autonomia e não
é prontidão operacional: a API confere formato e descarta.

**Identidade nesta prova:** o `/provar` rodou em processo com um admin de teste
no lugar do login. Isso não prova autenticação. O que foi provado sem dublê:
sem sessão → 401; token inválido → 401 (era 503, corrigido). O passo com a sua
sessão real está em `scripts/provar-sessao-real-gads.sh`.

## 2. Copy final registrada (fluxo existente, `PATCH /api/trafego/copy`)

Gerada pela cascata em 09/10 (2ª escrita, já com a LP no briefing), editada à
mão e gravada pela rota de edição, sem LLM. Edições sobre a saída da cascata:
- fora: "Justiça Apura Fraude no Gás" (sem lastro na LP), "Quer receber seu
  processo?" (sem sentido), sitelink "Consultar pelo CPF" (serviço que o guia
  não executa);
- reescrito: "Ajuste de Pendência Cadastral" → "Entenda Pendências Cadastrais";
  callout "Correção de Cadastro" → "Orientação sobre Cadastro";
  "Entenda o guia oficial de 23/03/2026" → "Veja os critérios do Gás do Povo e
  as orientações oficiais de 23/03/2026." (não sugerir que o guia é oficial).

A 1ª escrita (sem LP no briefing) é a regressão: "Gás do Povo Calendário 2025",
"Regras do Gás do Povo 2024", "Cadastro Grátis", "Entrega de Gás de Cozinha",
"Calendário Atualizado".

## 3. Bloqueios do destino, classificados

⚠️ **Os bloqueios medidos até aqui eram da HOME, não da LP.** A leitura pública
descarta a query string, e `?post_type=r&p=2477` foi lida como a home (200,
`body.home`). Corrigido: URL identificada por query agora é recusada com o
motivo (fail-closed). A LP é rascunho; anônimo recebe 404. **Nenhum bloqueio da
LP 2477 foi medido de verdade** — só depois do permalink publicado.

O que se sabe, e de onde:

| achado | onde foi visto | fundamento | elemento concreto | menor ajuste |
|---|---|---|---|---|
| CONTEUDO_ORIGINAL_INSUFICIENTE (417 < 600) | home | interpretação VOLC: o Google exige conteúdo original suficiente **sem número**; 600 é régua da casa | home | não se aplica à LP: o texto renderizado tem ~1.037 palavras. Não preencher texto |
| MARCA_GOVERNAMENTAL ×3 | home | interpretação VOLC | âncoras de posts do próprio site ("Saldo bloqueado no Caixa Tem…") | **falso positivo, corrigido**: link para o próprio site não entra na regra |
| LINK_EXTERNO_NO_CHROME + NAO_CLASSIFICADO | rodapé do tema (site inteiro) | regra interna (após conta suspensa) | `<a href="https://www.fabiolobo.com.br">Fabio Lobo</a>` no rodapé | tirar o crédito do rodapé no tema **ou** declarar o host no chrome com procedência (falta implementação: §5) |
| SCRIPT_TERCEIRO_NAO_DECLARADO ×3 | `<head>` do tema | interpretação VOLC | `dns-prefetch`/`preconnect`/`preload` para `office.`, `pageview.`, `script.joinads.me` | declarar JoinAds como adtech do projeto 2 (falta implementação: §5) |
| OFUSCACAO_DE_SCRIPT (risco) | inline do tema | interpretação VOLC (indício, não prova) | `function b2a(…)` do plugin **Ad Inserter** (`ai_install_click_trackers`) — codificador base64 de rastreio de clique | manter como risco conhecido; não bloqueia |
| RECIBO_DE_APROVACAO_AUSENTE | — | regra interna | — | emitir o recibo do portão depois de publicar |
| identidade/contato/divulgação | LP Senac, mesmo tema (08/10) | interpretação VOLC | rodapé sem operador/contato; sem aviso de monetização | decisão da casa (§5, lote 5) |

## 4. Gás do Povo × política do Google

Política "Government documents and official services"
(support.google.com/adspolicy/answer/13156083): a categoria *Health and welfare
assistance programs and benefits* cobre anúncios sobre **solicitar** benefício
de assistência. Quem não é governo nem provedor autorizado precisa de
certificação **ou** pedir exclusão (anunciante afetado que não promove o
serviço), além da verificação de anunciante. Nos anúncios dessas categorias, o
Google acrescenta "Not a government website" no Search. O Brasil aparece nas
exclusões regionais só de antecedentes criminais e pedágio.

Aplicabilidade ao card 106: termos como "gás do povo cadastro/inscrição/consulta
cpf" e títulos "Guia de Cadastro" podem ser lidos como acesso ao benefício.
`vertical=informativo` **não dispensa** esta análise: o `spec.json` só lista
documentos (RG, CPF, CNH, título, passaporte, INSS) em `governo_documentos`, e
não tem a categoria de benefícios. A VOLC não tem certificação nem pedido de
exclusão — nada foi inventado. O `validate_only` não julga esta política; ela
aparece na revisão depois de criada.

## 5. Decisões, em lotes separados

| lote | o quê | impacto | rollback |
|---|---|---|---|
| 1 · Conversões | (a) meta DOWNLOAD/APP `biddable=false` (validate_only aceito; escrita bloqueada pelo classificador); (b) PURCHASE/WEBSITE só depois de decidir quais ações medem receita e com que valor (hoje adView = R$ 10 fixo) | (a) nenhum lance muda (Senac é TARGET_SPEND com metas próprias); relatórios param de contar app; (b) muda "Conversões" em relatórios e o que Smart Bidding persegue | (a) `biddable=true`; (b) voltar `biddable=false` |
| 2 · Credencial remota | copiar `google-ads.yaml` (600) para `/opt/volc-gads-coleta/` no Hetzner | o servidor passa a ler a conta Google | apagar o arquivo; revogar o refresh token |
| 3 · Agenda | instalar `deploy/gads-coleta` (systemd) e manter os fluxos n8n inativos | coleta D0 4×/dia e D-1 diária, recibo e batimento | `systemctl disable --now volc-gads-coleta-*.timer` |
| 4 · Migrations | v17_03 (gestão sem delta) e v17_04 (arbitragem reconciliada); v17_02 fica para depois do teto acumulado | v17_04 troca o lucro mostrado por "receita não reconciliada" onde não há prova | `v17_04_rollback.sql`; v17_03 tem rollback próprio |
| 5 · Regras da casa no destino | identidade/contato/divulgação como bloqueio no pago; piso de 600 palavras como bloqueio ou risco | define se a LP pode virar destino pago | reverter a tabela de severidade |
| 6 · WordPress | publicar a LP 2477 com permalink; tirar o crédito "Fabio Lobo" do rodapé | habilita a medição real do destino | despublicar; restaurar rodapé |
| 7 · Política Google | pedir exclusão da política de serviços oficiais (ou não anunciar termos de cadastro) | sem isso, anúncios de cadastro/consulta podem ser limitados | — |
| 8 · Canário DG | teto diário ≥ R$ 30 para caber no mínimo do Google | permite canário DG real | voltar a R$ 20 |

Falta implementação local (não é decisão): fonte de `adtech_declarada` e de
chrome declarado para o portão de **campanha** (`_pagina_do_destino` não passa
nenhuma hoje); request ID do `validate_only` aceito não fica no recibo do
`/provar` (só em falha); moeda do Keyword Planner não é registrada no cluster.

## 6. Próximo passo mínimo para Search

1. Lote 6: publicar a LP 2477 com permalink.
2. Rodar o portão no permalink (agora mede a LP, não a home) e resolver o que
   ele apontar com base Google; decidir o lote 5 para o resto.
3. Lote 7 (exclusão) ou retirar termos de cadastro/consulta do conjunto.
4. `scripts/provar-sessao-real-gads.sh` com a sua sessão.
5. Só então o canário de criação PAUSADA (ato humano, `/subir`).

## 7. Display, Demand Gen e PMax

- **Display:** mídia aprovada para Google (≥ 1 paisagem + ≥ 1 quadrada); hoje há
  0 aprovações com finalidade Google. Canário Display e `CANAIS_COM_CRIACAO_AUTORIZADA`.
- **Demand Gen:** o mesmo, mais o lote 8 (teto do canário abaixo do mínimo).
- **PMax:** o mesmo, mais o lote 1(b): sem ação de conversão na métrica,
  `construir`/`planejar` recusam (correto). O ramo técnico de `pmax.validar`
  não emite selo.
