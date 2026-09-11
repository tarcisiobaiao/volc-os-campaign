# Meta ADK — execução e integração

Data: 10/09/2026. Roadmap: **P11-T21 partial**.
Nós: `doc:meta_adk_refinement_loop` → `cap_meta_ads`.

## Resultado

Google ADK instalado em runtime isolado. Loop real executou chamadas ao modelo
exato `gemini-3.8-flash`, HIGH e Google Search. O executor escreveu testes e código;
o crítico devolveu a primeira regressão; a rodada seguinte corrigiu o comportamento.
O lead revisou e integrou as duas alterações na worktree operacional.

Defeito corrigido: sugestões equivalentes apenas por maiúsculas/espaços ocupavam
novas posições no banco flexível de copy. Em banco com cinco textos, o botão de
acrescentar era bloqueado incorretamente. A comparação agora usa chave normalizada,
preservando o primeiro texto original. Uma sexta opção realmente distinta permanece
bloqueada; substituir continua uma decisão explícita do operador.

## Execuções pagas

| Execução | Chamadas | Tokens | Resultado |
| --- | ---: | ---: | --- |
| Probe | 1 | 1.751 | Modelo exato + grounding confirmados |
| Exploração ampla 1 | 23 | 463.980 | Limite; seis arquivos lidos, nenhum patch |
| Exploração ampla 2 | 26 | 611.187 | Limite; treze arquivos lidos, nenhum patch |
| Foco copy | 29 | 434.463 | Dois patches; regressão reproduzida e corrigida |
| Total | 79 | 1.511.381 | Nenhuma execução paga permanece ativa |

Custo monetário não informado pela API. A segunda execução excedeu seu teto
observado durante a resposta em voo. Não converter tokens em fatura presumida.
Recibos: `PROBE.json`, `RUN-1.json`, `RUN-2.json`, `RUN-COPY.json`.
Logs detalhados locais: `/private/tmp/volc-meta-adk-run-20260910{,-v2,-copy}/events.jsonl`.

O último crítico esgotou sua etapa sem parecer conclusivo; o estado original
`partial_iteration_limit` está preservado. Não foi promovido retroativamente a
`candidate`. A integração é uma decisão independente do lead sobre o patch pequeno.

## Provas

- Harness: oito testes locais passaram, incluindo bloqueio de paths sensíveis,
  SHA obsoleto, aplicação real de patch, invalidação de gates, modelo divergente,
  limites, alvo de teste e reserva da resposta final do crítico.
- Sandbox: 49 testes backend e 22 frontend passaram após corrigir o carregamento
  explícito dos plugins async e eliminar cache compartilhado do Vite.
- Regressão de copy: antes do fix, 21 passaram/1 falhou; depois, 22/22 passaram.
  O lead repetiu os 22 testes na worktree operacional após integrar.
- Build de produção aprovado (Vite, 10.611 módulos). Avisos de Browserslist antigo,
  classes Tailwind ambíguas e chunk grande permanecem; não são prova de regressão.
- `git diff --check` aprovado. Scanner não encontrou padrões fortes de segredo.
- Grafo reconstruído e frescor conferido no fechamento; a autoridade versionada é
  `docs/volc-os-graph/BUILD-STATUS.json`, com espelho em `graphify-out/UPDATE_STATUS.json`.
  O check confere o fingerprint dos inputs; o commit registrado identifica a base.

## Engenharia entregue

`tools/meta-adk-loop/`: dependências fixadas, probe, prompt mestre, foco específico,
host ADK com ferramentas, testes e consulta de status sem API.
ADR: `docs/architecture/ADR-META-ADK-REFINEMENT-LOOP.md`.
Base candidata: `b8bf70d1c35d981d9018c5f9be1b8eed6ae4f001`.
Branch candidata: `sprint/meta-adk-global-refinement-20260910`.
Integração operacional: `/private/tmp/volc-os-operacao-80-20`.
Checkout antigo e alterações concorrentes do tradutor criativo preservados.

## Pendências reais

Refino global não concluído. Faltam rodadas focadas e provas de front autenticado,
LP/spec/render, hierarquia/retomada/reconciliação, capabilities Meta e grão financeiro.
O harness não executou geração de imagem, mutação Meta, migration ou teste no banco.
Nenhuma campanha ativada, nenhum token ou arquivo de ambiente entregue ao agente.
A reserva do parecer final foi acrescentada após as execuções e tem teste local,
não uma quarta execução paga. A ampliação de leitura de nomes sensíveis foi recusada
pela revisão automática e não aplicada; fontes excluídas continuam a cargo do lead.

Próxima execução deve ter um defeito/critério verificável, contexto reduzido e teto
de chamadas definido. Não repetir o prompt global até gastar toda a cota.
