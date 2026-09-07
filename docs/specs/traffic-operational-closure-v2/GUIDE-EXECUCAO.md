# Fechamento operacional de tráfego — guia do executor

Spec pronto para implementação por marcos. Produto ainda não certificado para operação completa. Base inspecionada: `d54e10012c34aeaae2e2089945178bc20353e145`, em 07/09/2026.

## Comece por aqui

Abra **um terminal executor**, na worktree `/private/tmp/volc-os-operacao-80-20`, branch `execution/volc-os-operacao-80-20`. Não usar o checkout principal sujo nem criar outra versão escondida. Ler `AGENTS.md` antes de atuar e conferir HEAD/status. Se houver avanço, fazer diff e adjudicar o que já foi resolvido; nunca voltar a base com reset.

Primeiro lote: **T00, T01, T02, T03, T04, parte local de T10 e T11**. O objetivo é deixar o nascimento Meta estático recuperável e preparável para uma janela real. Fechar CP1; não tentar terminar todas as receitas da API no mesmo lote.

Este pacote não autoriza código nem chamadas externas. Antes de executar, o operador escolhe o marco e usa a autorização correspondente em [CHECKPOINTS.json](CHECKPOINTS.json). As autorizações antigas de push/canário não são permissões novas.

## O que mudou nesta análise

Não estamos começando engines do zero. Foram preservados o lote estático Meta, o orçamento compartilhado desligado, a proteção de duplicidade, os recibos, o gate por canal e a prova tipada de PMax.

Os problemas que justificam trabalho novo estão em [FINDINGS.json](FINDINGS.json):

- Gate técnico Meta aceita bytes que não são imagem; a reprodução usou `NOT_AN_IMAGE`, sem rede.
- Recuperação recompila ativos atuais e depende de declaração que expira; `IN_FLIGHT` órfão não entra no caminho normal de reconciliação.
- Aprovação/execução não têm navegação durável adequada após reload, e respostas assíncronas não usam a mesma proteção em todos os atos.
- Telas de campanha/conjunto/anúncio Meta ainda usam demonstrações; persistir snapshot não as liga automaticamente.
- Alguns endpoints ignoram filtro de conta; Insights coletados são account/hoje, e LPV soma ViewContent indevidamente.
- A memória humana ainda contém afirmações Google superadas, apesar do digest do grafo estar fresco.

São 23 achados/lacunas, não 23 bugs remotamente comprovados. Status e limitações estão por item. Quatro probes herméticos constam em [PROBES.md](PROBES.md). Não houve chamada de conta, inspeção de Supabase oficial ou validação visual autenticada nesta rodada.

## Arquivos e ordem de leitura

| Arquivo | Uso |
| --- | --- |
| [MASTER-SPEC.json](MASTER-SPEC.json) | Decisões, invariantes e contratos de destino, recovery, mídia, dados e UI. |
| [EXECUTION-PLAN.json](EXECUTION-PLAN.json) | 21 tarefas com dependências, paths, passos, contraprovas, aceite e rollback. |
| [FIELD-CONTRACTS.json](FIELD-CONTRACTS.json) | 22 campos atuais Meta + 11 da variação, campos fixos e grupos Google. |
| [GOOGLE-FIELD-INVENTORY.json](GOOGLE-FIELD-INVENTORY.json) | 14 modelos/109 declarações de campos Google extraídos por AST, com tipos, defaults e herança. Não prova binding da UI. |
| [CHECKPOINTS.json](CHECKPOINTS.json) | Gates locais/reais, critérios de parada e modelos de autorização. |
| [FINDINGS.json](FINDINGS.json) | Evidência do HEAD e gravidade, incluindo o que precisa de prova externa. |
| [API-EVIDENCE.json](API-EVIDENCE.json) | Fontes oficiais e dúvidas que a leitura do SDK não resolve. |
| [CURATION-HANDOFF.json](CURATION-HANDOFF.json) | Delta proposto, não aplicado, para Roadmap e memória. |
| [VERIFICATION.json](VERIFICATION.json) | Verificações documentais efetivamente executadas nesta rodada. |

Ler o pacote mestre e os achados do lote escolhido; depois só os paths e evidências relevantes. Não reler indiscriminadamente todos os megarelatórios anteriores.

## Sequência de entregas

1. **R0 — candidato Meta recuperável.** Campos fechados, bytes válidos, snapshot/ledger recuperável e recibo reabrível. Tudo local; provas de conta ainda pendentes.
2. **R1 — canário Meta completo PAUSED.** Schema de perfil exato, leitura/roots atuais e autorização de uma execução. Campaign + AdSet + Creative + Ad conferidos.
3. **R2 — operar o sistema.** Sync e métricas corretos, listas/detalhes reais na mesma base Google, gestão governada e perfil local/remoto claramente separados.
4. **R3 — ampliar Meta.** Estúdio, vídeo/thumbnail, flexível, custom conversions/CAPI e receitas Advantage+ por prova específica. Não bloqueiam R1.
5. **R4 — Google multicanal.** Delta de executor e mídia/mensuração; canários Display, Demand Gen e PMax, nessa ordem.
6. **R5/T20 — fechar o marco efetivamente escolhido.** Capabilities e memória com evidências; nenhuma declaração de tudo pronto se outros marcos faltam.

T05–T09 podem começar depois de R0 enquanto se aguarda autorização de conta. Isso não exige abrir vários escritores nem fazer o canário esperar o dashboard financeiro. T11 usa perfis de schema: CREATE_ONLY não aplica migrations de sync que não sejam dependência.

## Contratos que não podem ser relaxados

- Expiração fecha novo despacho, não apaga histórico nem impede leitura de objetos existentes.
- Antes do POST, persistir identidade/claim; após resposta, persistir ID antes do read-back. Snapshot congelado não contém token.
- Lease expirada ou listagem vazia não prova inexistência. Despacho ambíguo não recebe botão de reenviar.
- Campo inesperado recebido deve ser recusado. Não mostrar uma escolha que o DTO descarta.
- P0 Meta continua Facebook-only/LPV/ADSET budget; Creative não usa `PAUSED`. Vídeo/flexível/Sales/Leads são outras receitas.
- URL de destino é a LP autorizada, não apenas o domínio. PMax precisa controlar também fontes alternativas de destino.
- `NULL` não é zero. ViewContent não é LPV. ROAS da plataforma não é o percentual histórico de excedente.
- Demo precisa de entrada explícita; nenhuma falha real pode trocar dados por demonstração.
- Read-back de existência e permissão de ativar são perguntas distintas.

## Interface: mesma casa, dados distintos

Preservar a base de blocos em `/settings/campaigns` e o dashboard financeiro Google, adaptando tags, hierarquia e campos Meta. No inventário `/trafego`, conta tem cabeçalho forte e disclosure acessível; campanhas ficam na tabela/lista operacional. Não generalizar uma decisão visual para todas as rotas.

Uma ação dominante por contexto, campos fixos legíveis sem toggle, nomes/URLs longos quebrando corretamente e contrato técnico sob disclosure. Toda peça selecionada precisa de preview correspondente, inclusive vídeo/poster quando a receita estiver disponível.

Inspecionar sessão real do operador em 390px e 1440px, claro/escuro. Não pedir senha/token em chat, não inventar autenticação, não afirmar pixels validados por jsdom ou HTTP 200 da SPA. Se não houver browser/sessão, reportar isso no checkpoint, mantendo o restante pronto.

## Provas oficiais: o que sabemos e o que não sabemos

O [SDK Meta AdCreative 26.0.0](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/26.0.0/facebook_business/adobjects/adcreative.py) não lista `effective_status` na máscara gerada. Isso justifica revisar o pedido atual; não comprova, sozinho, uma rejeição Graph na conta. T01/CP3 fecham a diferença.

O [schema de destino Meta](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/26.0.0/facebook_business/adobjects/adcreativedestinationspec.py) não explica a semântica de Shop/website-only. Não inventar `destination_spec` para passar. T10 pode também corrigir uma premissa indevida do gate, desde que a fonte sustente.

O [guia oficial PMax](https://developers.google.com/google-ads/api/performance-max/optimizations) confirma o controle de expansão via automação nas versões atuais. Isso não substitui inventariar outros destinos clicáveis nem read-back da campanha específica.

## Checkpoints sem looping

Executar contraprovas focais por mudança; uma rodada de testes/build de integração por marco material. Fazer revisão concentrada em autorização, dinheiro, concorrência, identidade e dados, seguida de uma rodada corretiva. Achado P0 real não é dispensado pelo 80/20, mas também não manda reabrir toda a arquitetura.

Para baseline, comparar nomes/assinaturas de falhas e paths. Números herdados de relatórios não são um gate atual. Documentação pura usa validação JSON/refs/diff/scanner, não uma repetição de toda suíte.

Quando depender de autorização externa, entregar o candidato local e pedir o próximo ato mínimo. Não ficar horas 'provando' com mocks o que apenas a conta pode responder.

## Texto de abertura sugerido

> Execute o marco R0 do pacote `docs/specs/traffic-operational-closure-v2/`, após conferir a autorização local separada do operador. Base inspecionada `d54e10012c34aeaae2e2089945178bc20353e145`, branch `execution/volc-os-operacao-80-20`, worktree operacional única. Leia AGENTS, MASTER-SPEC, FINDINGS e as tarefas T00/T01/T02/T03/T04/T10/T11. Adjudique no HEAD atual, preserve correções existentes e implemente apenas o delta local autorizado. Um writer; revisores, se autorizados, read-only. Não faça push, conta Meta/Google, Supabase oficial, migration oficial, deploy, geração/upload real, criação/ativação, n8n ou WordPress. Termine CP1 com testes focais, recovery/SQL local e recibo navegável, e prepare CP2/CP3 sem executá-los. Não abra nova arquitetura nem substitua capacidades fechadas por defaults permissivos. Reporte SHA testado, arquivos, gates, URLs reais do ambiente e o próximo ato mínimo autorizado. O spec não é licença para passar aos marcos seguintes.

## Handoff esperado do executor

Entregar um recibo JSON com `selected_release`, `code_tested_sha`, `tasks` (estado/evidências), `gates` (comando/resultado), `capabilities` (local/prova real/autorização), `external_effects`, `remaining_blockers` e `next_operator_action`.

Para cada bloqueio: causa, path ou resposta sanitizada, se é local/conta/autoridade, e a menor ação que o resolve. Não usar 'infra pendente' para misturar cinco coisas diferentes.

Commits/push só no escopo autorizado. Não alterar upstream nem main. Se houver curadoria autorizada, corrigir a fonte humana uma vez e gerar o grafo; digest fresco não corrige texto falso automaticamente. Não apagar branches históricas para chamar o sistema de unificado.

## Limites desta entrega

Esta rodada gerou documentos. Não implementou as tarefas, não abriu credenciais, não alterou runtime/testes/migrations, não reiniciou processos, não fez push e não verificou o schema oficial. Os arquivos novos precisam de commit/publicação documental futura se forem consumidos por outro computador; no mesmo Mac já estão acessíveis nesta worktree.

Rastreabilidade da skill Ads: manifesto local em `.claude-ads/runs/traffic-operational-closure-v2-20260907/manifest.json` aponta para este pacote, sem duplicar os contratos. Não foi produzido score de conta. As skills orientaram fronteiras de autorização, separação de métricas, controles de banco, congruência visual e o formato executável do handoff.
