# SPEC — Estúdio Criativo VOLC

Status: proposta pronta para implementação após convergência do redesign de Tráfego  
Data: 27/08/2026  
Autoridades: `PRODUCT.md` → `DESIGN.md` → esta SPEC  
Fontes patrimoniais: Aprova Ad Studio, Positivo Ad Studio, PRENSA e Motor de Vídeo VOLC

## 1. Resultado esperado

Criar uma capacidade global do VOLC O.S. para produzir, versionar, validar, aprovar e distribuir imagens e vídeos. Ela deve atender três famílias sem misturá-las:

1. mídia paga em Google e Meta;
2. conteúdo orgânico;
3. exportação ou entrega manual.

O Estúdio produz patrimônio criativo. Tráfego, Conteúdo e integrações de publicação consomem esse patrimônio por contratos próprios. Gerar não significa aprovar. Aprovar não significa publicar. Publicar organicamente não autoriza gastar mídia.

## 2. Decisão arquitetural

```text
                       ESTÚDIO CRIATIVO
                  imagem · vídeo · variações
                              │
                     Biblioteca de Ativos
              identidade · hash · direitos · versões
                              │
          ┌───────────────────┼────────────────────┐
          ▼                   ▼                    ▼
   Pacote de mídia      Pacote orgânico      Pacote de exportação
   Google / Meta        social / editorial   download / entrega
          │                   │
   aprovação de gasto   aprovação editorial
          │                   │
   adapter de campanha  adapter de publicação
```

Existe um único núcleo de produção, uma biblioteca e múltiplos pacotes de destino. Nenhum motor guarda credencial de plataforma ou publica diretamente.

## 3. Não objetivos

- Não copiar os frontends completos de Aprova ou Positivo.
- Não transformar Positivo em núcleo do VOLC O.S.
- Não chamar pastas locais diretamente pelo navegador.
- Não construir um editor de vídeo livre equivalente a Premiere ou After Effects.
- Não guardar bytes grandes em colunas relacionais.
- Não guardar chaves de provider no browser, `localStorage`, banco editorial ou repositório.
- Não publicar em Google, Meta ou redes sociais como efeito colateral de uma geração.
- Não fingir progresso, render concluído, aprovação ou compatibilidade de destino.

## 4. Vocabulário canônico

### CreativeProject

Intenção durável que pode gerar muitas versões. Exemplo: “FGTS Saque-Aniversário, campanha de aquisição e posts educativos”.

### CreativeBrief

Objetivo, audiência, mensagem, marca, destino pretendido, restrições, fatos e referências.

### CreativeJob

Execução imutável de um brief por um motor e versão específicos. Retry cria uma tentativa identificada; alteração material cria nova versão.

### AssetMaster

Saída criativa principal preservada. Pode ser imagem, vídeo, áudio, texto, logo ou arquivo auxiliar.

### Rendition

Derivação de um master para dimensão, proporção, idioma, duração ou uso específico. Nunca apaga o master.

### DestinationPackage

Seleção versionada de assets, copy e metadados validada para um destino, como `google_display`, `meta_reels` ou `facebook_organic`.

### Approval

Decisão humana com pessoa, instante, escopo, versão e ressalvas. Aprovação é específica por master ou pacote.

### Delivery

Tentativa explícita de anexar, exportar, agendar ou publicar um pacote. Possui idempotência e recibo. Não pertence ao motor.

## 5. Fronteiras blindadas

| Camada | Pode | Não pode |
|---|---|---|
| Estúdio | criar brief, job e versões | publicar ou alterar campanha |
| Motor | renderizar e emitir evidências | conhecer token de Google, Meta ou social |
| Biblioteca | persistir arquivos, metadados e relações | considerar importação como aprovação |
| Pacote de destino | validar regras do destino | mutar plataforma |
| Aprovação | autorizar versão e finalidade | autorizar finalidade diferente por herança |
| Entrega | executar destino explicitamente aprovado | reutilizar autorização vaga |

## 6. Arquitetura de navegação

O Estúdio é uma área principal de Produção, não Configuração e não subaba exclusiva de Tráfego.

```text
/criativos
├── /criativos/novo
├── /criativos/imagens/novo
├── /criativos/videos/novo
├── /criativos/jobs/:creativeJobId
├── /criativos/biblioteca
├── /criativos/assets/:assetId
├── /criativos/aprovacoes
└── /criativos/brand-packs
```

Rotas de integrações e providers permanecem em Configurações. Segredos nunca aparecem no Estúdio.

## 7. Home do Estúdio

Objetivo: retomar trabalho e identificar bloqueios, não exibir métricas decorativas.

### Cabeçalho

- título `Estúdio Criativo`;
- frase curta sobre produção e aprovação;
- ação primária `Criar`;
- seletor Imagem ou Vídeo apenas quando a ação for iniciada.

### Workspace

- trabalhos em andamento;
- aguardando sua revisão;
- falhas que pedem decisão;
- aprovados recentemente;
- atalhos para Biblioteca e Brand Packs.

Cada linha mostra projeto, tipo, formato, motor, etapa real, custo conhecido, pessoa responsável e horário da última mudança. Não usar percentual quando o motor não medir progresso determinístico.

## 8. Experiência de imagem

### 8.1 Padrões reaproveitados

Do Aprova:

- tipo de conteúdo;
- formato e proporção;
- objetivo;
- quantidade de variações;
- progresso por eventos;
- falha isolada por saída;
- galeria e download.

Do Positivo:

- brand pack;
- logo;
- foto real preservada;
- preview do insumo;
- composição com asset controlado.

### 8.2 Padrões rejeitados

- API key configurada pelo navegador;
- brand pack cuja autoridade é `localStorage`;
- glow, glass e decoração promocional no workspace;
- formulário destruído ao iniciar geração;
- resultados transitórios apenas em object URL;
- ZIP como única forma de preservação;
- ação `gerar novamente` que perde o contexto anterior.

### 8.3 Fluxo

```text
Objetivo
  → modo de produção
  → marca e insumos
  → formatos e destinos pretendidos
  → quantidade e limites
  → revisão do pedido
  → geração
  → inspeção das variantes
  → aprovação
  → pacotes de destino
```

### 8.4 Modos oficiais

- `typography_only`;
- `deterministic_graphics`;
- `full_llm`;
- `photo_preserved`;
- `prensa_hybrid`;
- `full_llm_then_prensa`.

Cada modo explica velocidade, precisão de copy, uso de provider, possibilidade de crop e rastreabilidade. O operador escolhe finalidade, não implementação interna.

### 8.5 Tela de resultados

Mostrar:

- master e renditions;
- formato e dimensões;
- modo e motor;
- custo e duração conhecidos;
- hash e procedência em detalhe técnico progressivo;
- gates executados;
- falhas por variante;
- seleção para aprovação;
- ação `Criar pacote de destino`.

Uma variante reprovada não some. Ela permanece com motivo e pode originar nova versão.

## 9. Experiência de vídeo

### 9.1 Princípio

O frontend dirige um contrato narrativo e inspeciona evidências. Não oferece edição livre por frames na primeira versão.

O motor já recebe apenas `tema` como obrigatório e pode resolver nicho, skin, voz, hook e arco. A interface começa simples e revela controles avançados sob demanda.

### 9.2 Dois modos

#### Rápido

- tema;
- brand pack;
- destino pretendido;
- idioma;
- duração;
- objetivo.

O motor propõe nicho, skin, hook, voz, elementos, beats e CTA. Tudo permanece revisável antes do render.

#### Dirigido

Além dos campos rápidos:

- nicho e skin;
- tipo, linha, persona e cenário do hook;
- voz, estilo e velocidade;
- roteiro por beats;
- fatos, fontes e calibragem;
- assets reais, papel, licença e crédito;
- identidade e tipografia;
- elementos de retenção;
- CTA e destino;
- regras extras de compliance.

### 9.3 Workspace de vídeo

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Vídeo: título do projeto        Brand · 9:16 · 45s          estado do job   │
├───────────────────┬───────────────────────────────────────┬──────────────────┤
│ DIREÇÃO           │ PREVIEW E STORYBOARD                  │ INSPEÇÃO         │
│ destino           │ ┌───────────────────────────────────┐ │ contrato         │
│ tema              │ │                                   │ │ fatos e fontes   │
│ objetivo          │ │          PLAYER                    │ │ voz e assets     │
│ skin              │ │                                   │ │ custo            │
│ idioma            │ └───────────────────────────────────┘ │ QA técnico       │
│ duração           │ Hook · Contexto · Virada · Prova...   │ QA visual        │
│ hook              │ [beat 1] [beat 2] [beat 3] [beat 4]  │ compliance       │
├───────────────────┴───────────────────────────────────────┴──────────────────┤
│ salvo · versão 3                 [Validar contrato] [Gerar nova versão]      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 9.4 Storyboard semântico

O trilho representa intenção narrativa:

```text
Hook → Contexto → Virada → Prova → Revelação → CTA
```

Cada beat mostra:

- copy;
- papel narrativo;
- visual planejado;
- asset e origem;
- duração prevista e medida;
- elemento de retenção;
- status e pendências.

Reordenar beats ou renderizar cena isolada só aparece quando o runtime suportar a operação com prova. O frontend não simula capacidade.

### 9.5 Painel de inspeção

- contrato solicitado e contrato resolvido;
- slots ainda não preenchidos;
- fontes e calibragem dos fatos;
- licenças e créditos;
- conteúdo sintético e disclosure;
- provider, modelo e versão;
- voz e parâmetros;
- assets utilizados;
- custo estimado e realizado;
- QA técnico;
- QA visual;
- gate de publicação.

O painel responde por que a versão pode ou não ser usada.

### 9.6 Progresso real

Eventos possíveis:

- resolvendo contrato;
- aguardando fatos;
- preparando roteiro;
- gerando voz;
- produzindo assets;
- renderizando;
- compondo som;
- executando QA técnico;
- executando QA visual;
- aguardando revisão;
- concluído;
- falhou;
- cancelado.

O usuário pode sair da rota. O job continua no backend. Reconexão recupera o estado persistido e não duplica custo.

### 9.7 Versionamento

```text
Projeto de vídeo
├── v1 · QA técnico reprovado
├── v2 · aprovada internamente
└── v3 · pacote Meta Reels aprovado
```

Correção nunca sobrescreve a versão anterior. Cada versão preserva input, contrato resolvido, assets, hashes, custos, gates e aprovações.

## 10. Biblioteca global

A biblioteca atual de Tráfego é uma projeção de uso publicitário. A biblioteca global passa a ser autoridade dos assets e oferece projeções específicas para Tráfego e Conteúdo.

### Visões

- todos;
- imagens;
- vídeos;
- áudio;
- textos;
- logos e brand assets;
- aguardando revisão;
- aprovados;
- com restrição;
- em uso;
- uso não apurado.

### Asset detail

- preview;
- master e renditions;
- projeto e jobs de origem;
- motor e versão;
- procedência e hashes;
- dimensões, duração, MIME e tamanho;
- direitos, créditos e disclosure;
- gates;
- aprovações;
- pacotes de destino;
- campanhas, anúncios ou publicações que o utilizam;
- histórico imutável de versões.

`uso desconhecido` não é `sem uso`. `validação ausente` não é `não serve`.

## 11. Pacotes de destino

Primeiros identificadores:

- `google_display`;
- `google_demand_gen`;
- `google_performance_max`;
- `google_video`;
- `meta_feed`;
- `meta_stories_reels`;
- `facebook_organic`;
- `instagram_organic`;
- `youtube_shorts`;
- `pinterest_organic`;
- `manual_export`.

O pacote pode transformar dimensão, crop, composição, copy, duração, legenda e metadados, mas registra toda derivação. Regras de plataforma possuem versão e data de verificação.

## 12. Fluxos entre produtos

### Do Hub de Tráfego

```text
/criativos/novo?origem=trafego&destino=google_display&retorno=/trafego/criar/:id
```

Ao concluir, o Estúdio retorna IDs de assets ou pacote. Tráfego não recebe bytes em estado React e não incorpora o motor.

### Do Conteúdo orgânico

```text
/criativos/novo?origem=conteudo&destino=facebook_organic&retorno=/conteudo/:id
```

Conteúdo recebe pacote aprovado. Agendamento e publicação pertencem a outra autorização.

### Standalone

O operador cria patrimônio sem destino imediato. `destino futuro` permanece `null`, não `manual_export` inventado.

## 13. Contrato de dados mínimo

```text
CreativeProject
  id, title, objective, brand_pack_id, owner_id, created_at

CreativeBrief
  id, project_id, type, mode, objective, audience,
  requested_destinations[], constraints, facts[], references[]

CreativeJob
  id, brief_id, engine_id, engine_version, status,
  attempt, idempotency_key, input_hash, cost_estimate,
  cost_actual, started_at, finished_at, failure

AssetMaster
  id, job_id, kind, storage_key, content_hash, mime,
  width, height, duration_ms, provenance, rights

Rendition
  id, master_id, storage_key, transform, content_hash,
  destination_hint, validation

DestinationPackage
  id, project_id, destination, rule_version, assets[], copy,
  validation, status

Approval
  id, subject_type, subject_id, version, purpose,
  decision, actor_id, decided_at, reservations

Delivery
  id, package_id, target, operation, idempotency_key,
  authorization_id, status, receipt
```

Ausência de valor usa `null`. Zero é valor medido. Falha é objeto tipado, nunca string crua do provider.

## 14. Persistência e storage

- Metadados e relações vivem no Supabase oficial `database.agenciavolc.com.br`.
- Arquivos vivem em object storage acessado pelo backend, preferencialmente no storage oficial já governado.
- O banco guarda `storage_key`, hashes e metadados, não grandes bases64.
- Preview usa URL assinada curta e renovável.
- Originais privados permanecem privados até aprovação ou entrega.
- Derivações mantêm referência ao master.
- Exclusão lógica não remove arquivo utilizado, aprovado ou sob retenção.

## 15. Segurança e governança

- Providers e plataformas são chamados somente pelo backend.
- Segredos usam ambiente ou secret manager, nunca payload persistido ou bundle.
- Todo job tem dono, escopo e limite de custo.
- Retry usa idempotência e não duplica cobrança silenciosamente.
- Cada job usa workspace isolado; dois renders não compartilham `props`, `timings`, `ledger` ou saída.
- Cancelamento é explícito e não finge que provider já acionado deixou de cobrar.
- Foto real registra consentimento, finalidade, retenção e acesso.
- Asset de terceiro registra licença, crédito e origem.
- Conteúdo sintético registra disclosure quando aplicável.
- Aprovação é específica por versão e finalidade.
- Publicação e gasto exigem autorização independente.
- Recibos não armazenam segredo nem resposta bruta sensível.

Papéis futuros:

- `creator`: cria e revisa rascunhos próprios;
- `reviewer`: aprova qualidade e compliance;
- `publisher`: entrega pacote aprovado;
- `admin`: governa engines, brand packs e regras.

## 16. Estados de interface

| Estado | Interface |
|---|---|
| Nunca executado | Explica o que será necessário. |
| Na fila | Mostra posição apenas se for real. |
| Em execução | Mostra etapa observada e permite sair da tela. |
| Parcial | Preserva saídas boas e falhas por item. |
| Falhou | Mostra causa sanitizada e recuperação segura. |
| Cancelando | Distingue pedido de cancelamento e confirmação. |
| Aguardando insumo | Nomeia campo, fato, licença ou aprovação ausente. |
| Aguardando revisão | Preview e evidências disponíveis, sem liberar entrega. |
| Aprovado | Declara finalidade e versão aprovadas. |
| Entregue | Mostra destino e recibo. |

## 17. Responsividade e acessibilidade

- Criação e revisão profunda priorizam desktop e tablet.
- Mobile permite acompanhar job, reproduzir preview, comentar, aprovar ou reprovar quando o contexto couber.
- O workspace de três zonas vira abas `Direção`, `Preview` e `Inspeção` em telas estreitas.
- Player preserva controles nativos acessíveis.
- Storyboard funciona por teclado e não depende de drag.
- Estado combina ícone, palavra e descrição.
- Foco visível, labels persistentes, ordem lógica e WCAG 2.2 AA.
- Movimento respeita `prefers-reduced-motion`.
- Nenhum vídeo inicia som automaticamente.

## 18. Performance

- Thumbnails e previews carregam sob demanda.
- Vídeo usa streaming e poster; não baixa o master inteiro para listar biblioteca.
- Eventos de job podem usar SSE com cursor de retomada.
- Saídas não permanecem apenas em memória do navegador.
- Galerias virtualizam quando necessário.
- Hash de arquivo grande é calculado em worker/backend sem bloquear UI.

## 19. Fases de implementação

### C0 — Contrato e shell

- rotas globais;
- tipos compartilhados;
- home, navegação e estados;
- endpoints de job definidos;
- nenhuma geração fingida.

### C1 — Primeira imagem real

- adapter `full_llm`;
- job persistido;
- SSE retomável;
- storage;
- galeria e aprovação;
- três formatos reais;
- sem publicação externa.

### C2 — Imagem para Google Display

- pacote `google_display`;
- ponte de asset;
- validação;
- seleção pelo Hub;
- `validate_only` somente com autorização separada;
- campanha pausada somente com autorização separada.

### C3 — Vídeo observado

- importar um build existente sem alterar o motor;
- mostrar player, contrato, ledger, custos disponíveis e QA;
- provar que o VOLC O.S. entende o patrimônio atual.

### C4 — Primeiro vídeo pelo Estúdio

- runtime isolado por job;
- resolução real do contrato;
- vídeo 9:16 orgânico;
- QA técnico e visual;
- aprovação e exportação manual;
- zero publicação automática.

### C5 — Vídeo multicanal

- Meta Reels;
- YouTube Shorts;
- Demand Gen;
- Performance Max e Google Video apenas após requisitos atuais comprovados.

### C6 — Orgânico e aprendizado

- pacote de publicação;
- agendamento autorizado;
- recibo;
- métricas vinculadas à versão criativa;
- aprendizado retorna ao projeto e ao brand pack sem reescrever fatos históricos.

## 20. Critérios de aceite

- O Estúdio é global e acessível fora de Tráfego.
- Imagem e vídeo usam o mesmo modelo de projeto, job, asset, versão e aprovação.
- A interface de imagem preserva o que funcionava no Aprova e Positivo sem copiar seus riscos.
- O vídeo começa simples e permite inspeção profunda sem expor JSON cru como UX principal.
- Um job continua após sair da rota e é retomado sem duplicação.
- Nenhuma saída é perdida ao recarregar a página.
- Toda versão possui origem, motor, hash, custo conhecido e gates.
- Uma variante falha sem apagar as demais.
- Nenhuma aprovação vale para outra versão ou finalidade por inferência.
- Tráfego e Conteúdo selecionam assets por ID e pacote, não por path local.
- Nenhum segredo entra no browser.
- Nenhuma geração publica ou gasta mídia.
- Um vídeo existente do motor aparece com contrato, ledger e QA reais.
- Uma imagem real percorre criação, biblioteca, aprovação e pacote Display.
- Um vídeo 9:16 percorre criação, QA, aprovação e exportação.
- Temas claro e escuro, teclado, foco e mobile passam na revisão.
- Build, tipos e testes ficam verdes sem regressão funcional.

## 21. Evidências finais

- SHAs e ownership dos arquivos;
- screenshots desktop e mobile, claro e escuro;
- job real de imagem e job real de vídeo;
- prova de reconexão do job;
- prova de idempotência;
- prova de versão imutável;
- prova de segredo ausente do bundle;
- prova de zero publicação ou mutação externa;
- gates e achados adversariais;
- atualização única do roadmap, curadoria e grafo após convergência.
