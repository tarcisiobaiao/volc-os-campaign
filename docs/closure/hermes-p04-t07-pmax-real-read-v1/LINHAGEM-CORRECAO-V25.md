# Linhagem da correção — leitura real → campos recusados → correção

**Missão:** P04-T07 PMAX REAL READ V1 (rodada corretiva focal)
**Data:** 2026-09-01
**Branch:** `sprint/hermes-p04-t07-pmax-real-read-v1`
**Base:** `fb9bf5cbdb1f53902d5c3f75a34e15eff426af0c`

Este documento existe para que ninguém precise reconstruir de memória por que a
consulta mudou. Ele liga cada campo removido à chamada real que o recusou, e
cada estado corrigido ao recibo errado que a leitura real produziu.

## 1. Os três passos, na ordem em que aconteceram

| # | Passo | Evidência durável | Veredito |
|---|---|---|---|
| 1 | Primeira leitura real — descoberta forçando `login_customer_id` | `HANDOFF.md` §4, artefato em `fb9bf5c` | `NO_ELIGIBLE_PMAX`: 4 contas verdes sem PMax, 9 com `USER_PERMISSION_DENIED` |
| 2 | Rodada corretiva de topologia — contas diretas, sem forçar MCC | `REAL-READ-SUMMARY.json` (commit `23fbcf3`) | `REAL_READ_PARTIAL`: 13 contas, 12 vazias confirmadas, 1 com 12 campanhas PMax, alvo `PAUSED` determinístico |
| 3 | Correção do código contra o que a v25 real recusou | commits `5e935f5` (contraprovas) e `808e940` (correção) | 70 provas verdes, sem rede |

A evidência do passo 1 **não foi apagada**: o artefato daquela rodada está em
`fb9bf5c`, e as seções 1–10 do `HANDOFF.md` continuam descrevendo-a como ela
foi. A cobertura parcial daquele veredito (9/13 contas não inspecionadas) é o
motivo de a rodada 2 existir.

## 2. O que a v25 real recusou

Com alvo real, três das sete famílias caíram inteiras com
`query_error: UNRECOGNIZED_FIELD`. Os nove campos **existem nos descriptors do
SDK v25 instalado** — `assert_v25_descriptor_contract()` passava com todos eles.
Descriptor de proto não é contrato de seleção GAQL, e só a chamada real separou
as duas coisas.

| Família | Campo recusado | Cobertura perdida | Substituto |
|---|---|---|---|
| `PMAX_ASSET_GROUPS` | `asset_group.asset_coverage.ad_strength_action_items.action_item_type` | qual ação o Google sugere para subir a força | nenhum |
| `PMAX_ASSET_GROUPS` | `…add_asset_details.asset_field_type` | qual tipo de asset falta | nenhum |
| `PMAX_ASSET_GROUPS` | `…add_asset_details.asset_count` | quantos assets faltam | nenhum |
| `PMAX_ASSET_GROUPS` | `…add_asset_details.video_aspect_ratio_requirement` | proporção de vídeo exigida | nenhum |
| `PMAX_ASSET_GROUP_ASSETS` | `asset_group_asset.primary_status_details.status` | detalhe por trás do status do vínculo | nenhum |
| `PMAX_ASSET_GROUP_ASSETS` | `asset_group_asset.primary_status_details.reason` | razão detalhada do status | nenhum |
| `PMAX_ASSET_GROUP_ASSETS` | `…primary_status_details.asset_disapproved.offline_evaluation_error_reasons` | por que um asset reprovado foi reprovado | nenhum |
| `PMAX_RECOMENDACOES_FORCA` | `recommendation.improve_performance_max_ad_strength_recommendation.asset_group` | a qual grupo a recomendação se refere | nenhum |
| `PMAX_RECOMENDACOES_FORCA` | `…improve_performance_max_ad_strength_recommendation.ad_strength` | a força que a recomendação reporta | nenhum |

**Nenhum campo foi trocado por outro.** Nada equivalente foi comprovado na v25
real, e um fallback semântico responderia outra pergunta com cara de resposta.
Em particular: `asset_group.ad_strength` **não** substitui o `ad_strength` da
recomendação — são duas leituras diferentes, feitas por dois recursos
diferentes, e igualá-las inventaria uma equivalência que ninguém provou.

### O que sobrou de pé em cada família

- `PMAX_ASSET_GROUPS`: `id`, `resource_name`, `name`, `campaign`, `status`,
  `primary_status`, `primary_status_reasons`, `ad_strength`, `final_urls`,
  `final_mobile_urls`, `path1`, `path2`. A **nota** de força continua legível; o
  **que fazer a respeito** dela, não.
- `PMAX_ASSET_GROUP_ASSETS`: `primary_status` e `primary_status_reasons`
  sobrevivem — resta o motivo grosso, sem o fino. `policy_summary` continua
  trazendo aprovação e tópicos de política, que é outra pergunta.
- `PMAX_RECOMENDACOES_FORCA`: a recomendação continua identificada
  (`resource_name`, `type`, `campaign`, `dismissed`). Sabe-se que ela existe e a
  qual campanha pertence; não a qual grupo, nem qual força ela reporta.

A perda não vive só neste documento: ela viaja em
`payload.campos_recusados_pela_api` de cada recibo e em `cobertura_perdida` do
resumo sanitizado que o CLI imprime.

### `asset_group_asset.performance_label` — outra causa, outra prova

Adjudicado separadamente na leitura real, por `GoogleAdsFieldService` mais GAQL
mínima real: `NOT_SUPPORTED_IN_V25`. Ele continua em
`CAMPOS_NAO_SUPORTADOS_V25`, uma lista diferente, porque a causa é diferente — o
SDK não tem o campo, contra campos que o SDK tem e o endpoint recusa. Misturar
as duas listas apagaria a distinção entre as duas provas.

## 3. Onde a correção foi feita, e onde não foi

Os builders que projetavam os campos recusados estão em
`volc_ads/observabilidade_pmax/queries.py`, **fora do ownership desta rodada** e
com testes próprios que afirmam a presença de `asset_group.asset_coverage`
(`backend/tests/test_observabilidade_pmax.py:865`). Mudá-los aqui trocaria uma
correção focal por uma mudança de escopo em outra lane.

A poda acontece então em `volc_ads/inteligencia_google/pmax.py`, em
`sem_campos_recusados()`, e `assert_sem_campos_recusados()` fecha a porta de
volta: toda consulta desta coleta passa por `_select()`, que recusa qualquer
projeção com campo já recusado pela API real — venha ela de edição local ou de
mudança no builder da outra lane.

**Fica aberto:** aquele builder continua emitindo os nove campos para quem o
chamar direto. A lane dona precisa decidir entre podar na origem ou declarar a
mesma perda.

## 4. A correção epistemológica

Estados que a leitura real registrou, e o que estava errado neles:

| Família | Estado na leitura real | Diagnóstico | Estado após a correção |
|---|---|---|---|
| `PMAX_ASSETS` | `vazio_confirmado`, causa "no asset ids from asset_group_asset" | o prerequisito **falhou**; "não há assets" foi afirmado por quem nunca conseguiu perguntar | `falhou`, `erro_codigo = DEPENDENCIA_FALHOU:PMAX_ASSET_GROUP_ASSETS` |
| `PMAX_SINAIS` | `vazio_confirmado`, causa "no asset group ids" | idem, sobre `PMAX_ASSET_GROUPS` | `falhou`, `erro_codigo = DEPENDENCIA_FALHOU:PMAX_ASSET_GROUPS` |

Duas decisões dentro dessa correção:

1. **A distinção passou a morar na projeção**, não só no coletor.
   `documento_assets(pedidos=None)` e `documento_sinais(grupos_conhecidos=None)`
   já não conseguem produzir `vazio_confirmado`: `None` é "o prerequisito não
   concluiu" e `[]` continua sendo "foi lido e estava vazio". Enquanto a regra
   morava apenas no chamador, qualquer outro consumidor — inclusive o runner da
   leitura real — repetia o mesmo engano com a mesma lista vazia.
2. **Estado `falhou`, e não `parcial`.** `parcial` é o que a família de
   desempenho usa quando *uma parte* respondeu (a métrica agregada chegou, a
   segmentação por canal caiu). Numa família dependente não chegou nem uma
   linha, nem um zero; chamar isso de parcial afirmaria uma leitura que não
   houve. O que a correção acrescenta é a causa **estruturada** —
   `DEPENDENCIA_FALHOU:<familia>` no próprio `erro_codigo` — para que a
   diferença entre "esta família caiu" e "a família de que ela depende caiu"
   sobreviva à ida ao ledger, onde antes só o payload sabia disso.

⚠️ Efeito no ledger: `erro_codigo` entra na chave de idempotência quando o
estado é `falhou`. Recibos gravados antes desta rodada com
`PREREQUISITO_NAO_LIDO` continuam válidos e **não são reescritos**; uma
repetição futura no mesmo bucket grava um recibo novo com a causa estruturada,
em vez de deduplicar contra o antigo. É uma linha a mais, não um fato perdido.

## 5. Contraprovas

Escritas antes da correção, com a leitura real como fixture — não como
ilustração. Em `5e935f5` elas **falhavam** contra o código da época:
13 falhas, 57 passagens. Em `808e940`: **70 passagens**.

| Contraprova | O que ela recusa |
|---|---|
| `test_r_a_lista_de_campos_recusados_vem_do_artefato_da_leitura_real` | lista de campos que não venha do `REAL-READ-SUMMARY.json` |
| `test_r_o_codigo_nomeia_exatamente_os_campos_que_a_leitura_real_recusou` | campo removido sem perda declarada; mistura das duas listas de causa |
| `test_r_nenhuma_consulta_pede_campo_que_a_v25_real_recusou` | qualquer consulta da coleta que ainda peça um dos nove |
| `test_r_a_recusa_real_deixa_de_derrubar_familia` | a queda real, reproduzida por um dublê que recusa pelo mesmo critério da v25 |
| `test_r_o_duble_recusaria_a_consulta_antiga_com_a_mensagem_real` | um dublê complacente, que só passaria por estar cego |
| `test_r_campo_removido_sem_equivalente_declara_a_perda_de_cobertura` | perda silenciosa: o recibo e o resumo humano precisam nomeá-la |
| `test_r_metrica_de_campo_recusado_nao_vira_ausencia_observada` | `ausente` ("perguntei e não veio") sobre campo que ninguém pergunta |
| `test_r_pedir_de_novo_um_campo_recusado_explode_na_construcao` | reintrodução silenciosa do campo recusado |
| `test_r_a_poda_nao_derruba_campo_de_nome_parecido` | poda por substring, que levaria `asset_group.ad_strength` junto |
| `test_s_projecao_sem_prerequisito_lido_nao_produz_vazio_confirmado` | `vazio_confirmado` sem prerequisito lido, na projeção |
| `test_s_prerequisito_ausente_com_linhas_e_contradicao_recusada` | linhas vindas de uma consulta que nunca foi feita |
| `test_s_dependente_de_familia_caida_declara_causa_estruturada` | causa não estruturada, ou dependência não declarada, ponta a ponta |
| `test_s_a_dependencia_declarada_e_a_que_o_coletor_usa` | mapa de dependência que ninguém consulta |
| `test_s_dependencia_caida_nao_conta_como_familia_observada` | prontidão verde com família que ninguém leu |

## 6. Gates locais desta rodada

| Gate | Resultado |
|---|---|
| `pytest backend/tests/test_google_inteligencia_pmax.py` | 70 passed |
| `pytest backend/tests/test_google_inteligencia_persistente.py backend/tests/test_google_inteligencia_saude.py` | 96 passed |
| `pytest backend/tests/test_observabilidade_pmax.py backend/tests/test_trafego_pmax_cockpit.py` | 52 passed (lane vizinha, não tocada) |
| `git diff --check` | limpo |
| varredura de segredo no diff | nada |

## 7. O que continua em aberto

1. **A correção não foi certificada contra a API real.** Ela é provada contra um
   dublê que reproduz o erro real campo a campo, sem rede. Só uma nova leitura
   real com o mesmo alvo pode dizer se as sete famílias fecham verdes — e é ela
   que trocaria `REAL_READ_PARTIAL` por `REAL_READ_PROVEN`.
2. **`asset_group.asset_coverage` sozinho não foi testado.** A API recusou os
   quatro caminhos aninhados; se o campo raiz é selecionável, ninguém provou.
   Pedi-lo agora seria adivinhação, e uma adivinhação errada derruba a família
   inteira de novo.
3. **O builder da outra lane continua emitindo os nove campos** (§3).
4. **A lacuna do ledger não mudou:** seis das sete famílias continuam sem lugar
   no CHECK `trafego_google_coleta_tipo`, esperando a v12_03. Ver
   `V12-03-REQUIREMENTS.md`.
5. **`asset_group_signal.approval_status` e `disapproval_reasons`** continuam por
   coletar, pela mesma razão de ownership de §3.

## 8. Confirmações desta rodada corretiva

- zero chamada Google Ads (real ou simulada com credencial);
- zero leitura de `/root/google-ads.yaml` ou de qualquer credencial;
- zero Supabase;
- zero mutate, validate mutate, create, update, remove, upload, apply;
- zero migration, n8n, deploy, Roadmap/grafo;
- zero push, zero amend;
- edição restrita ao ownership declarado.

## 9. Adendo após nova leitura real

A seção 7 registrava corretamente o estado **antes** da reexecução real pós-correção. Essa reexecução foi feita depois de `808e940` e está no topo de `REAL-READ-SUMMARY.json`: veredito `REAL_READ_PROVEN`, sete famílias sem falha por incompatibilidade conhecida e `performance_label` mantido como `NOT_SUPPORTED_IN_V25`. Portanto, o item "correção não certificada contra API real" fica fechado por esta 3ª rodada; continuam abertos apenas o builder de outra lane, os campos deliberadamente não coletados e a migration v12_03.
