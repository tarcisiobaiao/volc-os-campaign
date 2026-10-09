# Google Ads — sprint de fechamento operacional (09/10/2026)

Conta 547-809-6539 (lida às 20:37 UTC): BRL, America/Sao_Paulo, ENABLED, não é
MCC; projeto 2 aponta para ela sob o MCC 601-673-9364. Nenhum objeto foi criado,
ativado, pausado ou editado no Google; nenhuma conversão, orçamento ou lance foi
alterado; nenhuma migration, publicação, push ou deploy. Recibos anteriores
preservados (`canarios/google-quatro-canais-real-20261009/`, `/tmp/volc-gads-blindagem/`).

## 1. CPC estimado não decide nada operacional (9c40a59)

Caminho rastreado: mineração → conjunto pago → ponte → cockpit → Brief → builder
→ payload → gestão.

| ponto | antes | agora |
|---|---|---|
| `decidir_keyword` (conjunto pago) | CPC presente = INCLUDE, ausente = EXPERIMENT; CPC acima do teto rebaixava | estimativa só anota (`cpc_estimado_*`); decisão por intenção, risco, volume e congruência |
| bloqueador `teto_economico_desconhecido` | teto ausente bloqueava o conjunto | alerta (o teto só comparava com a estimativa) |
| `/provar`, `/subir`, montadores | orçamento 10,0 e lance 0,12 preenchidos se ninguém declarava | sem padrão: 422 `PARAMETRO_DO_OPERADOR_AUSENTE` com o que falta (lance só em MANUAL_CPC de Search/Display, ou em todos os grupos) |
| ponte, Brief, copy, gestão | já não usavam CPC minerado como lance; prompts sem CPC; gestão recusa recomendação de verba/lance | inalterado |

Prova (testes): com a mesma seleção e configuração, CPC estimado **removido,
×10, ×0,01 ou inventado** não muda decisão, seleção, bloqueadores, impressão
aprovável (`selected_set_sha256` cobre termo/correspondência/sub-intenção, sem
CPC), o Brief nem as operações do Search
(`backend/tests/test_cpc_estimado_nao_decide.py`,
`volc_ads/testes_pautador_ponte.py::test_cpc_estimado_alterado_nao_muda_brief_nem_payload_do_search`).
A aprovação do cluster 10 (card 106) continua válida. CPC **observado** segue
disponível na leitura (ex.: Senac 08/10, Search mobile, R$ 0,89 de CPC médio).

## 2. URL real na requisição, sanitização só no recibo (f6c628c)

- `alvo_de_requisicao`: HTTPS, sem credencial, host público (DNS/IP), sem
  fragmento — e **com a query**.
- `url_para_recibo`: `p`, `page_id`, `post_type`, `cat`, `tag`, `lang` visíveis;
  qualquer outro valor (preview, nonce, gclid, utm, token) vira `~sha256[:10]`.
- `fetch_public_https_chain(preservar_query=True)`: requisita a URL real,
  revalida cada salto, devolve só formas sanitizadas. Padrão inalterado para os
  outros consumidores.
- `_pagina_recebida`: soft-404 (`error404`/título), id de post divergente e
  home servida no lugar da URL → "destino público não validado".

Prova real: `?post_type=r&p=2477` → HTTP 404 → "destino público não validado"
(rascunho; antes era lida como a home). `/r/guia-cursos-senac/` → 200,
`postid-2306`. `?p=2306` → 301 para o permalink, salto anotado, `postid-2306`.

## 3. Bloqueios revistos

**a) PMax/conversões (818fc4f)** — documentação v25 (docstrings do SDK 33.0.0):
o lance segue `primary_for_goal` + a meta **da campanha** (herda o padrão da conta
na criação, pode ser declarada); **meta personalizada ignora `primary_for_goal`**;
`include_in_conversions_metric` é campo de relatório do padrão da conta.

| caso (leitura real) | veredito local | natureza |
|---|---|---|
| plano sem meta declarada | `FORA_DA_METRICA_DE_CONVERSOES` — a campanha HERDARIA PURCHASE/WEBSITE não-biddable | configuração real da conta |
| plano com `metas_de_conversao` PURCHASE/WEBSITE biddable | campo vira aviso; próximo: `SINAL_NAO_COMPROVADO` | lacuna local: `pmax.ler_mensuracao` não lê volume |
| conta real | 3 metas personalizadas (adView, adViewInterstitial, adViewRewarded); a Senac usa meta personalizada de campanha (6456287716): 28 "conversions" de adViewInterstitial em 08/10 | a autoridade local não lê metas personalizadas — lacuna |

Valores das ações são fixos (adView R$ 10, `always_use_default_value`): 08/10,
adView 25 `all_conversions` = "R$ 250", sem relação com receita (JoinAds 07/10:
R$ 4,52). **Não é receita.**

**b) Conteúdo (19c0e14)** — `CONTEUDO_ORIGINAL_INSUFICIENTE` virou risco
(contagem isolada); `PAGINA_PONTE` segue bloqueando; engano, navegação e
congruência inalterados.

**c) Links e scripts (19c0e14)** — o portão de campanha recebe
`adtech_declarada`/`chrome_declarado_pelo_site` do projeto (linha
`project_wordpress`). Medido: **nenhuma declaração existe** (banco e
repositório); o destino diz "ausente" por extenso. Adtech não libera link de
navegação. `SCRIPT_TERCEIRO_NAO_DECLARADO` diz `dica_de_conexao` ou
`recurso_carregado`; a severidade ficou, porque rebaixar a dica exige regra nova
em `fontes_politica.json` — muda a versão da política e desatualiza os recibos
existentes, inclusive os da frente de publicação (decisão do integrador).
`String.fromCharCode` é o JS do Ad Inserter e continua risco (indício). Crédito
do tema (`LINK_EXTERNO_NO_CHROME`) e link editorial
(`LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO`) já são códigos distintos; link interno
continua sujeito a `ANCORA_INCONGRUENTE_COM_DESTINO`.

**d) Benefícios** — política "Government documents and official services":
cobre anúncios sobre **solicitar** benefício de assistência; exige certificação
ou pedido de exclusão (afetado que não promove o serviço) + verificação de
anunciante; o Google acrescenta "Not a government website". Card 106: o
anúncio fala de cadastro/consulta, o serviço oferecido é guia (não cadastra), o
destino declara que não faz inscrição. Enquadramento provável na categoria por
causa da intenção de solicitar, não por conter "benefício". Retirar palavras
não resolve sozinho. Nada foi pedido (certificação/exclusão) e o conjunto não foi
alterado.

## 4. Quatro canais

| canal | 1. builder aceito | 2. caminho HTTP/cockpit | 3. entrada e mídia | 4. elegível para lançar |
|---|---|---|---|---|
| SEARCH | sim — 15 ops, `xUsAh6AUPU_1FrNlaKXfvw` (Codex) | **sim** — card 106, 44 ops, `validate_only=true`, `partial_failure=false`, gRPC OK, `pNVi5pBJHo5K-w48h7rNdQ`; identidade **simulada**; auth real: passo do operador | real: oportunidade, conjunto aprovado, copy registrada; sem mídia | não — destino público não validado (rascunho 404), sem recibo de aprovação, política de benefícios, canário/trava fechados |
| DISPLAY | sim — 9 ops, `EqfdKLSt8Rq9Ne8alvKYEg` | **não** — a rota HTTP trata todo asset como produção; não há mídia aprovada para Google | ensaio (banners locais) | não |
| DEMAND_GEN | sim — 9 ops, `evcTANUKWqQckLlytFXcig`, **R$ 30/dia** no ensaio | **não** — idem | ensaio | não; teto do canário DG é **R$ 20/dia** e o Google exige US$ 5/dia em DG (deprecations, 2026) |
| PERFORMANCE_MAX | sim — 25 ops, `yMAhcaR7LNAAkf_AG0Rm0A` (ramo técnico de `validar`) | **não** — idem | ensaio | não; sem meta da campanha declarada a mensuração recusa (§3a) |

`validate_only` aceito: a API conferiu o pedido inteiro e pode recusar por
política detectável no envio — **não** é aprovação de veiculação (a revisão de
política ocorre depois de criado), não é autonomia, não é prontidão.

## 5. Leitura, análise e gestão — o essencial (Senac 24278665189, D-1 08/10)

| função | rota/adapter | evidência | lacuna |
|---|---|---|---|
| campanhas, grupos, anúncios, assets | `/api/trafego/inventario`; coletor `estado`, `asset` | leitura real: 734 estados, 19 assets | Senac fora do inventário e de `trafego_campanha` (sem `volc_campaign_id`) |
| orçamento e estratégia | GAQL `campaign`/`campaign_budget` | TARGET_SPEND, teto CPC R$ 1,00, parceiros ligados, R$ 30/dia, STANDARD | — |
| keywords e termos | coletor `keyword`, `termo` | 2 keywords (com QS), 365 termos | negativas não geradas (exige análise de relevância) |
| desempenho dia/dispositivo/rede | `campanha_dia` (ledger), `hora_dispositivo`, GAQL | 08/10: 942 impr., 74 cliques, R$ 59,52; mobile Search 60 cliques, CPC R$ 0,89 | — |
| conversões, metas, valores | GAQL `conversion_action`, metas, custom goals | §3a | autoridade local não lê custom goals nem volume (PMax) |
| diagnósticos e recomendações | `/gestao/recomendacoes`; `/campanhas/{volc_id}/diagnostico` | 5 recomendações reais (nenhuma aplicada) | diagnóstico persistido inalcançável para a Senac (sem `volc_campaign_id`) |
| coleta recorrente e idempotência | `volc_ads.coleta --agenda` | passo repetido pulado (08/10, recibos) | units não instaladas; credencial não transferida |
| preparar edição/pausa/ativação/verba/lance | `/gestao/propostas`; `conta_google.validar` | 409 `regra_ausente` (HTTP real); `validate_only` de 9 ações aceito na rodada de 08/10 (não repetido) | regra de gestão não publicada; v17_03 não aplicada; sem teto acumulado |

## 6. Pendências e menor próxima ação

| pendência | menor ação | dono |
|---|---|---|
| auth real no caminho HTTP | rodar `scripts/provar-sessao-real-gads.sh` (copiar a sessão `sb-database-auth-token`) | você |
| destino Search | publicar a LP 2477 (permalink) — fora desta sprint | decisão |
| Display/DG/PMax pelo cockpit | mídia com aprovação criativa para Google | criativo |
| DG | teto do canário ≥ mínimo do Google | decisão financeira |
| PMax | declarar meta da campanha no plano; ler volume em `ler_mensuracao`; ler custom goals | local (próxima) |
| Senac fora da identidade VOLC | `POST /gestao/campanhas/importar` (escreve em produção) | decisão |
| request ID de sucesso no recibo do `/provar` | hoje só falha guarda request ID; o desta sprint veio de interceptor de auditoria | local (próxima) |
| dica de conexão como risco | regra nova em `fontes_politica.json` (nova versão da política) | integrador |
| política de benefícios | pedido de exclusão no Google ou mudança de mensagem | decisão |
