# Prompt Grok - Sprint de Tráfego com contraste e criação por canal

## Contexto

Você está assumindo uma correção urgente e estritamente frontend do Hub de Tráfego do VOLC OS.

HEAD de partida esperado: `0be638d` ou descendente direto que contenha integralmente V0-V4 do redesign anterior.

O redesign anterior melhorou densidade, semântica e acessibilidade, mas falhou no resultado percebido pelo operador. A interface continua excessivamente cinza, plana e semelhante a um relatório sem acabamento. A hierarquia das ações é fraca, os dados não têm peso visual suficiente e a aba Criar usa uma jornada genérica que não representa os diferentes tipos de campanha do Google Ads.

Este feedback do dono é evidência de produto, não preferência descartável:

> A tela de login comunica uma marca forte e acabada. O workspace de Tráfego parece um mock quebrado, sem contraste, pesos ou botões claros.

As capturas de referência do problema são:

- `/Users/mac/Desktop/Capturas/Captura de Tela 2026-08-27 às 14.20.52.png`
- `/Users/mac/Desktop/Capturas/Captura de Tela 2026-08-27 às 14.20.57.png`
- `/Users/mac/Desktop/Capturas/Captura de Tela 2026-08-27 às 14.21.03.png`

A captura de login é uma referência de nível de acabamento e identidade, não um pedido para levar aurora e glassmorphism ao workspace:

- `/Users/mac/Desktop/Capturas/Captura de Tela 2026-08-27 às 14.19.44.png`

## Declaração obrigatória de método

Comece sua resposta exatamente com:

> Usarei, nesta ordem, `impeccable` para remover padrões genéricos e reorganizar hierarquia/IA; `emil-design-eng` para interação, densidade e microdetalhes; e `make-interfaces-feel-better` para o passe final de acabamento.

Carregue e aplique as três skills de verdade. Não apenas as mencione.

Use também as skills de acessibilidade e responsividade existentes no ambiente. Consulte a documentação oficial do Google Ads API v25 para qualquer afirmação de capacidade.

## Resultado esperado

Ao final desta rodada, o operador deve conseguir:

1. abrir `/trafego` e identificar imediatamente a rede, o trabalho atual, o estado dos dados e a ação primária;
2. ler campanhas e métricas sem esforço, com contraste, peso e alinhamento adequados;
3. clicar em **Nova campanha** ou **Começar campanha** sem procurar uma porta escondida;
4. escolher Search, Display, Demand Gen, Performance Max, Shopping ou Vídeo;
5. receber uma jornada específica daquele canal, derivada de capacidades reais;
6. entender claramente o que o VOLC já executa, o que somente valida, o que apenas observa e o que a API não suporta;
7. iniciar o cockpit real existente quando houver suporte, sem sucesso simulado;
8. usar a mesma interface em claro, escuro, desktop e mobile com qualidade equivalente.

Não encerre com wireframes ou um relatório. Implemente, valide no navegador e entregue a experiência funcionando em `localhost:8080`.

## Limites desta missão

Esta é uma frente de produto e frontend.

Pode:

- editar o frontend do Hub de Tráfego;
- editar componentes e tokens compartilhados quando houver evidência visual e teste de regressão;
- atualizar `DESIGN.md` e `.impeccable/design.json` de forma cirúrgica para tornar os critérios de contraste e hierarquia duráveis;
- criar componentes específicos por canal;
- consumir os contratos e manifestos existentes;
- criar testes, fixtures e histórias isoladas;
- conectar ações a rotas reais já existentes.

Não pode:

- aplicar migration;
- alterar banco de produção;
- executar `mutate` ou `validate_only` no Google Ads;
- fazer push ou deploy;
- inventar endpoint, permissão ou capacidade;
- colocar chave ou token no navegador;
- hardcodar sucesso de canal;
- transformar fixture em dado de produção;
- reescrever backend ou motores;
- iniciar a implementação do Estúdio Criativo global deste projeto;
- tocar nos 169 arquivos preexistentes fora do ownership desta frente.

## Preflight obrigatório

Antes de editar:

1. confirme HEAD, branch e worktree;
2. detecte outros escritores no mesmo worktree;
3. confira `git status` e registre as mudanças preexistentes;
4. leia `AGENTS.md`, `PRODUCT.md`, `DESIGN.md` e `.impeccable/design.json`;
5. leia completamente `docs/design/SPEC-REDESIGN-VOLC-OS-TRAFEGO.md`;
6. consulte o grafo conforme `AGENTS.md`;
7. leia `graphify-out/UPDATE_STATUS.json` e compare com o HEAD;
8. inspecione o produto real autenticado em `localhost:8080` antes de propor solução;
9. execute os gates de baseline no ambiente correto;
10. crie capturas de antes nas mesmas viewports usadas no aceite.

Não use o build da árvore suja como única prova. O incidente anterior demonstrou que ele pode passar com imports de arquivos não versionados. O gate final precisa incluir build e TypeScript em worktree limpa.

## Fontes oficiais obrigatórias

Use somente documentação oficial para fatos da plataforma. Registre URL, data de consulta e o fato sustentado.

### Campanhas e tipos

- `https://developers.google.com/google-ads/api/docs/campaigns/overview`
- `https://developers.google.com/google-ads/api/docs/campaigns/create-campaigns`

### Search

- `https://developers.google.com/google-ads/api/docs/responsive-search-ads/create-responsive-search-ads`
- `https://developers.google.com/google-ads/api/reference/rpc/v25/ResponsiveSearchAdInfo`
- `https://developers.google.com/google-ads/api/docs/assets/working-with-assets`

### Display

- `https://developers.google.com/google-ads/api/docs/responsive-display-ads/create-responsive-display-ads`

### Performance Max

- `https://developers.google.com/google-ads/api/performance-max/standard`
- `https://developers.google.com/google-ads/api/performance-max/asset-groups`

### Demand Gen

- `https://developers.google.com/google-ads/api/docs/demand-gen/create-campaign`

### Shopping

- `https://developers.google.com/google-ads/api/docs/shopping-ads/create-campaign`

### Vídeo

- `https://developers.google.com/google-ads/api/docs/video/overview`

Não transforme disponibilidade documental em capacidade implementada no VOLC. A interface deve cruzar:

```text
capacidade da API
AND capacidade do backend VOLC
AND permissão do usuário
AND estado da trava
```

Só o resultado dessa interseção pode liberar uma ação.

## Correção conceitual obrigatória

As mesmas sete etapas genéricas não servem para todos os canais.

Crie uma gramática de jornada por canal. Ela deve vir de contrato/manifesto tipado, não de condicionais soltas espalhadas pelo JSX.

### Search

Search não deve mostrar uma etapa genérica de imagem e vídeo como se fossem requisitos de criação.

A jornada deve representar:

1. objetivo operacional e conta;
2. destino e medição de conversão;
3. geografia, idioma e redes;
4. orçamento e estratégia de lance;
5. grupos de anúncios;
6. keywords, correspondências e negativas;
7. anúncio responsivo de pesquisa:
   - headlines;
   - descriptions;
   - URL final;
   - `path1` e `path2` quando aplicável;
   - pinning somente quando deliberado;
8. recursos opcionais e aplicáveis:
   - sitelinks;
   - callouts;
   - structured snippets;
   - chamadas, formulários ou imagens somente se elegíveis e suportados;
9. conferência de duplicidade, política, tracking e contrato;
10. validação;
11. criação pausada;
12. ativação como decisão separada.

Na interface, nomeie a etapa **Anúncio e recursos**, não **Criativos de imagem e vídeo**.

A documentação oficial exige pelo menos três headlines, duas descriptions e uma URL final para o RSA. Não reduza isso a um único campo de copy.

### Display

A jornada deve evidenciar que o Responsive Display Ad possui contrato visual próprio:

- imagens de marketing;
- imagens quadradas;
- headlines;
- long headline;
- descriptions;
- business name;
- URL final;
- logos quando aplicáveis;
- cores da marca e flexibilidade de cor quando suportadas;
- formato nativo, não nativo ou todos quando permitido;
- controles de vídeo gerado e asset enhancements quando disponíveis;
- público, posicionamentos e exclusões;
- orçamento, lance, conferência, validação e criação pausada.

### Demand Gen

Não trate Demand Gen como Display renomeado.

Mostre tipos de anúncio quando o manifesto confirmar:

- multi-asset;
- carousel;
- video responsive;
- product ad quando houver Merchant Center elegível.

A jornada deve separar:

- campanha e bidding;
- ad group;
- audiência;
- channel controls;
- tipo de anúncio;
- assets obrigatórios;
- copy e destino;
- conferência e criação atômica.

A documentação recomenda criar as entidades relacionadas em um único `GoogleAdsService.Mutate` para evitar órfãos. A UI deve comunicar que o pacote é validado como unidade, sem executar nada nesta rodada.

### Performance Max

A jornada precisa ser centrada em asset groups, não ad groups Search disfarçados:

- objetivos e conversion goals;
- orçamento e bidding;
- geografia e idioma;
- brand guidelines;
- final URL e expansão de URL;
- asset groups;
- headlines, long headlines e descriptions;
- imagens e logos;
- vídeos;
- audience signals;
- search themes quando disponíveis;
- listing groups quando retail;
- preview quando o serviço estiver disponível;
- conferência dos mínimos do asset group;
- criação atômica do asset group e seus vínculos.

Não mostre o botão de criação como habilitado se os mínimos de assets ou o manifesto do backend não estiverem satisfeitos.

### Shopping

Shopping depende do Merchant Center e do catálogo, não de um editor de criativo manual genérico.

Mostre:

- conta Merchant Center vinculada;
- país/mercado e configurações aplicáveis;
- feed e diagnóstico do catálogo;
- orçamento e bidding;
- prioridade quando Standard Shopping exigir;
- product groups/listing groups;
- inventário incluído e excluído;
- tracking e conferência.

Se não houver vínculo elegível com Merchant Center, o estado é pré-requisito ausente, não erro de campanha.

### Vídeo

A documentação oficial afirma que a Google Ads API somente consulta e reporta campanhas Video existentes; ela não cria nem atualiza novas campanhas Video.

Portanto:

- não mostre **Criar campanha Video pela API**;
- mostre capacidade **Observar e analisar**;
- ofereça Demand Gen ou Performance Max como rotas programáticas de vídeo quando aplicáveis;
- se existir integração manual/externa futura, rotule-a como externa e não implementada;
- não confunda a existência de `VideoAdInfo` no schema com autorização para criar campanhas Video.

## Arquitetura da aba Criar

Redesenhe `/trafego?aba=criar` como uma bancada operacional, não uma documentação vertical.

### Estrutura recomendada

```text
Cabeçalho curto
  Criar campanha
  Escolha o canal e veja somente o que ele exige
  [Nova campanha] ação primária

Seletor de canal com estado de capacidade
  Search           operacional
  Display          parcial / operacional conforme manifesto
  Demand Gen       planejado ou parcial
  Performance Max planejado ou parcial
  Shopping         depende de Merchant Center
  Vídeo            somente leitura pela API

Workspace do canal
  resumo do que este canal resolve
  pré-requisitos medidos
  jornada específica
  capacidades e limites
  ação primária ou próximo desbloqueio
```

Requisitos:

- precisa existir um CTA visualmente dominante;
- Search operacional deve apontar para o cockpit real;
- se for necessário escolher um funil, o CTA abre a seleção ou leva a Preparar com contexto preservado;
- não esconda a ação principal num parágrafo;
- estados indisponíveis não podem parecer botões desativados sem explicação;
- um canal planejado deve mostrar seu próximo desbloqueio, não sete etapas falsas;
- use progressive disclosure para requisitos avançados;
- permita comparar capacidade sem transformar a página numa matriz enorme.

## Redesign visual obrigatório

### Diagnóstico atual

O problema não é ausência de aurora. É ausência de hierarquia:

- canvas, tabela, grupo e linha usam tons próximos demais;
- texto secundário tem contraste e peso insuficientes;
- ações primárias parecem controles neutros;
- grupos de conta não criam marcos visuais claros;
- a tabela é uma planilha larga sem foco operacional;
- a identidade VOLC desaparece ao entrar no workspace;
- o operador não sabe onde olhar primeiro.

### Princípios de correção

1. Defina uma estratégia cromática operacional explícita. Preserve neutros VOLC, mas use o gradiente de marca apenas como assinatura rara, não como papel de parede.
2. Crie quatro níveis distinguíveis:
   - canvas;
   - superfície de trabalho;
   - grupo de conta;
   - linha interativa/selecionada.
3. Use sombra multicamada leve para elevação de superfícies e preserve bordas para divisores e inputs.
4. Aumente contraste e escala entre título, contexto, dado e ressalva.
5. Use cor semântica em estados e evidências, sempre com glifo, palavra e descrição.
6. Dê peso visual às métricas que decidem gasto. Números devem usar `tabular-nums`.
7. Faça ações primárias parecerem ações primárias. Controles de filtro não podem competir com elas.
8. Use `text-balance` em títulos e `text-pretty` em explicações curtas.
9. Adicione `antialiased` no root se ainda não existir.
10. Use áreas de clique de pelo menos 40x40px.
11. Use `active:scale-[0.96]` somente em controles que se beneficiem de feedback tátil.
12. Não use `transition: all`.
13. Não anime ações frequentes de teclado ou navegação de tabela.
14. Popovers devem nascer do trigger; modais permanecem centrados.
15. Respeite `prefers-reduced-motion`.

### Relação com o login

O login prova que a marca possui energia visual. Extraia dele:

- contraste forte;
- tipografia confiante;
- ação primária inequívoca;
- detalhe VOLC reconhecível;
- acabamento de superfícies;
- ritmo de espaçamento.

Não copie:

- aurora por baixo de números operacionais;
- glassmorphism em tabelas;
- grande área ornamental;
- fundos escuros compulsórios;
- gradiente em todo botão.

No workspace, a marca deve aparecer como precisão, contraste e assinatura, não como decoração contínua.

## Campanhas: abandonar a planilha sem perder densidade

Não transforme cada campanha num card alto. Preserve densidade, mas reorganize a linha.

Cada linha precisa ter uma leitura dominante:

```text
estado + nome + canal
decisão/condição atual
métricas essenciais
frescor
ação contextual
```

Requisitos:

- o nome completo deve ser alcançável sem depender de tooltip;
- métricas numéricas precisam alinhar e ter peso suficiente;
- conta e campanha não podem competir na mesma escala tipográfica;
- linhas ativas, pausadas e históricas devem ser distinguíveis sem depender apenas da cor;
- linha expandida deve parecer continuação da linha, não uma página sem moldura;
- **Abrir campanha** deve ser uma ação reconhecível;
- ações secundárias aparecem sob demanda, sem poluir todas as linhas;
- o recorte operacional continua escondendo removidas por padrão;
- não reordene no browser e não quebre paginação/cursor;
- não busque Google Ads no render.

## Componentes e ownership provável

Inspecione antes de editar. A lista abaixo é direção, não autorização cega:

- `src/pages/trafego/HubDeTrafegoPage.tsx`
- `src/components/trafego/estudio/EstudioMulticanal.tsx`
- `src/components/trafego/estudio/EstudioLigado.tsx`
- `src/components/trafego/inventario/InventarioDeCampanhas.tsx`
- `src/components/trafego/inventario/GrupoDeConta.tsx`
- `src/components/trafego/inventario/LinhaDeCampanha.tsx`
- `src/components/trafego/inventario/FiltrosDoInventario.tsx`
- `src/components/trafego/inventario/Selos.tsx`
- `src/components/trafego/hub/EixosDoHub.tsx`
- `src/components/trafego/hub/contrato.ts`
- `src/components/trafego/canal/capacidades.ts`
- `src/components/ui/button.tsx`
- `src/index.css`
- `tailwind.config.ts`
- `DESIGN.md`
- `.impeccable/design.json`

Crie um único registry tipado de apresentação por canal, consumindo o manifesto do backend. Não faça seis telas copiadas nem uma floresta de `if (canal === ...)`.

## Protocolo de implementação

### Etapa A: auditoria e contrato visual

1. capture a interface atual;
2. produza uma tabela **Before | After | Why** conforme `emil-design-eng`;
3. produza as tabelas de mudança exigidas por `make-interfaces-feel-better`;
4. registre a matriz factual API x VOLC x permissão x trava;
5. atualize o DESIGN apenas com decisões duráveis;
6. adicione testes de contrato por canal antes do JSX principal.

### Etapa B: hierarquia do Hub

1. contraste de canvas/superfícies;
2. ação primária;
3. rede e tarefas;
4. filtros subordinados;
5. inventário com grupos e linhas legíveis;
6. estados de hover, foco, selecionado, expandido e indisponível.

### Etapa C: criação por canal

1. registry tipado;
2. seletor de canal com capacidade;
3. Search específico e porta real para cockpit;
4. Display específico;
5. Demand Gen específico;
6. Performance Max específico;
7. Shopping com pré-requisito Merchant Center;
8. Vídeo somente leitura e alternativas honestas.

### Etapa D: acabamento

1. tipografia e wrapping;
2. alinhamento óptico;
3. sombras e raios concêntricos;
4. números tabulares;
5. hit areas;
6. motion criterioso;
7. claro e escuro;
8. mobile;
9. redução de movimento;
10. contraste medido.

### Etapa E: revisão adversarial

Tente refutar:

- Search ainda mostra requisito visual obrigatório;
- canal sem suporte libera CTA;
- Vídeo sugere criação pela API;
- Display/PMax/Demand Gen usam a mesma lista genérica;
- botão primário não existe ou fica fora da primeira viewport;
- ausência vira sucesso ou zero;
- cor é o único portador de estado;
- dark mode perde contraste;
- tabela quebra em 1024px ou mobile;
- frontend consulta Google Ads no render;
- ordem do servidor é substituída por `sort()` local;
- histórico removido é pré-carregado;
- build só funciona na árvore suja.

Corrija cada achado confirmado com teste de regressão.

## Aceite visual obrigatório

Valide no Chromium autenticado com os dados reais das três contas e as duas campanhas da Crédito Up.

Capture e confira:

1. `/trafego?aba=campanhas`, claro, 1920 e 1440;
2. `/trafego?aba=campanhas`, escuro;
3. campanhas em 1024px;
4. campanhas em 390px;
5. `/trafego?aba=criar&canal=SEARCH`;
6. `/trafego?aba=criar&canal=DISPLAY`;
7. `/trafego?aba=criar&canal=DEMAND_GEN`;
8. `/trafego?aba=criar&canal=PERFORMANCE_MAX`;
9. `/trafego?aba=criar&canal=SHOPPING`;
10. `/trafego?aba=criar&canal=VIDEO`;
11. Search com botão claro para iniciar o fluxo real;
12. linha FGTS e linha Maquininha;
13. estado expandido;
14. foco por teclado;
15. zoom 200%;
16. `prefers-reduced-motion`.

O aceite não é “cabe na tela”. Precisa passar nestas perguntas:

- Em três segundos, dá para apontar a ação principal?
- Em cinco segundos, dá para dizer qual campanha está ativa e qual merece atenção?
- Search mostra apenas as decisões e recursos que pertencem a Search?
- Cada canal tem identidade funcional própria sem parecer outro produto?
- O workspace parece pertencer à mesma marca do login sem copiar sua decoração?
- O usuário consegue começar algo, ou continua apenas lendo documentação?

## Gates

- suíte frontend completa;
- TypeScript igual ou melhor que o baseline de worktree limpa;
- build Vite na árvore atual;
- build e TypeScript em worktree limpa;
- backend e `volc_ads` sem regressão;
- zero segredo no bundle;
- zero request ao Google no render;
- zero `mutate` e zero `validate_only` externo;
- zero 4xx/5xx inesperado;
- zero erro de console;
- zero overflow horizontal;
- auditoria de acessibilidade;
- contraste medido nos dois temas;
- teste de contract registry para todos os seis canais.

## Commits

Faça commits pequenos e exclusivos:

1. contrato visual e registry por canal;
2. hierarquia e contraste do Hub;
3. inventário e linhas;
4. criação Search;
5. demais canais;
6. acabamento e acessibilidade;
7. correções adversariais;
8. documentação e grafo.

Não inclua WIP alheio. Antes de cada commit, confira o staging por arquivo e diff. Ao final, prove build limpo.

Reconstrua o grafo uma única vez, conforme `AGENTS.md`, somente depois da convergência. Não use `graphify update .`.

## Relatório final

Entregue:

1. resultado em linguagem simples;
2. tabela **Before | After | Why**;
3. SHAs e arquivos por fase;
4. matriz final por canal;
5. fontes oficiais com data;
6. capturas de antes e depois;
7. prova do CTA real de Search;
8. prova de que Vídeo não promete mutação impossível;
9. gates exatos;
10. achados adversariais confirmados, corrigidos e refutados;
11. estado da trava e prova de zero mutação externa;
12. estado do grafo;
13. pendências reais para o sprint do Estúdio Criativo global.

Não pare depois de “melhorar a aparência”. A rodada fecha quando a interface estiver visualmente convincente e operacionalmente correta por canal.

