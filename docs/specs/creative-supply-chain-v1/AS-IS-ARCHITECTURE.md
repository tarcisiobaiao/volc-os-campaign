# AS-IS — arquitetura real da cadeia de criativos (884393b0, 05/09/2026)

Leitura de código, não de intenção. Cada afirmação aponta `arquivo:linha`; os achados
numerados estão em `AS-IS-INVENTORY.json` (ASIS-nn) e a evidência oficial em
`OFFICIAL-API-EVIDENCE.json` (EV-*). O grafo (`graphify-out/UPDATE_STATUS.json`) foi
construído em `1ad7b8a8` com árvore suja; foi usado só para navegar.

## 1. Os dez contextos que existem hoje

| # | Contexto | Onde mora | O que decide sozinho | Estado |
|---|---|---|---|---|
| 1 | Estúdio Criativo | `backend/app/criativo/{dominio,execucao,persistencia,apresentacao,armazenamento}.py`, `backend/app/routers/criativos.py` | job de imagem `full_llm`, `criativo_master` por `content_hash`, aprovação humana por (master, versão, finalidade) | implementado; storage local; Supabase storage desarmado (`armazenamento.py:385-402`) |
| 2 | Bancada | `backend/app/criativo/bancada/**`, `backend/app/routers/criativos_execucao.py` | claim/lease/fencing, gates técnicos medidos do arquivo, storage relido, recibo imutável | implementado local (SQLite); v11_03 não aplicada no oficial |
| 3 | Porta de criativos | `volc_ads/criativo/**` | vocabulário `Asset`/`Procedencia`/`NaturezaDaProcedencia`, régua por canal (`requisitos.yaml`), `validar_lote`, catálogo em memória, envelopes por destino | implementado |
| 4 | Ponte criativo→Google | `volc_ads/criativo_ponte.py` | projeção para `ImagensDisplay/DemandGen/PMax`, `Linhagem`, `ReciboAssetAprovado`, reconferência de bytes | implementado e consumido por `backend/app/routers/trafego.py:1940-2032, 2547, 2685` |
| 5 | Engine Google | `volc_ads/campanha/{display,demand_gen,pmax,brief}.py`, `volc_ads/subir.py` | `asset_operation` inline com bytes no mesmo mutate atômico | Display cria PAUSED; Demand Gen valida; PMax planeja offline |
| 6 | Engine Meta | `backend/app/trafego/meta_execucao/**`, routers `trafego_meta_{validacao,criacao}.py` | plano P0, compilação, validate_only, aprovação durável, saga, reconciliação | validate_only real provado (`contrato.py:185-207`); create PAUSED atrás de duas flags |
| 7 | Espelho da biblioteca Meta | `backend/app/trafego/meta_execucao/ativos.py` | referências opacas de page/image/video da conta, preview autenticado | somente leitura |
| 8 | Redator/FunnelForge | `funnelforge-migracao/engine/src/funnelforge/pipeline/steps.py` | hero image por prompt LLM + gpt-image; upload para WordPress | fora da cadeia criativa (ASIS-26) |
| 9 | Portão de destino pago | `backend/app/landing_policy/**` | veredito por página sobre texto e links; detectores de marca de terceiro **em texto** | não inspeciona pixels |
| 10 | Cofre | `backend/app/asset_vault/**` | referências seguras de página/conta/credencial/identidade | schema aplicado; sem página real |

## 2. Os fluxos que realmente rodam

### 2.1 Estúdio → master → aprovação (imagem)
`POST /api/criativos/jobs` (`criativos.py:323-406`, exige admin) → `Executor.criar_job_de_imagem`
(chave de idempotência por conteúdo do pedido, `dominio.py:159-212`) → despacho
(`despacho.py:245-268`; serverless recusa) → `_produzir_peca` chama Gemini por slot
(`execucao.py:447-530`) → `publicar_artefato` sobe e relê (`armazenamento_verificado.py`) →
master com `content_hash`, `storage_chave`, `insumo_hash` → `POST /assets/{id}/aprovacoes`
(`criativos.py:719-800`). O browser recebe `previewUrl` assinada (300 s) e nunca a chave
(`apresentacao.py:31-35`).

### 2.2 Bancada → recibo → ponte → Display (imagem local)
`servico.produzir_local` enfileira e executa (`servico.py:303-380`) → operário mede MIME,
dimensão e sha256 do arquivo (`operario.py:610-735`) → recibo com procedência, custo
`Declarado`, storage e destinos → `_PORTA_DA_PONTE[canal]` atravessa `criativo_ponte`
(`servico.py:584-597`) → `Entrega` com `ImagensDisplay` + `Linhagem` + recibos por asset.

### 2.3 HTTP de tráfego Google → asset no mesmo mutate
`ProvarEntrada` aceita imagens de Display (`routers/trafego.py:1940-2032`), Demand Gen
(`:2547`) e PMax (`:2685-2731`) via a ponte; `display.construir` emite `asset_operation.create`
com `image_asset.data` por id temporário (`demand_gen.py:820-845`, `pmax.py:879-897`). Google
identifica asset por conteúdo (`display.py:389-413`, medido). Vídeo entra só por
resource name de YouTube (`pmax.py:743-754`).

### 2.4 Meta → biblioteca da conta → plano → validate_only → aprovação → saga
`GET .../criacao/ativos` lê `promote_pages`, `adimages`, `advideos` e devolve referências
opacas (`ativos.py:132-232`); `POST /compilar` resolve `asset_ref` para `image_hash` só no
processo (`contrato.py:252-300`); `compilar_plano_pausado` monta `object_story_spec.link_data`
com `image_hash`, `link`, `message`, `name`, `description`, `call_to_action` e hasheia o plano
(`compilador.py:94-216`); `validar_raizes` valida Campaign e Creatives com
`execution_options=validate_only` (`executor.py:218-267`); aprovação durável com manifesto de
passos, validation_id UNIQUE e `plan_request` (`trafego_meta_criacao.py:351-435`); saga
prepara recibo antes do POST, read-back por tipo, AMBÍGUO nunca reenvia
(`executor.py:269-450`, `CONTRATOS.md`).

### 2.5 LP + hero image (Redator)
`step_image` cria prompt por LLM e gera imagem 9:16 (`steps.py:1585-1660`);
`_upload_hero_and_rewrite` sobe para o WordPress de forma best-effort e não-fatal
(`steps.py:2685-2721`). O portão de destino pago audita o HTML/links depois
(`landing_policy/varredura.py`), sem olhar a imagem. Foi assim que a marca CAIXA num envelope
chegou ao ar (`docs/closure/hermes-redator-google-ads-policy-incident-v1/ROOT-CAUSE-ANALYSIS.md`).

## 3. Diagrama textual do fluxo AS-IS

```
briefing ──► Estúdio (Gemini full_llm) ──► master(content_hash) ──► aprovação humana ──► [fim]
                                                                        │
             Bancada (tipográfico/png/remotion) ──► recibo ──► ponte ───┤
                                                                        ▼
                                             Google: ProvarEntrada → asset_operation (bytes) → PAUSED
                                             (Display cria; Demand Gen valida; PMax offline)

biblioteca da conta Meta ──► referências opacas ──► plano P0 ──► validate_only ──► aprovar ──► saga PAUSED
        ▲ (nenhum master, nenhuma procedência, nenhum gate)

Redator ──► hero image (gpt-image) ──► WordPress media ──► LP ──► portão de destino (texto/links)
```

Não existe hoje uma aresta `Estúdio/Bancada → Meta`, nem `Redator → cadeia`, nem
`aprovação de peça → invalidação do plano`. Cada consumidor resolve identidade a seu modo.

## 4. Autoridades duplicadas (resumo; detalhe em ASIS-01..05)
1. Procedência em três formas (ASIS-01).
2. Quatro catálogos de formato/envelope (ASIS-02).
3. Vocabulários de destino sem interseção (ASIS-03).
4. Três modelos de aprovação sem vínculo entre peça e plano (ASIS-04).
5. Duas máquinas de job e uma de storage, nenhuma do **ativo como suprimento** (ASIS-05).
6. `hash_de_conteudo` replicada em três módulos com o mesmo formato `sha256:` (`volc_ads/criativo/contrato.py:190`, `backend/app/criativo/dominio.py:230`, `armazenamento.py:113`), equivalência coberta por teste — aceitável, registrada.

## 5. Lacunas que a spec fecha ou declara
- **Sem caminho Estúdio → Meta**: nenhum upload (`adimages`/`advideos`) existe (ASIS-12). Meta usa a biblioteca da conta sem procedência (ASIS-11).
- **Sem gate de identidade de terceiro em pixel** em nenhum dos dez contextos (ASIS-25, ASIS-26).
- **Sem ciclo de vida do ativo como suprimento**: `RESERVED/CONSUMED/STALE/REVOKED` inexistem; `usos` é sempre `[]` com `usoApurado=false` (`apresentacao.py:218-222`).
- **Sem elegibilidade por canal/placement** exposta ao browser (ASIS-17).
- **Storage remoto e worker hospedado** ausentes (ASIS-14, ASIS-15).
- **Vídeo** sem identidade comum entre observado, gerado, biblioteca Meta e YouTube (ASIS-29).
- **Flexível/dinâmico Meta** bloqueado por um único fato não exemplificado na doc (ASIS-13, EV-META-11).
- **Thumbnail de vídeo Meta** exige `image_hash` de imagem da conta (EV-META-05) → depende de upload.

## 6. O que já está certo e a spec preserva
- Ausência é `None`, nunca 0 (`volc_ads/criativo/contrato.py:234-241`, `bancada/contrato.py:52-111`, `apresentacao.py:49-55`).
- Hash cobre bytes e é reconferido antes do payload (`criativo_ponte.py:596-604`, `brief.py:628-632`).
- Referências opacas e ids brutos confinados ao processo (`meta/dominio.py:76-105`, `contrato.py:252-300`).
- Preview por URL assinada curta e proxy autenticado (`apresentacao.py:31-35`, `trafego_meta_validacao.py:275-313`).
- Recibo antes do POST e ambiguidade terminal na saga Meta (`executor.py:304-366`).
- Idempotência por conteúdo com tenant na chave (`bancada/contrato.py:225-247`, `dominio.py:187-212`).
