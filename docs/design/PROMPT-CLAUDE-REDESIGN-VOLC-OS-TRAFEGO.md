# Prompt único — Claude Code — Redesign do VOLC O.S. / Hub de Tráfego

Copie a partir da linha abaixo para uma sessão nova do Claude Code, aberta na raiz do repositório.

---

Você assume uma missão de implementação frontend no VOLC O.S. Não quero apenas uma avaliação, brainstorm, wireframe ou novo plano. Quero que você implemente e valide a nova referência visual do produto, com continuidade até a fatia convergir.

## Objetivo

Redesenhar o Hub de Tráfego e suas superfícies relacionadas para torná-lo um **VOLC Mission Control**: denso, claro, confiável, multicanal e operacional. A tela atual funciona, mas a hierarquia, densidade e linguagem visual ainda parecem um admin genérico e expõem demais a estrutura interna. O resultado deve ser state of the art, reconhecível como VOLC O.S. e utilizável com os dados reais que já existem.

## Antes de agir

1. Leia completamente, nesta ordem:
   - `AGENTS.md`
   - `PRODUCT.md`
   - `DESIGN.md`
   - `docs/design/SPEC-REDESIGN-VOLC-OS-TRAFEGO.md`
   - `docs/design/DESIGN-SYSTEM.md`, apenas para entender a marca de apresentações e não confundi-la com o produto
   - `.impeccable/design.json`
2. Leia completamente as skills disponíveis de:
   - frontend design, incluindo `/Users/mac/Downloads/Bonus 3 - Arsenal de Skills (Pixel) (1)/skills-exclusivas-pixel/frontend-design/SKILL.md`
   - impeccable
   - UX/UI Pro, se instalada
   - taste/design taste, se instalada
   - accessibility
   - mobile responsiveness
3. Consulte o grafo segundo `AGENTS.md` antes de concluir arquitetura, impacto ou capacidades existentes. Use:
   - `graphify-out/UPDATE_STATUS.json`
   - `graphify-out/wiki/index.md`, se existir
   - `.venv-graphify/bin/graphify query`, `explain`, `path` e `affected`
   - `docs/volc-os-graph/curadoria-operacional.json` como verdade operacional humana
4. Registre HEAD, `git status`, mudanças preexistentes e worktrees/sessões concorrentes. Não descarte, sobrescreva ou reorganize trabalho alheio.
5. Confirme que a frente funcional de Tráfego anterior terminou e que você parte de seu HEAD final. Se ainda houver outro escritor atuando nos mesmos arquivos, não inicie edição concorrente: faça apenas a investigação read-only e espere a convergência. O redesenho não pode ressuscitar defeitos funcionais que acabaram de ser corrigidos.

## Modelo de trabalho com agentes

Use subagentes, mas preserve **escritor único por arquivo e por etapa**.

- `investigator`: read-only; inventaria rotas, componentes, contratos, estados reais, screenshots e divergências entre UI e DESIGN.
- `design-architect`: read-only; transforma DESIGN e SPEC em mapa de componentes, hierarquia e critérios de revisão.
- `frontend-implementer`: único escritor funcional da etapa; implementa os arquivos sob ownership declarado.
- `accessibility-responsive-reviewer`: read-only; revisa teclado, foco, semântica, contraste, zoom, mobile e overflow.
- `adversarial-reviewer`: read-only; tenta provar que a interface mente, perde estado, reordena dados, inventa zero, esconde falha ou facilita ação perigosa.
- `gatekeeper`: read-only; executa gates e confere bundle, console, requests e screenshots.

O coordenador integra e pode corrigir achados confirmados. Não permita dois agentes escrevendo na mesma árvore ao mesmo tempo. Cada agente deve separar `[FATO]`, `[INFERÊNCIA]`, `[RISCO]` e `[PROPOSTA]`.

## Autoridades e invariantes que você não pode quebrar

- `DESIGN.md` é a autoridade visual do produto. Não o reescreva para acomodar a implementação atual.
- `docs/design/DESIGN-SYSTEM.md` governa apresentações. Não leve sua aurora de tela inteira, ruído, tipografia teatral ou composição promocional para o workspace.
- O frontend consome os contratos existentes. Não mude backend, API, SQL, migrations ou regras de domínio por conveniência visual.
- A ordem das campanhas vem do servidor. Não crie `sort()` local.
- Histórico removido permanece oculto e sem request até o operador abri-lo.
- `volc_campaign_id` é a identidade canônica. ID externo não abre a página interna.
- Reconciliação ausente bloqueia criação. `correspondencia_provavel` não recebe ação de montar campanha.
- FGTS e Maquininha não podem voltar a parecer candidatas inéditas.
- Número medido, zero medido, ausência, falha e dado antigo são estados diferentes.
- Nenhum número decisório sem frescor.
- Uma falha nova não apaga silenciosamente a última leitura boa.
- O browser não consulta Google Ads no render, não recebe segredo privilegiado e não executa mutação.
- `proxima_acao`, diagnóstico, reconciliação e autoridade de estado não são recalculados no frontend.
- Ações de orçamento, lance, pausa, duplicação, publicação ou gasto explicam consequência e permanecem bloqueadas quando o contrato não as autoriza.
- Use os dados reais. Não injete mock na rota autenticada para a captura ficar bonita.

## Direção visual obrigatória

O norte é `VOLC Mission Control`, não landing page.

- claro como padrão; escuro completo;
- aproximadamente 90% de neutros frios tingidos;
- azul profundo para ação primária;
- cyan para evidência verificada;
- verde para sucesso real;
- laranja para atenção ou pendência;
- vermelho apenas para erro, bloqueio ou risco verdadeiro;
- aurora VOLC somente na borda do shell, identidade ou ativação contida;
- Space Grotesk para títulos curtos e Inter para operação e dados;
- densidade inspirada em Linear;
- clareza e confiança inspiradas em Stripe Dashboard;
- familiaridade de domínio inspirada em Google Ads;
- marca VOLC sem transformar o workspace em apresentação.

Proibido:

- cabeçalho ocupando metade da primeira tela;
- cards dentro de cards;
- pilhas de badges para fatos que cabem em uma frase;
- faixas laterais coloridas;
- texto em gradiente;
- glassmorphism, glow ou aurora atrás de tabela;
- estado baseado apenas em cor;
- botões desabilitados sem motivo e próximo passo;
- raw errors, stack traces, PostgREST, GAQL, SQL, nomes de tabela ou flags internas;
- gasto e publicação tratados como cliques triviais.

## Sequência de implementação

Execute as fases abaixo sem parar para pedir aprovação a cada microcheckpoint. Envie atualizações curtas, mas continue enquanto houver trabalho seguro dentro do escopo.

### V0 — Fundação visual

- mapear tokens e componentes atuais;
- alinhar `src/index.css`, Tailwind e primitivas aos tokens normativos sem quebrar o restante do produto;
- conter aurora e ruído fora do workspace;
- criar primitivas reutilizáveis para shell, página, tarefa, filtros, estados e dados;
- garantir tema claro/escuro, foco e reduced motion.

### V1 — Hub e Campanhas

- reduzir cabeçalho total a aproximadamente 220–280 px em desktop;
- hierarquizar Rede → tarefa → canal/filtros;
- manter a primeira linha operacional no primeiro viewport;
- reconstruir cabeçalhos de conta em 48–56 px;
- reconstruir campaign rows densas, comparáveis e legíveis;
- substituir pilhas de tags por um estado dominante e uma linha de evidência;
- manter histórico subordinado, lazy e fechado por padrão;
- reconstruir o detalhe inline para responder identidade, fonte, frescor, vínculo, ressalva e próxima ação sem virar outro dashboard;
- validar com as cinco campanhas operacionais reais e com FGTS/Maquininha.

### V2 — Página canônica

- implementar a ordem definida na SPEC: identidade, entrega/frescor, evidência, diagnóstico, vínculo/linhagem, manifesto por canal, histórico/recibos e ações;
- tratar 404 e 503 como estados diferentes;
- preservar manifesto `null` como indisponibilidade honesta;
- não percorrer inventário para achar o detalhe.

### V3 — Preparar, Criar e Atenção

- reorganizar Preparar pelos estados do contrato sem liberar duplicação;
- transformar Criar em estúdio multicanal com etapas de objetivo, estratégia, alcance, criativos, conferência, `validate_only`, recibo e aprovação;
- antecipar canais planejados apenas como capacidade explícita, nunca como sucesso fictício;
- organizar Atenção pela decisão do operador e preservar a mesma autoridade de contagem da API e do sino.

### V4 — Blindagem

- revisar estados de loading, fonte vazia, recorte vazio, nunca lido, parcial, antigo, falha com dado anterior, falha sem dado anterior e sem permissão;
- revisar desktop 1440 e 1920, tablet e mobile 390;
- revisar claro e escuro;
- revisar zoom 200%, teclado, foco, nomes acessíveis e reduced motion;
- corrigir overflow horizontal;
- executar revisão adversarial e corrigir todos os achados altos confirmados;
- reconstruir o grafo uma única vez ao final, conforme `AGENTS.md`, apenas se houve mudança material de código/documentação e nenhuma frente concorrente ainda estiver escrevendo.

## Inspeção visual obrigatória

Use o navegador real contra `http://localhost:8080`, autenticado pelo fluxo normal do produto. Não conclua apenas com jsdom.

Capture e revise:

- Hub Campanhas claro e escuro;
- Crédito Up com FGTS e Maquininha;
- histórico fechado e aberto;
- detalhe inline;
- página canônica;
- Preparar com correspondência provável e sem campanha;
- Criar em Search, Display, Demand Gen e Performance Max, mesmo que algumas capacidades fiquem honestamente indisponíveis;
- Atenção e sino;
- mobile claro e escuro.

Prove:

- zero erro de console;
- zero 4xx/5xx inesperado;
- zero request ao Google Ads no render;
- zero overflow horizontal;
- primeira campanha operacional acima da dobra;
- FGTS e Maquininha localizáveis em menos de dez segundos;
- cinco campanhas operacionais legíveis sem abrir as 79 removidas.

## Gates

Rode, no ambiente correto do projeto:

- testes focalizados das superfícies alteradas;
- suíte frontend completa;
- TypeScript, sem aumentar o baseline herdado;
- build Vite;
- verificações de bundle para segredos e chamadas proibidas;
- testes de acessibilidade disponíveis;
- inspeção visual real;
- testes de regressão dos invariantes de ordem, histórico lazy, identidade canônica, reconciliação e ausência.

Se um gate falhar, classifique entre regressão da frente e falha herdada com prova. Não chame uma falha de herdada sem medir no baseline correto.

## Commits e limites operacionais

- Faça commits pequenos por fase ou capacidade coerente.
- Não use `git reset --hard`, não descarte mudanças preexistentes e não inclua cópias Finder/Drive ou arquivos fora do ownership.
- Não faça push ou deploy.
- Não aplique migration.
- Não habilite escrita.
- Não execute `mutate` nem `validate_only` contra conta real sem autorização explícita separada.
- Não toque em `webgo`.

## Critério de parada

Não pare ao terminar o shell, uma tela ou um conjunto de componentes. Pare quando a fatia visual completa convergir e os gates acima estiverem medidos. Se existir um bloqueador externo verdadeiro, siga em todas as demais frentes seguras e reporte exatamente o que ficou bloqueado.

## Relatório final obrigatório

Entregue:

1. resultado visual alcançado;
2. SHAs e arquivos alterados por fase;
3. screenshots e caminhos;
4. comparação objetiva antes/depois;
5. regras do `DESIGN.md` exercitadas;
6. dados reais usados na validação;
7. achados adversariais confirmados, refutados e corrigidos;
8. gates e contagens;
9. prova de trava e zero mutação externa;
10. estado do grafo e da curadoria;
11. pendências verdadeiras, separadas de melhorias opcionais.

Comece pelo preflight, investigação read-only e mapa de ownership. Em seguida, avance pela implementação sem transformar esta missão em outra rodada apenas de documentação.
