# Matriz mestre de capacidades — o que o VOLC O.S. faz hoje no Google Ads

**Levantada em:** 27/08/2026 · **HEAD:** `9de42b9` · **API alvo:** Google Ads v25
**Método:** leitura de código + `docs/growth-engine/matriz-api/` + consulta somente-leitura ao
Supabase oficial. **Nenhuma chamada foi feita à API do Google para produzir este documento.**

> Este documento responde *"o que existe"*. Ele **não** decide o que deve existir — isso é do
> [PRD](../PRD-TRAFEGO-OPERACAO.md) — e **não** é autoridade sobre a API: para campo, limite e
> política, a autoridade é [`matriz-api/`](./matriz-api/), que cita fonte oficial com data.

## Os estados, e o que cada um obriga

| Estado | Significa | O que a tela pode fazer |
|---|---|---|
| `REAL_AGORA` | há código executável, com caminho até a conta | oferecer |
| `IMPLEMENTADO_NAO_EXPOSTO` | o código existe e **nenhuma rota o alcança** | não oferecer; **não reimplementar** |
| `FRONT_MOCKAVEL` | dá para desenhar a jornada com fixture declarada | oferecer marcado `PROTÓTIPO` |
| `PLANEJADO` | há ponto de extensão, falta implementação | declarar ausência |
| `BLOQUEADO_EXTERNO` | falta credencial, conta ou decisão de fora | dizer o que falta |
| `NAO_CONFIRMADO` | não foi possível provar nesta rodada | dizer que não se sabe |
| `NAO_SUPORTADO` | não existe, por decisão ou por limite da API | recusar, e ensinar por quê |

⚠️ **`IMPLEMENTADO_NAO_EXPOSTO` é o estado mais perigoso da tabela.** Ele parece ausência para
quem procura por rota, e o custo do erro é uma segunda implementação da mesma coisa.

---

## 1. Plataformas

| Plataforma | Estado | Evidência |
|---|---|---|
| Google Ads | `REAL_AGORA` | 3 contas, 84 campanhas sincronizadas; `trafego_campanha_espelho` lida em 27/08 10:45 |
| Meta Ads | `BLOQUEADO_EXTERNO` | `plataforma.py:META` declara `capacidades=()` — sem credencial, sem adaptador, sem conta ligada. O eixo existe na navegação para o vocabulário do Meta (CONJUNTO, não "grupo de anúncios") não ser traduzido errado |

---

## 2. Canais do Google — o resumo que decide produto

| Canal | Inventariar | Ler filhas (lance, URL) | Criar | Evidência |
|---|---|---|---|---|
| **Search** | `REAL_AGORA` | `REAL_AGORA` | `REAL_AGORA` | `volc_ads/campanha/search.py`; `adaptador_search.py` é o **único** registro em `sincronizador._PERFIS` |
| **Display** | `REAL_AGORA` | `PLANEJADO` | `REAL_AGORA` | `volc_ads/campanha/display.py` (26/08/2026); sem adaptador de leitura |
| **Demand Gen** | `REAL_AGORA` | `PLANEJADO` | `NAO_SUPORTADO` | `perfil.py`: `campos_operados=()`; o engine sabe ajustar campanha existente, não criar |
| **Performance Max** | `REAL_AGORA` | `PLANEJADO` | `NAO_SUPORTADO` | `perfil.py`: o engine levanta exceção |
| **Vídeo** | `REAL_AGORA` (camada comum) | `NAO_SUPORTADO` | `NAO_SUPORTADO` | sem manifesto: `plataforma.manifesto()` devolve `None` |
| **Shopping** | `REAL_AGORA` (camada comum) | `NAO_SUPORTADO` | `NAO_SUPORTADO` | idem |

**A consequência de produto, em uma frase:** o inventário é canal-agnóstico e mostra os seis;
a operação é de dois. Uma tela com seis botões de "criar" seria simétrica e falsa.

⚠️ **Demand Gen e PMax não são "só falta expor na UI".** Não há construtor no código-fonte.
Construí-los é engenharia equivalente à que foi feita para Search e Display — grafo atômico,
validação e taxonomia próprias —, não um toggle.

---

## 3. Leitura — o que já roda hoje

Nove consultas GAQL, todas `SELECT`, em duas famílias:

**Pipeline de varredura (7)** — fora do caminho de renderização, por ADR-08:

| # | Onde | Traz |
|---|---|---|
| 1 | `sincronizador.py:118` `GAQL_CAMPANHAS` | id, nome, status, serving_status, canal, estratégia, orçamento |
| 2 | `sincronizador.py:129` `GAQL_METRICAS` | impressões, cliques, custo por janela |
| 3 | `adaptador_search.py:46` `GAQL_LANCE` | `ad_group.cpc_bid_micros` — **só Search** |
| 4 | `adaptador_search.py:65` `GAQL_URL_FINAL` | `ad_group_ad.ad.final_urls` — **só Search** |
| 5 | `contas.py:41` `GAQL_CLIENTES` | árvore do MCC |
| 6 | `contas.py:59` `GAQL_CONTA` | moeda, fuso, `auto_tagging_enabled` |
| 7 | `contas.py:160` `GAQL_METAS` | ações de conversão |

**Sob demanda, em rota (2):** veredito de política (`trafego.py:1635`) e conferência
pré-remoção (`trafego.py:1805`).

---

## 4. Ações — por estado

### Liberadas hoje

| Ação | Estado | Portão |
|---|---|---|
| listar, filtrar, agrupar por conta | `REAL_AGORA` | sessão |
| diagnosticar entrega | `REAL_AGORA` | sessão |
| varredura sob demanda de UMA conta | `REAL_AGORA` | `exigir_admin` (gasta quota do cliente) |
| `validate_only` de um pedido | `REAL_AGORA` | `exigir_admin` — **não** espera a trava de escrita: a API confere e descarta |
| veredito de política | `REAL_AGORA` | sessão |
| **confirmar / desfazer vínculo** | `REAL_AGORA` | sessão + papel ativo — **grava no VOLC, nunca no Google** |
| criar campanha pausada | `NAO_SUPORTADO` **nesta missão** | trava de dois fatores fechada (`volc_ads/gads/modo.py`) |

### Construído e sem rota — **não reimplementar**

| Capacidade | Onde vive | Por que importa |
|---|---|---|
| pedido de isenção de política | `volc_ads/isencao.py` | distingue `policy_violation_error` de `policy_finding_error`; nenhuma rota o chama |
| lote com idempotência e recibo | `backend/app/trafego/lote.py` | máquina de estados de 4 camadas, `desfecho='em_voo'`; nenhuma rota o chama |
| diagnóstico `entrega.py` | `volc_ads/entrega.py` | 6 GAQL próprias, consumido só por CLI |

### Não existe

| Ação | Estado | Nota |
|---|---|---|
| duplicar campanha | `NAO_CONFIRMADO` | nenhuma função de clonagem encontrada em `volc_ads/` nem `backend/app/trafego/` |
| reverter a partir de `change_event` | `NAO_SUPORTADO` | a leitura do forense existe; desfazer, não |
| otimizar termos, negativas automáticas, ajuste de lance | `NAO_SUPORTADO` | ADR-11: **nenhuma** regra de bidding, graduação ou automação está aprovada |

---

## 5. Autorização — as cinco capacidades

Implementadas em `backend/app/trafego/capacidades.py`, servidas por `GET /api/trafego/capacidades`.

| Capacidade | Resolvida em | Regra |
|---|---|---|
| `is_admin` | banco, via `volc_role_of` | papel de **produto** |
| `lab_mode` | config do servidor (`VOLC_LABORATORIO`, padrão `auto`) + admin | em `auto`, **fecha sozinho quando a escrita abre** |
| `google_read` | papel ativo | revogação vale no ato |
| `google_validate_only` | `is_admin` | **não** espera a trava: `validate_only` é leitura |
| `google_mutate` | `is_admin` **e** trava aberta | dois fatores, ambos no servidor |

> **`is_admin` não implica `google_mutate`.** A implicação inversa vale, e é invariante
> cobrada no tipo (`Capacidades._coerente`). Nada disso vira claim de JWT — o token viaja ao
> navegador e tem vida longa; a resposta é um retrato do instante.

---

## 6. Vínculo campanha ↔ funil

| Peça | Estado | Onde |
|---|---|---|
| motor de sugestão (funil → campanha) | `REAL_AGORA` | `reconciliacao.py:reconciliar` |
| **inversão (campanha → funil)** | `REAL_AGORA` | `reconciliacao.py:correspondencias_da_campanha` |
| rota de sugestão | `REAL_AGORA` | `GET /campanhas/{id}/correspondencias` |
| gravação da decisão humana | `REAL_AGORA` | `POST /vinculos` |
| **superfície de revisão** | `REAL_AGORA` | `RevisarCorrespondencia.tsx` |

Força dos sinais, e por que nenhuma é `forte` hoje:

| Regra | Força | Motivo |
|---|---|---|
| `url_final_da_conta` | `historica` | o espelho guarda a URL e **não** guarda quando ela foi lida; o gatilho da v9_04 a preserva entre varreduras. Volta a ser `forte` quando existir `url_final_lida_em` |
| `url_no_nome_declarado` | `medio` | declaração nossa; pode ter mudado no painel |
| `linhagem_declarada` | `forte` | os dois lados declaram |
| `lancamento_declarado` | `medio` | tabela legada, como sinal e não como autoridade |

⚠️ **Confirmação humana é obrigatória em todos os casos** (ADR-09). Nenhuma composição de
sinais dispensa o clique — vínculo errado contamina atribuição de receita de forma permanente,
e a linha é imutável: só dá para desfazer, nunca corrigir.

---

## 7. Armadilhas de versão v25

| Achado | Fonte |
|---|---|
| O SDK instalado (`google-ads` 31.3.0) está **uma minor atrás** da API viva (v25.1, 19/08/2026) | `matriz-api/comum.md` §1 |
| `search themes` em PMax **existe em v25** — um dos 3 tipos de `AssetGroupSignal` | `matriz-api/performance-max.md` |
| `partial_failure` é **inutilizável** em criação de estrutura nova, e **proibido** em PMax | `matriz-api/comum.md` §4 |
| A API **não oferece idempotência** — é problema da aplicação | `matriz-api/comum.md` §5 |
| `AdGroupAd.ad` é **imutável**: "editar anúncio" não existe, só substituir | `matriz-api/search.md` §3 |
| `ACCELERATED` está no enum e é **inutilizável** desde 2020 | `matriz-api/comum.md` |
| **Não existe guia oficial de criação de campanha Display** | `matriz-api/display.md` §0 |
| Placement positivo em Display: **duas fontes oficiais se contradizem** — por isso declarado indisponível | `matriz-api/display.md` §7 |

---

## 8. O que esta rodada não conseguiu provar

| Item | Por quê |
|---|---|
| capturas das telas **autenticadas** com dado real | o produto é fechado por login e a credencial do operador não é inferível. As superfícies novas foram conferidas com o CSS real do produto, em claro/escuro e 390/1280px |
| `validate_only` contra a conta real | exigiria disparar a prova numa conta de cliente; fora do escopo declarado desta missão |
| paridade `public.users` ↔ `app_auth.user_roles` | necessária para aposentar o caminho legado de papel em `api/_lib/identidade.js` |
