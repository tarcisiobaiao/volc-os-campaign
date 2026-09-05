# Handoff — Meta Completion v1

**META_COMPLETION_SPEC_PARTIAL**

Modelo: `gpt-6-astra`, medium, conforme confirmação expressa do usuário. Metadado independente de runtime não foi exposto. Branch documental: `spec/gpt6-meta-completion-v1`. Base: `884393b0e99b5ee403a6f38e1e4225012705f942`. O SHA do commit documental é o HEAD desta branch após o commit; não é incorporado ao próprio conteúdo para evitar autorreferência impossível.

## Leitura recomendada

1. META-COMPLETION-SPEC.json: releases, registro de campos/flags e fronteira Fable.
2. AS-IS-ARCHITECTURE.md e AS-IS-INVENTORY.json: verdade atual e 54 evidências.
3. OPEN-CONTRACT-CONFLICTS.json:16 conflitos, nove bloqueiam P0.
4. EXECUTION-WORKBREAKDOWN.json:29 tarefas com arquivos, dependências, aceite, testes e autoridade.
5. FIRST-PAUSED-CANARY-RUNBOOK.json:20 passos, todos não executados e bloqueados até os gates.

O restante separa fontes oficiais, capacidades, objetivos/mensuração, estados, mutações governadas, dados de Insights, UX, revisão e handoff de curadoria. Foram normalizados os nomes corrompidos do pedido para META-INSIGHTS-DATA-MODEL.json e OPEN-CONTRACT-CONFLICTS.json; OPEN_CONTRACICTS é somente alias registrado.

## Decisões essenciais

- Aprovar, criar, validar, ler, reconciliar e futuramente ativar são atos distintos.
- Preservar ledger antes do POST e ID antes do read-back; só fechar sucesso após prova durável das decisões críticas.
- Timeout ambíguo não autoriza retry. Nome/tempo/120s não provam ausência. Creative pode não ter created_time e ser reutilizado pelo provider.
- Campaign, AdSet e Ad devem estar configurados PAUSED; Creative tem estado de biblioteca, sem enum PAUSED.
- Toda escolha de orçamento/Advantage/placements/destino precisa ser explícita. v26 introduz risco de destino loja por default em criativos elegíveis.
- Actions/action_values, atribuição, moeda, nível, janela e revisões permanecem separados. Não somar ViewContent como LPV nem reutilizar ROAS/FX demo como métrica canônica.
- Fable fornece manifests e ativos; não há redesenho dos engines criativos.

## Cinco primeiras tarefas

P0-01: adjudicar receita v26, destino, identidade e defaults.
P0-02: selar hash e adapter de imagem existente com manifests/content SHA.
P0-03: separar flags, recibo durável e aprovação.
P0-04: corrigir concorrência/recuperação sem duplicação.
P0-05: corrigir e persistir read-back e semântica Creative.

As tarefas podem iniciar por pesquisa e código local em missão futura; a execução remota continua bloqueada. P0 não espera vídeo, flexível, catálogo, Leads, Sales, CAPI completa, ativação ou dashboard avançado.

## Provas e autorizações pendentes

A única validação real existente cobre Campaign/Creative e criou zero objetos. AdSet/Ad, criação PAUSED/read-back dos quatro nós, schema/RPC/RLS oficial, persistência real e métricas positivas comparáveis ainda exigem prova. Novas receitas e CAPI precisam de suas próprias provas.

São necessárias adjudicação independente da Bia, publicação autorizada de SHA corrigido, checkpoint/migration oficial autorizados e autorização exata de canário com conta/Page/ativo/destino/hash/teto/deadline. Ativação, edição, eventos CAPI e conversões administrativas exigem autoridades separadas.

A [v26 foi lançada em29/07/2026](https://developers.facebook.com/docs/graph-api/changelog/version26.0/). Tabelas/defaults oficiais conflitantes estão documentados; nenhum erro de acesso foi tratado como fonte positiva.

## Isolamento

Somente documentos neste diretório. Zero runtime de produto, acesso a token, chamadas Graph/Marketing API, acesso ao Supabase oficial, mutação externa ou push. Houve leitura de páginas públicas de documentação Meta e escrita/commit documental local, que não são chamadas operacionais à API.

Skills utilizadas: ads para disciplina de evidência e restrições de campanha; documentação/Diátaxis para separar referência, arquitetura e runbook; Supabase/Postgres para separar grants, RLS, autoridade do banco e segurança do journal. O escopo do usuário prevaleceu: nenhum teste de produto, banco ou alteração compartilhada.

## Revisão e gates

Uma revisão adversarial documental integral, pelo mesmo modelo, registrou22 achados e25 verificações; não é revisão independente cross-model. Uma única rodada corretiva documental foi aplicada. O scanner de segredos passou; validação estrutural/referências e escopo são conferidos antes do commit. Os hashes da primeira versão congelada constam em ADVERSARIAL-REVIEW.json. Os bloqueios de produto/provider não foram corrigidos por esta missão.
