# Meta ADK — de relatório para patches integrados

Base operacional: `db91a06`, branch `execution/volc-os-operacao-80-20`.
Modelo efetivo: `gemini-3.8-flash`, thinking HIGH. Sem fallback de modelo.

## Resultado entregue

O Gemini produziu dois candidatos em worktrees isoladas. O lead inspecionou os diffs,
integrou os quatro arquivos no ramo operacional e repetiu os testes.

- **Copy:** retry preserva preview válido; aplicar/substituir/descartar ficam desabilitados
  durante a chamada; falha recupera o preview anterior; sucesso troca atomicamente.
  Guardas de conta, Página, conjunto, versão, contexto, demo e cinco opções preservadas.
- **Editor flexível:** adicionar foca o novo campo (inclusive quinta opção); remover
  foca próximo/anterior ou Adicionar descrição. Refs locais isolam instâncias; disabled
  impede mutação; render sem ação local não solicita foco.
- **Lead:** alinhou o teste estático de unidade de retorno à delegação real da rota
  para `MetaCampaignReadView`, mantendo a verificação do rótulo na view e adicionando
  prova de que ambos os ramos demo/real usam essa view. Nenhuma fórmula mudou.

## Harness e prompts

`tools/meta-adk-review/EXECUTION.md`: prompt mestre de implementação.
`tasks.py`: tickets executáveis com evidência, aceite, fontes/hashes, arquivos e teste.
`REFINEMENT-QUEUE.md`: missões das quatro áreas; **não é lista de features já entregues**.
`ticket_workflow.py`: pesquisa → proposta JSON → aplicação/testes pelo host → crítico
→ revisão limitada. Paralelismo entre tickets sem arquivos sobrepostos.

O host executa os testes, sem depender de o modelo decidir chamar a ferramenta certa.
SHA/âncoras são conferidos antes de escrever. JSON incompleto não é aplicado. Não há
acesso do modelo a shell livre, secrets, Meta, banco ou deploy. Integração é do lead.

O caminho antigo de exploração por ferramentas consumia chamadas em leituras. Além
disso, recusava repetir testes após editar, não mostrava testes novos no diff e tinha
um fallback permissivo para caminhos de testes. Essas três falhas foram corrigidas.
Agora o teste do harness exercita também o Workflow ADK real com modelo dublê,
passagem de estado tipado, aplicação e rota final — não apenas a forma do grafo.

## Experimentos e custo observado (esta rodada)

| Execução | Chamadas | Tokens totais | Resultado |
|---|---:|---:|---|
| copy-run | 12 | 209184 | limite, sem patch |
| focus-run | 10 | 198334 | limite, sem patch |
| copy-structured | 2 | 33230 | JSON truncado, sem patch |
| focus-structured | 2 | 28332 | JSON truncado, sem patch; grounding não comprovado |
| copy-final | 2 | 50796 | JSON truncado, sem patch |
| focus-final | 2 | 45676 | JSON truncado, sem patch |
| copy-bounded | 5 | 92550 | candidato, revisão corrigiu helper de teste, 24 testes verdes |
| focus-bounded | 3 | 52756 | candidato, 14 testes verdes |
| **Total** | **38** | **710858** | dois patches revisados/integrados |

Os dois ciclos produtivos consumiram 8 chamadas/145306 tokens. O total acima inclui
as tentativas malsucedidas, não apenas as que funcionaram. Valor monetário não foi
retornado pela API; `cost_usd=null`, sem estimativa inventada. Relatórios detalhados
em `/private/tmp/volc-meta-ticket-{copy,focus}-{run,structured,final,bounded}/`.

Descoberta: com HIGH, o raciocínio consumiu quase todo o allowance de 16000/32768 e
o JSON terminou em `MAX_TOKENS`. A versão funcional usa saída máxima 65536 e patches
compactos, com teto total entre respostas e até duas rodadas (normalmente cinco
chamadas por ticket). Uma resposta em voo pode ultrapassar o teto de tokens.
Os dois candidatos finais comprovaram modelo exato e grounding real.

## Provas e limites

- 24 testes do harness, incluindo passagem real de estado ADK com modelo dublê.
- 38 testes dos dois componentes alterados.
- Suíte ampliada Meta: inicialmente 258 aprovados/1 falha estática preexistente;
  o teste da rota antiga foi alinhado à composição real, sem esconder rótulo incorreto.
  Nova execução completa: **260/260 testes aprovados em 29 arquivos**.
- Build de produção aprovado; avisos de bundle grande, Browserslist e CSS existentes.
- TypeScript global continua com erros fora dos componentes alterados; não é gate verde.
- Nenhum novo teste visual autenticado; foco comprovado em jsdom, não em browser real.
- Zero escritas Meta, banco, deploy, criação de anúncios ou ativações nesta rodada.
- Rascunhos, aprovação final e regra PAUSED não foram alterados.

P11-T23 representa a entrega local; P11-T21 permanece **partial**: revisão global
de API/publicação, mensuração, integrações e QA autenticado ainda não foi encerrada.
O harness não continua consumindo chamadas em background depois desta rodada.

Referências técnicas usadas na construção do harness:

- https://adk.dev/workflows/graph-routes/
- https://github.com/google/adk-python/blob/main/docs/guides/workflow/function_node/index.md
- https://ai.google.dev/gemini-api/docs/google-search
- https://ai.google.dev/gemini-api/docs/thinking
