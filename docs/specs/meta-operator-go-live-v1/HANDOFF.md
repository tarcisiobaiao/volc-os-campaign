# Meta Operator Go Live — pacote executor

Base de código inspecionada: `4c2d17a215a13c7202c99bf89b65ef92926e9300`.
Branch única: `execution/volc-os-operacao-80-20`.
Worktree: `/private/tmp/volc-os-operacao-80-20`.
Data: 07/09/2026.

## Veredito

SPEC_READY_FOR_SCOPED_EXECUTION. Este pacote não implementou runtime, aplicou schema ou publicou workflow. Não certifica operação completa nem “100% da API”.

O criador atual é **ABO**, com orçamento no conjunto. A percepção de CBO decorre de falta de clareza/seleção na UI, não do payload atual. Públicos configuráveis e otimização por custom conversion ainda não percorrem o contrato; arquivos/ZIP também não entram pelo criador.

## Entregas previstas

13 tarefas, 40 bindings de campos e 46 critérios de aceite. O pacote inclui orçamento ABO/CBO/multi-conjuntos, público/localização/Advantage+, conversões existentes, arquivos/ZIP e registro de mídia, schema oficial Meta e reporting n8n/GAM.

A ordem está em EXECUTION-PLAN.json. FIELD-BINDINGS.json obriga a ligar cada escolha à API, ao hash e à leitura de retorno; não é um checklist de widgets.

O escopo exclui envio CAPI, criação de público/customer list/custom conversion, ativação de campanhas e agenda automática. Importar arquivo, registrar mídia na conta, validar plano e criar campanha são quatro atos diferentes.

## Achados determinantes

- Custom conversion sem flags pode hoje parecer disponível: corrigir tri-state e validar fonte/conta.
- Importação precisa respeitar master→job→owner e tipos de projeto distintos; não inventar um job de geração. O manifest anterior exige adjudicação de origem importada.
- O gerador n8n usa tipo de credencial fictício. Trocar só o nome do workflow não resolve.
- A API n8n respondeu à leitura paginada completa: 396 workflows. Há coletores GAM oficiais ativos. Não recriar/duplicar a coleta de receita.
- Catálogo oficial Supabase e escrita n8n não foram exercitados nesta rodada. Permissão de leitura da API não prova permissão de criar workflow.
- SDK oficial main sustenta presença de campos, não todas combinações v26. Algumas páginas Meta retornaram 429/erro; a elegibilidade dessas combinações continua exigindo prova específica.
- Não houve inspeção visual autenticada nesta rodada; conclusões de UI são de código.

## Como executar

Cole EXECUTOR-PROMPT.md em um terminal novo na worktree operacional. Ele referencia os JSONs, permissões e checkpoints. Não abra nova worktree. Commits posteriores exclusivamente documentais são esperados; confirme ancestralidade em vez de voltar ao SHA da base.

O operador já pediu tabelas Meta no Supabase e flows n8n para validar. O executor pode cumprir esse escopo exato após catálogo/prova/backup, sem pedir novamente uma autorização genérica. Descoberta de destruição de dados necessária exige pausa localizada. Upload Meta e teste manual permanecem atos explícitos com conta/arquivos/janela escolhidos; criação de campanha requer autorização distinta.

Se uma credencial falta, o trabalho local independente continua. Workflows publicados ficam INATIVOS mesmo depois de teste manual.

## Provas e memória

EVIDENCE.json separa código, histórico, documentação e leitura remota. ACCEPTANCE-CHECKLIST.json separa schema operacional, criador ligado, mídia provada, relatórios manuais e preparação de canário.

CURATION-HANDOFF.json identifica P11-T02/T03/T04/T05/T06 e P10-T16, sem promoção. O executor registra provas reais antes de atualizar seus estados. O graph --check estava current por digest na base; não confundir commit documental novo com código stale.

Nenhum token, lista de pessoas, ID bruto de conta, dados de mídia do usuário ou resposta bruta n8n foi incluído no pacote.
