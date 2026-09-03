# UX-READOUT — o que foi validado no navegador, e como reproduzir

## Recibo reproduzível

A página real (`/pautador-pro`) está atrás de `ProtectedRoute` e exige o
Supabase oficial, que esta missão está proibida de tocar. A validação usou um
**harness dev** que monta os MESMOS componentes com fixtures, fora do
roteamento do app e **fora do bundle** (`vite build` não produz `harness.html`
— verificado em `dist/`).

```bash
# 1 · servidor
./node_modules/.bin/vite --port 5199 --strictPort

# 2 · capturas (Chrome do sistema, headless)
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CH" --headless=new --disable-gpu --virtual-time-budget=9000 \
  --window-size=1440,5200 --screenshot=desktop.png \
  "http://localhost:5199/harness.html"

# mobile: o headless do Chrome no macOS tem PISO de 500px de viewport, então
# `--window-size=390` produz um RECORTE de um layout de 500, não um layout de
# 390. Por isso o container é constrangido por querystring:
"$CH" --headless=new --disable-gpu --virtual-time-budget=9000 \
  --window-size=520,1400 --screenshot=mobile390.png \
  "http://localhost:5199/harness.html?so=comparador&w=390"
```

O harness imprime um **diagnóstico medido** no rodapé (overflow + contraste),
então o recibo não depende de eu olhar o screenshot e opinar.

Screenshots ficaram em diretório temporário (`scratchpad/ui/`) e **não foram
versionados** — nenhum dado privado, mas também nenhum binário no Git.

---

## Diagnóstico medido — resultado final

```
viewport=1430  scrollWidth=1430  body_rola_horizontal=false
elementos_fora_de_scroller_que_estouram=0
nos=440  folhas_com_texto=260
contraste: 208 medidos, 0 abaixo do piso WCAG
```

`208 medidos` importa tanto quanto `0 reprovados`: um gate que mede zero
elementos não é um gate verde. Ver "o probe errou três vezes", abaixo.

---

## O probe errou três vezes antes de ser confiável

Registrado porque um gate de acessibilidade que passa por engano é pior que
gate nenhum — ele produz uma afirmação falsa com aparência de prova.

| versão | defeito | o que reportava | o que era |
|---|---|---|---|
| 1 | `requestAnimationFrame` logo após `createRoot().render()` | `contraste: 0 medidos, 0 abaixo do piso` | React 18 commita assíncrono; media um DOM **vazio**. "Aprovação" de nada. |
| 2 | sem composição de alfa | `26 abaixo do piso`, com razões de `1.00` | lia `bg-info/[.07]` na força cheia; as reprovações eram artefato do probe |
| 3 | composição correta | **`50 abaixo do piso`** | reprovações **reais**, nos meus próprios componentes |

A correção do probe deixou o gate **mais rigoroso**, não menos. As 50
reprovações eram minhas: usei modificadores de opacidade (`/80`, `/60`, `/50`)
em texto com significado, e isso derruba `text-muted-foreground` abaixo de
4,5:1.

Correções aplicadas, em duas classes:

1. **Texto com significado perdeu a opacidade.** A explicação de cada grupo, a
   procedência do rodapé, os itens de lista, os números da tabela e o nome do
   tema passaram a usar o token cheio.
2. **Pontuação decorativa ganhou semântica em vez de contraste.** A barra em
   `4 / 0` é pontuação: a célula ganhou
   `aria-label="4 fatos, 0 desconhecidos"` e a barra saiu da árvore de
   acessibilidade. Isentar `aria-hidden` do piso segue a WCAG 1.4.3, que
   isenta conteúdo puramente decorativo — o significado está na palavra ao
   lado, e essa **é** medida.

O travessão de valor ausente (`—`) **não** foi tratado como decorativo: ele
afirma "não há valor", que é significado. Ganhou contraste cheio e
`aria-label`.

Progressão: **50 → 5 → 0**, com 208 nós medidos.

---

## Estados validados

| estado | o que a tela precisa provar | resultado |
|---|---|---|
| **pronto · aprofundar** | decisão legível em 3s, formato com os observáveis que o geraram | ✓ glifo + palavra + frase; chips com `max ramos_de_acao 3` |
| **ausente · experimentar** | ausência vira desconhecido declarado e propõe experimento | ✓ bloco `DESCONHECIDOS 2 · Buraco declarado. Não é zero.` |
| **bloqueado** | motivo do bloqueio e próximo ato, sem falta de dado | ✓ "O canal oficial fecha todas as 4 perguntas sozinho" |
| **contradição** | dois sinais discordam e ninguém resolveu em silêncio | ✓ bloco destacado, primeiro, com `ring-destructive` |
| **retido** | sem base para comparar, e por quê | ✓ "cobertura 0.3 abaixo do mínimo 0.5" |
| **sem validação** | lacuna declarada, não veredito | ✓ "Nunca medido"; índice e cobertura em `—`, **nunca 0** |
| **carregando** | esqueleto preserva layout, sem spinner no meio do conteúdo | ✓ |
| **falha** | não apaga a tela sem explicar | ✓ "O que está na tela pode estar desatualizado" |
| **vazio** | ensina a interface | ✓ "Arraste cards para Em validação — ou meça a coluna inteira" |

---

## Evidência, hipótese e decisão são visivelmente distintas

Os três conjuntos são **blocos irmãos, sempre visíveis**, cada um com glifo,
título, contagem e uma frase que diz o que aquele conjunto é:

```
◆ FATOS 4          Medido por sensor ou contado sobre a resposta escrita.
◇ HIPÓTESES 1      Vem de fora deste card. Não move a decisão.
· DESCONHECIDOS 2  Buraco declarado. Não é zero.
≠ CONTRADIÇÕES 2   Dois sinais discordam. Ninguém resolveu por você.
```

Nenhum deles está atrás de aba, acordeão ou tooltip. Esconder o desconhecido
atrás de um clique é a forma mais barata de transformar lacuna em confiança, e
é exatamente o que a missão proíbe.

O prior do Webgo, quando ligado, viaja com procedência **na própria linha**:
`[prior webgo/ramificacao-cosmetica · confiança media · controle parcial]`.

---

## Comparação sem falso ranking

É **tabela**, não grade de cartões — a pergunta é "esta acima daquela?", então
as colunas alinham. Contrato de design do produto: inventário comparável é
tabela.

- **Não existe coluna `score`.** Verificado por teste
  (`não inventa coluna de nota`).
- As colunas são: `#`, Tema, Decisão (glifo + palavra), Formato, Índice,
  Cobertura, Fato/Desc — com numerais tabulares.
- **Cobertura ao lado do índice, sempre.** Um índice de 0,91 sobre 30% de
  cobertura é opinião sobre o vazio, e a tabela mostra os dois juntos.
- **`FORA DO RANKING 2`** é uma seção própria: o card sem base **não some** e
  não é ordenado. Traz o motivo escrito.
- A ordenação é a do servidor (`oportunidade.comparar`). Reordenar no cliente
  criaria duas verdades.

---

## Teclado e leitor de tela

- Linha da tabela: `role="button"`, `tabIndex=0`, `aria-pressed`, e responde a
  **Enter** e **Espaço** (testado em vitest, não só afirmado).
- `<caption class="sr-only">` em cada tabela.
- `<th scope="col">` em todas as colunas.
- Cada bloco de procedência é `<section aria-labelledby>`.
- A tese é `<article aria-label="Tese de oportunidade: …">`.

---

## Responsivo

Em container de **390px reais** (não recorte):

```
viewport=520  scrollWidth=520  body_rola_horizontal=false
elementos_fora_de_scroller_que_estouram=0
```

A tabela rola **dentro do próprio container** (`overflow-x-auto` +
`min-w-[560px]`), com a barra visível sob as linhas. O corpo da página nunca
rola na horizontal. Os chips de observável reflowem para várias linhas; nenhum
texto é cortado.

---

## Movimento

Uma entrada só, de 180ms, `cubic-bezier(.22,1,.36,1)`, em `opacity` e
`transform` — nunca em propriedade de layout. Envolvida em
`@media (prefers-reduced-motion: no-preference)`. A linha da tabela usa
`[transition:background-color_160ms_…]`, propriedade nomeada, nunca
`transition: all`.

---

## O que NÃO foi validado

- Leitor de tela real (VoiceOver/NVDA). A árvore de acessibilidade foi montada
  e testada por atributo, não ouvida.
- Safari e Firefox. Só Chromium.
- `prefers-reduced-motion: reduce` ativo no sistema: a regra existe e foi
  lida, não exercitada.
- Tema escuro: os tokens existem e o contraste foi medido **no claro**.
- O fluxo real de arraste ponta a ponta, porque exige o Supabase oficial.
  O que foi exercitado do arraste está em vitest e nos testes de rota.
