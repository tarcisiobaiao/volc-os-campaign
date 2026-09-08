# Campanha Meta: demonstração com a interface canônica

08/09/2026. Rota: `/dashboard/campaign/campanha-descoberta-01?rede=meta&modo=demo`.

O dashboard demonstrativo separado foi substituído por MetaCampaignReadView, o mesmo componente da campanha real. Um provider React limitado à subárvore demonstrativa injeta cinco métodos com fixtures. Não há substituição do singleton global, token, API, persistência nem fallback da leitura real para mock.

Funcionalidades de exemplo: financeiro por conjunto, conferência da soma da campanha, conjuntos expansíveis com anúncios e peças vinculadas, filtro real sobre dias fictícios de 29/08 a 04/09/2026, propostas de pausa/orçamento/lance/duplicação e download JSON marcado como demonstrativo. Propostas não alteram nem os objetos fictícios; representam a mesma etapa de conferência disponível na gestão real. Elas não são aprovações nem planos executáveis. IDs e carimbos da demo são fictícios e identificados como tal.

A inspeção de navegador encontrou uma falha compartilhada: a lista mobile não tinha expansão, apesar de a tabela desktop ter. Corrigida no componente ConjuntosFinanceiros, incluindo CTR/CPC na lista mobile. O grupo de selos de conta também passou a respeitar a largura disponível. As duas correções valem para a tela real.

Verificação: 61 testes em cinco arquivos focais passaram (roteamento, isolamento da demo, propostas, financeiro, somas exatas, período e expansão mobile). TypeScript medido após o adaptador: 76 erros globais, sem erro nos arquivos alterados. Build passou; ajustes finais de expansão mobile, espaçamento e largura são posteriores a esse build e cobertos pelos testes/browser. Browser com a mesma vista e provider, isolados do shell autenticado: 375/1440, sem overflow, sem erros de página, zero chamadas de API; download meta-demo-proposta-ficticia.json confirmado. Não se afirma QA autenticado das contas reais.

Nenhum objeto Meta criado/editado/ativado, nenhuma geração, migration, Supabase oficial, n8n ou push. Sem nova branch/worktree. Os commits concorrentes 25df7f6 e 969b69c do terminal de criativos incluíram arquivos desta lane; sua história foi preservada. Entradas temporárias de browser incluídas por esse commit concorrente foram removidas no fechamento, sem reescrever histórico.

P11-T06 continua partial: a demo não prova dados oficiais nem execução de gestão. Nó operacional cap_meta_ads registra paridade visual, não prontidão de produção.
