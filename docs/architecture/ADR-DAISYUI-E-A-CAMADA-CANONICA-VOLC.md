# ADR — DaisyUI não entra; a camada canônica VOLC sobe sobre Radix

- **Data:** 2026-08-29
- **Estado:** aceito
- **Escopo:** vocabulário de componentes do produto operacional (`src/components/**`)
- **Decisor:** dono do produto, na abertura da revisão visual global
- **Contexto de origem:** missão "Revisão visual global e evolução do Design System VOLC OS"

## A pergunta

A missão pediu, textualmente: *"Quero reduzir a aparência genérica herdada do
shadcn. Avalie e use DaisyUI, mas não faça uma substituição mecânica ou
destrutiva."* E fixou o critério de sucesso: *"Se o resultado parecer um exemplo
padrão do DaisyUI, a missão falhou."*

O passo 2 do procedimento pedido era **confirmar a versão compatível com o
Tailwind deste projeto** antes de qualquer instalação. Esse passo é o que
decidiu.

## O que foi medido

O projeto está em **Tailwind CSS 3.4.11** (`package.json`, `devDependencies`).

| Fato | Evidência |
|---|---|
| DaisyUI mais recente é **5.7.22** | `npm view daisyui versions` |
| A v5 é distribuída como **CSS puro** (`daisyui.css`, `components/*.css`, `theme/*.css`), sem plugin JS para `tailwind.config` | `npm pack daisyui@5.7.22`, inspeção do tarball; `description: "daisyUI 5 - The Tailwind CSS Component Library"`, `peerDependencies: null` |
| Esse formato é o modelo `@plugin` **CSS-first do Tailwind v4** | arquitetura do pacote |
| A última linha compatível com Tailwind v3 é a **4.12.24** | `npm view daisyui versions` |
| A 4.12.24 foi publicada em **2025-02-25** | `npm view daisyui time` |
| A 5.0.0 saiu **três dias depois**, em 2025-02-28 | idem |

Ou seja: adotar DaisyUI aqui significa **ou** um major congelado há dezoito
meses, **ou** migrar o Tailwind para a v4 antes — o que reescreve
`tailwind.config.ts`, muda a sintaxe dos tokens de `src/index.css` e obriga a
revalidar os 54 componentes shadcn vendorizados.

## Por que a decisão foi "não"

O custo de versão foi o que motivou a pergunta, mas não é o argumento principal.
Os três abaixo são.

### 1. DaisyUI não resolve o problema que motivou o pedido

O incômodo relatado é aparência genérica. Mas o shadcn/ui **não é uma biblioteca
com aparência própria**: os 54 componentes vivem dentro deste repositório, em
`src/components/ui/`, e cada decisão visual deles já pertence ao projeto. A
genericidade não vem de "o shadcn é assim" — vem de **ninguém ter sobrescrito os
padrões**, e a auditoria mediu exatamente isso:

- `badge.tsx` mantinha `bg-green-500 text-white` — o default de template, com
  2,28:1 de contraste, fora do vocabulário semântico que o `design.md` declara
  fechado;
- `tabs.tsx` mantinha `transition-all` e `data-[state=active]:bg-background`,
  os dois banidos nominalmente pelo contrato;
- 25 ocorrências de `transition-all` estavam **dentro dos próprios primitivos**.

Trocar por DaisyUI substitui "padrões que você possui e pode editar" por
"padrões que vêm de um pacote externo e você combate com variáveis de tema". O
resultado mais provável é justamente o que a missão definiu como falha.

### 2. Ele criaria o terceiro vocabulário que o contrato proíbe

`design.md`, seção *Agent contract*: **"Do not invent a third visual language."**
Nos *Hard bans*: **"a second tab vocabulary on the same product."** A própria
missão repete: *"Não mantenha dois componentes canônicos concorrentes."*

DaisyUI não fornece semântica acessível — a missão reconhece isso ao dizer que
*"Radix pode continuar fornecendo semântica, foco e interação"*. O arranjo
resultante seria: **Radix** (comportamento) + **DaisyUI** (classes) + **shadcn**
(os wrappers que já existem e têm 104 consumidores). Três vocabulários, não um.

### 3. Os tokens VOLC governariam pouca coisa

A missão pede que *"os tokens VOLC governem DaisyUI, nunca os presets
genéricos"*. DaisyUI traz o seu próprio espaço de nomes de tokens (`--p`, `--b1`,
`--bc`, em OKLCH). Fazer os tokens VOLC governarem significa escrever um tema
completo — e, feito isso, o que DaisyUI ainda contribui é uma convenção de nomes
de classe.

## O que foi feito no lugar

O item §6.4 da missão — **"Crie uma camada canônica de componentes VOLC"** — é a
parte que tem valor, e foi entregue sobre os primitivos que já existem:

| Entregue | Onde | O que resolve |
|---|---|---|
| Chip de estado no vocabulário fechado, com glifo + palavra | `src/components/ui/badge.tsx` | 2,28:1 → AA; paleta crua → tokens; sem `animate-pulse`; cor deixa de ser o único portador |
| `transition-volc` | `tailwind.config.ts` | um vocabulário de transição, com as propriedades nomeadas que o contrato exige |
| `<Icone>` + `ICONES` | `src/components/ui/icone.tsx`, `src/lib/icones.ts` | escala fechada, peso único, contrato de nome acessível |
| `<VariacaoDoPeriodo>` | `src/components/dashboard/VariacaoDoPeriodo.tsx` | impede que ausência vire zero positivo |
| `touch-target` real | `src/index.css` | a classe existia em 55 chamadas e era no-op |
| Cores de ROAS no vocabulário | `src/utils/roasCalculations.ts` | uma fonte para cinco páginas |

Nenhuma dependência nova de UI foi adicionada além do Hugeicons, que a missão
pediu à parte.

## Consequências

- **Positiva:** o produto continua com um vocabulário só, governado por
  `design.md`, e sem major congelado no `package.json`.
- **Positiva:** o Tailwind permanece na 3.4.11; a migração para a v4 pode ser
  decidida pelos próprios méritos, e não como pré-requisito de uma biblioteca de
  componentes.
- **Negativa:** a camada canônica é escrita à mão. Componentes que o DaisyUI
  entregaria prontos (drawer, timeline, stat) continuam sendo trabalho nosso
  quando forem necessários.
- **Negativa:** os 54 componentes vendorizados seguem sendo manutenção nossa,
  incluindo os 18 sem consumidor (ver a dívida no handoff).

## Quando reabrir

Esta decisão deve ser reavaliada se, e somente se, o Tailwind for migrado para a
v4 por outro motivo. Nesse cenário o DaisyUI 5 passa a ser a linha viva, e o
argumento de versão desaparece — restam os argumentos 1 e 2, que continuam
valendo enquanto `design.md` proibir um segundo vocabulário de componentes.
