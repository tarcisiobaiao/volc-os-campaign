# Missão executora — Meta Operator Go Live v1

Você é o executor principal, em Claude, com um único writer na linha operacional. Sua tarefa é IMPLEMENTAR este pacote, não produzir outro diagnóstico amplo. Avance por entregas utilizáveis no localhost:8080, com provas proporcionais. Não prometa ausência absoluta de bugs nem declare produção por testes locais.

## 1. Linha operacional e preflight

- Worktree: /private/tmp/volc-os-operacao-80-20
- Branch: execution/volc-os-operacao-80-20
- Base de código inspecionada: 4c2d17a215a13c7202c99bf89b65ef92926e9300
- Pacote: docs/specs/meta-operator-go-live-v1/
- Não criar branch/worktree paralela, não usar o checkout principal, não alterar origin/upstream.
- Leia AGENTS.md. Confirme branch, HEAD, status e ancestralidade da base.
- Um commit documental posterior à base é esperado. Confira seu diff, não tente voltar o HEAD.
- Se houver alterações alheias, preserve-as. Pare somente o trecho sobreposto; não use reset/stash/rebase/amend/merge/force.
- Não mate processos por porta às cegas. Identifique PID/cwd de frontend, Node e Python. Mantenha 8080 e sessão do operador; antes de configuração/startup rode scripts/verificar_autoridade_supabase.py.
- Consulte graphify conforme AGENTS. Grafo serve à navegação; confronte estado com código, curadoria e provas. Não recomece auditoria global.

## 2. Leia o contrato completo antes de editar

Nesta pasta, leia integralmente:
1. HANDOFF.md
2. RUN-MANIFEST.json
3. SPEC.json
4. FIELD-BINDINGS.json
5. EXECUTION-PLAN.json
6. ACCEPTANCE-CHECKLIST.json
7. EVIDENCE.json
8. CURATION-HANDOFF.json

Autoridades complementares, conforme tarefa:
- docs/closure/meta-gam-final-local-v1/HANDOFF.md
- docs/closure/traffic-operational-closure-v2/SCHEMA-DEPLOY-MANIFEST.json
- docs/specs/meta-creative-p0-reconciliation-v1/MASTER-P0-CONTRACT.json
- docs/specs/creative-supply-chain-v1/ASSET-SUPPLY-MANIFEST.schema.json
- docs/closure/hermes-meta-v26-ground-truth-v1/META-CREATIVE-ZIP-CONTRACT.json
- docs/specs/meta-completion-v1/OBJECTIVE-MEASUREMENT-MATRIX.json
- docs/refs/meta-webgo-20260907/COMPARISON.json

Código/runtime e evidência nova prevalecem sobre afirmação histórica incorreta, mas registre a adjudicação. Não misture silenciosamente dois schemas de manifest.

Use as skills instaladas de ads, Supabase/Postgres e interface (impeccable, contexto de produto), e as de n8n pertinentes. Antes de ferramenta n8n leia n8n-mcp-tools-expert; ao configurar nodes, expressões e Code leia suas skills correspondentes. Preserve PRODUCT.md/design.md, login, branding e componentes VOLC; não invente outro design system.

## 3. O que estamos efetivamente corrigindo

A base NÃO é CBO: é ABO, orçamento no AdSet, Traffic/LPV, um conjunto, Facebook-only. Esta limitação precisa evoluir de verdade.

Entregue:
- ABO/CBO, diário/total e programação elegíveis, múltiplos conjuntos com identidade estável e Ads corretamente associados.
- Público por conjunto: amplo/manual, personalizados/semelhantes EXISTENTES, geografia e exclusões, raio quando elegível, idade/idiomas permitidos; controles versus sugestões Advantage+ explícitos.
- Pixel/dataset, evento e custom conversion EXISTENTE: distinguir seleção de reporte de otimização. Corrigir UNKNOWN que hoje pode parecer disponível.
- Biblioteca Meta + Estúdio + importação individual/ZIP, com thumbnail/player, ownership, bytes/hash, política e registro por conta.
- Schemas Meta e dependências de importação realmente aplicados no Supabase oficial dentro do escopo abaixo.
- Workflows Meta realmente criados INATIVOS na instância n8n, credenciais suportadas, uma prova manual delimitada e financeiro GAM ligado.
- Recompilar e validar por clique o plano atual com tracking; entregar ficha para autorização do primeiro canário.

Um botão ou seletor sem DTO/resolver/payload/hash/read-back não fecha uma task. Um estado BLOCKED honesto não significa que a feature está entregue; registre a lacuna concreta.

## 4. Autoridade e efeitos externos

Esta missão admite implementação local, testes, documentos e migrations candidatas; consulta/aplicação do schema Meta oficial delimitado, storage privado necessário e criação dos workflows novos INATIVOS, conforme pedido do operador.

Supabase operacional único: https://database.agenciavolc.com.br.
- Confira destino, catálogo, histórico, assinaturas/ACL/RLS e checksums; backup restrito; aplique apenas migrations exatas dos perfis Meta e novas dependências mínimas de importação após prova descartável.
- Banco parcial não autoriza DROP/reapply. Não enviar arquivos com metacomandos psql como SQL API bruto.
- Não aplicar GOOGLE_PMAX nem migration alheia por conveniência. Não executar rollback destrutivo depois de dados reais.

Meta:
- Catálogos reais e teste manual: conta escolhida pelo operador; não scan indiscriminado.
- validate_only somente após clique explícito, do hash atual.
- Upload de mídia é efeito externo diferente de validação. Só após confirmação que lista conta/arquivos/efeito, por botão dedicado; importar ZIP local não chama Meta.
- Não criar Campaign/AdSet/Ad nesta missão, nem PAUSED. Não ativar, não editar campanha existente, não criar públicos/listas/custom conversions, não enviar CAPI.

n8n:
- Criar flows delimitados INATIVOS e confirmar por leitura da API. Não sobrescrever workflows por nome semelhante.
- Uma conta/janela deve ser confirmada para sincronização manual; persistência correspondente deve usar RPC canônica.
- Não ativar agenda, backfill amplo ou flows GAM. Não copiar token do Mac para n8n sem ato seguro explícito.
- Credencial ausente: pedir provisionamento pelo operador na UI segura, nunca token no chat. Continue tasks locais não dependentes.

Zero push/deploy/merge/publicação WordPress/n8n schedule activation. Commits locais lineares são permitidos; transporte será autorizado depois.

## 5. Execução prática

Siga T01–T13 e CP0–CP6. Dependência de prova remota não deve bloquear implementação local independente. Não execute sete rodadas de planejamento.

1. Confira schema existente e feche o perfil Meta; prepare extensão de importação sem catálogo paralelo.
2. Versione o contrato do criador e as receitas; orçamento, público e mensuração precisam ser coerentes em todo o caminho.
3. Ligue importação/preview/registro de mídia. Preserve master→job→owner; arquivo importado não é geração VOLC fictícia.
4. Integre a interface existente, com hierarquia e disclosure; detalhe técnico fora do caminho principal, preview real e ações claras.
5. Resolva o gerador n8n e crie flows inativos. Confirme bootstrap de objetos e D-1 pelo fuso da conta.
6. Faça prova manual delimitada, read-back e cards no mesmo período. Prepare validação atual e ficha de canário; não o crie.
7. Feche bindings, testes, memória operacional e relatório.

Fatos que não devem se perder:
- n8n/gerar_flows_meta_ledger.py tem metaGraphApiNaoProvisionada e REPLACE_ME; passar teste local não provisiona credencial.
- Leitura n8n desta spec percorreu 396 workflows/4 páginas. Já existem coletores GAM oficiais ATIVOS; não criar um segundo coletor da mesma receita.
- Receita financeira Meta vem do GAM com utm_campaign_value=campaign_id, rede/projeto/conta GAM/moeda/fuso. Meta purchase value não substitui receita.
- Tracking atual: utm_source=meta&utm_medium=paid_social&utm_campaign={{campaign.id}}&campaign_id={{campaign.id}}. Roots não prova expansão das macros nem receita.
- Público custom/semelhante existente não implica permissão de criar público nem de enviar PII.
- Disponibilidade de campo no SDK main não prova combinação v26. Consulte docs oficiais da versão e marque a prova de conta necessária; nunca invente enum/default.
- Vídeo, flexible/dynamic creative e lote de Ads são capacidades diferentes. ZIP não é asset_feed_spec.
- Leitura incompleta/estado desconhecido não autoriza entrega nem vira zero.

## 6. Verificação sem looping

- Rode testes focais reais por área alterada; não suite vazia, nenhum HTTP externo em teste hermético.
- SQL: apply→uso→idempotência/isolamento→rollback→reapply em Postgres descartável; depois catálogo/read-back oficial delimitados.
- Build e TSC por diferença com baseline medida. Não “corrigir” contagem removendo testes.
- Prove UI com browser autenticado em desktop e mobile. Se a ferramenta não conecta, peça ao operador login/captura; não alegue pixel QA por jsdom.
- Uma revisão focal de riscos: autoridade de escrita, cross-account, orçamento/público/conversão, ZIP, saga, financeiro e credenciais. Uma rodada corretiva.
- Co-revisor disponível pode ler um diff delimitado; não multiplique writers na mesma árvore nem gere novos specs concorrentes.
- Falha externa isolada tem motivo, evidência e próximo ato; não fica escondida em “pronto”.

## 7. Entrega

Criar docs/closure/meta-operator-go-live-v1/ com:
- HANDOFF.md: SHA/base, mudanças, URLs, estado por marco, provas e bloqueios;
- FIELD-BINDINGS-IMPLEMENTED.json: F01–F40 → arquivo:linha UI/DTO/resolver/compilador/hash/persistência/read-back, ou UI-only justificado;
- CHECKPOINT-RESULTS.json: CPs e A01–A46, tipo de prova, sem PASS por inferência;
- SCHEMA-APPLY-RECEIPT.json: perfil/versão/hash/catálogo/grants, sem credenciais;
- N8N-REMOTE-RECEIPT.json: workflows/revisões/active=false, teste manual sanitizado, sem conteúdo de tokens;
- CANARY-AUTHORIZATION-REQUEST.json: somente ficha, conta opaca/LP/peça/hash/orçamento/contagem/estado PAUSED e prova faltante; nenhuma execução implícita.

Atualize uma vez Roadmap/curadoria apenas com fatos comprovados, execute o wrapper do grafo e --check; não edite grafo gerado à mão.
Não marque P11-T05/P11-T06 done sem seus aceites reais. Relate o que está local, remoto, pendente de conta e pendente de autorização.

Mantenha http://localhost:8080/trafego/meta/nova no mesmo worktree para o operador acompanhar. Termine com árvore organizada, commits locais lineares, nenhum push, e um próximo ato único e concreto.
