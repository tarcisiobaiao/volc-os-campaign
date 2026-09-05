# HANDOFF — Creative Supply Chain Master Spec v1

**Veredito:** `CREATIVE_SUPPLY_CHAIN_SPEC_READY_FOR_RECONCILIATION`

- Branch documental: `spec/fable-creative-supply-chain-v1` (worktree `/private/tmp/volc-spec-creative-supply-chain-v1`), base `884393b0e99b5ee403a6f38e1e4225012705f942`.
- Origem factual: `execution/volc-os-operacao-80-20`, HEAD `884393b0`, árvore limpa, não alterada.
- Grafo: construído em `1ad7b8a8` (≠ HEAD, árvore suja) — usado só para navegar; `graphify update` não executado.
- Runtime, frontend, migrations, testes de produto, Roadmap, curadoria e grafo: **não tocados**. Zero chamadas a Meta/Google com credencial, zero Supabase, zero push.

## Artefatos (todos em `docs/specs/creative-supply-chain-v1/`)
RUN-MANIFEST.json · AS-IS-ARCHITECTURE.md · AS-IS-INVENTORY.json (36 achados) · OFFICIAL-API-EVIDENCE.json (39 entradas) · CREATIVE-CAPABILITY-MATRIX.json (47 células) · ASSET-DEMAND-MANIFEST.schema.json · ASSET-SUPPLY-MANIFEST.schema.json · CREATIVE-SUPPLY-CHAIN-SPEC.json (24 decisões, 14 estados) · UX-OPERATOR-CONTRACT.json · POLICY-AND-PROVENANCE-CONTRACT.json · ADVERSARIAL-REVIEW.json (14 lentes, 1 rodada corretiva) · EXECUTION-WORKBREAKDOWN.json (16 tarefas com release P0–P3) · OPEN-CONTRACT-CONFLICTS.json (10) · CURATION-HANDOFF.json.

## Fontes oficiais e versões
Meta Marketing API **v26.0** (changelog 29/07/2026; referências de ad-creative, link_data, video_data, adimages, advideos, asset-feed-spec options/dynamic-creative, ad-image, video, generatepreviews, ads-guide Feed/Stories/vídeo, Ad Standards). Google Ads API **v25/v25.1** (release notes; protos oficiais googleapis v25 `asset_types`, `ad_type_infos`, `asset`, `asset_service`, `asset_field_type`; PMax asset requirements; Help Center Demand Gen e Search image assets; Misrepresentation policy). Páginas não legíveis (placement asset customization, image_crops, Advantage+ creative, sunset) estão declaradas como RESEARCH_REQUIRED, nunca preenchidas por memória.

## Autoridades encontradas
Estúdio (master/aprovação), Bancada (execução/recibo/storage), Porta+Ponte Google (régua/validação/linhagem), Engine Google, Engine Meta (plano/saga — outro spec), espelho da biblioteca Meta, FunnelForge (hero), portão de destino pago, Cofre. Duplicações: procedência (3 formas), formatos (4 catálogos), destinos (vocabulários sem interseção), aprovação (3 modelos), máquinas de estado (2 de job + 1 de storage).

## Decisões principais
Identidade por conteúdo com sal de tenant; referências opacas em toda fronteira; seis eixos de estado com lifecycle derivado; aprovação vinculada a (bytes, recibo de política, copy, finalidade); gate de identidade de terceiro sobre a imagem final com `THIRD_PARTY_IDENTITY_UNVERIFIED` bloqueando mídia paga; thumbnail Meta só por `image_hash`; vídeo Google só por referência YouTube; lote com falha parcial explícita; retry por chave antes do despacho e AMBIGUOUS fechado só por leitura; preview do provedor via backend ou simulado rotulado; retenção com recibos append-only.

## Conflitos abertos com o spec Meta
OCC-01 biblioteca da conta sem gate · OCC-02 associação asset×conta · OCC-03 Advantage+ creative OPT_OUT · OCC-04 supply_sha256 no plano · OCC-05 reserva/consumo na saga · OCC-06 copy inline vs copy_ref · OCC-07 instagram_actor_id vs instagram_user_id · OCC-08 upload de vídeo/thumbnail · OCC-09 flexível · OCC-10 engine Google. OCC-01 bloqueia o canário estático até o gate mínimo sobre a peça selecionada (bytes lidos no backend, hash, gate técnico e de política, recibo CLEAR/AUTHORIZED, correspondência com o image_hash); os demais não bloqueiam.

## Capacidades
Prontas (PROVEN_REMOTE_VALIDATE): Meta imagem estática, texto e validação remota das raízes do lote (Campaign + N Creatives, objects_created=0 — CAP-META-LOTE-01); Google Display imagem/lote/texto. IMPLEMENTED_UNPROVEN: criação PAUSED do lote completo Meta (Campaign + AdSet + N Creatives + N Ads — CAP-META-LOTE-02), à espera do primeiro create_paused real com read-back. Bloqueadas pelo provedor: Meta vídeo e thumbnail. RESEARCH_REQUIRED: Meta flexível/dinâmico, variação por placement, Search BUSINESS_LOGO. NOT_IMPLEMENTED: Search AD_IMAGE, Demand Gen vídeo/carrossel. Contagem completa no gate abaixo.

## Primeiros cinco lotes
1. WBS-C01 + WBS-C02 (contrato, hashes, envelopes) · 2. WBS-S01 + WBS-P01 (preview seguro, gate de política) · 3. WBS-B01 (lote, reserva/consumo, migration em cluster descartável) · 4. WBS-M01 + WBS-P03 (demanda Meta + canário estático; hero da LP no gate) · 5. WBS-S02 + WBS-G01 + WBS-M02 (bucket privado, Google por asset_ref, upload Meta).

## Lacunas que exigem prova real
validate_only de AdCreative com `asset_feed_spec` + `object_story_spec.page_id`; upload `adimages`/`advideos` em conta de teste; validate_only Demand Gen/PMax; criação do bucket `criativos`; leitura das páginas Meta não acessíveis.
