# HANDOFF — Google Multichannel Completion Spec v1

**Veredito:** `GOOGLE_MULTICHANNEL_COMPLETION_SPEC_READY`

- Branch documental: `spec/fable-google-multichannel-completion-v1`, base `884393b0e99b5ee403a6f38e1e4225012705f942`, somente `docs/specs/google-multichannel-completion-v1/**`.
- Fontes congeladas lidas e não alteradas: operacional 884393b, candidato 21fbc3b, creative supply chain 5d2cbd0. Zero merge/cherry-pick/rebase/push; zero chamada Google Ads com credencial; zero validate_only; zero mutate; zero Supabase; zero n8n/WordPress.

## O que já existe
- Builders dos três canais com contratos tipados, plano projetado e sonda de protos v25; Display e Demand Gen com `validate_only` remoto aprovado em 01/09/2026 (9 operações cada); PMax serializa 27 operações offline com opt-out de expansão de URL.
- Fronteira HTTP `/provar` para Display e Demand Gen (flag), `/planejar-pmax` local, `/subir` governado por ledger v10 (provado em Search), `/reconciliar`, `/canais` com quatro portões.
- Search como referência real: criação PAUSED + read-back + ledger (recibos citados em `OFFICIAL-API-EVIDENCE.json` EV-17).

## O que pode ser reaproveitado
- Tudo do candidato 21fbc3b já está em 884393b byte a byte (`DIVERGED-CANDIDATE-ADJUDICATION.json`: 17× SUPERSEDED). Não fazer merge.
- Ledger, trava de dois fatores, selo, portão de destino, ponte criativa, régua PMax e observabilidade PMax são canal-agnósticos ou já cobrem os três canais.

## O que precisa ser refeito ou completado
- Janela do canário por canal (é SEARCH-only); `/subir` monta Display pelo caminho Search; Display nasce com ad group e anúncio ENABLED; sem `control_spec`; Display aceita asset remoto sem recibo.
- Demand Gen: abrir mutação, traduzir mínimo diário por moeda, opt-out das três automações default.
- PMax: lote do executor, trava de URL completa (`TEXT_ASSET_AUTOMATION`, `GENERATE_IMAGE_ENHANCEMENT`, `GENERATE_ENHANCED_YOUTUBE_VIDEOS` OPTED_OUT, `excluded_parent_asset_set_types=[PAGE_FEED]`, `final_mobile_urls` vazio), ledger v12_03 no oficial, `/provar` com mensuração lida no servidor.
- UI: escada de lançamento por canal e fatos travados (`UI-OPERATOR-CONTRACT.json`).

## Bloqueadores reais
1. Portão de lance recusa Smart Bidding sem medição PRONTO e a conta-laboratório tem zero ações de conversão válidas (OCC-G04/G07) — precondição de conta, não contornável por código.
2. Gate de identidade de terceiro sobre pixels não existe (OCC-G17) — modo mínimo antes de qualquer canário.
3. PMax: v12_03 não aplicada no oficial (OCC-G20); aceitação de `AssetGroup.status=PAUSED` e das automações só provável no validate_only (OCC-G18/G13); regra de ação válida usa campo deprecado (OCC-G15, RESEARCH_REQUIRED).

## As cinco primeiras tarefas
T01 política de canário por canal · T02 paridade `/provar`×`/subir` e duplicidade por destino · T03 builder Display PAUSED + `control_spec` + recibo obrigatório · T04 precondição de medição e adjudicação de `include_in_conversions_metric` · T05 primeiro canário Display.

## Ordem dos canários
1. Display estático (CAN-DSP-01) · 2. Demand Gen estático (CAN-DGN-01) · 3. Performance Max com URL exclusiva (CAN-PMX-01). Hipótese inicial confirmada por evidência (`CANARY-SEQUENCE.json`).

## Artefatos
RUN-MANIFEST.json · AS-IS-ARCHITECTURE.md · DIVERGED-CANDIDATE-ADJUDICATION.json · OFFICIAL-API-EVIDENCE.json (20 entradas) · GOOGLE-MULTICHANNEL-CAPABILITY-MATRIX.json (39 células) · GOOGLE-MULTICHANNEL-FIELD-CONTRACT.json · CREATIVE-ASSET-REQUIREMENTS.json · VALIDATE-CREATE-READBACK-CONTRACT.json · UI-OPERATOR-CONTRACT.json · OPEN-CONTRACT-CONFLICTS.json (23) · CANARY-SEQUENCE.json · EXECUTION-WORKBREAKDOWN.json (15 tarefas) · CURATION-HANDOFF.json · HANDOFF.md.

## Revisão adversarial (uma rodada, documental)
- Field/proto inventado: `url_expansion_opt_out` NÃO é usado (ausente em v25, EV-02); todos os campos citados existem no proto local ou na doc lida. Corrigido durante a escrita: `excluded_parent_asset_set_types` citado com docstring do proto.
- Capability inflation: nenhuma prova local promovida a remota; PMax permanece PROVEN_LOCAL/BLOCKED; a afirmação do candidato "Display cria PAUSED" foi rebaixada a "só no engine".
- Falso validate_only: nenhum validate_only novo declarado; os de 01/09 citados por caminho.
- Asset incompatível: régua por canal reconciliada com requisitos.yaml e Help Center; logo 144 adotado.
- URL expansion: opt-out atual parcial; contrato completo em F-PMX-09 e read-back com `final_url_expansion_asset_view` e `campaign_asset_set PAGE_FEED`.
- Criação ENABLED: Display ad group/ad ENABLED registrado como FIX_BEFORE_FIRST_CANARY (OCC-G03).
- Identidade de conta errada / reuso de outra conta: guardas existentes citadas; Display `str` sem recibo marcado (OCC-G16).
- Payload aprovado ≠ enviado: paridade `/provar`×`/subir` para Display marcada (OCC-G02).
- Idempotência gerando duplicação: destino de PMax não coberto pela pré-checagem (OCC-G08).
- UI com controle sem efeito / backend invisível: lacunas listadas no UI-OPERATOR-CONTRACT (vídeo por resource name raw; automações não exibidas).
- Falta de read-back: contratos GAQL por canal escritos; espelho só ENABLED registrado.
- Doc desatualizada: v25.1 sem SDK (EV-12); páginas não renderizadas marcadas RESEARCH_REQUIRED (EV-19/EV-20).
