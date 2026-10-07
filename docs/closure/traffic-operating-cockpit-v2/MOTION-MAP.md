# MOTION-MAP — o movimento desta sprint, e por que ele é quase nada

## O resumo honesto

**Esta sprint não acrescentou nenhuma animação.** A única transição no código
novo é `transition-volc duration-150` no hover/foco de um botão de releitura.

Não é omissão: é a resposta certa para o que foi construído. A escada de portões
e a lista de etapas são **leitura** — o operador chega para saber se pode fazer
algo e por que não. Movimento aqui competiria com o trabalho.

## O que existe, item a item

| Onde | Movimento | Duração | Propriedade | Por quê |
|---|---|---|---|---|
| Botão "Tentar ler de novo" (falha total) | cor de fundo no hover/foco | 150ms | `transition-volc` | resposta imediata ao ponteiro; nada de layout |
| Botão "Tentar ler de novo" (aviso de releitura) | idem | 150ms | idem | idem |
| Etapa clicável da conversa (herdado) | `transition-colors` no hover | 150ms | cor | herdado de `ConversaDeCriacao` |

`transition-volc` é o vocabulário do projeto (`tailwind.config.ts`) e cobre
exatamente o que o `design.md` autoriza animar — cor, borda, sombra, transform e
opacidade. Ele **não** inclui width, height, top e left, que são layout.
`transition-all` é banido pelo contrato e não aparece no código novo.

## O que NÃO foi feito, e a razão é de honestidade

**A varredura de evidência do §8.4 não existe.**

`POST /provar` é UMA requisição HTTP. Não há sub-fases observáveis: nenhuma
notificação parcial, nenhum stream, nenhum endpoint de status. Animar nove fases
— identidade, destino, política, estrutura, orçamento, mensuração, conta,
idempotência, autorização — sobre uma única chamada seria progresso movido a
temporizador. É exatamente o "loader falso" e a "IA analisando sem fase real
correspondente" que o próprio briefing proíbe.

A varredura honesta existe, e é uma sprint própria: encadear atos **realmente
sequenciais** (validação local → leitura do destino → releitura dos portões →
prova na conta), cada um com tempo próprio e resultado factual próprio, e mover a
barra quando cada um termina de verdade.

## `prefers-reduced-motion`

O projeto já tem a regra global (`src/index.css:567`): sob `reduce`, toda
animação e transição caem para `0.01ms`, exceto o que estiver marcado
`data-motion="essencial"` e os dois indicadores de progresso indeterminado.

O código novo **não** marca nada como essencial, então a regra o cobre inteiro.

### A evidência, e o seu limite

13 cenas capturadas em 1440×900 com `reducedMotion: 'reduce'`, comparadas
byte a byte com as mesmas cenas em modo normal: **12 idênticas, 1 diferente**.

⚠️ **A diferença é ruído de captura, não movimento.** Duas capturas da MESMA cena
no MESMO modo (`jornada__search-criavel`) também produzem bytes diferentes — a
serialização do PNG não é determinística aqui. Registrar "12 de 13" como prova de
reduced-motion seria contar sorte como medida.

**A evidência conclusiva é estrutural, não fotográfica:** o módulo novo não tem
`animate-*`, não importa `framer-motion`, não declara `keyframes`, e a única
`transition` que ele usa é neutralizada pela regra global. Isso se lê no arquivo,
e não depende de o compressor de PNG concordar consigo mesmo.
