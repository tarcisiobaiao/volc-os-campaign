# Refino contextual do Redator e piloto SENAC

Data: 2026-09-18. Roadmap: P10-T17, partial. Capacidade: cap_funnel.
Estado editorial: DRAFT_WITH_GAPS. Nenhuma pagina publicada nesta rodada.

## Decisao

Planejar por intencao do leitor, entrega util, conexoes pertinentes, CTAs curtos,
apresentacao e medicao. A leitura pode terminar com uma resposta satisfeita;
cliques adicionais nao sao obrigatorios. Seguranca, fontes, identidade e limites
de custo continuam verificaveis por codigo. Relevancia editorial passa ao
contrato contextual e ao juiz semantico, sem quotas artificiais.

## Implementacao no motor e no backend

- `EditorialIntent` declara pergunta, entrega, rotulo de entrada e destinos com
  justificativa. `EditorialLink` aponta para slug exato do plano.
- O arquiteto e o reviewer preservam esse contrato. PageFactory, normalizacao
  de roles e adaptador VOLC transportam os campos e remapeiam slugs dos links.
  Nao bastava alterar o extractor: o caminho VOLC usa arquitetura estruturada.
- Planos contextuais nao clonam hubs nem ordenam destinos por numero de pagina.
  Permitem retorno voluntario a outro guia. Alvos inexistentes, duplicados,
  auto-links e contratos incompletos sao rejeitados antes de montar rotas.
- Removidas as exigencias de quantidade de orgaos/siglas, variacao obrigatoria
  dos botoes, alternancia de primeira solucao e convite obrigatorio com "toque".
- Prompts de internas e hub agora pedem respostas completas. FAQ respondida,
  exemplos regionais delimitados e encaminhamento oficial sem simular servico.
- Planos contextuais nao usam cotas de palavras/H2, obrigacao de formatos
  visuais ou comparacao lexical de CTA como prova de qualidade editorial.
  O codigo continua verificando os destinos realmente inseridos no HTML.
- O juiz recebe o conteudo uma vez, a entrega esperada e os contratos dos
  destinos. Compliance, disciplina de CTA, entrega util e pertinencia dos
  destinos bloqueiam quando reprovados ou ausentes. A LP contextual tambem e
  revisada semanticamente, alem do contrato estrutural.
- Reprovacao de escrita OU juiz interrompe SEO, imagens, build e publicacao
  daquela pagina. Teste cobre ausencia dos passos seguintes.
- `reachable_pages` mede alcancabilidade do grafo. `pv_per_session` passa a
  `null`, com `measurement_status=not_collected`. Nao ha metrica comportamental
  deduzida da quantidade de paginas planejadas.

Arquivos principais: `backend/app/n8n_prompts/funnel_builder.py`,
`backend/app/agents/funnel_pro/{reviewer,page_factory}.py`,
`backend/app/entities/funnel_roles.py` e
`funnelforge-migracao/engine/src/funnelforge/{domain/models.py,adapters/briefing_volc.py,pipeline/routing.py,pipeline/pagespec.py,pipeline/steps.py,pipeline/pipeline.py,pipeline/validators/checks.py,prompts/}`.

## O que continua deterministico

HTML permitido, scripts e interacao com anuncios, dados e identidade do portal,
grounding de fatos criticos, autorizacao de destinos externos, estrutura do
WordPress, checksum de imagens, deduplicacao, estados de publicacao e tetos.
Regras de seguranca nao foram substituidas por confianca cega no LLM.

Compatibilidade: planos antigos sem `editorial` mantem o caminho legado,
sem rotacao dos destinos. Runs ja salvos nao ganham uma arquitetura contextual
por magica; precisam de conciliacao ou novo planejamento. O template LP ainda
tem slots fixos (secoes, FAQ e tres posicoes de CTA), com um a tres destinos.
Links internos de retorno para a LP continuam fora deste contrato porque o
resolvedor distingue /r/ de /rec/. Nao declaramos um layout totalmente livre.

## Piloto aplicado no WordPress

Reescrita supervisionada, nao uma execucao paga do pipeline completo. Mesmos
IDs, slugs, tipos e templates, com leitura autenticada antes e depois. Conferidos
hashes imediatamente antes das escritas para detectar edicao concorrente.

| ID | Papel | Entrega |
| --- | --- | --- |
| 2306 | LP | Apresentacao do guia e acesso direto as duvidas |
| 2309 | Orientacao | Requisitos e escolha do caminho |
| 2312 | Guia | Comparar formacao, modalidade e rotina |
| 2315 | Guia | Consultar oferta do estado sem presumir vaga aberta |
| 2318 | Guia | Usar o portal regional e acompanhar a inscricao oficial |

Todos continuam draft. CTAs como "Ver requisitos", "Comparar cursos" e
"Guia de inscricao" descrevem a leitura. Conexoes permitem consultar outra
duvida sem percorrer uma sequencia obrigatoria. A pagina final entrega os
passos e o canal oficial, sem coletar dados ou realizar inscricoes.

Os quatro artigos foram reescritos, removendo as antigas imagens de corpo e
um widget local de orientacao do 2318. Esse widget apenas alternava elementos
da interface; a inspecao nao identificou envio de telemetria. Nao foi removido
por classificacao de malware e nenhum GTM ou codigo de anuncios foi alterado.

A LP preserva widgets, IDs e estrutura editada pelo operador. Texto, botoes e
referencia de imagem foram atualizados nos campos existentes. A imagem com
anatomia impossivel foi substituida por uma ilustracao de formacao em
gastronomia, sem pessoas, logotipos ou identificacao de unidade real. Alt e
legenda informam que foi gerada por IA e nao representa uma unidade Senac.
A referencia foi alterada nos breakpoints que ja tinham imagem configurada;
nao afirmamos uma revisao completa do layout desktop.

Midia nova: 2365. SHA-256 do JPEG:
`b5f31470ceed1097730ead4278aea5e1e252cbf48bf227e087584d5583550b8a`.
Arquivo: `assets/senac-contextual-20260918/formacao-profissional-ilustrativa.jpg`.

## Provas e limites da verificacao

- Motor: 795 testes aprovados. Backend: 39 testes selecionados aprovados.
- Quinze posts conferidos via WP-CLI: todos draft. SENAI e MEC nao receberam
  esta reescrita contextual.
- REST confirmou campos enviados, status, slug, tipo e template dos cinco posts.
- Links extraidos dos snapshots confirmam os cinco IDs alcancaveis, sem
  auto-link ou destino interno fora dos cinco slugs. A LP supervisionada tem
  quatro destinos distintos contando os links no corpo, enquanto o contrato
  automatizado atual limita a tres destinos na LP. Esse limite do template
  ainda precisa ser separado de links editoriais secundarios antes de reproduzir
  integralmente este piloto por geracao automatica.
- O renderer detectou cache antigo no 2306 apesar do banco atualizado. Cache
  preservado fora do document root e invalidado somente nesse ID. Releitura
  confirmou "Cursos Senac", novo subtitulo, CTA e referencia da nova imagem.
- Renderer das tres LPs: um aviso global, zero aviso canonico duplicado e um
  aviso canonico ainda salvo para fallback. A desduplicacao nao depende de
  apagar permanentemente a identidade editorial do rascunho.
- A comparacao antiga `title_present` deu falso no 2306: o titulo editorial do
  post e o H1 curto sao diferentes. A verificacao posterior leu os headings
  reais. Isso nao equivale a prova visual em navegador autenticado.
- Backups privados antes/depois, propostas e recibos em
  `/Users/mac/Downloads/CreditoUp-revisao-rascunhos-2026-09-18-private/contextual-pilot/`.
  Diretorio 0700, arquivos 0600. Manifesto sanitizado neste diretorio de auditoria:
  `REFINO-CONTEXTUAL-FUNIS-2026-09-18.json`.
- Nao houve publicacao, purge global, mudanca de Nginx, GTM ou monetizacao.
- Lint focal encontrou uma linha longa preexistente em `lp_template.py`;
  nao representa falha funcional. A suite de testes passou integralmente.

## Fontes do piloto

Fontes oficiais consultadas, sem apresentar editais locais como regras nacionais:

- https://www.senac.br/
- https://www.sp.senac.br/bolsas-de-estudo
- https://www.sp.senac.br/unidades
- https://ms.senac.br/cursos/gratuitos/como-se-inscrever
- https://portal.ac.senac.br/psg/editais

## Eficiencia e medicao

Prompts mais curtos e sem instrucoes contraditorias; conteudo nao duplicado no
juiz; bloqueio antes dos custos seguintes. Isso e implementacao, nao economia
percentual comprovada. A LP contextual acrescenta uma chamada de juiz por funil.
Esta rodada nao chamou APIs pagas de pesquisa/redacao do motor. Houve uma
geracao pela ferramenta de imagem, cujo custo nao foi disponibilizado.

Falta um benchmark comparavel por funil: custo total, tokens, tentativas, tempo,
reprovacoes materiais e paginas aprovadas. Medicao de leitura requer eventos
reais e contrato de privacidade: visualizacao, clique editorial com origem e
destino, saida oficial e engajamento, separados de impressao publicitaria.
Nao instalamos novo coletor, pixel nem conversao nesta rodada. Otimizar por
satisfacao/entrega e receita observadas, nunca inflar pageviews ou ad views.

## Pendencias

1. Preview autenticado desktop/mobile do piloto, incluindo hero, dobras,
   quebras de texto, links, FAQs e carregamento dos assets. Renderer nao substitui
   esse teste e nao houve publicacao para viabiliza-lo.
2. Refinar SENAI e MEC usando a arquitetura validada, sem copiar o texto SENAC.
3. Conciliar runs antigos antes de reaproveitar artefatos e recibos de imagens.
4. Benchmark de custo/qualidade e instrumentacao real separados da geracao.
5. Rebuild do grafo bloqueado pelo detector de segredos: `.env_webgo: jwt`,
   preexistente, valor oculto. Nenhum bypass ou alteracao desse arquivo.
   `--check` retornou `current=false`: snapshot de 2026-08-29, commit de build
   `a539dbd`, HEAD `9f70f65`. Roadmap P10-T17 e curadoria cap_funnel atualizados;
   o grafo gerado continua desatualizado.

Nenhum teste ou aviso editorial garante aprovacao em politica de anuncios.

## Correcao da hero pelo motor original, na mesma data

O operador rejeitou a imagem da sala de gastronomia por inadequacao visual.
Ela foi substituida na LP 2306 pela hero produzida pelo `step_image` original:
prompt gpt-4.1, geracao `gpt-image-2` medium 1024x1536, conversao WebP do motor
e revisao visual-v2 gpt-4.1, seguida de inspecao manual. Uma geracao, sem retry.
Cena: aluna adulta em atividade de aprendizagem digital, blusa coral, ambiente
azul e materiais criativos. Dois bracos/maos coerentes, sem marcas visiveis.

Custo registrado no motor: US$ 0,053557 (prompt, imagem e revisao).
Midia 2371, SHA-256 `38635733928a8fa317c00caa81ced063b7dd48051e06463ec058a1c573417863`.
Arquivo local: `assets/senac-contextual-20260918/hero-gpt-image-2-v3.webp`.
Prova detalhada: `HERO-SENAC-GPT-IMAGE-2-2026-09-18.json`.
Alterado somente `00600a83.settings.background_image_mobile`; copy, estrutura,
outros metadados e status draft preservados por leitura REST. A configuracao
desktop, que ja nao continha uma imagem, nao foi redesenhada nesta substituicao.
Backups privados preservados; invalidacao de elementos/CSS restrita ao 2306.
Arquivo publico responde 200 image/webp, com hash identico ao asset aprovado.
Renderer confirmou nova hero, ausencia da hero rejeitada, copy preservada e
ausencia de aviso duplicado. Rebuild/check do grafo repetidos: bloqueio pelo
mesmo segredo preexistente e `current=false`, sem bypass.
O JPEG de gastronomia e o manifesto anterior permanecem como historico, nao
como aprovacao da imagem atual. Esta secao substitui a descricao anterior da hero.
