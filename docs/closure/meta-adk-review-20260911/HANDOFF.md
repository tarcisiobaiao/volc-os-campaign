# Fechamento — reconstrução do harness Meta ADK v2

Data: 11/09/2026
Estado honesto: `PARTIAL` — harness reconstruído e executado; nenhum patch do domínio
Meta foi aprovado nesta rodada.

## O que mudou

- O harness ativo antigo `tools/meta-adk-loop/` e seu runtime foram removidos.
- O runtime novo e isolado usa `google-adk==2.8.0` e `google-genai==2.22.0`.
- `tools/meta-adk-review/` usa o graph `Workflow` atual: pesquisa oficial e cartografia
  em paralelo, barreira, executor, crítico e rota limitada de revisão.
- Quatro lanes usam processos, branches e worktrees independentes: jornada, sistema
  criativo, publicação PAUSED e mensuração/operação.
- O host não oferece shell, Git, Meta, Supabase, deploy ou credenciais. Edições são
  limitadas por lane e protegidas por SHA; testes rodam sem rede.
- O callback ADK 2.x foi corrigido para o contrato nomeado `tool_response`.
- A segunda calibração reserva orçamento para implementação: cartógrafo com entrega
  final obrigatória, recusa a ferramenta repetida e impede exploração/diff prematuro.

## Provas

- Harness local: 16/16 testes.
- Três probes pagos: modelo efetivo exato `gemini-3.8-flash`, thinking `HIGH` e Google
  Search grounding com queries/chunks comprovados em todos.
- Execuções: 135 chamadas de lane, 1.252.953 tokens de lane e 0 edições. Os três
  probes somaram 5.287 tokens. Total observado nesta reconstrução: 1.258.240 tokens.
- Custo em dólares: indisponível (`null`), pois a API não devolveu valor faturado.
- Efeitos externos: 0 chamadas Meta, 0 migrations, 0 deploys, 0 ativações e 0 merges
  automáticos.

## Parecer do lead

Os achados sobre teto/vazio de copy flexível, rateio GAM e perda de rascunho foram
contraditos pelas proteções já presentes no código; não viraram patches. A pesquisa
levantou `instagram_actor_id` legado, enquanto readbacks reais disponíveis usam
`instagram_user_id`. O fluxo atual resolve explicitamente somente a Página Facebook
(`FACEBOOK_ONLY_PAGE_PROVEN`) e não possui prova da identidade Instagram. Renomear ou
traduzir esse ID sem resolver a identidade upstream poderia assinar uma identidade
errada; por isso o item fica como risco a pesquisar, não correção automática.

As raízes completas da execução permanecem temporariamente em:

- `/private/tmp/volc-meta-adk-v2-20260911T151406Z`
- `/private/tmp/volc-meta-adk-v2-20260911T152115Z`
- `/private/tmp/volc-meta-adk-v2-20260911T153356Z`

## Limites restantes

- A reconstrução prova o harness, modelo, grounding e contenção — não um refino global
  do produto nem produção.
- Nenhuma lane produziu candidato com patch + teste pós-edição; portanto não houve
  integração de mudança Meta.
- Falta uma missão focal para identidade Instagram, começando pela leitura/prova do
  ativo e somente depois pelo campo do payload e readback.
- QA visual autenticado, Supabase vivo e validação remota Meta permanecem fora deste
  harness e exigem atos separados.
