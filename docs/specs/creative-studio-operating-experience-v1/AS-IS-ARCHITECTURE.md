# AS-IS — Arquitetura do Estúdio Criativo em `5cb654f`

Base factual: `5cb654fbf1dbc226a995b0c60a37310c2aa4eb4c` (origin/execution/volc-os-operacao-80-20), lida na worktree documental `spec/fable-creative-studio-operating-experience-v1`. Nenhum arquivo fora de `docs/specs/creative-studio-operating-experience-v1/` foi tocado. Referências `arquivo:linha` apontam para esse SHA.

Grafo: `graphify-out/` não é rastreado e não existe nesta worktree; a cópia do repositório principal foi construída em `a539dbd7` (2026-08-29, árvore suja) e está defasada em relação a `5cb654f`. Foi consultada apenas como orientação; todo fato abaixo foi confirmado em código, migration, teste ou documento do SHA congelado.

## 1. Três autoridades de produção convivendo

| Caminho | Onde vive | Persistência | Motores | Estado |
|---|---|---|---|---|
| **Estúdio (jobs)** | `backend/app/criativo/{dominio,execucao,persistencia,apresentacao,armazenamento,parque}.py`, `backend/app/routers/criativos.py` | Supabase oficial, tabelas `criativo_*` da v11_01/v11_02 (aplicadas em 28/08/2026) | `services/creative_engine/motores/gemini_imagem.py` (`full_llm`) | implementado; despacho síncrono local; storage local em disco |
| **Bancada (trabalhos)** | `backend/app/criativo/bancada/**`, `backend/app/routers/criativos_execucao.py` | SQLite local `fila.db` (`bancada/servico.py:51-64`); adaptador Postgres para v11_03 (`bancada/deposito_postgres.py`, migration **não aplicada**) | `png-local`, `tipografico-local`, `remotion-local` (`bancada/adaptadores/*.py`), natureza `local` | provado localmente (golden); não publicável em produção |
| **Vídeo observado** | `backend/app/criativo/video_observado.py`, `video_ponte.py` | nenhuma: lê `VOLC_FACTORY_RAIZ` (`video_observado.py:84`) | fábrica externa `volc-factory` (leitura, procedência `observado`) | leitura quando a fábrica está acessível |

O router de produto declara as duas primeiras como caminhos separados (`criativos_execucao.py:1-6`: "conserva integralmente o contrato público existente em `/api/criativos/bancada`"). A interface expõe as duas: o briefing de imagem chama `POST /jobs`; o Laboratório chama `POST /bancada/trabalhos`. O operador não vê que são fábricas diferentes com armazenamentos diferentes.

## 2. Contrato do job de imagem (caminho Estúdio)

1. `POST /api/criativos/jobs` (`criativos.py:323-406`) exige admin, recusa sem credencial (`ESTUDIO.motor_sem_credencial`, 503) e recusa `modo != full_llm` (`ESTUDIO.modo_indisponivel`, 400).
2. `Executor.criar_job_de_imagem` (`execucao.py:107-242`) grava projeto, briefing, job (`estado=queued`, `idempotency_key`, `insumo_hash`, `custo_estimado_usd = n × 0,039`) e uma rendition `pendente` por slot; evento `aceito`.
3. `Executor.disparar` (`execucao.py:272-316`) escolhe o despachante (`bancada/despacho.py:245`) — fail-closed em ambiente serverless — e executa **sincronamente** no request (`to_thread`, `criativos.py:396-403`).
4. `_executar` (`execucao.py:395-445`): job `running`, evento `iniciando`; por peça: rendition `gerando` + evento `gerando(slot)`; chamada ao motor; `peca_pronta(slot)` ou `peca_falhou(slot)`; conflito de master → `peca_reaproveitada(slot)`.
5. `_fechar` (`execucao.py:667-718`): estado do lote por `dominio.estado_do_lote` (`dominio.py:245-274`) e evento `fim`.
6. Retry (`execucao.py:748-778`): `partial|failed|cancelled|queued` → `queued`, `tentativa+1`, evento `retry`, preserva peças prontas. Cancelamento (`execucao.py:780-814`): grava `cancelado_pedido_em`, evento `cancelando`; confirmação só quando o laço observa o pedido entre peças.
7. Eventos por SSE-sobre-fetch (`criativos.py:496-570`): quadros `evento`, `job`, `fim`; cursor `desde` por `seq`; teto de 600 s ociosos; falha do stream vira `fim` com `estado: desconhecido`.

Vocabulário real de `fase` (única fonte: `execucao.py`): `aceito`, `iniciando`, `gerando`, `peca_pronta`, `peca_falhou`, `peca_reaproveitada`, `retry`, `cancelando`, `fim`. `percentual` é sempre `null` (`execucao.py:455-457`). Nenhum evento de "QA", "persistência" ou "medição" é emitido separadamente: medir, normalizar e guardar acontecem dentro de `gerando → peca_pronta`.

## 3. Motor Gemini (`full_llm`)

`MotorGeminiImagem` (`gemini_imagem.py:140-303`): modelo `gemini-3.1-flash-image`, adaptador `1.0.0`, slug `gemini-imagem`, credencial do ambiente (`GEMINI_API_KEY` ou `settings.gemini_api_key`), `configurado = bool(chave)`. Uma chamada por peça, `imageConfig.aspectRatio` nativa, normalização por `enquadramento.enquadrar` (`resize | cover_crop | nao_normalizado`). Não aceita imagem de referência, seed, variações múltiplas, texto na imagem (instrução proíbe texto), nem devolve custo em dólares (`custo_usd=None`; estimativa de referência em metadados). Erros tipados com `permanente` (`_traduzir_status`, `gemini_imagem.py:378-399`).

## 4. Persistência e storage

- Tabelas com runtime: `criativo_brand_pack` (só leitura), `criativo_projeto`, `criativo_briefing`, `criativo_job`, `criativo_job_evento`, `criativo_master`, `criativo_rendition`, `criativo_aprovacao` (`persistencia.py:230-737`).
- Tabelas **sem** escritor no runtime: `criativo_pacote`, `criativo_entrega`, `criativo_master_gate`, `criativo_master_direito` (v11_01/v11_02). `criativo_job.motor_id`, `criativo_briefing.modo_id`, `criativo_aprovacao.finalidade_id` são resolvidos por slug pelo `Resolvedor` (`parque.py:369-447`).
- Storage: `ArmazenamentoLocal` é o padrão (`armazenamento.py:238-320`); `ArmazenamentoSupabase` está "implementado e desarmado" porque o bucket `criativos` não existe (`armazenamento.py:385-402`). Links assinados por chave, TTL de minutos (`armazenamento.py:20-30`; `Preview.tsx:6-10` fala em cinco minutos).
- v11_03 (`criativo_render_*`) existe como SQL provado em cluster descartável e **não aplicado** (`supabase/migrations/PLANO-v11_03.md:1-8`).
- Grants: `service_role` só `SELECT/INSERT/UPDATE`; RLS ligada e forçada; zero policies (RECONCILIACAO-ESTUDIO-2026-08-28.md §3).

## 5. Superfície HTTP disponível ao browser

`criativosApi.ts:271-453` cobre: `resumo`, `parque`, `bancada/*` (motores, trabalhos, arquivo, cancelar, retomar, linhagem), `jobs` (criar, listar, ler, retry, cancel, eventos), `assets` (listar, ler, decidir), `brand-packs` (listar), `formatos`, `videos`, `video/{slug}`. **Sem cliente** para `POST /assets/{id}/aprovacoes/{aprovacao_id}/revogar` (`criativos.py:804-841`). **Sem rota** para criar/editar brand pack, para criar pacote de destino, para registrar entrega ou para filtrar por destino (`criativos.py:634-643` recusa com `ESTUDIO.filtro_indisponivel`).

## 6. Frontend (rotas e componentes)

Rotas em `src/App.tsx:141-155`, todas sob `RotaDoEstudio` (ProtectedRoute + Suspense). Páginas em `src/pages/criativos/` (10 arquivos, 1998 linhas); componentes em `src/components/criativos/` (44 arquivos incl. 14 testes). Contrato de tipos em `src/types/criativos.ts` e `src/types/parqueCriativo.ts`. Navegação: item "Criativos" em `src/components/layout/Navigation.tsx:85-91` (adminOnly). `/criativos/laboratorio` não usa `Layout` (`LaboratorioPage.tsx:30`).

Padrões já corretos e a preservar: ausência ≠ zero (`comum/formato.ts`, `biblioteca/filtros.ts:97-131`), quatro estados de lista (`comum/leitura.ts`), sem barra de progresso inventada (`job/progresso.ts:78-100`), cancelamento pedido ≠ confirmado (`job/pecas.ts:129-186`), procedência não apurada (`comum/Selo.tsx:226-266`), prévia com renovação de link (`comum/Preview.tsx`), briefing preservado ao gerar (`BriefingDeImagemPage.tsx:92`), erros sanitizados no servidor (`dominio.py:343-363`), isolamento por dono (`criativos.py:410-453`, testes `test_criativo_autenticacao_confinada.py`).

## 7. Consumidores de asset e o buraco entre eles

| Destino | Como o asset chega hoje | Ligação com a Biblioteca do Estúdio |
|---|---|---|
| Google Display / Demand Gen / PMax | Bancada de Tráfego: `SeletorDeAsset` = `<input type="file">` → base64 (`ControlesMulticanal.tsx:127-208`) → `POST /provar` decodifica, mede e passa por `criativo_ponte.imagens_de_*` (`trafego.py:1954-2030`, `2397-2547`, `2617-2685`) | **nenhuma**: o operador baixa a peça do Estúdio e sobe o arquivo à mão; o link "Produzir no Estúdio" (`ControlesMulticanal.tsx:238-244`) envia `?destino=trafego&canal=` que a Home ignora |
| Meta | seleção na biblioteca da **conta** Meta (`MetaCriacaoPage.tsx:335-352`, `meta_execucao/ativos.py:171-232`); vídeo bloqueado (`trafego_meta_validacao.py:236-242`) | **nenhuma** (`adimages` só leitura; ASIS-12 do spec de supply chain) |
| Search | só texto (`requisitos.yaml:40-41`) | não aplicável |
| WordPress / FunnelForge (hero) | hero gerada pelo pipeline FunnelForge (`volc_ads/criativo/adaptadores/funnelforge_imagem.py:1-30`; ASIS-26) | **nenhuma** |
| Postiz / orgânico | `publicacao_organica` envia texto; `upload_de_midia` declarado não exercitado (`publicacao_organica/portas.py:170-180`); o pedido referencia `peca_id/peca_versao` de outra autoridade de "peça" | **nenhuma** |

Conclusão: hoje o Estúdio termina na aprovação. "Gerar", "aprovar", "subir", "vincular", "publicar" e "ativar" são atos diferentes e apenas os dois primeiros existem como runtime ligado ao patrimônio.

## 8. Vocabulários duplicados (a reconciliar na experiência, não no schema)

- Formatos: `dominio.FORMATOS` (4) × `criativo_formato` (7) × `FORMATOS_DE_IMAGEM` (4, `criativos.ts:576-613`) × envelopes de `volc_ads/criativo/destinos.py:172-237` (6). `GET /parque` já mede a divergência (`parque.py:214`).
- Destinos: briefing oferece `manual` (`briefing/contrato.ts:165-169`); catálogo semeia `manual_export` (`v11_02:854`); `destinos.py:71-75` usa `google|meta|organico`.
- Finalidade da aprovação: texto livre na UI (`aprovacoes/Decisao.tsx:42-48`) com `finalidade_id` resolvido por slug quando bate (`criativos.py:751-760`); catálogo tem 9 finalidades com classe.
- Estados: job (7, `dominio.py:39-41`) × trabalho da bancada (7, `bancada/contrato.py:42-49`) × armazenamento (4, `armazenamento_verificado.py:78`).
- "Peça": master do Estúdio × `peca_id` da publicação orgânica.

## 9. O que está provado, e onde

- Hermético/local: ~500 testes em `backend/tests/test_criativo_*.py` (idempotência, lote parcial, sanitização, tokens, enquadramento, bancada, worker, parque, storage verificado, goldens de imagem e de vídeo com `skipif` sem `node`/sandbox, vídeo observado com `skipif` sem fábrica) e 14 arquivos de teste de contrato de UI em `src/components/criativos/__tests__/`.
- Produção: schema v11_01/v11_02 aplicado; zero linhas operacionais em 28/08/2026 (RECONCILIACAO-ESTUDIO §3). Nenhuma evidência posterior de job real em produção foi encontrada neste SHA.
- Externo: Display e Demand Gen com `validate_only` remoto aprovado em 01/09/2026; Meta com `validate_only` de raízes; nenhum objeto criado (specs de referência, HANDOFF.md de cada uma).
