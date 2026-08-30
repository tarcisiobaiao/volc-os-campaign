# Motores de imagem VOLC — inventário operacional

Atualizado em 26/08/2026.

## A resposta curta

O patrimônio já é muito maior do que “alguns geradores de imagem”. Há quatro capacidades complementares e comprováveis:

1. **Aprova Ad Studio oficial** — recebe um pedido, pesquisa contexto, cria direções visuais, gera variações com IA, transmite progresso real e entrega um pacote.
2. **Positivo Ad Studio** — acrescenta a capacidade mais rara: preservar uma foto real enviada pelo usuário e compor o anúncio ao redor dela por quatro estratégias.
3. **Motor de Imagem VOLC** — reúne contratos, destinos, brand packs, renderizadores, regras e provas de diferentes laboratórios.
4. **PRENSA** — transforma imagem e texto em uma peça gráfica determinística: tipografia real, camadas físicas, medição, adaptação por proporção e gates sobre os pixels finais.

Isso permite uma arquitetura muito mais forte do que chamar uma LLM e aceitar o PNG: a IA produz o que pode variar; o motor de código controla o que precisa ser exato.

## O que é fato, o que é intenção

| Marca | Significado |
|---|---|
| **Executado** | Há arquivo de saída e evidência verificável. |
| **Observado no código** | A capacidade está implementada no código auditado, mas não foi executada nesta rodada. |
| **Documentado** | Existe contrato ou decisão escrita; pode ainda não estar implementado. |
| **Declarado** | Informação fornecida pelo dono, ainda sem prova independente. |

Nenhuma dessas marcas significa que o motor já está integrado ao VOLC O.S.

## Autoridade dos projetos

### 1. Aprova Ad Studio oficial

**Path canônico**

`/Users/mac/Library/CloudStorage/GoogleDrive-tarcisio@agenciavolc.com.br/Drives compartilhados/VOLC/VOLC/CLIENTES/IESDE/2026/Aprova-Ad-Sstudio`

**Versão observada:** Git `a1d9ae65bb5d18097d33b7e16d86dcd0713779b8`.

**Papel:** produto de geração agentic para Aprova Concursos.

**Observado no código:**

- front Vite/React e backend FastAPI;
- endpoints `/generate` e `/generate/stream`;
- pipeline Brand Guardian → pesquisa → estratégias em paralelo → geração limitada por semáforo → revisão → pacote;
- SSE com fases, início, sucesso ou falha de cada imagem e encerramento;
- provedores intercambiáveis Gemini, OpenAI Image e mock;
- tipos de conteúdo `meta-ads`, `news` e `pinterest`;
- request aceita `dimensions` exatas, e o caminho `gpt-image-2` transforma o alvo numa dimensão nativa válida, orienta a composição para a proporção pedida e entrega o PNG exatamente no tamanho solicitado;
- 12 proporções reconhecidas pelo backend e oito formatos prontos no front, sem limitar o contrato a esses presets;
- retentativa de falhas transitórias e cancelamento após erro fatal;
- logo Aprova ou upload de logo próprio;
- testes de erros, tamanhos, eventos do orquestrador e streaming.

**Limite importante:** a revisão atual confere integridade técnica básica da imagem. Ela não oferece os gates tipográficos, geométricos e de contraste final da PRENSA.

**Opção full-LLM multi-formato:** a peça inteira — cena, texto e composição — pode ser criada pela LLM já pensando no canvas solicitado. O provider preserva a proporção durante a geração nativa quando ela está dentro do envelope implementado e usa Pillow para chegar aos pixels finais sem esticar. Se precisar recorrer a um tamanho padrão ou receber proporção extrema, o acabamento atual é `cover` com crop central; isso precisa aparecer na proveniência.

**Estado do diretório:** árvore de trabalho externa está suja, com arquivos rastreados removidos e ambientes/builds locais não rastreados. Este inventário não alterou nem limpou nada.

### 2. Aprova do Desktop — ramo divergente, não autoridade

`/Users/mac/Desktop/SISTEMAS/IESDE/Aprova-Ad-Sstudio`

Esse ramo contém uma interface de intake mais estruturada para IES/curso e integração direta com n8n, mas não é o Aprova oficial informado pelo dono. Deve ser tratado como fonte de ideias de briefing, nunca como origem canônica do motor.

### 3. Positivo Ad Studio

**Path canônico**

`/Users/mac/Library/CloudStorage/GoogleDrive-tarcisio@agenciavolc.com.br/Drives compartilhados/VOLC/VOLC/CLIENTES/CURSO POSITIVO/IMAGE-SYSTEM/positivo-ad-studio`

**Versão observada:** Git `9d0035d`.

**Papel:** estúdio de anúncios com preservação e composição de foto real.

**Observado no código:**

- a mesma fundação FastAPI + Vite + provedores do Aprova, já bastante especializada;
- upload e análise visual da foto real antes do layout;
- seleção da zona de foto conforme sua geometria, evitando forçar uma foto horizontal em recorte vertical estreito;
- quatro modos de composição: nativo pelo modelo, visão por coordenadas, chroma key e híbrido;
- `PhotoAnalyzer`, `VisionZoneAgent`, `CoordinateCompositor` e `PhotoAdComposer`;
- no modo híbrido, o modelo produz apenas o bloco gráfico e o código preserva a fotografia separadamente;
- fontes e marcas vendorizadas, brand config e rotação criativa;
- o mesmo contrato de dimensão exata e provider `gpt-image-2` do Aprova, permitindo geração full-LLM no canvas desejado além dos presets da interface;
- 14 proporções/dimensões no orquestrador e onze formatos prontos no front;
- testes de geração, saúde, falhas, schemas, tamanhos, eventos e rotação.

**Valor para o VOLC:** prova que uma foto verdadeira pode permanecer verdadeira, enquanto o restante da peça é gerado ou renderizado ao redor dela.

**Duas opções no próprio Positivo:** sem foto, ou no modo nativo, a imagem final pode ser 100% gerada pela LLM em qualquer dimensão-alvo processável; com preservação, os compositores mantêm o asset real e montam o restante ao redor dele. Esses caminhos precisam permanecer escolhas explícitas no futuro motor VOLC.

**Limite importante:** ainda é um produto especializado por marca. Antes de virar serviço comum, branding, contratos e segredos precisam sair da lógica específica do cliente.

### 4. Motor de Imagem VOLC

**Path canônico**

`/Users/mac/Desktop/Volc Mídia Global/motor-imagem`

**Papel:** parque de engenharia e contrato comum, não um único aplicativo.

O índice de extração registra 403 arquivos úteis e 4,7 MB vindos de um parque original de 2,2 GB, excluindo saídas, ambientes e dependências. A pasta contém:

- `dace`: contratos, planejamento, medidas, topologias, render e gates;
- `positivo`: snapshot das peças centrais do motor Positivo;
- `bancada-n8n`: automações e experimentos de geração;
- `contrato`: nichos, skins, destinos e resolução;
- `compartilhado`: especificação PRENSA, POC e provas;
- `destinos`: regras de empacotamento e formatos;
- `prensa`: API Python de render fail-closed.

Não é um repositório Git único. Por isso, cada integração deve guardar hash do contrato, hash dos assets, versão do brand pack e evidência do render.

## PRENSA: o núcleo determinístico

A PRENSA implementa a divisão mais valiosa do parque:

> A LLM compõe a cena e os assets que podem variar. Código determinístico controla texto, fonte, geometria, camadas, contraste, formatos e aprovação.

### O pipeline observado

1. **Pauta** — tema, cliente e destinos.
2. **Guard** — compliance antes do custo.
3. **Resolve** — tokens, brand pack, layout e variantes viram uma especificação literal e hasheada.
4. **Assets** — banco de imagens ou geração por IA; a composição já provisiona a zona de texto.
5. **Compile** — Chromium mede a tipografia com as mesmas fontes do render.
6. **Render** — HTML/CSS/SVG absoluto vira PNG sem refazer o fit.
7. **Gates** — DOM e pixels finais verificam overflow, contraste, clipping, clearance e orçamento de acento.
8. **Pacote** — variantes próprias de cada destino, com ledger auditável.

### O que ele controla por código

- fontes reais vendorizadas e verificadas por hash;
- tipografia dual, runs de acento e hierarquia editorial;
- grain, halation, light leak, vignette, ink bleed, varnish e dissolução;
- máscaras, gradientes, scrim calculado por luminância, contraste e safe areas;
- composição em duas passadas: primeiro estabiliza o layout, depois mede;
- fail-closed: peça reprovada não é promovida como saída final;
- determinismo por bytes em ambiente pinado ou por geometria entre máquinas;
- recompilação por canvas; nunca crop cego de uma peça-mãe.

### O modo sem imagem generativa é uma capacidade de primeira classe

O snapshot completo do POC encontrou 64 saídas renderizadas no `out` canônico:
26 são `typography_only`, 12 são gráficos + tipografia determinísticos e 26 são
híbridas com asset de IA. Portanto, PRENSA não pressupõe uma imagem-base.

`carrossel_produtividade_metodo90_s02.png` é prova direta: o spec não contém
`assets[]`; a peça é composta por tipografia real, frames, retângulos, paginação,
grain, vazamento e vinheta. A mesma estrutura foi renderizada em base, FX, FXD,
Titanium e Dossier — 20 PNGs — mostrando que conteúdo e pele podem evoluir
separadamente.

O catálogo exaustivo, os hashes e a matriz de extração estão em:

- `CATALOGO-PRENSA-E-MOTOR-IMAGEM.md`;
- `snapshots/motor-imagem-2026-08-26.json`;
- `PACOTE-REUSO-MOTOR-IMAGEM.json`.

## Provas visuais executadas

### VOLC News — iPhone laranja

Asset base:

`/Users/mac/Desktop/Volc Mídia Global/motor-imagem/compartilhado/prensa-poc/out/volcnews_iphone_laranja.png`

| Destino | Arquivo | Dimensão observada | Prova |
|---|---|---:|---|
| Base editorial / 4:5 | `volcnews_iphone_laranja.png` | 1088×1360 | `PIXEL_READY`, 9/9 checks |
| Performance Max paisagem | `volcnews_iphone_laranja__pmax__img_191x1.png` | 1200×628 | veredito `ok: true` |
| Performance Max quadrado | `volcnews_iphone_laranja__pmax__img_1x1.png` | 1200×1200 | veredito `ok: true` |
| Performance Max retrato | `volcnews_iphone_laranja__pmax__img_4x5.png` | 1088×1360 | veredito `ok: true` |
| Demand Gen vertical | `volcnews_iphone_laranja__demandgen__img_9x16.png` | 1080×1920 | veredito `ok: true` |

A inspeção visual mostra recomposição real: no 1.91:1, a manchete sobe e reduz; no 9:16, a imagem ocupa o topo e o bloco editorial desce. Não é o mesmo layout cortado.

Há especificações resolvidas adicionais para Demand Gen, Display, orgânico, PMax e YouTube. Nem todas possuem PNG materializado nesta pasta; portanto elas são contrato resolvido, não saída executada.

### Kintsugi planejado

Asset:

`/Users/mac/Desktop/Volc Mídia Global/motor-imagem/compartilhado/prensa-poc/out/kintsugi_planejado.png`

Dimensão observada: 1088×1360. Resultado: `PIXEL_READY`, 12/12 checks.

A cena deixa um campo escuro à direita e o render escreve ali com tipografia real, acento, subtítulo e handle. É a prova concreta do fluxo em duas etapas: imagem gerada com espaço semântico e composição final controlada.

## Matriz de capacidades

| Capacidade | Aprova oficial | Positivo | PRENSA |
|---|---:|---:|---:|
| Intake de campanha | forte | médio | contrato mínimo |
| Pesquisa e blueprint por LLM | sim | sim | pode consumir |
| Geração full LLM | sim | sim | cadeia de assets |
| Foto real preservada | não especializada | **sim** | previsto para fusão |
| Tipografia exata | delegada ao modelo | parcial | **sim** |
| Efeitos e layers determinísticos | baixo | composição espacial | **sim** |
| Multi-proporção | full-LLM para dimensão exata; 8 presets de UI | full-LLM para dimensão exata; 11 presets e 14 mappings | **re-resolve layout** |
| Streaming de progresso | **sim** | **sim** | ainda biblioteca/CLI |
| Gates sobre pixels finais | técnico básico | técnico básico | **DOM + pixel** |
| Pacote por destino de mídia | ZIP genérico | ZIP genérico | **contrato por destino** |
| Serviço comum do VOLC O.S. | não | não | não |

## Duas estratégias oficiais para criar formatos

### A. Full-LLM multi-formato — Aprova e Positivo

O contrato recebe dimensão exata, como `1200x628`, `1080x1350` ou `1080x1920`. O provider:

1. calcula um tamanho nativo aceito pelo modelo;
2. preserva a proporção-alvo dentro do envelope implementado;
3. informa à LLM o canvas e a entrega final;
4. gera a peça completa por IA;
5. redimensiona para os pixels finais com LANCZOS;
6. usa `cover` e crop apenas quando a proporção da resposta diverge ou exige fallback.

Essa estratégia não depende dos cards da interface; os presets são atalhos. É excelente para velocidade, exploração e composições livres. Como texto e tipografia estão rasterizados pela própria LLM, exatidão editorial e repetibilidade são menores.

### B. Recompilação determinística — PRENSA

A imagem-base pode ser gerada por IA, mas cada destino recompila texto, tipografia, layers, safe areas e gates. É a estratégia indicada quando a copy precisa ser literal, a fonte precisa ser real e o mesmo sistema visual deve sobreviver a vários canvases.

### Escolha por job

- `full_llm`: exploração rápida e peça integralmente criada pela IA;
- `typography_only`: texto, formas e atmosfera inteiramente por código, sem provider de imagem;
- `deterministic_graphics`: texto + SVG/data-viz inteiramente por código;
- `photo_preserved`: foto real + composição controlada;
- `prensa_hybrid`: cena/asset por IA + acabamento determinístico;
- `full_llm_then_prensa`: geração aprovada vira matéria-prima para finalização e variantes.

“Qualquer formato” fica registrado com uma ressalva factual: a saída exata pode ser produzida para qualquer dimensão positiva processável, mas composição nativa fiel sem crop depende do envelope de proporção do provider observado. Para extremos, PRENSA ou regra específica é o caminho seguro.

## Arquitetura-alvo no VOLC O.S.

### Fundação interna que já chegou durante esta auditoria

O commit `6eed77f` criou `volc_ads/criativo/`: contrato de asset e procedência, requisitos por canal, validação, porta assíncrona de motor, catálogo por hash e adaptadores. São 80 testes no pacote e 343 provas verdes no `volc_ads` reportadas pela entrega.

Essa camada **não gera imagem, não sobe asset e não chama o Google**. Ela é justamente a fronteira interna que faltava para receber motores externos sem importá-los diretamente. Hoje há um adaptador real para o gerador de imagem injetado do FunnelForge e um motor falso determinístico. Aprova, Positivo e PRENSA ainda não têm adaptadores.

O contrato interno já resolve parte importante da rastreabilidade — identidade por conteúdo, procedência obrigatória, medidas desconhecidas como `None`, falha por asset e deduplicação. O envelope editorial maior deste inventário (`CreativeJob`, brand pack, gates, aprovação e vínculo posterior) continua sendo a próxima camada, não uma substituição desse núcleo.

```text
Briefing no Hub
  → Creative Job versionado
  → contrato e brand pack
  → estratégia/pesquisa
  → assets por provedor (LLM, banco ou foto real)
  → compositor de foto real quando necessário
  → PRENSA: tipografia + layers + variantes
  → gates e evidências
  → pacote por canal
  → revisão humana
  → Google Ads validate_only / Meta preview
  → autorização explícita de publicação
```

O VOLC O.S. não deve importar esses repositórios diretamente nem fundi-los numa pasta gigante. A porta interna estável já começou em `volc_ads/criativo`; agora precisa receber adaptadores por motor e o envelope de job. Cada job precisa registrar:

- pedido e versão do contrato;
- cliente, brand pack e destinos;
- motor e versão usados;
- prompt/blueprint sanitizado;
- assets de entrada e seus hashes;
- variantes e dimensões;
- gates, avisos e recusas;
- custo e duração;
- aprovador e decisão;
- vínculo posterior com campanha, asset group, anúncio ou publicação.

A decisão completa de extração está em `ADR-001-SERVICO-CRIATIVO-VOLC.md`: microserviço dentro do monorepo, runtime separável, sem transformar o Positivo num núcleo hardcoded.

## Ordem recomendada de integração

### I0 — Patrimônio conhecido

- [x] Corrigir o path canônico do Aprova.
- [x] Separar projeto oficial de cópia divergente.
- [x] Inventariar Aprova, Positivo, Motor de Imagem e PRENSA.
- [x] Registrar provas reais e limitações sem promover intenção a implementação.
- [ ] Cadastrar esses motores no futuro Cofre de Ativos.

### I1 — Contrato comum

- [x] Criar contrato interno de asset, procedência, requisitos, validação, catálogo e porta de motor.
- [ ] Definir o envelope de `CreativeJob`, `CreativeVariant`, `BrandPack`, aprovação e `GateResult` sobre esse núcleo.
- [ ] Mapear os payloads Aprova/Positivo/PRENSA para adaptadores, sem alterar os motores primeiro.
- [x] Normalizar a primeira matriz de requisitos de Display, Demand Gen e Performance Max, preservando `null` onde a fonte oficial não confirma número.
- [x] Exigir identidade por hash e procedência no catálogo interno.

### I2 — Primeiro corte que destrava mídia

- [ ] Escolher uma única vertical Google com aceite operacional claro.
- [ ] Gerar o pacote mínimo pelo contrato comum.
- [ ] Renderizar e aprovar variantes obrigatórias.
- [ ] Enviar primeiro para `validate_only`, nunca publicar direto.
- [ ] Mostrar preview, faltas e provas no Hub.

### I3 — Serviço criativo interno

- [ ] Criar gateway autenticado do VOLC O.S. e fila de jobs.
- [ ] Isolar segredos dos provedores no servidor.
- [ ] Persistir eventos de progresso em vez de depender apenas de SSE.
- [ ] Tornar workers idempotentes e retomáveis.
- [ ] Adicionar armazenamento, expiração e política de dados para fotos reais.

### I4 — Fusão das forças

- [ ] Levar a composição de foto real do Positivo à cadeia PRENSA.
- [ ] Converter marcas em brand packs, removendo literais de cliente do núcleo.
- [ ] Rodar torture set por formato, marca e volume de texto.
- [ ] Integrar Meta Ads e orgânico pela mesma base, com contratos de canal diferentes.

## Riscos que não podem desaparecer do mapa

1. **Bifurcação:** existem ramos e snapshots divergentes. Novo recurso deve nascer no contrato comum, não em mais uma cópia.
2. **Qualidade falsa:** integridade de arquivo não equivale a qualidade visual. Gate precisa medir DOM e pixel.
3. **Crop disfarçado:** adaptar uma imagem 4:5 com center crop não substitui recomposição por destino.
4. **Fonte não governada:** tipografia remota ou sem licença/hash quebra determinismo e rastreabilidade.
5. **Foto real:** exige política de retenção, consentimento, acesso e exclusão.
6. **Custo:** geração paralela precisa orçamento, limites e idempotência.
7. **Regras de plataforma:** formatos e requisitos de Google/Meta mudam; o contrato deve ser atualizado contra documentação oficial antes do lançamento.
8. **Diretórios sujos:** os projetos externos têm estado de trabalho próprio. Integração não autoriza limpeza, commit ou sobrescrita neles.

## Decisão arquitetural

Preservar os motores como laboratórios/produtos especializados e evoluir `volc_ads/criativo` para um **Creative Engine Registry + Creative Job Contract**. O Registry responde “quem sabe fazer o quê”; o contrato permite orquestrar sem acoplar o Hub à implementação de um cliente.

Essa decisão aproveita tudo que já existe sem transformar o legado em dependência invisível.
