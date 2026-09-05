# WIREFRAMES — Estúdio Criativo (experiência única)

Convenções: larguras 1440 (desktop, shell com sidebar; conteúdo `max-w-[1400px]`), 768 (tablet), 390 (mobile). Todo cabeçalho segue SURF-CABECALHO (kicker+chip, H1 Space Grotesk 32/36, `aurora-rule w-16`, propósito, 1 botão primário, situação, sub-navegação segmented). Superfície de trabalho = `Secao` com `shadow-card`; regiões internas = hairline + `bg-muted/20`. Estados: C=carregando (skeleton), V=vazio, E=erro, I=indisponível. Teclado: Tab pela ordem visual; setas em grids; Esc fecha inspetor/folha. Motion: ver MOTION-AND-FEEDBACK-CONTRACT. Light/dark: mesmos tokens; checklist ao fim de cada tela. Dados: cada região cita a fonte.

Legenda de blocos: `[P]` botão primário · `[S]` secundário · `(selo)` glifo+palavra · `▣` thumb/preview · `≡` tabela · `⋯` menu.

---

## W1 · `/criativos` — Home (R-HOME)

### 1440
```
┌ Sidebar ─┬────────────────────────────────────────────────────────────────────────────┐
│          │ ◈ PRODUÇÃO                                                   [P] Criar peça │
│          │ Estúdio Criativo                                                            │
│          │ ━━━━  (aurora-rule)                                                          │
│          │ Onde as peças são produzidas, revisadas e aprovadas antes de virarem …        │
│          │ (motor configurado) (leitura de vídeo: indisponível)   lido às 14:02 [S] Reler│
│          │ [Início][Criar][Trabalhos][Biblioteca][Aprovações][Identidade][Ensaio]        │
│          ├──────────────────────────────────────── 2fr ─────────┬──────── 1fr ──────────┤
│          │ Secao "Em produção"            ver todos →           │ Secao "O que posso    │
│          │  (Em execução) FGTS · imagem · 2/3 prontas · gerando │  criar" ≡             │
│          │   Retrato · gemini · est. 0,12 USD · há 40 s      →  │  Motor imagem  ✓ Gemini│
│          │  (Na fila) …                                          │  Formatos      4 de 7 │
│          │ Secao "Aguardando decisão"     abrir a fila →        │  Vídeo         leitura │
│          │  (Aguardando) Encceja · Quadrado 1080×1080 · v1   → │                  indisp.│
│          │ Secao "Prontas recentes"                             │  Ensaio        3 motores│
│          │  (Aprovado p/ google_display) … decidido por … →     │  Destinos      Display │
│          │ Secao "Reutilizáveis"                                │   ligado; DG/Meta P1   │
│          │  briefing "FGTS Saque" · 3 formatos · [S] Repetir    │  fonte: /formatos,     │
│          │                                                      │  /parque, /bancada …   │
│          │                                                      │ Secao "Próximo ato"    │
│          │                                                      │  2 peças aguardam sua  │
│          │                                                      │  decisão   [S] Decidir │
└──────────┴──────────────────────────────────────────────────────┴────────────────────────┘
```
Ordem: cabeçalho → sub-nav → listas (esq) → capacidades/próximo ato (dir). Componentes: CabecalhoDoEstudio, SubNavegacao, Secao, LinhaDeJob (com fase real), LinhaDeAtivo, PainelDeCapacidades, Vazio/Carregando/ErroDeLeitura. Fontes: GET /resumo (listas), /formatos+/parque+/bancada/motores+/videos (capacidades). Estados: C skeleton por lista; V primeira visita → única Secao "Comece por aqui" com briefing embutido (W2 secções 1-7) e capacidades ao lado; E alerta no topo + último dado com hora; I faixa "servidor sem credencial" com o que continua possível. Proveniência: cada linha traz hora da última mudança; capacidades trazem "lido às". Motion: nenhuma coreografia de carga; hover em linha 150 ms.

### 768
Uma coluna: cabeçalho (sub-nav rolável) → capacidades (tabela colapsável, aberta na primeira visita) → listas. ### 390
Igual a 768; `[P] Criar` no cabeçalho; linhas com 2 linhas de texto; setas `→` viram área inteira clicável (min-h 48).

Light/dark: linhas `hover:bg-muted/50`; selos com token semântico; capacidades sem cor de fundo.

---

## W2 · `/criativos/novo` — Briefing único (R-NOVO)

### 1440
```
│ ◈ NOVA PEÇA                                                                              │
│ Briefing                                                                                 │
│ ━━━━                                                                                     │
│ Responda o que a peça precisa fazer. A revisão mostra o custo antes de qualquer chamada. │
│ (origem: Tráfego · canal Display)  ← só quando vier por query                            │
├────────── 260px ──────────┬───────────────────────────── 1fr ──────────────────────────┤
│ TRILHO (scroll-spy)        │ Secao 1 "Finalidade"            (obrigatório)               │
│ ● 1 Finalidade      ✓      │  ( ) Uso interno   — não autoriza gasto nem publicação      │
│ ○ 2 Destino e canal        │  (●) Google Display — mídia paga · exige regua do canal e   │
│ ○ 3 Identidade             │      gate de identidade (não executado neste ambiente)      │
│ ○ 4 Mensagem               │  ( ) Meta feed …   ( ) Instagram orgânico …  ( ) Exportação │
│ ○ 5 Tipo e motor           │ Secao 2 "Destino e canal"  (aparece se ≠ interno)           │
│ ○ 6 Formatos               │  chips: [Google Display ✓][Meta feed]…  canal: [DISPLAY]    │
│ ○ 7 Revisão                │ Secao 3 "Identidade"  (●) Nenhum  ( ) Pack X v2             │
│                            │  "Hoje o motor registra o pack na procedência; não altera a │
│ REVISÃO VIVA (sticky)      │   composição."                                              │
│ Projeto: FGTS Saque        │ Secao 4 "Mensagem": objetivo (3 linhas) · mensagem (5) ·   │
│ Finalidade: Google Display │  público (opcional; vazio = ausência)                       │
│ Formatos: 1.91:1, 1:1      │ Secao 5 "Tipo e motor"                                      │
│ Motor: Gemini              │  tipo: [Imagem ✓][Vídeo (P1)][Adaptação (P2)][Variação(P2)]│
│ Custo est.: 0,08 USD       │  Ficha do motor: Composição por modelo (Gemini)             │
│  (referência do provider)  │   aceita: texto, proporção nativa · não aceita: referência, │
│ ─────────────────────────  │   seed, texto na imagem, variações · 0,039 USD/peça (fonte) │
│ Gerar produz 2 peças e faz │  modos indisponíveis (5) ▸ ver motivos                       │
│ 2 chamadas ao motor.       │ Secao 6 "Formatos"  SeletorDeFormato                        │
│ [P] Gerar 2 peças          │  ┌────┐ ┌──┐ ┌─┐ ┌────────┐   ┌──────┐(16:9 sem executor)  │
│ [S] Descartar rascunho     │  │1:1 ✓│ │4:5│ │9:16│ │1.91:1 ✓│  │ 16:9 │ motivo             │
│                            │  │1080²│ └──┘ └─┘ │1200×628│   └──────┘                    │
│                            │  aviso: 4:5 e 9:16 não são aceitos em Display (não ocultos) │
│                            │ Secao 7 "Revisão": ficha completa + frase de consequência   │
│                            │  + "reenviar o mesmo formulário devolve o trabalho existente"│
└────────────────────────────┴─────────────────────────────────────────────────────────────┘
```
Ordem/foco: seções ancoradas; Tab desce pelas seções; trilho é `nav` com `aria-current`. Ação primária única: Gerar (na revisão viva e repetida no fim). Estados: C catálogos em skeleton (Gerar desabilitado); E finalidades sem leitura → Gerar desabilitado "catálogo não lido"; formatos sem leitura → fallback rotulado "lista local"; I sem credencial → Indisponivel na revisão + botão desabilitado com motivo; rascunho restaurado → aviso com Descartar; envio → botão "Enviando o pedido; o servidor produz antes de responder" (despacho síncrono, OCF-07) sem barra; replay → navega ao job com banner. Fontes: /formatos, /parque (finalidades, formatos.executavelAgora, exigênciasDeCanal, motores), /brand-packs, /jobs/{de}. Proveniência: custo estimado sempre com "referência do provider"; nunca custo medido aqui.

### 768
Trilho vira segmented rolável no topo; revisão viva vira folha inferior "Revisar e gerar (2 peças)" fixa 56px. ### 390
Idem; SeletorDeFormato 2 colunas; barra fixa inferior com `[P] Revisar e gerar`; `scroll-margin-bottom: 72px`.

Light/dark: selecionado `border-primary bg-primary/[0.06]`; desabilitado `opacity-60` + texto de motivo (não só cor).

---

## W3 · `/criativos/jobs/:id` — Produção (R-JOB)

### 1440
```
│ ◈ TRABALHO                                          [P] Preencher as 1 peça que faltou   │
│ FGTS Saque-Aniversário                                                                    │
│ ━━━━                                                                                      │
│ Uma peça por formato, cada uma com estado próprio. Você pode sair desta tela.             │
│ (Parcial) (Produzido aqui)  Gemini 1.0.0 · tentativa 1 · est. 0,12 USD · medido: não ap. │
│ ▭ banner replay | ▭ banner cancelamento pedido/confirmado (quando houver)                 │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Secao "Fases" (TrilhoDeFases)                                                             │
│  ●aceito 14:01:02 ─ ●iniciando 14:01:03 ─ ●gerando ─ ●peças (2 prontas · 1 falhou) ─ ●fim │
│  conexão: encerrada por término  |  ▸ ver 9 eventos (timeline: seq · hora · slot · frase) │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Secao "Peças"   (2 de 3 prontas; 1 falhou; repetir preenche só a que faltou)              │
│  ┌ Quadrado 1:1 ────┐ ┌ Paisagem 1.91:1 ──────────┐ ┌ Retrato 4:5 ───┐                    │
│  │ ▣ imagem 220px   │ │ ▣ imagem                    │ │ ✕ erro           │                  │
│  │ (Pronta) [1:1][⇩]│ │ (Pronta) [1:1][⇩]           │ │ (Falhou) transit.│                  │
│  └──────────────────┘ └─────────────────────────────┘ │ "cota esgotada"  │                  │
│  ≡ Fatos: slot | pedido | medido | nativo | enquadramento | mime/bytes | hash | erro       │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```
Componentes: TrilhoDeFases, TimelineDeEventos (`<ol>` com `<time>`), TileDeRendition (skeleton→imagem no evento), TabelaDeFatos, Indisponivel (falha do job), banners. Ação primária contextual: Interromper (queued/running) | Preencher (partial/failed transitório) | Abrir na fila (succeeded); secundária: "Repetir com ajuste". Estados: C cabeçalho skeleton + tiles skeleton com slots; E job não lido; conexão: aberta / reconectando (n de 5) / parada (motivo) + "Reler o trabalho"; observado → substitui por W9. Fontes: /jobs/{id}, /jobs/{id}/eventos. Proveniência: cada marco tem hora do evento; custo com rótulo estimado/medido. Motion: MOT-01/02/03/04. Teclado: tiles em faixa com setas; Enter abre zoom 1:1 (dialog com foco).

### 768
Trilho horizontal rolável; tiles 2 por linha. ### 390
Trilho vertical compacto (marco atual expandido); tiles 1 por linha (160px); fatos como lista de pares; ação primária no cabeçalho.

---

## W4 · `/criativos/trabalhos` — Lista de trabalhos (R-TRABALHOS)

### 1440
```
│ ◈ TRABALHOS                                                              [P] Criar peça   │
│ Trabalhos                                                                                 │
│ ━━━━  Todos os pedidos, com fase real e custo estimado.  lido às 14:05 [S] Reler          │
│ [Todos 12][Em execução 1][Na fila 0][Parcial 2][Falhou 1][Concluído 8][Cancelado 0]       │
│ ≡ estado | projeto | tipo | peças (prontas/falhas) | fase atual | motor | custo est. | mudou │
│   (Em execução) FGTS … imagem  2/3  gerando Retrato  gemini  0,12  há 40 s   [S] Abrir   │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```
Fonte: GET /jobs?estado=&limite=100 (URL state). Estados: C 8 linhas; V "nenhum trabalho neste estado"; E alerta + último dado. 768/390: colunas essenciais (estado, projeto, peças, mudou); linha inteira clicável.

---

## W5 · `/criativos/biblioteca` — Biblioteca (R-BIBLIOTECA)

### 1440 (visão tabela + inspetor)
```
│ ◈ PATRIMÔNIO                                               [Tabela ✓][Grade]  [P] Criar │
│ Biblioteca                                                                               │
│ ━━━━  Todo ativo produzido ou observado, com procedência, medidas, direitos e decisão.    │
│ Filtros: [busca……][tipo ▾][revisão ▾][brand pack ▾][formato ▾][de][até]  chips ativos ×  │
│ 24 de 132 neste recorte · lido às 14:06                                                  │
├──────────────────────────────── 1fr ───────────────────────────┬──── 400px inspetor ────┤
│ ≡ [ ] ▣ | projeto | formato | tipo | motor | revisão | destinos | criado | ⋯               │
│   [x] ▣ FGTS Saque  1.91:1 1200×628  imagem  gemini (Aprovado p/ Display) 1 disp. 09/05  │
│   [ ] ▣ FGTS Saque  1:1 1080²        imagem  gemini (Aguardando)          bloq.   09/05  │
│   [x] ▣ Encceja     4:5 1080×1350    imagem  gemini (Ajuste pedido)       —       04/09  │
│   … (virtualizado > 100)                                                                 │
│ ▭ Barra de ações (2 selecionados): [S] Comparar  [S] Aprovar…  [S] Usar no Tráfego  [S] Exportar │
│ paginação: ‹ 1–24 de 132 ›                                                              │ InspetorDePeca (W6 modo lateral) │
└─────────────────────────────────────────────────────────────────┴──────────────────────────┘
```
Componentes: PainelDeFiltros (sem destino), TabelaDeAtivos (roving tabindex, `aria-sort`), Grade (visão grade 4-5 col), BarraDeAcoes (aparece com seleção; MOT-12), InspetorDePeca lateral (MOT-06), paginação. Fontes: /assets (busca, kind, estado, brandPack, slot, desde, ate, ordem, limite, offset), /brand-packs, /formatos. Estados: C; V biblioteca vazia vs vazio após filtro (Limpar) vs total não informado; E alerta + última página com hora. Seleção máxima 50. Modo seleção (vindo do Tráfego): cabeçalho mostra "Escolhendo peças para Display · papel imagem_marketing" e a barra tem `[P] Usar 2 selecionadas` + `[S] Cancelar e voltar`.

### 768
Tabela com thumb/projeto/formato/revisão; inspetor em folha lateral (85vw). ### 390
Grade 2 col ou lista; filtros em folha "Filtrar (3)"; inspetor em folha inferior tela cheia (dialog); barra de ações fixa inferior; ações de gasto exigem confirmação.

Light/dark: linha selecionada `bg-primary/[0.06]` + inset ring; thumbs sobre `bg-muted/40` com borda.

---

## W6 · `/criativos/assets/:id` — Ficha do ativo (R-ASSET) e InspetorDePeca

### 1440 (modo página)
```
│ ◈ ATIVO                                                    [P] Registrar decisão          │
│ FGTS Saque-Aniversário · Paisagem 1.91:1                                                  │
│ ━━━━  (Aprovado p/ Google Display) (Produzido aqui) (Concluído)   job de origem →         │
├──────────────── 1fr ────────────────┬──────────────────────── 1fr ───────────────────────┤
│ Secao "Prévia"                       │ Secao "Ficha técnica" ≡ tipo · mime · 1200×628 ·   │
│  ▣ imagem em tamanho real (até 640px)│  bytes · versão 1 · hash sha256:9f3a… [copiar] ·    │
│  [Ajustar][1:1][Moldura: Display ▾]  │  criado 05/09 14:03 · arquivado: não                │
│  safe zones do destino (overlay 10%) │ Secao "Política e direitos"                         │
│  [S] Baixar o arquivo                │  (Gate de identidade: não executado) → bloqueia     │
│                                      │   mídia paga até existir · licença: não declarada ·  │
│                                      │   sintético: sim (gerado por modelo) · insumos: 0   │
├──────────────────────────────────────┴─────────────────────────────────────────────────────┤
│ Secao "Destinos" ≡ destino | estado | motivo | ação                                        │
│  Google Display   (Disponível)     aprovado p/ Display; 1.91:1 ok; gate não executado   [S] Usar no Tráfego │
│  Google Demand Gen(Compatível)     sem aprovação p/ DG; logo 144 obrigatório (Pack)     —  │
│  Meta feed        (Incompatível)   1.91:1 não é 1:1/4:5                                  —  │
│  Instagram orgân. (Bloqueado)      upload de mídia não disponível (P1)                   —  │
│  Exportação       (Disponível)                                                       [S] Baixar │
│  … (13 linhas; bloqueados mostram release)                                                 │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Secao "Procedência" ≡ motor Gemini 1.0.0 · execução: produzido aqui · hash do insumo 4c1… · │
│  brand pack: Pack X v2 · custo: est. 0,04 USD (referência) · medido: não apurado          │
│ Secao "Usos"  (não apurado | apurado: 1 pacote Display validado em 05/09 → plano "X")     │
│ Secao "Versões"  v1 (esta)                                                                 │
│ Secao "Histórico" (append-only): 14:03 aprovado p/ google_display por Ana · 13:50 gerado … │
│   [S] Revogar (admin, confirmação com escopo)                                             │
│ Secao "Decidir" FormularioDeDecisao (W7)                                                   │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```
Modo lateral (inspetor): mesma ordem em coluna única de 400px, prévia 360px, tabelas compactas, ações no rodapé sticky. Fontes: /assets/{id}, /assets/{id}/destinos (novo), /brand-packs, /parque. Estados: C prévia skeleton proporcional; V destinos "não avaliados (parque não lido)"; E "ativo não lido" sem afirmar inexistência. Proveniência: cada bloco cita fonte e hora. Teclado: zoom por botões; Esc fecha zoom.

### 768 / 390
Uma coluna: prévia → decisão (ação primária no cabeçalho) → destinos → ficha → procedência → histórico.

---

## W7 · `/criativos/aprovacoes` — Fila (R-APROVACOES)

### 1440
```
│ ◈ GOVERNANÇA                                                                              │
│ Fila de aprovação                                                                         │
│ ━━━━  2 peças aguardam decisão · lido às 14:07                                            │
├──────────── 1fr fila ────────────┬───────────────── 1fr inspetor ────────────────────────┤
│ ≡ ▣ | projeto · formato | motor | criado | gate | [Decidir]                               │
│   ▣ FGTS 1:1 1080²  gemini 05/09  (não exec.)  ●selecionada                               │
│   ▣ Encceja 4:5     gemini 04/09  (não exec.)                                             │
│                                   │ ▣ prévia grande [1:1][Moldura ▾]                       │
│                                   │ Decisão: (●) Aprovar ( ) Pedir ajuste ( ) Rejeitar     │
│                                   │ Finalidade (catálogo, por classe):                     │
│                                   │  Interna: (●) Uso interno — não autoriza gasto         │
│                                   │  Mídia paga: ( ) Google Display ⚠ gate não executado … │
│                                   │  Orgânica: ( ) Instagram … · Exportação: ( ) Manual    │
│                                   │ Motivo (obrigatório em ajuste/rejeitar)                │
│                                   │ Você está aprovando o arquivo 9f3a… 1080×1080, 412 KB │
│                                   │ [P] Registrar decisão  · ator/hora gravados no servidor│
└───────────────────────────────────┴────────────────────────────────────────────────────────┘
```
Estados: C; V "nada aguardando decisão"; E "a contagem não chegou; nenhuma decisão foi perdida"; 409 → oferece Revogar. Após decisão: MOT-08 + aria-live; item sai da fila. 768: fila; decisão inline abaixo do item. 390: fila; decisão em folha.

---

## W8 · `/criativos/comparar?itens=` — Comparação (R-COMPARAR, P1)

### 1440
```
│ ◈ COMPARAÇÃO      [Ajustar][1:1][200%]  [Moldura: nenhuma ▾]         [P] Aprovar selecionadas │
│ 3 peças                                                                                      │
│ ┌ A FGTS 1:1 ───────┐ ┌ B FGTS 4:5 ───────┐ ┌ C FGTS 9:16 ─────┐                              │
│ │ ▣                 │ │ ▣                 │ │ ▣                │  zoom sincronizado (botões)   │
│ │ (Aguardando)      │ │ (Aprovado interno)│ │ (Aguardando)     │                              │
│ └───────────────────┘ └───────────────────┘ └──────────────────┘                              │
│ ≡ Diff: dimensão | bytes | hash | enquadramento | motor | aprovação | destinos compatíveis     │
│   células divergentes com glifo ◆                                                            │
```
768: 2 colunas; 390: segmented A|B|C. Sem divisor arrastável. Estados: <2 itens → instrução; coluna em erro isolada.

---

## W9 · `/criativos/videos/:buildSlug` e job observado (R-VIDEO) — PRESERVED
Mantém LeituraDeVideo (3 zonas 320/1fr/360; abas <1024) com cabeçalho novo (W1 padrão) e DeclaracaoDeOrigem. Fontes: /video/{slug}. Estados existentes.

## W10 · `/criativos/novo?tipo=video` — Vídeo (alias)
Mesmo shell de W2 com secção 5 em "Vídeo": Indisponivel com `limitacaoDeclarada` do servidor + lista de builds observados (existente). Sem formulário até T09.

## W11 · `/criativos/brand-packs` — PRESERVED (P0)
Cabeçalho padrão; lista existente; P1: `[P] Novo pack` (admin) com editor (nome, slug, tokens em campos rotulados, fontes hash), versão nova por edição.

## W12 · `/criativos/laboratorio` — Ensaio (dentro do Layout)
```
│ ◈ ENSAIO                                                                                   │
│ Laboratório de receitas                                                                    │
│ ━━━━  Monte uma receita e produza uma peça de teste local. Catálogo lido às 14:08          │
│ ▭ faixa fixa: "Ensaio local. As peças daqui não entram na Biblioteca nem vão a produção."  │
│ (conteúdo existente: Direção · Receita compilada · Compatibilidade · Produzir peça de teste)│
```

## W13 · Tráfego — `SeletorDeAsset` com "Escolher da Biblioteca" (fora do Estúdio, T08)
```
│ Imagens de marketing (1.91:1)  0/15 itens                                                 │
│ [S] Enviar arquivo   [S] Escolher da Biblioteca                                            │
│ ▭ folha lateral 480px: lista W5 em modo seleção filtrada por slot 1.91x1 · estado aprovado│
│   ▣ FGTS Saque 1200×628 hash 9f3a… (Aprovado p/ Display) (gate não exec.)  [ ]            │
│   [P] Usar 1 selecionada   [S] Cancelar                                                   │
│ item anexado: ▣ FGTS Saque · 1200×628 · "da Biblioteca" · hash 9f3a…  [×]                 │
```
Após `/provar` aprovado: ficha do ativo mostra "vinculado ao plano <nome> · 05/09 14:20".

---

## Checklist light/dark por tela (gate visual de cada tarefa)
- [ ] Nenhuma cor absoluta além do fundo do player; tokens semânticos apenas.
- [ ] Selos legíveis (≥ 4.5:1) nos dois temas; thumbs escuras separadas por borda em dark.
- [ ] Foco visível em todo interativo; alvos ≥ 40×40.
- [ ] Skeletons com a altura final; sem salto de layout.
- [ ] Nenhuma barra/percentual sem evento com percentual; nenhum pulso.
- [ ] Capturas 1440/768/390 × light/dark anexadas ao handoff da tarefa.
