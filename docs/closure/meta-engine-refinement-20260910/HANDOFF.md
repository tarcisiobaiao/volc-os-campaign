# Refino adversarial do engine Meta — 10/09/2026

## Veredito

**LOCAL VERIFIED / REMOTE PENDING.** Seis chamadas controladas ao modelo exato
`gemini-3.8-flash`, com `thinkingLevel=high` e Google Search solicitado, foram
adjudicadas contra o código completo e testes locais. Nenhuma sugestão foi
aplicada automaticamente.

Foram corrigidos defeitos reproduzíveis em cinco fronteiras:

- timeout de `validate_only` antes da reserva do passo volta como 504 retentável,
  sem exigir reconciliação de um objeto que nunca foi enviado; a retomada usa a
  mesma aprovação e reaproveita pais já criados;
- catálogo de posts lê `creative_asset_groups_spec` no Ad, preserva anúncios
  flexíveis como preview não reutilizável estaticamente e aceita descrição
  opcional sem perder social proof elegível;
- fontes/conversões explicitamente arquivadas ou indisponíveis e vínculo de
  conversão com outro pixel são recusados antes da criação; metadado ausente
  continua desconhecido e segue para validação remota;
- autosave recupera falha transitória somente após nova edição, sem loop do
  mesmo payload; resposta tardia de pack atualiza o conjunto capturado, sem
  contaminar o conjunto que passou a ter foco;
- bytes de fotografia são conferidos contra o SHA aprovado antes de qualquer
  geração paga, e briefings modernos exigem exatamente uma spec válida por
  formato. Briefings legados sem specs continuam executáveis.

O contrato mantém aprovação final por plano, criação exclusivamente `PAUSED` e
nenhuma rota de ativação.

## Orquestra Gemini

- Chamadas: **6 de 6**; concorrência máxima 2; retries automáticos 0.
- Modelo servido: **6/6 `gemini-3.8-flash`**, sem substituição.
- Thinking solicitado: **high em 6/6**.
- Search solicitado: **6/6**; grounding verificável retornou em **2/6**. A
  ferramenta ser solicitada não significa que o provedor a usou.
- Uso informado pelo provedor: **350.561 tokens totais** — 177.346 de prompt,
  6.641 de resposta, 166.574 de thinking e 88.485 cacheados. O total do
  provedor inclui sua própria contabilidade; os campos não devem ser somados
  novamente.
- Custo monetário: **não informado pela resposta da API**; nenhum valor em dólar
  foi inventado.

Recibos e packets sanitizados estão em
`.claude-ads/runs/meta-engine-refinement-20260910/`. Eles contêm somente trechos
allowlisted de código, hashes e resultados; nenhum `.env`, token, credencial,
dado de conta ou dado pessoal foi enviado.

## Adjudicação

Aceitos após reprodução local: timeout de validação, latch de autosave, corrida
de foco do pack, leitura Ad-level do flexível, descrição opcional, flags
negativas de mensuração, mismatch conhecido de pixel, SHA de anexo e cobertura
exata de specs por slot.

Não aplicados: colisão global de `variation_key` (já recusada no contrato),
copy manual em post existente (já autofill/read-only), cache de validação
obsoleto (todos os setters relevantes passam por `invalidar()`), custom
conversion sem `source_ref` (estado impossível em `MensuracaoMeta`), mudança de
semântica de `promoted_object`, inversão ABO/CBO e retorno antecipado financeiro
(contraditos pelos validadores e pelo grão financeiro completo). Não foi criada
allowlist improvisada de eventos padrão.

## Verificação

- Backend integrado focal: **222 passed**.
- Cadeia do motor de imagem: **102 passed**.
- Interface de rascunho/retomada: **21 passed**.
- Runner sanitizado e recibos: **10 passed**.
- Build Vite de produção: **passou**.
- TypeScript global: continua com erros herdados fora dos arquivos alterados;
  `MetaCriacaoPage.tsx` e `useMetaCampaignDraft.ts` não aparecem no resultado.
- `git diff --check`: passou.
- Chrome headless abriu a rota real em 375 e 1440 px sem overflow ou erro JS,
  mas a sessão isolada foi corretamente redirecionada para `/login`; portanto
  isto não é QA autenticado do wizard.
- Autoridade Supabase: `https://database.agenciavolc.com.br` confirmada. Não
  houve DDL, migration ou escrita no banco porque nenhuma correção exigiu schema.
- Nenhuma chamada Meta, criação de campanha, geração paga de imagem ou ativação
  ocorreu nesta rodada.

## Pendências reais

Uma campanha completa `PAUSED` ainda precisa de canário operacional autenticado
com validação, criação de campaign/adset/creative/ad e readback. A qualidade
visual/CTR do criativo exige geração e experimento; testes de contrato não a
provam. O catálogo de eventos padrão ainda precisa de contrato versionado com
fonte oficial atual, sem bloquear valores válidos por uma lista especulativa.
