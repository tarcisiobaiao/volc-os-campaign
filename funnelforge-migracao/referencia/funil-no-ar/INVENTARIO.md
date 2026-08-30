# Inventário medido — Funil 2, Saque-Aniversário FGTS

Levantado em 11/08/2026 via WordPress REST (`creditoup.com.br`), com as 7 páginas
publicadas. Tudo abaixo é **medição sobre o conteúdo real**, não impressão.

## Grafo e tamanhos

```
LP  /r/antecipacao-saque-aniversario-fgts      id 2064   8.476 ch   Elementor canvas
 ├─ PR1 /rec/quem-tem-direito-antecipar-fgts-pr1   2067  12.676 ch  Gutenberg
 ├─ PR2 …-pr2                                     2070  11.650 ch
 └─ PR3 …-pr3                                     2073  12.332 ch
        ├─ P1 /rec/como-consultar-fgts-pelo-cpf-p1        2077  12.467 ch
        ├─ P2 /rec/bancos-antecipar-fgts-pix-whatsapp-p2  2080  24.805 ch
        └─ P3 /rec/regras-demissao-quitar-emprestimo-fgts-p3 2083 30.896 ch
```

Ligações reais: LP → PR1/PR2/PR3 (2 botões cada: mobile + desktop).
PR1/PR2/PR3 → **os mesmos** P1/P2/P3. P1 → P2, P3. P2 → P3.
P3 → **fora do funil** (`/como-consultar-e-pedir-restituicao-de-desconto-indevido-do-inss…`).

Acíclico, sem link quebrado, sem colisão de slug `-2`. **O grafo está correto.**

## 1 · As três pré-sells são a mesma página

Os `<h2>` são **idênticos nas três**:

```
Requisitos de Elegibilidade: Quem realmente pode antecipar?
Valores e Canais Rápidos: Antecipação a partir de R$ 20 via Pix ou WhatsApp
Regras Especiais: Demissão, Quitação de Saldo e Novas Antecipações
```

Similaridade de texto: PR1×PR2 12,3% · PR1×PR3 11,0% · PR2×PR3 17,3%.
São **paráfrases da mesma estrutura** — três execuções do mesmo molde.

Os rótulos dos botões da LP prometem coisas diferentes:

```
botão 1 → PR1   "Será que tenho direito ao saque? Ver"
botão 2 → PR2   "Como consultar o saldo atualizado"
botão 3 → PR3   "Ver o passo a passo de liberação"
```

Nenhum dos três destinos tem um `<h2>` sobre consulta de saldo nem sobre passo a
passo de liberação. **Promessa do botão ≠ conteúdo entregue** nos botões 2 e 3.

## 2 · Contradições internas verificáveis pelo leitor

**A carência de 90 dias é usada para três coisas diferentes:**

| onde | para quê |
|---|---|
| LP, P1, P3, PR1, PR2 | autorizar bancos a consultarem o saldo |
| P2, passo 2 | "carência de 90 dias para novas mudanças" |
| P2, próximos passos | "caso você decida **retornar à modalidade Saque-Rescisão**" |

A terceira **contradiz P1, P2 e P3**, que dizem que voltar ao Saque-Rescisão vale
a partir do **1º dia do 25º mês** (carência de 24 meses).
**P2 contradiz P1 e contradiz a si mesma.**

**O piso de valor:**

- P1, P3, LP: "mínimo R$ 100,00, máximo R$ 500,00 por parcela anual"
- PR1: "Até 31/10/2026 · até 5 parcelas (teto R$ 2.500) · após · 3 parcelas (teto R$ 1.500)"
- PR2 apresenta a distinção de forma correta, em tabela:
  `Regra Oficial R$ 100,00 · Fintechs e Bancos Digitais a partir de R$ 20,00 via Pix`
- **o widget interativo de P2 afirma:** "A Resolução CCFGTS nº 1.130/2025 **impede
  qualquer operação abaixo desse valor mínimo** por parcela em 2026"

O widget — a superfície de maior confiança da página — **nega a tabela de PR2 e o
próprio `<h2>` das três pré-sells** ("a partir de R$ 20 via Pix").

**A unidade do limite muda:** a tabela de P1 diz "Até **5 anos** do
Saque-Aniversário"; PR1/PR3 dizem "5 **parcelas anuais**"; P2 diz "5 **saques
anuais**". Teto de R$ 500 **por parcela** (P1) vs teto de R$ 2.500 **para 5
parcelas** (PR1) — que é o mesmo número, mas nenhum texto liga os dois.

## 3 · A norma citada, seis vezes, sustenta as duas afirmações centrais

`Resolução CCFGTS nº 1.130/2025` aparece em P2 (4×) e PR1/PR2 (2×) como fonte de:

- o piso de R$ 100,00 por parcela
- a carência de 90 dias para autorizar bancos

**Nenhuma das citações tem link.** Se o número da resolução estiver errado, o erro
é do tipo mais caro que existe: número de norma confere credibilidade máxima e é
trivialmente checável por um leitor ou por um revisor de política de anúncios.

Outras citações sem link nem número: "diretrizes operacionais de 2026",
"novas regras da CAIXA para 2026", "regulamentadas pelo MTE".

## 4 · A doença do disclaimer

Ocorrências de "independente / sem vínculo / não solicitamos / apenas informativo":

```
P1  7      PR1 3   PR2 3   PR3 3   P2 3   P3 4
```

Em P1 (~1.900 palavras), **três delas interrompem a instrução no meio da frase**:

> "baixar o aplicativo do FGTS (desenvolvido pela Caixa Econômica Federal, **sendo
> nosso portal um veículo informativo independente do banco**)"

> "Mantenha o seu cadastro atualizado diretamente na 👉 página de informações sobre
> o FGTS no site da Caixa (**lembrando que nosso portal é independente e apenas
> indica o caminho**)"

> "consulte o 👉 portal gov.br (**plataforma federal informativa, sem qualquer
> vínculo com nosso site independente**)"

E a primeira frase do corpo, antes de qualquer conteúdo útil:

> "Como este portal de jornalismo de serviço é totalmente independente e sem
> qualquer vínculo com órgãos públicos, preparamos este guia prático…"

## 5 · O caminho foi apagado onde mais importa

P1 é a página "como consultar o FGTS pelo CPF". O passo 1 diz:

> "O download pode ser feito diretamente na loja de aplicativos do seu celular,
> **buscando pelo nome do programa** para sistemas Android ou iOS."

**Não diz o nome do app.** O leitor chegou de um anúncio pago para descobrir como
consultar, e a instrução mais básica foi substituída por uma perífrase.

Padrão repetido: "👉 página de informações sobre o FGTS no site da Caixa",
"👉 página de regras do saque-aniversário no site da Caixa" — o destino é nomeado
e **o link existe**, mas o texto âncora não diz para onde vai.

## 6 · Links de saída para quem disputa o mesmo clique

P2 aponta para fora do site em 8 links, incluindo:

```
meutudo.com.br/blog/existe-emprestimo-fgts-a-partir-de-20-ou-25-reais-via-pix/   (2×)
bancobmg.com.br/emprestimo/antecipacao-saque-aniversario-fgts/                   (2×)
upp.com.br/                                                                      (2×)
```

`meutudo.com.br` é **um portal de conteúdo concorrente** que monetiza o mesmo
leitor. Numa página cujo lucro é RPM menos CPC, um link de saída para concorrente
é o clique comprado indo embora de graça.

As pré-sells, ao contrário, têm **zero** links externos — nem oficiais.

## 7 · Os widgets: bonitos, mudos e sem porta de saída

Dois widgets interativos, ambos grandes e bem construídos visualmente:

```
P2 · "Simulador de Rota: Antecipação FGTS 2026"     13.885 ch
P3 · "Termômetro de Prontidão do FGTS"              17.885 ch
```

Medido nos dois:

| | P2 | P3 |
|---|---|---|
| `dataLayer` / evento de GTM | **0** | **0** |
| atributo `aria-` | **0** | **0** |
| `display:none` para trocar estado | 3 | 5 |
| `grid-area:1/1` + `visibility` (CLS zero) | não | não |
| link no resultado (CTA de saída) | **0** | **0** |

Três consequências:

1. **Sem medição.** A ferramenta que deveria ser o motivo de a sessão durar não
   emite um evento. Não há como saber se alguém a usou.
2. **CLS.** Painel de resultado com `display:none` → aparece e empurra o conteúdo.
   O engine novo resolve isso por construção; estes widgets são anteriores.
3. **Beco sem saída.** O leitor responde três perguntas, recebe o diagnóstico —
   e o resultado **não leva a lugar nenhum**. O momento de maior intenção da
   página inteira termina em texto estático.

## 8 · Distribuição de esforço

```
P1  12.467 ch   1 widget estático (caixa "A favor / Atenção")   nenhum interativo
P2  24.805 ch   1 estático + 1 interativo
P3  30.896 ch   4 estáticos + 1 interativo
```

P1 é a página de entrada das soluções, a que recebe o clique de P1 na LP, e é a
**mais pobre em recurso visual e a única sem ferramenta**.

## 9 · Achado solto

`LP.md` contém `[/su_spoile` — shortcode `su_spoiler` (Shortcodes Ultimate) órfão,
não fechado e provavelmente não renderizado no tema atual.
