# HANDOFF — Creative Studio Operating Experience Spec v1

**Veredito:** `CREATIVE_STUDIO_OPERATING_EXPERIENCE_SPEC_READY`

Missão documental. Nenhum runtime, frontend, backend, banco, migration, n8n, WordPress, Postiz, deploy, imagem ou vídeo real. Zero chamadas autenticadas a Meta/Google, zero Supabase oficial, zero credencial lida. Somente `docs/specs/creative-studio-operating-experience-v1/` foi criada.

- Base factual: `5cb654fbf1dbc226a995b0c60a37310c2aa4eb4c` (`origin/execution/volc-os-operacao-80-20`), branch documental `spec/fable-creative-studio-operating-experience-v1`, worktree `/private/tmp/volc-spec-creative-studio-operating-experience-v1`.
- Branch operacional e sua worktree não foram tocadas (prova em `RUN-MANIFEST.json`). `localhost:8080` não foi usado.
- Referência Positivo lida read-only; HEAD e status idênticos antes e depois (prova em `RUN-MANIFEST.json`). Nenhum código, token, imagem, texto ou marca copiado.
- Grafo: `graphify-out/` não existe na worktree; a cópia principal está construída em `a539dbd7` (defasada). Não foi reconstruído; todo fato foi confirmado em código/migration/teste do SHA.
- Nota: o item 9 da lista de entregáveis chegou truncado (`OP0.`); foi entregue como `OPERATOR-JOURNEY.json`.

## Artefatos (26)
RUN-MANIFEST.json · HANDOFF.md · AS-IS-ARCHITECTURE.md · AS-IS-INVENTORY.json (48 itens) · CURRENT-UX-ADVERSARIAL-AUDIT.json (30 achados) · POSITIVO-REFERENCE-EXTRACTION.json (18 princípios) · ENGINE-CAPABILITY-MATRIX.json · ROUTE-AND-INFORMATION-ARCHITECTURE.json · OPERATOR-JOURNEY.json · CREATIVE-STUDIO-EXPERIENCE-CONTRACT.json · UI-SURFACE-SPEC.json · WIREFRAMES.md (13 telas, 1440/768/390, light/dark) · MOTION-AND-FEEDBACK-CONTRACT.json · DATA-CONTRACT-MATRIX.json (38 linhas) · DATABASE-AND-PERSISTENCE-GAPS.json · ASSET-LIFECYCLE-AND-STATE-MACHINE.json · APPROVAL-AND-PROVENANCE-CONTRACT.json · CAMPAIGN-HANDOFF-CONTRACT.json · ORGANIC-DISTRIBUTION-HANDOFF.json · COMPONENT-ARCHITECTURE.json · RESPONSIVE-A11Y-THEME-CONTRACT.json · ERROR-EMPTY-LOADING-STATES.json · OPEN-CONTRACT-CONFLICTS.json (14) · EXECUTION-WORKBREAKDOWN.json (18 tarefas) · ADVERSARIAL-REVIEW.json (18 perguntas, 1 rodada corretiva) · CURATION-HANDOFF.json.

## Autoridades encontradas
Três fábricas convivem: Estúdio (jobs, Supabase `criativo_*`, Gemini, storage local), Bancada (SQLite local, motores `tipografico-local`/`png-local`/`remotion-local`, natureza ensaio) e Vídeo observado (fábrica externa). Duplicações: formatos (4 catálogos), destinos (3 vocabulários), procedência (3 formas), aprovação (3 modelos), estados (2 de job + 1 de storage), "peça" (Estúdio × publicação orgânica).

## Motores reais e estado
- `gemini-imagem` (full_llm): IMPLEMENTED_UNPROVEN em produção; provado localmente; sem referência, sem seed, sem variações, sem texto na imagem; custo só estimado (0,039 USD/peça, referência).
- `tipografico-local`, `png-local`: PROVEN_RUNTIME local; natureza `local`, não publicável.
- `remotion-local`: IMPLEMENTED_UNPROVEN (golden com `skipif` sem node/sandbox); ensaio.
- `volc-factory` (observado): BLOCKED_EXTERNAL (código pronto; depende da raiz da fábrica no servidor).
- PRENSA, photo_preserved, full_llm_then_prensa: NOT_IMPLEMENTED no VOLC.
- Destinos: Display/Demand Gen com `validate_only` remoto (01/09); PMax offline; Meta só com imagem da conta; Search texto; Postiz texto; WordPress/FunnelForge fora da cadeia. **Nenhum destino recebe asset da Biblioteca por id hoje.**

## Principais defeitos de UX (S1/S2)
Ficha do ativo sem destinos/próximo ato (UX-A01); Tráfego só aceita upload manual e ignora `?destino=&canal=` (UX-A02); finalidade da aprovação em texto livre (UX-A08); gate de identidade inexistente sem aviso (UX-A28); Home sem capacidades reais (UX-A03); trilho de fases sem o vocabulário real do executor (UX-A04); briefing em 5 etapas sem forma dos formatos nem rascunho (UX-A06); vocabulário `manual` × `manual_export` (UX-A07); revogar invisível (UX-A09); biblioteca sem tabela/inspetor/seleção/compare (UX-A10, A16); filtro destino que o backend recusa (UX-A11); id cru do brand pack (UX-A12); cabeçalho sem identidade VOLC e `Secao` sem `shadow-card` (UX-A13); Laboratório fora do shell (UX-A15).

## Princípios extraídos do Positivo
ADOPT: miniatura proporcional de formato, slots sincronizados a eventos reais, erro com dica por código, frase-resumo de consequência, SSE por fetch. ADAPT: briefing em página única com trilho, quantidade de variações (P2), resultado com ações por peça e zoom (sem hover-only, sem zip como única preservação), badge sólido, brand studio no servidor, foto própria com direitos (P2). REJECT: percentual/ETA estimados, chaves no navegador, localStorage como autoridade, glass/blur/blobs/stagger/glow, destruir o formulário ao gerar.

## Jornada proposta
IDEIA (Home com capacidades reais e próximo ato) → BRIEFING único com revelação progressiva (finalidade → destino/canal → identidade → mensagem → tipo/motor → formatos com miniatura → revisão → disparo) → PRODUÇÃO (trilho de fases reais + tiles que trocam no evento + timeline) → RENDITIONS (fatos medidos) → COMPARAÇÃO (P1) → INSPEÇÃO (InspetorDePeca) → APROVAÇÃO por finalidade do catálogo vinculada ao hash → BIBLIOTECA (tabela/grade, seleção, inspetor) → VÍNCULO (seleção pelo Tráfego por id; pacote gravado) → CAMPANHA/ORGÂNICO (fora do Estúdio) → RECIBOS/HISTÓRICO/REUTILIZAÇÃO.

## Matriz de dados e lacunas
38 linhas campo→endpoint→tabela. Gaps principais: API_GAP `asset_id` no `/provar` de Display, `GET /assets/{id}/destinos`, `slot`/`ordem` em `/assets`, revogar no cliente; RUNTIME_GAP `criativo_pacote` (vínculo), `usos` derivados, entrega (P1), storage remoto, v11_03; MIGRATION_CANDIDATE MIG-01 policy receipt (P1), MIG-02 reservas (P2), MIG-03 variações (P2, opção sem migration recomendada), MIG-04 templates (P1 condicional). Nenhuma tabela nova em P0.

## Conflitos críticos
OCF-03 (aprovação de master × gatilho exige aprovação de pacote na entrega) bloqueia P1-entrega; OCF-04 (gate de identidade inexistente) bloqueia canário Meta; OCF-05/12 (bancada como segunda fábrica; vídeo real) bloqueiam vídeo P1; OCF-07 (despacho síncrono em serverless) é tratado na UI. Nenhum bloqueia P0.

## Cinco primeiras tarefas
T01 shell único + identidade + query params · T02 Home com capacidades reais + lista de trabalhos · T03 briefing único de imagem · T04 produção real no Job · T08 handoff ao Tráfego por `asset_id` + vínculo em `criativo_pacote`.

## Gates documentais executados
Ver `RUN-MANIFEST.json`: 24 JSONs válidos, IDs únicos por artefato, dependências acíclicas e sem release posterior, scanner de segredos limpo, `git diff --check` limpo, Positivo e branch operacional inalterados, nenhum arquivo fora da pasta.

## Limitações
Sem capturas de tela (servidor local pertence a outro executor e roda outra branch); avaliação visual por leitura de código. Grafo defasado. Nenhum teste executado nesta worktree (sem `node_modules`/venv); a classificação PROVEN baseia-se em testes existentes lidos, não re-executados. Persistência de receitas (Laboratório) depende de decisão de schema.

## Confirmação literal
Zero runtime alterado. Zero arquivo da referência Positivo alterado. Zero mutação externa (Meta, Google, Supabase, n8n, WordPress, Postiz, deploy). Um único commit documental, sem push.
