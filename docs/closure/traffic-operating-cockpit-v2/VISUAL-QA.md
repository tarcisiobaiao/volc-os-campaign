# VISUAL-QA — o que foi conferido em navegador, e o que não foi

## O que foi feito

Navegador de verdade (Chromium via playwright-core já presente na máquina;
**nenhum pacote instalado neste repositório**), ambiente local isolado, com o
`.env` da worktree montado **fail-closed** — sem credencial nenhuma do Google Ads
e sem n8n. O backend respondeu `{"engine":"mock"}`.

**104 capturas**: 13 cenas × 4 larguras (375, 768, 1440, 1920) × 2 temas
(claro, escuro), a 2× de densidade. Mais 13 capturas em `prefers-reduced-motion:
reduce`.

## Medição automática de cada captura

| medida | resultado |
|---|---|
| overflow horizontal (`scrollWidth > clientWidth + 2`) | **0 de 104** |
| erros de console / `pageerror` | **0 de 104** |
| capturas que falharam ao renderizar | **0 de 104** |
| alvos interativos com altura < 40px | **0 em todas as larguras** |
| capturas sem landmark (`main`/`nav`/`header`…) | **0 de 104** |

Estas medidas são feitas dentro da página, por captura, e ficam no
`SCREENSHOT-MANIFEST.json` cena a cena. Não são impressão: são consulta ao DOM.

## O que foi olhado, e o que se viu

Inspeção visual das capturas, com atenção ao que o briefing manda procurar:

- **Hierarquia** — kicker → h1 → frase de contexto → escada → conversa. O olho
  cai na escada, que é a resposta à primeira pergunta do operador.
- **Cor semântica com função** — verde só em `PERMITIDO`; vermelho só em
  `BLOQUEADO`; **âmbar em `INDETERMINADO`**, que é a distinção mais cara desta
  tela; ciano/`info` nos chips de origem `produto`/`política`. A cor mora na
  borda, no fundo e no glifo — nunca na palavra, que usa tinta de texto normal.
- **Estados distinguíveis sem cor** — cada chip carrega glifo + palavra +
  descrição acessível. Nenhum estado depende de cor sozinha.
- **Sem cartão dentro de cartão.** A escada é uma lista com divisores
  (`border-b border-border`); os bloqueios usam uma barra lateral de 2px, não uma
  caixa aninhada. Nenhum `card-volc` dentro de `card-volc`.
- **Sem glassmorphism, sem glow, sem gradiente decorativo, sem caixa-alta em
  excesso** no código novo.
- **Escuro** — os tokens do projeto já são auditados por contraste, e as capturas
  em `dark` mantêm legibilidade dos chips e das causas. Conferido em 375 e 1440.

### O que a inspeção encontrou e foi corrigido

1. **Treze parágrafos idênticos.** Só apareceu ao montar o componente. Corrigido.
2. **Tipografia abaixo do piso do `design.md`.** Causa, pergunta do portão,
   revalidação e "a quem pedir" estavam em 11–12px; `design.md:172` exige que
   ação e texto explicativo nunca caiam abaixo de 14px. Subiram.
3. **O "Lendo…" era mudo para leitor de tela.** Virou `role="status"` com
   `aria-live="polite"`.

## ⚠️ O que NÃO foi conferido, e é a maior limitação desta sprint

**As rotas reais `/trafego*` nunca foram abertas em navegador.** Elas estão sob
`ProtectedRoute` e exigem sessão Supabase; sem credencial — e digitar senha é
proibido — o navegador só alcança `/login`.

Tudo acima foi feito na **bancada de fixtures**, que monta os componentes REAIS
com dados tipados. Isso vale para conferir composição, contraste, hierarquia,
responsividade e os estados que uma conta saudável não produz sob demanda.

**Não vale como prova de integração.** Não exercita `useCanais` contra o
servidor, nem o Hub inteiro, nem a interação entre a aba Criar e as outras quatro.

## ⚠️ Comprimento não é overflow

`jornada__pmax-retido__375x812` passa de 4000px de altura. Zero overflow
horizontal e zero alvo pequeno **não** significam que a tela esteja curta: em
mobile, escada + treze etapas empurram a próxima ação por várias telas. A revisão
adversarial apontou isso (lente 8) e **não foi corrigido** — está em
`REMAINING-RISKS.md` §4 com o próximo ato.

## ⚠️ A revisão das capturas por um segundo modelo não aconteceu

O briefing pede que Codex e Gemini revejam uma amostra dos screenshots finais.
**Gemini não rodou** (sem método de autenticação configurado; comando e erro
literais em `REMAINING-RISKS.md` §2). O Codex revisou o **diff**, não as imagens.

Logo: as capturas foram lidas por um olho só, o meu.
