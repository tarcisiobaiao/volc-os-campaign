# Autoridade visual do VOLC O.S. — quem manda, e no quê

Produzido na revisão visual global de 2026-08-29 (base `9885459`), em resposta
à pergunta: *qual arquivo representa o contrato atual do produto, quais regras
são de apresentação, e onde eles se contradizem?*

## A resposta curta

**`design.md`, na raiz do repositório, é o contrato do produto.** Não porque
alguém decidiu agora, mas porque ele já se declara assim, o loader do Impeccable
o carrega, e ele foi mantido junto com o código — o histórico mostra sete
commits de design entre 2026-08-05 e 2026-08-28, incluindo uma rodada de
correções vinda de revisão adversarial (`0be638d`).

A revisão **não reescreveu** esse contrato. Encontrou um contrato bom, aplicado
às salas novas e nunca aplicado às salas herdadas do webgo — e foi isso que
corrigiu.

## A cadeia, por autoridade

| # | Arquivo | Governa | Autoridade |
|---|---|---|---|
| 1 | **`design.md`** (raiz) | tudo sob `src/` — workspace, tabelas, formulários, decisão | **Contrato.** Vence qualquer divergência |
| 2 | `PRODUCT.md` (raiz) | registro (`product`), usuários, anti-referências, princípios | Contrato de **intenção**. Não é receita de componente |
| 3 | `.impeccable/design.json` | mesmos tokens, em forma legível por máquina | **Derivado.** Espelha `design.md` |
| 4 | `docs/DESIGN.md` | ponteiro + as mesmas receitas em português | **Ponteiro.** Ele próprio diz: "se divergir da raiz, a raiz vence" |
| 5 | `docs/design/DESIGN-SYSTEM.md` | apresentações, decks, login, material externo | **Apresentação/marketing.** Nunca governa o produto |

### O que é de apresentação, e por que não pode vazar

`docs/design/DESIGN-SYSTEM.md` se descreve como *"Design system for Volc's
explosive, premium, and tech-forward presentations"*. Ele define
`display-hero` em **4rem, peso 800, caixa-alta**, fundo `#000000` puro e branco
`#FFFFFF` puro.

Nada disso pode entrar no workspace, e o `design.md` diz por quê: o produto
evita preto absoluto e branco puro, o título de página vive entre 32 e 40px, e
caixa-alta é auxílio de navegação, não textura. São dois registros diferentes
para dois trabalhos diferentes — não uma contradição a resolver.

## Contradições reais encontradas

Foram três, e todas foram fechadas.

### 1. `docs/DESIGN.md` × `design.md` na pílula da aba selecionada

| Fonte | Diz |
|---|---|
| `design.md` §Components | *"Selected pill: `bg-background shadow-card`"* |
| `design.md` §Surfaces | *"**Never** `bg-background` for the selected pill: that token **is** the canvas"* |
| `docs/DESIGN.md` | *"Nunca `bg-background` no pílula: esse token é o canvas"* |

O próprio `design.md` se contradiz **entre duas seções suas**. A seção §Surfaces
está certa e explica o motivo (`--background` é `#F3F5F7`, o canvas — uma pílula
pintada com ele desaparece no fundo); a §Components carrega a redação antiga.

**Estado:** corrigido — e a primeira redação desta seção estava errada. Ela
afirmava que "a implementação segue a versão correta", e a revisão adversarial
provou o contrário: `src/components/ui/tabs.tsx` seguia a redação ANTIGA
(`data-[state=active]:bg-background`), e sete linhas em `UsersSettings.tsx` e
`V6AdminPage.tsx` a reafirmavam. Medido, a pílula selecionada contra o poço da
lista: **1,025:1** — indistinguíveis.

O primitivo é consumido por 13 arquivos. Todos os nove pontos foram migrados
para `bg-card` + `shadow-card`. A dívida de texto em `design.md` §Components
permanece, e está na proposta de curadoria abaixo.

### 2. O contrato exigia contraste que os próprios tokens não entregavam

`PRODUCT.md` §Accessibility manda estados combinarem *"glifo, palavra e
descrição"*, com *"contraste adequado"*. `design.md` manda a palavra do chip usar
o token semântico.

Medido contra as superfícies reais do produto: `--warning` dava **2,51:1**,
`--info` **2,44:1**, `--success` **3,70:1**, `--verified` **3,35:1** — todos
abaixo do piso de 4,5:1 que o próprio contrato invocava.

Não era contradição entre documentos: era o documento contra a implementação.
**Corrigido** em `a407381`, com os valores resolvidos por medição, seguindo o
precedente que o próprio `src/index.css` já registrava para `--verified`.

### 3. Duas salas de identidade não listadas

`design.md` autoriza `text-aurora` na segunda palavra do H1 em QG, Pautador Pro
e Redator, e escreve *"Nowhere else"*. Mas a mesma seção lista `login` entre os
marcos de aurora, e `/change-password` é a superfície irmã do login (identidade,
sem shell de workspace) sem estar citada em lugar nenhum.

**Resolvido por leitura, não por mudança:** as duas foram tratadas como
superfícies de identidade e preservadas. As outras onze ocorrências saíram
(`fc1c149`).

## O achado que organiza tudo

O contrato não estava sendo violado por igual. Ele foi **aplicado às salas
novas e nunca às herdadas**:

| Sala | Origem | Estado antes da revisão |
|---|---|---|
| `/trafego`, `/pautador-pro`, `/redator`, `/criativos`, QG | escritas para este contrato | conformes — `design.md` manda copiá-las em caso de dúvida |
| `/`, `/reports`, `/dashboard/*`, `/settings/*` legadas | herdadas do webgo | quase nenhuma regra aplicada |

O Dashboard Geral, que é a rota `/` e a primeira tela do ADMIN, concentrava:
seis hero-metrics em grade idêntica, ícone em círculo colorido, blob decorativo,
gradient text no H1, fio aurora em cada cartão, e todos os números em zero
inventado com seta verde para cima.

**A dívida era de aplicação, não de contrato.** É por isso que esta revisão não
propôs um design system novo: propôs terminar de aplicar o que já existia.

## Proposta de curadoria (não aplicada)

Conforme o protocolo do `CLAUDE.md`, a revisão **não** tocou o Roadmap Vivo nem
o grafo. O integrador central decide:

1. corrigir a frase obsoleta de `design.md` §Components (*"Selected pill:
   `bg-background shadow-card`"* → `bg-card`), alinhando-a a §Surfaces;
2. registrar `/login` e `/change-password` como superfícies de identidade na
   lista de aurora de `design.md`;
3. anotar em `design.md` que os valores de `--success`, `--warning`,
   `--verified`, `--info` e `--destructive` no tema claro passaram a ser
   derivados por medição de contraste, e que o hex normativo descreve o matiz,
   não a luminosidade final;
4. apontar `docs/design/INVENTARIO-DE-ROTAS.md` e
   `docs/architecture/ADR-DAISYUI-E-A-CAMADA-CANONICA-VOLC.md` como nós novos.
