# Roadmap mestre — VOLC O.S.

**Atualizado em:** 24/08/2026\
**Objetivo:** fechar um ciclo operacional confiável de **pauta → funil → campanha → resultado → decisão**, sem depender de memória humana para descobrir falhas.

Este documento organiza a execução. Os detalhes técnicos continuam nas especificações existentes:

- [PRD de arbitragem](./PRD-ARBITRAGEM.md)
- [Hub de Tráfego](./SPEC-HUB-DE-TRAFEGO.md)
- [Página do Redator](./SPEC-PAGINA-REDATOR.md)
- [Smart Bidding](./SMART-BIDDING-2026-08-17.md)
- [Handoff de Tráfego](./HANDOFF-CODEX-20260820.md)
- **[Tráfego — porta de entrada](./TRAFEGO.md)** e o [ledger de evidências](./EVIDENCIAS-TRAFEGO.md) *(pacote em proposta em revisão, 24/08/2026)*

## Leitura rápida do estado atual

| Frente | Estado observado | O que falta para considerar fechada |
|---|---|---|
| Base do produto | Existe e reúne projetos, campanhas, relatórios e configurações | Empacotar o trabalho atual em um estado recuperável e repetir a prova integrada |
| Pautador | Motor, rotas, telas e migrações existem; correções recentes estão registradas nos relatórios de auditoria | Congelar uma versão aceita e validar a saída que alimentará o Redator |
| Redator | Matriz, rotas, telas e migrações estão parcialmente construídas | Corrigir a identidade das URLs, provar com fixture de produção e fechar a regra de publicação |
| Tráfego | A criação de campanha pausada no Google Ads já foi provada. **Medido em 24/08: existem duas campanhas na conta e o produto conhece uma** ([E-01](./EVIDENCIAS-TRAFEGO.md#e-01), [E-02](./EVIDENCIAS-TRAFEGO.md#e-02)) | Inventário reconciliado, identidade interna, prevenção de duplicidade e persistência confiável — ver [porta de Tráfego](./TRAFEGO.md) |
| Notificações | O sino global e o primeiro alerta de entrega foram implementados e vistos funcionando | Transformar alertas isolados em saúde sistêmica. **Escopo revisado:** o P0 entrega evento operacional; Ocorrência/Incidente são do P1 ([ADR-14](./ADR-TRAFEGO.md)) |
| Dados de mídia | Há leitura e operação de Google Ads | Ingestão própria e reconciliável de custos, termos de pesquisa e dados de afiliados |
| Governança de escrita | Existem travas locais no fluxo de tráfego | Criar propostas, autorizações, execuções, política única e um único portão de mutação |
| Automação | Ainda não é uma base segura para operação autônoma | Depende de observabilidade, dados próprios, governança e laço de conversão concluídos |
| Segurança operacional | Há pendências de credenciais e componentes antigos | Desligar legados confirmados e rotacionar os segredos registrados no handoff |

## Ordem de execução

### R0 — Tornar o trabalho atual recuperável

Esta é a prioridade imediata. O repositório contém várias frentes misturadas e componentes centrais ainda não rastreados pelo Git.

Entregas:

- inventariar alterações por módulo: base, Pautador, Redator, Tráfego, segurança, documentação e banco;
- separar checkpoints recuperáveis sem apagar ou sobrescrever trabalho existente;
- registrar a prova atual de frontend, backend e fluxo integrado;
- identificar migrações que apenas existem no código e as que foram realmente aplicadas;
- atualizar o handoff com o estado do sino e das notificações.

Pronto quando:

- nenhum módulo central depender de arquivo não rastreado e sem cópia recuperável;
- as mudanças estiverem agrupadas de forma revisável;
- testes executados, falhas herdadas e limitações externas estiverem registrados com seus comandos e resultados.

### R1 — Segurança e desligamento do legado

Executar a fase F0 do [PRD de arbitragem](./PRD-ARBITRAGEM.md).

Entregas:

- confirmar quais fluxos, webhooks e chamadores antigos ainda estão ativos;
- desligar somente os componentes comprovadamente obsoletos;
- rotacionar as credenciais expostas registradas no handoff;
- procurar dependências ocultas antes de cada desligamento;
- registrar dono, substituto e evidência de desativação.

Pronto quando:

- não houver produtor fantasma conhecido;
- cada credencial pendente tiver sido substituída e invalidada;
- o sistema novo não depender dos componentes desligados.

### R2 — Fazer o sistema saber se está vivo

Executar a fase F1 do [PRD de arbitragem](./PRD-ARBITRAGEM.md). O sino atual será um consumidor dessa fundação, não a fundação em si.

Entregas:

- catálogo de fontes monitoradas;
- recibos de ingestão e heartbeats;
- alertas persistidos, com deduplicação e resolução;
- watchdog interno;
- vigilância externa independente;
- tela de Saúde;
- rotina de câmbio com prova de execução.

Pronto quando:

- uma fonte interrompida gera alerta sem depender da interface aberta;
- a ausência de execução também é detectada;
- o operador vê o incidente, a última evidência recebida e o estado de resolução.

### R3 — Fechar o caminho produtivo já iniciado

Consolidar Pautador, Redator e Tráfego como um único produto operacional.

Entregas:

- congelar o contrato de saída do Pautador;
- executar a fixture real do Redator e registrar os resultados;
- substituir inferências pelo nome da campanha pelo vínculo com `funnel_run_id`;
- centralizar a identidade de URL e eliminar a divergência entre `/rec/` e `/r/`;
- exigir páginas publicadas antes da criação de campanha;
- decidir e implementar o fluxo controlado de rascunho para publicação;
- persistir campanha, execução e URLs de forma transacional;
- configurar preços reais dos modelos usando a cobrança do usuário, sem estimativas inventadas.

Pronto quando:

- uma pauta aprovada percorre o Redator e chega a uma campanha pausada;
- cada artefato é rastreável até o mesmo run;
- uma falha intermediária não deixa estado falso de sucesso;
- o fluxo pode ser repetido em ambiente controlado.

### R4 — Construir a verdade própria dos dados

Executar a fase F2 do [PRD de arbitragem](./PRD-ARBITRAGEM.md).

Entregas:

- ingestão própria de custo e desempenho do Google Ads;
- ingestão do backend de afiliados;
- termos de pesquisa;
- recibos por fonte e janela;
- reconciliação entre origem, banco e interface;
- tratamento explícito de atraso, ausência e reprocessamento.

Pronto quando:

- cada valor exibido informa origem e janela de medição;
- uma reexecução idempotente não duplica dados;
- divergências ficam visíveis em vez de serem silenciosamente aceitas.

### R5 — Governar qualquer escrita externa

Executar a fase F3 e concluir a parte estrutural da F4 do [PRD de arbitragem](./PRD-ARBITRAGEM.md).

Entregas:

- propostas persistidas;
- autorizações com escopo e validade;
- execuções auditáveis;
- política única de decisão;
- executor único para mutações;
- criação completa da campanha, inicialmente pausada;
- ação de conversão e tabela de estratégia de lance.

Pronto quando:

- nenhum módulo escreve diretamente em uma plataforma externa;
- toda mutação aponta para uma autorização válida;
- a execução pode ser auditada e, quando possível, revertida;
- ativar campanha continua sendo uma decisão explícita do dono.

### R6 — Fechar o laço de conversão

Executar a fase F5 do [PRD de arbitragem](./PRD-ARBITRAGEM.md).

Entregas:

- sensor próprio;
- eventos de hospedagem e visualização de anúncio;
- fila de conversões;
- identidade e deduplicação;
- envio de conversões somente após autorização permanente específica;
- reconciliação entre clique, evento, conversão e receita.

Pronto quando:

- o sistema consegue explicar o caminho completo de uma conversão;
- falhas de envio podem ser retomadas sem duplicação;
- receita e mídia podem ser comparadas na mesma identidade operacional.

### R7 — Automatizar somente o que já é observável e governado

Executar, nessa ordem, as fases F6, F7 e F8 do [PRD de arbitragem](./PRD-ARBITRAGEM.md).

Entregas:

- motor de otimização próprio em replay e shadow mode;
- defesa pré-autorizada apenas para redução de risco, com kill switch;
- telas operacionais de portfólio;
- previsões persistidas somente onde houver dados observados suficientes.

Pronto quando:

- cada recomendação mostra evidência, regra e impacto medido;
- a automação defensiva respeita limites autorizados;
- previsão nunca atua como executor;
- o operador consegue interromper a automação de forma independente.

## Decisões do dono

Estas decisões não devem ser escondidas dentro de tarefas técnicas:

- autorizar uma janela acompanhada para rotação das credenciais pendentes;
- definir se o Redator pode publicar páginas individualmente, sempre com confirmação;
- fornecer os preços reais de entrada e saída dos modelos usados;
- autorizar separadamente qualquer execução que consuma modelo pago ou publique no WordPress;
- decidir se a campanha de FGTS será ativada;
- autorizar, no momento da ação, qualquer alteração na campanha ativa de Maquininha;
- conceder autorização permanente específica antes de qualquer envio de conversão ao Google Ads.

As duas decisões de campanha são operacionais e não devem bloquear a construção da fundação do sistema.

## Estacionamento — não abrir agora

- experimento de ponderação da variedade de copy por palavras-chave de maior volume;
- automações ofensivas de orçamento ou lance;
- previsão financeira antes de haver histórico próprio confiável;
- novas telas que apenas reorganizem dados ainda não reconciliados;
- novas integrações antes de recibos, heartbeat e portão único de mutação.

## Próximo bloco de trabalho recomendado

1. Concluir R0 e produzir um mapa recuperável das mudanças atuais.
2. Transformar R1 em checklist operacional com evidências e responsáveis.
3. Implementar R2 antes de ampliar as automações.
4. Retomar o caminho Pautador → Redator → Tráfego em R3 já sobre a base observável.

Essa ordem preserva o que já foi construído, reduz o risco operacional e evita que novas funcionalidades aumentem uma base que ainda não consegue detectar sozinha quando parou.
