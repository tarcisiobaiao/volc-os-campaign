# Prompt de execução — Estúdio Criativo VOLC

> Use este prompt somente depois que a frente atual de redesign do Tráfego estiver concluída, testada e commitada. Abra uma nova sessão do Claude Code no HEAD final para que os agentes e as instruções do projeto sejam carregados desde o início.

## Missão

Você está assumindo a primeira implementação vertical do **Estúdio Criativo VOLC**, uma capacidade global do VOLC OS para criar, versionar, aprovar, organizar e entregar imagens e vídeos para múltiplos destinos.

O Estúdio não pertence ao Google Ads, ao Meta Ads ou ao orgânico. Ele é uma fábrica transversal. Tráfego, Conteúdo Orgânico e outros módulos devem consumir ativos e pacotes gerados por ele, sem duplicar motores ou bibliotecas.

Implemente uma primeira fatia real e demonstrável, sem sucesso simulado e sem tentar integrar todo o ecossistema numa única rodada.

## Resultado obrigatório desta rodada

Entregar **C0 + C1 + C3** da SPEC:

1. O chassi global e navegável do Estúdio em `/criativos`.
2. Um contrato único para projetos, briefings, jobs, ativos, versões, aprovações e pacotes de destino.
3. Um job real de imagem, persistente e retomável, produzindo ao menos três formatos reais a partir de um único briefing.
4. Biblioteca global com os ativos gerados, detalhe, versões, procedência, aprovação e download.
5. Visualização de um build real já existente do motor de vídeo, importado ou observado de forma segura, com player, contrato, fases e evidências de QA. Nesta rodada, não é obrigatório iniciar um novo render de vídeo.
6. Integração honesta com o Hub de Tráfego: as superfícies atuais continuam funcionando como projeções/consumidoras. Não reescreva nem remova o que existe sem prova de substituição.
7. Validação visual e funcional no navegador com dados reais, em desktop e mobile.

Ao final, eu preciso conseguir abrir o VOLC OS, criar uma imagem real pelo Estúdio, sair da página, voltar ao job, encontrar o ativo na biblioteca e entender claramente como ele poderá ser usado em campanhas ou conteúdo.

## Fontes obrigatórias e ordem de autoridade

Leia completamente, antes de implementar:

1. `AGENTS.md`
2. `PRODUCT.md`
3. `DESIGN.md`
4. `docs/design/SPEC-ESTUDIO-CRIATIVO-VOLC.md`
5. `docs/creative-engines/ADR-001-SERVICO-CRIATIVO-VOLC.md`
6. `docs/creative-engines/ADR-002-INTEGRACAO-MOTOR-VIDEO.md`
7. Inventários, catálogos e snapshots existentes em `docs/creative-engines/`
8. `src/components/trafego/estudio/EstudioMulticanal.tsx`
9. `src/components/trafego/criativos/BibliotecaDeCriativos.tsx`

Consulte o grafo conforme `AGENTS.md`, começando por:

```bash
.venv-graphify/bin/graphify query "Estúdio Criativo VOLC imagem vídeo biblioteca assets aprovação destination packs Google Meta orgânico frontend rotas CreativeJob"
```

Consulte também a fonte humana:

- `docs/volc-os-graph/curadoria-operacional.json`

Antes de declarar o grafo atual, confira `graphify-out/UPDATE_STATUS.json` e compare com o HEAD. Se estiver defasado, use-o com essa ressalva. Não edite saídas geradas à mão.

## Referências externas a investigar, não copiar integralmente

### Interfaces e motores de imagem

- Aprova Ad Studio oficial:
  `/Users/mac/Library/CloudStorage/GoogleDrive-tarcisio@agenciavolc.com.br/Drives compartilhados/VOLC/VOLC/CLIENTES/IESDE/2026/Aprova-Ad-Sstudio`
- Positivo Ad Studio:
  `/Users/mac/Library/CloudStorage/GoogleDrive-tarcisio@agenciavolc.com.br/Drives compartilhados/VOLC/VOLC/CLIENTES/CURSO POSITIVO/IMAGE-SYSTEM/positivo-ad-studio`
- Motor de imagem VOLC e PRENSA:
  `/Users/mac/Desktop/Volc Mídia Global/motor-imagem`

Extraia padrões e núcleos necessários. Não copie aplicações inteiras nem seus frontends.

O que deve ser preservado conceitualmente:

- múltiplos formatos por job;
- progresso por fases e slots;
- falha parcial por peça sem perder o restante do lote;
- uso opcional de imagem real como referência;
- preservação de marca, logo e pack visual;
- geração integral por modelo de imagem;
- composição programática com tipografia real, máscaras, gradientes, grain e área semântica reservada para texto;
- exportação de peças derivadas a partir de um master;
- procedência e parâmetros suficientes para reprodução.

O que não deve ser herdado:

- chave de API no navegador;
- `localStorage` como autoridade de marca, job ou ativo;
- blobs temporários como biblioteca;
- ZIP como única forma de persistência;
- telas promocionais com glow, glass e excesso de ornamento;
- estado de carregamento que substitui toda a aplicação;
- uma cópia separada do motor para cada canal.

### Motor de vídeo

- Fábrica oficial:
  `/Users/mac/volc-factory`
- Contratos:
  `/Users/mac/volc-factory/contrato`
- Leia especialmente:
  `/Users/mac/volc-factory/contrato/design_c01_workspace.md`

Preserve o conceito de contrato resolvido, beats, hook, voz, identidade, elementos, fatos/fontes, CTA, assets reais, licenciamento, compliance, publicação e gates de QA.

Existe um risco arquitetural comprovado: o runtime atual usa arquivos e diretórios globais compartilhados. Até a isolação por workspace/job estar provada, não apresente render concorrente como capacidade segura. Nesta rodada, importe ou observe um build real já existente em modo somente leitura.

## Skills obrigatórias

Use, quando disponíveis, nesta ordem:

1. a skill local de frontend design em `/Users/mac/Downloads/Bonus 3 - Arsenal de Skills (Pixel) (1)/skills-exclusivas-pixel/frontend-design`;
2. `impeccable`;
3. `accessibility`;
4. `mobile-responsiveness`;
5. `best-practices`;
6. `remotion-best-practices`, apenas para decisões ligadas ao player e ao contrato de vídeo.

Registre quais foram realmente carregadas e como influenciaram a solução. Se alguma não existir ou não puder ser lida, declare e prossiga com as demais.

## Protocolo de agentes e escrita

Faça preflight antes de qualquer edição:

- confirme branch, HEAD e worktree;
- detecte outras sessões ou agentes ocupando a mesma árvore;
- não trabalhe com dois escritores sobre os mesmos arquivos;
- preserve todas as mudanças preexistentes;
- não apague cópias, legados ou arquivos alheios apenas para limpar gates.

Use subagentes com ownership disjunto:

1. **Investigador de produto e legado**, somente leitura: motores, contratos e superfícies atuais.
2. **Arquiteto de domínio**, somente leitura: contrato, limites, estados e decisões.
3. **Implementador de frontend**, escritor exclusivo das rotas e componentes do Estúdio.
4. **Implementador de backend/runtime**, escritor exclusivo dos contratos, endpoints, adapters e persistência.
5. **Revisor adversarial**, somente leitura: ausência virando afirmação, segurança, idempotência, concorrência, persistência e UX.
6. **Gatekeeper**, somente leitura: testes, build, acessibilidade, bundle e prova no navegador.

O coordenador integra e corrige. Não permita que dois agentes editem o mesmo arquivo ou camada simultaneamente.

Não pare em relatórios intermediários enquanto ainda houver trabalho seguro e independente dentro desta missão. Atualize brevemente o progresso, mas prossiga até a fatia vertical convergir ou surgir um bloqueio externo real.

## Arquitetura obrigatória

### 1. Um Estúdio global

Crie o módulo global, não uma nova aba presa ao Tráfego:

```text
/criativos
/criativos/novo
/criativos/imagens/novo
/criativos/videos/novo
/criativos/jobs/:creativeJobId
/criativos/biblioteca
/criativos/assets/:assetId
/criativos/aprovacoes
/criativos/brand-packs
```

O item de navegação deve ser claro para o usuário e coerente com a organização atual do VOLC OS. Use **Criativos** como nome curto no menu e **Estúdio Criativo** como nome da área.

### 2. Uma autoridade de domínio

Implemente os conceitos canônicos definidos na SPEC:

- `CreativeProject`
- `CreativeBrief`
- `CreativeJob`
- `AssetMaster`
- `Rendition`
- `DestinationPackage`
- `Approval`
- `Delivery`

Não use o formato de uma plataforma como modelo central. Google, Meta e orgânico são destinos.

### 3. Runtime separável

Siga o ADR aceito e estabeleça a fronteira de `services/creative-engine` como runtime separável. O VOLC OS deve falar com um contrato estável de job. Caminhos absolutos dos projetos externos não podem fazer parte do contrato de produção.

Pode haver adapter local de desenvolvimento, mas ele deve ficar explicitamente separado do contrato futuro de serviço.

### 4. Supabase oficial

A única autoridade de dados deste projeto é o Supabase self-hosted:

```text
https://database.agenciavolc.com.br/
```

Não introduza outro projeto Supabase, URL hospedada ou fallback legado.

Escreva migrations e testes necessários, mas **não aplique migration em produção sem autorização explícita**. Valide em cluster descartável ou ambiente local equivalente.

Arquivos binários devem ir para object storage. O Postgres guarda metadados, relações, hashes, estados e auditoria. Não persista base64 ou bytes grandes em colunas relacionais.

### 5. Jobs duráveis

O job precisa sobreviver à navegação e ao refresh:

- idempotency key;
- estados canônicos;
- fases e eventos persistidos;
- retry explícito;
- falha parcial por rendition;
- cancelamento quando suportado;
- cursor de eventos ou reconexão SSE;
- resultado recuperável por `creativeJobId`;
- nenhum percentual inventado se o motor não emitir progresso medido.

Estados mínimos:

```text
draft
queued
running
partial
succeeded
failed
cancelled
```

### 6. Versão imutável e procedência

Novo prompt, crop, render, adaptação ou correção produz nova versão. Não sobrescreva silenciosamente o master aprovado.

Cada ativo precisa dizer:

- quem ou o que o criou;
- qual motor e versão;
- qual briefing e brand pack;
- quando foi criado;
- hash do arquivo;
- dimensões, duração e MIME;
- relação com master e renditions;
- direitos/licença dos insumos;
- estado de aprovação;
- usos e destinos conhecidos.

## Escopo funcional desta rodada

### A. Home do Estúdio

Entregue uma entrada operacional e limpa com:

- ações **Criar imagem** e **Criar vídeo**;
- jobs recentes;
- itens aguardando revisão;
- atalhos para biblioteca e brand packs;
- resumo real por estado;
- vazios honestos, sem métricas simuladas.

Evite um dashboard de cartões decorativos. Priorize trabalho atual, próximos passos e evidência.

### B. Primeiro fluxo real de imagem

Implemente um fluxo guiado com progressive disclosure:

1. intenção e destino;
2. formato(s);
3. mensagem e conteúdo;
4. brand pack;
5. imagem de referência opcional;
6. revisão do contrato;
7. gerar;
8. acompanhar job;
9. revisar resultados;
10. aprovar e salvar na biblioteca.

Escolha **um adapter estreito e comprovável** para a primeira geração real. Dê preferência ao caminho mais isolável e documentado, como uma geração full-LLM já existente. Não conecte três motores parcialmente.

Produza ao menos três renditions reais no mesmo job, por exemplo:

- 1:1;
- 4:5;
- 9:16.

As três não podem ser apenas o mesmo bitmap esticado. Use o contrato do motor para gerar ou adaptar com enquadramento válido.

Se o adapter usar fonte externa, registre source lock, hash e evidência de paridade mínima. Não copie o frontend original.

### C. Biblioteca e detalhe

Entregue:

- busca;
- filtros por tipo, estado, brand pack, destino e data;
- visualização em grade/lista conforme densidade;
- thumbnail real;
- master e renditions;
- versão e procedência;
- estado de aprovação;
- download por URL assinada;
- detalhe do ativo em rota própria;
- vazio, erro, loading e indisponibilidade distintos.

Não exponha prompt sensível, token, caminho de servidor ou stack trace ao operador.

### D. Aprovação

Implemente aprovação humana no escopo interno:

- aprovar;
- pedir ajuste com observação;
- rejeitar com motivo;
- registrar ator e instante;
- nunca promover automaticamente um ativo parcial ou falho.

### E. Primeiro fluxo observado de vídeo

Não desenhe um editor de timeline genérico. Crie uma leitura editorial orientada ao contrato:

- player;
- resumo do contrato resolvido;
- hook;
- beats/cenas;
- voz e identidade;
- fontes e compliance;
- ledger de assets;
- gates de QA;
- outputs e formatos;
- procedência do build.

Importe ou observe um build real existente de `/Users/mac/volc-factory`, sem alterá-lo. Transforme-o em um `CreativeJob` observado/importado, com evidência de origem. Não diga que o VOLC OS renderizou o vídeo se ele apenas leu um build anterior.

O botão **Criar vídeo** pode abrir o briefing e explicar honestamente que o novo render ainda depende da isolação C-01. Não mostre sucesso ou capacidade operacional inexistente.

### F. Projeções no Tráfego

As superfícies existentes em Tráfego são projeções específicas de campanha:

- `EstudioMulticanal.tsx`
- `BibliotecaDeCriativos.tsx`

Não as transforme na autoridade global. Nesta rodada:

- preserve o comportamento atual;
- permita que apontem para o ativo canônico ou abram o Estúdio quando houver contrato seguro;
- não duplique a biblioteca;
- não crie mutação no Google Ads ou Meta;
- não declare um ativo como compatível com destino sem validação de formato e contrato.

## Fora do escopo e proibido nesta rodada

- publicar ou subir criativo no Google Ads, Meta ou canais orgânicos;
- aplicar migration em produção;
- `mutate` ou `validate_only` contra conta de anúncio real;
- novo render de vídeo concorrente antes de provar workspaces isolados;
- automação autônoma de aprovação;
- editor livre de vídeo no estilo NLE;
- transformação do Estúdio em DAM corporativo genérico;
- copiar integralmente Aprova, Positivo, PRENSA ou `volc-factory` para dentro do repo;
- colocar segredos ou chaves no browser;
- alterar `DESIGN.md` ou a SPEC para justificar limitações da implementação;
- rebuild parcial do grafo com `graphify update .`.

## Direção de experiência e interface

Siga `DESIGN.md` e o sistema VOLC Mission Control.

Princípios:

- a tarefa domina, a decoração recua;
- interface clara por padrão e escuro completo;
- progressive disclosure;
- controles familiares;
- estados e próximos passos em linguagem humana;
- uma hierarquia visual clara, sem três barras competindo;
- sem glassmorphism, aurora operacional, glow ou excesso de cards;
- sem cards dentro de cards;
- não use modais para fluxos longos;
- não use ícones ou símbolos improvisados quando já houver componente do sistema;
- não use `transition: all`;
- respeite `prefers-reduced-motion`;
- não use travessão em textos finais da interface;
- mobile não pode ser uma tabela desktop espremida.

Para o vídeo, prefira três regiões claras em desktop:

```text
estrutura e cenas | preview principal | contrato e inspeção
```

Em mobile, transforme isso em navegação sequencial ou abas acessíveis, sem esconder o estado do job.

## Segurança e permissões

- JWT e papel validados no backend;
- RLS e grants mínimos;
- URLs assinadas curtas para assets privados;
- upload com limite de tamanho, MIME permitido, hash e nome sanitizado;
- nenhuma `service_role` no bundle;
- nenhum caminho do filesystem exibido ao frontend;
- auditoria de criação, aprovação, rejeição, retry e download;
- confirmação humana antes de qualquer entrega futura a plataforma;
- separação entre quem cria, quem aprova e quem publica, mesmo que hoje o usuário ADMIN reúna os três papéis.

Não use `localStorage` como autoridade de segurança, aprovação, job ou brand pack.

## Contratos de API esperados

Defina contratos estáveis equivalentes a:

```text
POST   /api/criativos/jobs
GET    /api/criativos/jobs/:creativeJobId
GET    /api/criativos/jobs/:creativeJobId/events
POST   /api/criativos/jobs/:creativeJobId/retry
POST   /api/criativos/jobs/:creativeJobId/cancel
GET    /api/criativos/assets
GET    /api/criativos/assets/:assetId
POST   /api/criativos/assets/:assetId/approvals
GET    /api/criativos/brand-packs
```

Os nomes finais podem seguir as convenções do backend, mas a semântica não pode depender do frontend.

Não faça o request HTTP esperar o render terminar. Criar job deve responder com identidade e estado inicial; acompanhamento ocorre por consulta/eventos.

## Estratégia de testes

Crie provas para, no mínimo:

1. idempotência de criação de job;
2. refresh e retomada por `creativeJobId`;
3. desconexão e reconexão do stream;
4. falha parcial de uma rendition;
5. retry sem duplicar ativos já concluídos;
6. versão nova sem sobrescrever master;
7. permissão de aprovação;
8. upload inválido recusado;
9. URL assinada e expiração;
10. nenhum segredo ou caminho absoluto no bundle/API;
11. job observado de vídeo não confundido com job renderizado pelo VOLC OS;
12. histórico e procedência preservados;
13. vazio diferente de falha;
14. zero percentual inventado;
15. nenhum request a Google ou Meta no render das telas;
16. navegação por teclado, foco, labels e anúncios de estado;
17. mobile sem overflow horizontal;
18. temas claro e escuro;
19. contraste e `prefers-reduced-motion`;
20. três formatos reais vinculados ao mesmo master/job.

## Gates obrigatórios

Rode os comandos oficiais da casa, usando os ambientes corretos do repo:

- suíte frontend completa;
- TypeScript sem aumentar o baseline conhecido;
- build Vite;
- suíte backend completa;
- testes do creative engine;
- testes de migration em banco descartável, se houver schema novo;
- varredura de bundle por segredo e caminho absoluto;
- prova de que não houve request a Google Ads ou Meta no render;
- prova de zero mutação externa;
- validação visual no Chromium real em `localhost:8080`.

Valide visualmente:

- home do Estúdio;
- briefing de imagem;
- job em execução e concluído;
- job parcial ou falho;
- biblioteca;
- detalhe e aprovação;
- build observado de vídeo;
- desktop claro e escuro;
- mobile claro e escuro;
- zero erro de console;
- zero 4xx/5xx inesperado;
- zero overflow horizontal.

Use dados reais para a prova principal. Fixtures servem aos testes, não ao aceite visual final.

## Commits e limites operacionais

Faça commits pequenos e coerentes por camada, sem incluir mudanças alheias.

Sugestão:

1. contrato e migrations não aplicadas;
2. runtime/adapters de imagem;
3. API de jobs e storage;
4. shell e fluxo de imagem;
5. biblioteca e aprovação;
6. importador/observador de vídeo;
7. correções da auditoria;
8. documentação, roadmap e grafo.

Não faça push, deploy, migration em produção, rotação de segredo ou mutação em plataforma externa.

Depois de mudanças materiais em código, schema e roadmap, atualize o grafo uma única vez conforme `AGENTS.md`:

```bash
python3 scripts/atualizar_grafo_volc_os.py
```

Não use `--reuse-technical` se a camada de código mudou.

Edite a curadoria humana apenas se a evidência justificar. Não promova `partial` para `implemented` porque a interface existe. Capacidade implementada exige fluxo real, persistência e prova.

## Condições para considerar a rodada concluída

Só declare a missão concluída se todas forem verdadeiras:

- `/criativos` existe e está integrada ao app shell;
- o contrato canônico está implementado e testado;
- um job real de imagem foi persistido e retomado após refresh;
- o job produziu pelo menos três formatos reais;
- os ativos aparecem na biblioteca com versão e procedência;
- aprovação humana funciona e é auditada;
- um build real de vídeo aparece como observado/importado, sem autoria inventada;
- o Tráfego não foi quebrado nem transformado em segunda autoridade;
- nenhum segredo foi para o browser;
- nenhuma ação externa foi executada;
- gates e validação visual passaram;
- grafo e roadmap refletem apenas o que foi provado.

## Relatório final esperado

Entregue:

1. resultado funcional em linguagem simples;
2. SHAs e arquivos alterados;
3. arquitetura final e decisões tomadas;
4. qual adapter real de imagem foi escolhido e por quê;
5. prova do job real e das três renditions;
6. prova de persistência, refresh e idempotência;
7. prova do build de vídeo observado e sua origem;
8. capturas e URLs para inspeção;
9. resultados exatos dos gates;
10. achados adversariais confirmados, corrigidos e refutados;
11. estado da trava e prova de zero mutação externa;
12. estado do grafo e da curadoria;
13. pendências verdadeiras para C2, C4, C5 e C6;
14. qualquer limitação que a interface ainda precise declarar ao usuário.

Não encerre com uma lista genérica de arquivos. O aceite é uma jornada real: criar, acompanhar, reencontrar, revisar e aprovar um ativo.

