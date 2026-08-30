# SPEC — Redesign do VOLC O.S. e Hub de Tráfego

Status: aprovado para implementação visual  
Data: 27/08/2026  
Autoridade visual: `PRODUCT.md` → `DESIGN.md` → esta SPEC  
Escopo de referência: Hub de Tráfego, inventário, Preparar, Criar, Atenção e página canônica de campanha

## 1. Resultado esperado

Transformar o Hub de Tráfego em uma central operacional confiável, densa e clara, na qual o operador consegue:

1. entender em poucos segundos quais campanhas estão operacionais;
2. localizar FGTS e Maquininha sem atravessar histórico ou ruído;
3. comparar entrega, lance, orçamento, custo e frescor;
4. distinguir o que foi observado, diagnosticado, vinculado e decidido;
5. preparar e criar Search, Display, Demand Gen, Performance Max, Vídeo e Shopping sem uma interface centrada apenas em Search;
6. navegar do inventário ao detalhe canônico sem perder contexto;
7. compreender a consequência de qualquer ação antes de autorizar escrita ou gasto.

O resultado deve parecer um produto VOLC maduro. Não deve parecer mock, painel administrativo genérico ou exposição visual da estrutura do grafo.

## 2. Limites desta frente

### Incluído

- sistema visual oficial do produto;
- arquitetura de informação do Hub;
- refatoração visual das superfícies de Tráfego;
- componentes de navegação, inventário, detalhe, preparação, criação e atenção;
- estados reais de carregamento, ausência, recorte vazio, falha, frescor e histórico;
- responsividade, teclado, foco, contraste e tema escuro;
- inspeção visual com dados reais disponíveis na API atual.

### Não incluído

- mudar contratos de backend para facilitar layout;
- criar migrations;
- aplicar SQL;
- inventar dados ou métricas ausentes;
- habilitar mutação no Google Ads;
- publicar, pausar, duplicar ou alterar campanhas;
- push ou deploy;
- reescrever a lógica funcional que estiver sendo corrigida na frente atual.

## 3. Diagnóstico da interface atual

As capturas de 27/08 mostram defeitos de estrutura, não apenas de acabamento:

- o cabeçalho consome uma parcela excessiva da primeira tela e empurra o trabalho para baixo;
- Rede, Canal, tarefa e filtros parecem camadas de igual importância;
- a listagem mistura tabela, acordeão, badges e cards sem um modelo visual dominante;
- o nome da campanha é truncado enquanto estados secundários ocupam várias linhas;
- `ENABLED`, `entregando`, `encontrada na conta` e `sem vínculo` competem visualmente como se fossem a mesma espécie de informação;
- existe muito espaço vazio, mas pouca facilidade de comparação;
- a expansão repete dados e vira uma segunda tabela sem decisão central;
- contas com zero campanha recebem grandes blocos vazios;
- a marca VOLC quase desaparece do workspace, que se torna um admin cinza genérico;
- ações e próximos passos não possuem uma hierarquia inequívoca;
- linguagem interna aparece mais do que a tarefa do operador.

## 4. Princípios operacionais obrigatórios

### 4.1 Verdade dos dados

- Número medido, zero medido, ausência, falha e dado antigo são estados diferentes.
- Todo número decisório informa a leitura que o sustenta.
- Uma falha nova não apaga silenciosamente a última leitura boa.
- O frontend não recalcula a autoridade da ordem, diagnóstico, próxima ação ou reconciliação.
- O frontend não declara vínculo ou existência sem veredito do backend.

### 4.2 Autoridade e segurança

- A ordem das campanhas vem do servidor e permanece estável ao paginar.
- Histórico removido permanece oculto por padrão e só é carregado ao ser aberto.
- ID externo não substitui `volc_campaign_id` na página canônica.
- Render não consulta Google Ads diretamente.
- Nenhum segredo privilegiado entra no navegador.
- Ações de gasto ou escrita permanecem indisponíveis quando o contrato não as autoriza.

### 4.3 Linguagem

- A interface fala sobre campanha, conta, entrega, evidência, vínculo, decisão e consequência.
- Nomes de tabela, PostgREST, GAQL, SQL, flags e stack traces não aparecem.
- Quando algo falha, a mensagem diz o que não foi possível conferir, o que continua válido e o próximo passo seguro.

## 5. Arquitetura de informação

```text
Tráfego
├── Rede
│   ├── Google Ads
│   └── Meta Ads
├── Tarefa
│   ├── Campanhas
│   ├── Preparar
│   ├── Criar
│   └── Atenção
├── Canal, quando Google Ads
│   ├── Todos
│   ├── Search
│   ├── Display
│   ├── Demand Gen
│   ├── Performance Max
│   ├── Vídeo
│   └── Shopping
└── Nível, quando Meta Ads
    ├── Campanhas
    ├── Conjuntos
    ├── Anúncios
    └── Criativos
```

Rede define o ecossistema. Tarefa define o trabalho. Canal ou nível restringe o universo. Eles não devem ser apresentados como três barras equivalentes.

## 6. Estrutura comum da página

### 6.0 Wireframe de referência — desktop

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ COMPRA DE TRÁFEGO                                      leitura há 2 min  [↻]│
│ Tráfego                                                                      │
│ Controle campanhas, criação e decisões de mídia com evidência da conta.      │
│ [Google Ads] [Meta Ads]                                                      │
│                                                                              │
│ Campanhas 5     Preparar     Criar     Atenção 2                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Buscar nome ou ID_______________] [Conta ▾] [Estado ▾] [Canal ▾] [Filtros] │
│ 5 de 84 campanhas                    [Mostrar histórico removido: 79]         │
├──────────────────────────────────────────────────────────────────────────────┤
│ Crédito Up  ••••-•••-1692 · 2 campanhas     recente · há 2 min [Ler conta]  │
├──────────┬──────────────────────┬────────────┬────────┬────────┬──────┬───────┤
│ ESTADO   │ CAMPANHA             │ CANAL      │ LANCE  │ VERBA  │ CLIQ │ CUSTO │
├──────────┼──────────────────────┼────────────┼────────┼────────┼──────┼───────┤
│ Ativa    │ FGTS Saque-Aniv.     │ Search     │ R$ .12 │ R$ 10 │  5   │ R$ 0  │
│ atenção  │ Google · vínculo pendente · leitura há 2 min                 [›]  │
├──────────┼──────────────────────┼────────────┼────────┼────────┼──────┼───────┤
│ Ativa    │ Maquininha de Cartão │ Search     │ R$ .12 │ R$ 10 │  1   │ R$ 0  │
│ atenção  │ Google · vínculo pendente · leitura há 2 min                 [›]  │
└──────────┴──────────────────────┴────────────┴────────┴────────┴──────┴───────┘
```

O desenho é estrutural, não pixel-perfect. Ele fixa quatro resultados: primeira campanha acima da dobra, uma única hierarquia de tarefa, linhas comparáveis e histórico subordinado.

### 6.0.1 Wireframe de referência — mobile

```text
┌──────────────────────────────┐
│ Tráfego                [↻]   │
│ Google Ads ▾                 │
│ Campanhas 5 · Atenção 2      │
│ [Buscar campanha__________]  │
│ [Conta] [Canal] [Filtros]    │
├──────────────────────────────┤
│ Crédito Up · há 2 min        │
├──────────────────────────────┤
│ ● Ativa · atenção            │
│ FGTS Saque-Aniversário       │
│ Search · vínculo pendente    │
│ Verba R$10  Imp. 83          │
│ Cliques 5   Custo R$0        │
│ Ver detalhes              ›  │
├──────────────────────────────┤
│ ● Ativa · atenção            │
│ Maquininha de Cartão         │
│ Search · vínculo pendente    │
│ Verba R$10  Imp. 83          │
│ Cliques 1   Custo R$0        │
│ Ver detalhes              ›  │
└──────────────────────────────┘
```

### 6.1 Cabeçalho compacto

Altura-alvo no desktop: 220 a 280 pixels, incluindo navegação de contexto e tarefa.

Conteúdo:

- eyebrow curta: `Compra de tráfego`;
- título: `Tráfego`;
- uma frase de propósito;
- rede atual;
- resumo de frescor e universo;
- uma única ação global primária, quando aplicável;
- tarefas na borda inferior do cabeçalho.

Canal pode ficar na linha de filtros da tarefa. Não precisa ocupar uma faixa ampla própria quando não houver benefício.

### 6.2 Barra de filtros

- busca por nome ou ID;
- conta;
- estado;
- canal, quando não estiver no cabeçalho;
- recorte operacional;
- controle de filtros avançados;
- disclosure do histórico;
- frase `N de M campanhas` após qualquer recorte.

A barra e o cabeçalho das colunas podem ficar sticky. Em mobile, filtros secundários entram em sheet ou disclosure, preservando busca e recorte principal.

## 7. Campanhas — master-detail operacional

### 7.1 Estado padrão

- Mostrar apenas campanhas operacionais.
- Ordenação é a recebida do servidor.
- Campanhas que exigem atenção podem receber um marcador dominante, mas não uma pilha de chips.
- Histórico removido aparece em controle secundário com contagem e carregamento lazy.

### 7.2 Cabeçalho da conta

Altura aproximada: 48 a 56 pixels.

Mostrar:

- nome e ID mascarado;
- número de campanhas no recorte;
- frescor da última leitura boa;
- condição de leitura, se existir;
- ação `Ler esta conta`, claramente read-only.

Conta sem campanhas no recorte recebe uma linha vazia compacta com explicação. Não recebe um banner alto.

### 7.3 Linha da campanha

Desktop, colunas prioritárias:

1. estado operacional dominante;
2. campanha e metadados;
3. canal e estratégia;
4. lance;
5. orçamento diário;
6. impressões;
7. cliques;
8. custo;
9. entrega e frescor;
10. affordance de detalhe.

Regras:

- a identidade principal usa nome legível antes do ID;
- a segunda linha concentra `Google Ads · Search · vínculo pendente` em texto discreto;
- usar chip apenas para o estado dominante;
- métricas comparáveis usam números tabulares;
- frescor não ocupa uma coluna enorme, mas permanece acessível;
- nomes longos têm acesso ao valor completo;
- linha selecionada usa tinta e borda, não sombra ou faixa colorida.

### 7.4 Detalhe inline

O detalhe inline responde somente:

- qual é a campanha completa;
- de qual conta e fonte veio;
- quando foi lida;
- qual é o identificador interno e externo;
- se existe vínculo, linhagem ou ressalva;
- qual é a próxima ação segura;
- como abrir o detalhe canônico ou o Google Ads.

Diagnóstico extenso, histórico, estruturas de anúncio e gestão pertencem à página canônica.

### 7.5 Mobile

A linha vira uma composição em duas zonas:

- identidade, estado e próximo passo;
- quatro métricas essenciais em grade 2×2.

As demais métricas ficam no disclosure. Não usar tabela espremida com rolagem horizontal como experiência principal.

## 8. Página canônica da campanha

Rota: `/trafego/campanhas/:volcCampaignId`.

Ordem das seções:

1. breadcrumb, nome, plataforma, canal, conta e IDs;
2. estado de entrega, frescor e fonte;
3. resumo medido e comparação temporal disponível;
4. diagnóstico, confiança, evidências e próxima ação;
5. vínculo com funil, campanha declarada e linhagem;
6. estrutura específica do canal;
7. histórico, recibos e mudanças;
8. trilho de ações assistidas.

### Manifestos por canal

- Search: orçamento, estratégia, grupos, keywords, negativos, termos, anúncios e URLs.
- Display: orçamento, estratégia, públicos, placements, assets e formatos.
- Demand Gen: objetivos, públicos, assets, feeds e superfícies.
- Performance Max: objetivos, sinais, grupos de recursos, assets, feeds e conversões.
- Vídeo: objetivo, formato, público, criativo, placements e duração.
- Shopping: merchant, feed, produtos, grupos e estratégia.
- Meta: campanha, conjunto, anúncio e criativo como níveis separados.

Manifesto ausente é uma capacidade não disponível, não um conjunto de zeros.

## 9. Preparar

Preparar organiza candidatos antes da criação e mantém a reconciliação como autoridade.

Estados mínimos:

- `vinculada`: abre a campanha existente;
- `correspondência provável`: permite confirmar vínculo, não criar duplicata;
- `conflito`: bloqueia e pede revisão;
- `sem campanha`: permite seguir somente quando `pode_montar` for verdadeiro;
- `somente histórico`: oferece relançamento declarado;
- reconciliação ausente: bloqueia criação e explica que a conferência ainda não terminou.

Cada candidato mostra funil, destino, canal sugerido, evidência, campanha observada, confiança e próxima ação. FGTS e Maquininha nunca recebem `montar campanha` enquanto estiverem em correspondência provável.

## 10. Criar — estúdio orientado a canal

Criar deixa de ser um formulário Search e passa a ser um estúdio com etapas visíveis:

1. **Objetivo e canal**: resultado esperado, conta, destino e canal.
2. **Estratégia**: orçamento, lance, conversão e limites.
3. **Alcance**: keywords, públicos, sinais, inventário, placements ou feed conforme o canal.
4. **Criativos**: textos, imagens, vídeos, proporções, origem e validação.
5. **Conferência**: política, duplicidade, rastreamento, diagnóstico e pendências.
6. **Validação**: `validate_only`, operações previstas, alertas e recibo preliminar.
7. **Publicação**: resumo de consequência e confirmação explícita, apenas quando autorizada.

O estúdio pode antecipar superfícies ainda não conectadas, mas deve marcá-las como planejadas ou indisponíveis e nunca simular sucesso. Mock visual não entra no fluxo real autenticado.

## 11. Atenção

A fila é organizada por decisão necessária:

- entrega;
- leitura e frescor da conta;
- orçamento e lance;
- política e aprovação;
- rastreamento e conversão;
- vínculo e reconciliação;
- criativo e inventário.

Cada item possui:

- observação;
- impacto possível;
- confiança;
- dado e horário que sustentam a condição;
- próxima ação segura;
- destino para aprofundamento.

Condição da conta não infla a contagem de campanhas. O sino e a aba usam a mesma autoridade de contagem.

## 12. Estados transversais

| Estado | Comportamento |
|---|---|
| Carregando | Preserva estrutura e largura para evitar salto. |
| Recorte vazio | Informa que os filtros não encontraram resultados e oferece limpar recorte. |
| Fonte vazia | Informa que a leitura confirmou ausência. |
| Nunca lido | Declara que ainda não existe evidência. |
| Parcial | Mantém o que foi medido e nomeia o que faltou. |
| Leitura antiga | Mostra idade e recomenda nova leitura antes de decidir gasto. |
| Falha com dado anterior | Exibe a última leitura boa e a falha separadamente. |
| Falha sem dado anterior | Não inventa conteúdo e oferece tentativa segura. |
| Sem permissão | Explica a permissão necessária sem revelar detalhes internos. |

## 13. Acessibilidade

- WCAG 2.2 AA para texto, controles, foco e estados essenciais;
- navegação integral por teclado;
- ordem de foco igual à ordem da tarefa;
- foco visível em ambos os temas;
- labels acessíveis para ícones, disclosures, tabelas e botões;
- `aria-expanded`, `aria-controls`, `aria-current` e regiões vivas usados com parcimônia;
- estado nunca depende apenas de cor;
- zoom a 200% sem perda de ação ou conteúdo;
- `prefers-reduced-motion` respeitado;
- tabelas mantêm associação de cabeçalhos; composição mobile continua semântica.

## 14. Responsividade

### ≥ 1280 px

Inventário tabular completo, filtros inline e detalhe lateral ou inline conforme contexto.

### 768 a 1279 px

Reduzir colunas secundárias, manter identidade, estado, orçamento, entrega e ação. Métricas restantes ficam no detalhe.

### < 768 px

Cabeçalho compacto, tarefas roláveis com indicação de overflow, filtros em sheet, campanhas em linhas compostas e ações em área tocável mínima de 44 pixels.

Não deve existir overflow horizontal da página em nenhuma faixa.

## 15. Plano de implementação

### Fase V0 — Fundação

- consolidar tokens oficiais em `src/index.css` e Tailwind sem quebrar componentes legados;
- criar primitivas VOLC para shell, página, tabs, filtros, chips e estados;
- conter aurora e ruído fora do workspace;
- provas de tema, foco e contraste.

### Fase V1 — Hub e inventário

- compactar cabeçalho;
- hierarquizar Rede, tarefa e canal;
- reconstruir filtros;
- implementar account header e campaign row;
- corrigir expansão e histórico visual;
- validar com as cinco campanhas operacionais reais.

### Fase V2 — Página canônica

- reorganizar identidade, evidência, diagnóstico, vínculo, manifesto e recibos;
- criar trilho de ação com consequência e bloqueios honestos;
- validar ID interno e estados 404/503.

### Fase V3 — Preparar, Criar e Atenção

- aplicar estados de reconciliação sem mudar autoridade funcional;
- construir estúdio multicanal;
- reorganizar fila por decisão;
- unificar linguagem e componentes.

### Fase V4 — Blindagem visual

- desktop 1440 e 1920;
- mobile 390;
- claro e escuro;
- teclado e leitor de tela básico;
- zero overflow e zero erro de console;
- revisão adversarial;
- screenshots e relatório antes/depois.

## 16. Critérios de aceite

- A primeira linha operacional aparece sem rolar em desktop comum.
- As cinco campanhas operacionais são compreensíveis sem uma página interminável.
- FGTS e Maquininha são encontradas em menos de dez segundos.
- As 79 removidas permanecem subordinadas e fechadas por padrão.
- Estado, vínculo, presença e entrega não competem como quatro badges equivalentes.
- Linhas permitem comparar orçamento, lance e entrega.
- Toda ação mostra consequência e toda indisponibilidade mostra motivo.
- Nenhuma ausência é exibida como zero medido.
- Nenhuma métrica decisória aparece sem frescor.
- Não há mudança da ordem do servidor no frontend.
- Não há consulta ao Google Ads no render.
- Não há dados privilegiados no bundle.
- Não há overflow horizontal em desktop ou mobile.
- Temas claro e escuro são completos.
- Teclado, foco e nomes acessíveis passam na revisão.
- Build e testes ficam verdes sem novos erros de tipo.
- A interface é reconhecível como VOLC O.S. sem transformar a operação em peça publicitária.

## 17. Evidências de entrega

A entrega final deve apresentar:

- SHAs e arquivos alterados;
- lista de regras do `DESIGN.md` exercitadas;
- capturas antes/depois em desktop e mobile, claro e escuro;
- prova com dados reais de Crédito Up, FGTS e Maquininha;
- prova do histórico fechado e aberto;
- prova dos estados de falha e ausência;
- resultado dos gates;
- pendências reais separadas de melhorias opcionais.
