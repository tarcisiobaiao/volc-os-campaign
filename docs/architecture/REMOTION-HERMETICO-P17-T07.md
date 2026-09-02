# Remotion hermético — medição, vendorização de fontes e decisão de licença (P17-T07)

**Data:** 01/09/2026 · **Estado:** medido; aceite **não fechado**
**Parque medido:** `/Users/mac/volc-factory/remotion` — **lido, nunca escrito**
**Dados estruturados:** `docs/architecture/remotion-hermetico.json`
**ADR de referência:** `docs/architecture/ADR-REMOTION-RUNTIME-STORAGE.md` (proposto, decide o dono do produto — este documento **não** o edita)

O aceite de P17-T07 é: *"render offline reproduz hash aprovado, não abre conexão
externa, carrega somente fontes necessárias e possui decisão de licença registrada
antes de faturar vídeo."*

Deste aceite, **uma parte está fechada e três não estão.** A decisão de licença tem
fato datado e está abaixo. As outras três exigem executar um render offline, e essa
execução está atrás de uma fronteira que esta lane não pode atravessar sem
autorização. A fronteira está nomeada no fim, com o comando exato que falta.

Tudo que segue foi **executado nesta máquina**. Onde não foi, está escrito
`NÃO PROVADO` e o motivo é o impedimento, não o esquecimento.

---

## 1. Lockstep — íntegro, e maior do que o ADR contou

O Remotion publica todos os pacotes na mesma versão no mesmo dia, e misturar
versões quebra de um jeito difícil de diagnosticar. Medido pacote por pacote, lendo
`node_modules/<pacote>/package.json`:

**21 pacotes, todos em `4.0.479`. Zero divergência.**

```
remotion  @remotion/cli  @remotion/renderer  @remotion/bundler  @remotion/player
@remotion/studio  @remotion/studio-server  @remotion/studio-shared  @remotion/transitions
@remotion/google-fonts  @remotion/media-utils  @remotion/media-parser  @remotion/paths
@remotion/shapes  @remotion/zod-types  @remotion/licensing  @remotion/streaming
@remotion/timeline-utils  @remotion/canvas-capture  @remotion/web-renderer
@remotion/compositor-darwin-arm64
```

O ADR listou **6**. São 21 — os outros 15 entram por resolução transitiva. Isso
muda a instrução prática: **pinar os 6 declarados deixa 15 flutuando.** O pin exato
tem de valer para a árvore inteira, e é o `package-lock.json` que hoje faz esse
trabalho, não o `package.json` (que declara `^4.0.0` nos seis).

**Ausentes e necessários para o plano do próprio ADR:** `@remotion/fonts` (é o que
troca `loadFont()` do Google por arquivo local — sem ele não existe hermetismo) e
`@remotion/rough-notation` (exige ≥ 4.0.490; a fábrica está em 4.0.479).

---

## 2. A dependência de rede que o ADR não viu: o navegador

O ADR trata hermetismo como problema de fonte. Medindo, a maior dependência de rede
do render **não é fonte**:

| | |
|---|---|
| Binário | Chrome Headless Shell **149.0.7790.0** |
| Onde | `node_modules/.remotion/chrome-headless-shell/…` |
| Tamanho | **159.972.320 bytes** (193 MB com a pasta) |
| No `package-lock.json`? | **Não.** Não é pacote npm |
| De onde vem | `remotion.media`, `storage.googleapis.com`, `playwright.azureedge.net` |

Um container frio que embuta as 11 fontes e nada mais **continua baixando 193 MB
antes do primeiro quadro**. Fontes são 106 URLs; o navegador é um único download
maior que todas elas somadas.

**A notícia boa, também medida:** a versão não flutua. `TESTED_VERSION =
'149.0.7790.0'` é constante compilada em
`@remotion/renderer@4.0.479/dist/browser/get-chrome-download-url.js:41`. **Pinar
`@remotion/renderer` exato pina o navegador** — o determinismo entre máquinas com a
mesma versão de renderer é sustentável, e o binário só precisa ser pré-assado na
imagem, não versionado à mão.

Duas consequências para quem for montar a imagem:

- **glibc ≥ 2.35** para os binários de `remotion.media` (constante
  `MINIMUM_GLIBC_FOR_REMOTION_MEDIA`, mesmo arquivo, linha 59). Ubuntu 24.04 serve;
  Alpine/musl vai por outro caminho.
- O compositor é **por plataforma** (`optionalDependencies` do renderer). Aqui está
  `@remotion/compositor-darwin-arm64`; um worker Linux resolve
  `@remotion/compositor-linux-x64-gnu`. **Equivalência de pixel entre macOS e Linux
  é NÃO PROVADA** e não deve ser presumida ao comparar hash aprovado.

---

## 3. Fontes — o que é baixado, o que é usado, e o que sobra

### 3.1 Quantas chamadas existem de fato

**32 chamadas `loadFont()` em 11 famílias**, não 34.

O ADR conta 34. Duas delas moram em `src/Holerite.tsx.bak`. `Root.tsx` não importa
esse arquivo, nenhum outro módulo o referencia, e o webpack só empacota o que é
alcançável a partir da raiz — conferido por busca de referências. **`.bak` não custa
rede.** A diferença é pequena e a corrijo pelo mesmo motivo que o resto existe: um
número repetido de ouvido deixa de ser medição.

### 3.2 O teto de rede é 229 faces, não 290 requisições

Lendo `getInfo()` de cada módulo `@remotion/google-fonts` e contando
estilo × peso × subset publicados:

| Família | Estilos | Pesos publicados | Subsets | **Faces** | URLs |
|---|---|---|---|---|---|
| IBM Plex Mono | normal+italic | 100–700 (7) | 5 | **70** | 70 |
| Archivo | normal+italic | 100–900 (9) | 3 | **54** | 6 |
| Cormorant Garamond | normal+italic | 300–700 (5) | 5 | **50** | 10 |
| Oswald | normal | 200–700 (6) | 5 | **30** | 5 |
| Cinzel | normal | 400–900 (6) | 2 | **12** | 2 |
| Anton | normal | 400 | 3 | **3** | 3 |
| VT323 | normal | 400 | 3 | **3** | 3 |
| Limelight | normal | 400 | 2 | **2** | 2 |
| Special Elite | normal | 400 | 2 | **2** | 2 |
| Archivo Black | normal | 400 | 2 | **2** | 2 |
| Creepster | normal | 400 | 1 | **1** | 1 |
| **Total** | | | | **229** | **106** |

O ADR lê "~290 requisições" do log. **O log conta a mesma família duas vezes.** As
linhas aparecem em pares — `Archivo 27` e `54`, `IBM Plex Mono 35` e `70`,
`Cormorant 25` e `50` — e em cada par o primeiro número é exatamente metade do
segundo. As três famílias que aparecem em par são **exatamente** as três que têm
itálico e romano; Oswald, que só tem romano, aparece uma vez só. Somar 25+50 conta
Cormorant duas vezes. O teto real, medido no metadado do pacote, é **229 faces
resolvendo 106 URLs distintas**.

Isso **não** enfraquece o argumento do ADR — 229 handles de `delayRender` por
quadro continua sendo cauda inaceitável. Corrige o número para que ele sobreviva à
próxima conferência.

Também refino "todos os pesos e os 5 subsets": vale para **3 famílias das 11**
(Oswald, IBM Plex Mono, Cormorant Garamond). As outras oito publicam 1 a 3 subsets.
O desperdício de cirílico e vietnamita em peça de língua portuguesa é real, e está
concentrado nessas três.

### 3.3 Usadas × baixadas: ninguém baixa fonte que ninguém usa

**Nenhuma das 11 famílias é supérflua ao conjunto.** As 11 são usadas por alguma
composição. O desperdício tem outra forma: `Root.tsx` importa as 15 composições no
topo e cada módulo chama `loadFont()` no topo do seu escopo, então **toda composição
paga o custo das 11 famílias**. Um `still` de `Corta` (Limelight, Oswald, Special
Elite) baixa Cormorant de `Esoterico`, Archivo de `Arquivo` e IBM Plex Mono de
`Holerite`. Confirmo o ADR aqui, inclusive na causa: é forma do bundle, não erro de
configuração.

**Zero das 32 chamadas passa `{weights, subsets}`** (`rg -n "weights|subsets"
src/*.tsx` não acha nada além de `fontWeight` de CSS).

### 3.4 O conjunto mínimo: 33 faces

Cruzando cada `fontFamily:` do código com o `fontWeight` do mesmo objeto de estilo,
e mantendo só `latin` + `latin-ext`:

**229 → 33 faces (−85,6%).**

Ao fazer esse cruzamento apareceu um defeito que ninguém tinha registrado:

> ⚠️ **Oswald é pedido em 800 e 900. O Google publica Oswald só até 700.**
> O código usa `fontWeight: 800` e `900` com a família Oswald em CausaFamilia,
> RelatoProibido, Lendas, TribunalZap, CartasPerdidas e Corta. Esses pesos **não
> existem** no arquivo. O que se vê hoje é **negrito sintetizado pelo Chrome** sobre
> o 700.

Isso importa para a vendorização e é uma armadilha exata: ao trocar o `.woff2`
variável do Google por um `.ttf` estático local, a síntese do Chrome parte de outro
arquivo e pode engordar diferente. **O peso 800/900 de Oswald tem de ser conferido
por hash de pixel, nunca assumido como equivalente.**

---

## 4. Vendorização — seguindo o precedente da bancada

O precedente é `backend/app/criativo/bancada/fontes/PROCEDENCIA.md`, e a razão dele
vale igual aqui: *"uma fonte resolvida por caminho de máquina faz o mesmo pedido
produzir assinaturas diferentes em máquinas diferentes"*. Detalhe que valida o
precedente: o `Inter-Variable.ttf` versionado na bancada tem sha256
`29160a80ff49ddca…`, **byte a byte idêntico** ao da PRENSA. A cópia foi fiel; é a
forma a replicar.

**`remotion/public` tem 0 arquivos de fonte** (`.ttf`/`.otf`/`.woff`/`.woff2`). Não
existe hoje caminho local para apontar.

### 4.1 Registro por família

| Família | Arquivo nesta máquina | sha256 | Licença | Estado factual |
|---|---|---|---|---|
| **Archivo** | `…/prensa-poc/fonts/Archivo-Variable.ttf` (658.596 B) | `0e094a7d3c7c4c25cf1310c4b30014f1dae9332220b1c2c88f4fa996f0b05053` | **OFL 1.1** (lida da tabela `name`) | **presente — cobertura completa** |
| **CormorantGaramond** | `…/prensa-poc/fonts/CormorantGaramond-Variable.ttf` (1.195.560 B) | `b20b7d9626dd956b2c5e558692ad328b1f19e3275e2782db4fa07670d83f35e0` | **OFL 1.1** (tabela `name`) | **presente — cobertura PARCIAL** |
| **IBMPlexMono** | `…/prensa-poc/fonts/IBMPlexMono-Bold.ttf` (137.784 B) | `ac27abd6450a64dd94467580a02fe6235156d5b92f2926ebbc8e7489df64e0be` | **OFL 1.1** (tabela `name`) | **presente — cobertura PARCIAL** |
| Limelight | — | — | não verificada (arquivo ausente) | `unavailable_on_machine` |
| Oswald | — | — | não verificada (arquivo ausente) | `unavailable_on_machine` |
| SpecialElite | — | — | não verificada (arquivo ausente) | `unavailable_on_machine` |
| Anton | — | — | não verificada (arquivo ausente) | `unavailable_on_machine` |
| Creepster | — | — | não verificada (arquivo ausente) | `unavailable_on_machine` |
| VT323 | — | — | não verificada (arquivo ausente) | `unavailable_on_machine` |
| Cinzel | — | — | não verificada (arquivo ausente) | `unavailable_on_machine` |
| ArchivoBlack | — | — | não verificada (arquivo ausente) | `unavailable_on_machine` |

As licenças das três presentes foram **lidas da tabela `name` do próprio arquivo**,
como manda o precedente — não do catálogo. As oito ausentes ficam com licença **não
verificada**: sem arquivo não há tabela `name` para ler, e o catálogo do Google não
é o arquivo. Registrar "OFL" para elas seria trocar ausência por fato.

Busca feita em `~/Library/Fonts`, `/System/Library/Fonts`, `/Library/Fonts`,
`~/Desktop` e `~/volc-factory` (fora de `node_modules`): **zero resultados** para as
oito.

### 4.2 As duas parciais são a armadilha

O ADR diz que as fontes da PRENSA "não têm par" com as 11. **Têm par parcial**, e é
pior do que não ter — porque parece resolvido.

> ⚠️ **Cormorant Garamond não tem itálico.** `src/Esoterico.tsx:180` renderiza o
> versículo com `fontFamily: CORM, fontStyle: 'italic'`. O
> `CormorantGaramond-Variable.ttf` da PRENSA tem **um eixo só, `wght` 300–700**,
> nenhum eixo `ital`/`slnt`, e `fsSelection.italic = false`. Vendorizar esse arquivo
> faz o Chrome **inclinar o romano por transformação** em vez de usar o itálico
> desenhado que o Google entrega hoje. Outro pixel — e a assinatura determinista
> **não acusaria**, porque o sha256 do arquivo seguiria estável. É exatamente o
> colapso *documentado ≠ verificado* que o protocolo proíbe.

> ⚠️ **IBM Plex Mono não tem o peso 400.** O código usa 400 e 700. A PRENSA tem
> `IBMPlexMono-Bold.ttf` (`usWeightClass` 700 ✓) e `IBMPlexMono-Light.ttf`
> (`usWeightClass` **300**, sha256 `780bcf65509d72a3…`). **300 não é 400.** Usar o
> Light no lugar do Regular muda o pixel de toda composição Holerite.

> ⚠️ **Archivo Black não é o Archivo em 900.** São famílias distintas com desenhos
> distintos. O `Archivo-Variable.ttf` presente **não** cobre `ArchivoBlack`.

**Saldo real da vendorização: 1 família coberta, 2 parciais, 8 sem nenhum arquivo.**

### 4.3 O que falta obter, com licença conferida

Oito arquivos, mais o itálico do Cormorant, mais o Regular 400 do IBM Plex Mono.
Cada um entra pela forma do `PROCEDENCIA.md`: arquivo no repositório, sha256
registrado, e as strings de copyright/licença **lidas da tabela `name`** e citadas.
Enquanto isso não existir, **render hermético não sobe** — não por escolha de
arquitetura, por falta de arquivo.

---

## 5. Composições — 15, sem Zod, e 12 com `defaultProps` que não fecham

`Root.tsx` declara **15** composições. A missão fala em 12 e o upgrade
4.0.479→4.0.518 conferiu por hash apenas `Corta`: **são 14 não conferidas, não 11.**

As 15 são idênticas em forma: `width={1080} height={1920}` literais,
`durationInFrames={P.durationInFrames}` e `fps={P.fps}` (hoje **690 frames a 30 fps
= 23,000 s**), `defaultProps={P}` com `P = ../props.json` — **o mesmo objeto para
todas** — e `calculateMetadata={meta as any}`.

**Zod: nenhuma.** Nenhuma `<Composition>` declara `schema`. `@remotion/zod-types`
está instalado e não é importado por nenhum arquivo de `src/`. Os `as any` em
`component` e `calculateMetadata` são o buraco exato onde o schema entraria.

Cruzando as props obrigatórias de cada assinatura `React.FC<Props>` com as chaves
que `props.json` realmente tem:

| | Composições |
|---|---|
| **`defaultProps` completos (3)** | `Copa`, `Esoterico`, `Holerite` |
| **Degradados — prop ausente, lida sob guarda (7)** | `Main`, `Gossip`, `Achadinhos`, `Promo`, `Lendas`, `Arquivo`, `Corta` |
| **Quebram — deref sem guarda (5)** | `TribunalZap` (`evidence.some`, `poll.t`), `RelatoProibido` (`endChoice.t`), `CartasPerdidas` (`endChoice.t`), `CausaFamilia` (`endChoice.t`), `BrigaEstado` (`times.map`) |

`Promo` é a mais distante do próprio default: **10 de 15 props obrigatórias** não
existem em `props.json`.

Isso não quebra a produção — o comentário em `Root.tsx:21` diz que em runtime manda
`--props=<workspace>/props.json`, e `defaultProps` é só default de preview. **Mas
muda o custo da Decisão 3 do ADR.** O ADR propõe adotar schema Zod argumentando que
"a incompatibilidade vira erro de build, não surpresa no render". Correto — e o
efeito imediato, medido, é que **declarar Zod hoje quebra o build de 12 das 15
composições** até alguém escrever `defaultProps` de verdade para cada uma. Isso é
desejável (o erro aparece cedo), mas é **trabalho a orçar**, não configuração a
ligar. `defaultProps` compartilhado entre 15 composições **não pode ser o contrato**
que a Decisão 3 quer que ele seja.

*Limite do método:* classificação por varredura estática do corpo de cada
componente, não por preview executado. Executar esbarra na mesma fronteira da seção 7.

---

## 6. Licença — fato datado, não memória

Consultado em **01/09/2026**. O ADR registra os preços como "NÃO CONFIRMADOS"; parte
disso continua verdade e parte foi resolvida em outra URL.

**Fontes:** `https://www.remotion.dev/license` (307 → `github.com/remotion-dev/remotion/blob/main/LICENSE.md`) · `https://www.remotion.pro/license` · `https://www.remotion.dev/docs/license/faq`

### Limiar de organização

> *"You are eligible to use Remotion for free if you are: an individual, a
> for-profit organization with up to 3 employees, a non-profit or not-for-profit
> organization"* — LICENSE.md oficial

**Até 3 pessoas: grátis. A partir de 4: Company License paga.** Confirma o ADR.

**Fato novo e é o que mais atinge a VOLC:** a FAQ oficial diz que, quando uma
agência contrata terceiros ou outros estúdios para trabalhar **no mesmo projeto**, a
headcount deles **soma com a sua** para o limiar de 4 pessoas. A VOLC é agência. A
contagem não é a folha de pagamento.

### Preços

| Opção | Preço | Para quê |
|---|---|---|
| **Remotion for Automators** | **US$ 0,01 por render, mínimo US$ 100/mês** (cobrado em blocos de 1000 renders = US$ 10) | pipeline automatizada, prompt-to-video, **embutir o Player** |
| **Remotion for Creators** | **US$ 25/mês por assento** (1 assento por usuário) | operador humano |
| Enterprise | a partir de US$ 500/mês — **NÃO CORROBORADO** | — |

O Enterprise apareceu numa leitura de `remotion.pro/license` e **não se repetiu** na
segunda leitura da mesma URL. Fica como indício, não como preço.

`/docs/license/pricing` **continua renderizando por componente e sem números no HTML
servido** — o obstáculo que o ADR descreveu segue de pé. Os valores acima vieram de
`remotion.pro/license`, URL que o ADR não citou, e foram obtidos em duas leituras
independentes que concordaram.

### O que conta como render

> *"1 Render é a geração bem-sucedida de um vídeo, áudio, GIF, PDF ou imagem
> estática."* · *"Previews no Remotion Studio ou no Remotion Player NÃO contam como
> Renders."*

### ⚠️ Onde isto contradiz a Decisão 4 do ADR

O ADR conclui, no Risco 1, que *"preview no Player e no Studio não conta"*, e na
Decisão 4 que o `<Player>` *"cabe no app Vercel hoje, sem tocar em backend"*.

A primeira metade é verdadeira: preview não é render, não gera custo por render.
**A conclusão não fecha.** A FAQ oficial de hoje classifica **embutir o Player num
site** como automação, e automação exige Company License na opção **Automators, no
mínimo de US$ 100/mês** — mesmo que nenhum vídeo seja renderizado no mês.

Ou seja: **a Decisão 4 tem preço de tabela, e o ADR não o atribuiu a ela.**
"Sem tocar em backend" continua certo. "Sem custo" nunca foi dito, mas é o que se
lê. Isso precisa ir para o dono do produto antes de o Player entrar no app.

### Achado colateral: os termos não estão no artefato

O pacote npm `remotion` declara `"license": "SEE LICENSE IN LICENSE.md"` e **não
publica o `LICENSE.md` no tarball** — o arquivo não existe em
`node_modules/remotion/`, e o `README.md` aponta para um link que não resolve
localmente. Os irmãos MIT (`@remotion/paths`, `@remotion/shapes`,
`@remotion/media-utils`) publicam o seu. Conclusão prática: **a licença do Remotion
só pode ser conferida na web, com data.** Nem memória nem `node_modules` servem —
que é a razão desta seção existir com URL e data em vez de repetir o ADR.

### O que a VOLC precisa decidir antes de faturar vídeo

1. **Quantas pessoas a VOLC tem para efeito da licença**, contando contratados e
   estúdios parceiros do mesmo projeto. Acima de 3, a Free License não se aplica e
   nada aqui é opcional.
2. **Se o `<Player>` vai ao app.** Pela FAQ isso já é automação e puxa Automators
   com mínimo de US$ 100/mês, independente de volume.
3. **Qual opção cobre o desenho da fábrica.** Automators casa com pipeline
   automatizada; Creators é para operador humano no Studio. Pipeline + Player
   embutido cai em Automators.
4. **Registrar a decisão** — é a única metade do aceite de P17-T07 que está ao
   alcance hoje, e ela depende de uma pessoa, não de código.

---

## 7. Hermetismo — o que provei, e a fronteira exata que impede o resto

### 7.1 Provado, lendo o código instalado

**A falha é fechada.** `@remotion/google-fonts@4.0.479/dist/cjs/base.js` abre
`delayRender(label, {timeoutInMilliseconds: 60000})` por face (linha 96) e, no
`catch`, depois de 2 tentativas faz `throw err` **sem chamar
`continueRender(handle)`** (linhas 117–123). O handle nunca é liberado: o render
trava e aborta. **Não troca de fonte silenciosamente.** Confirma o adendo de 29/08
do ADR, agora lendo o código instalado em vez do experimento.

**E custa tempo, não erro imediato.** Cada tentativa espera **18.000 ms**
(`base.js:22` — apesar de a função se chamar `loadFontFaceOrTimeoutAfter20Seconds`)
e são 2 tentativas, dentro de um handle de 60 s. Um blackhole de rede **estaciona
~36–60 s antes de abortar**. Isso é orçamento de timeout do worker; um worker com
timeout de 30 s reportaria "timeout" onde a causa é "sem rede", e o operador
caçaria o defeito errado.

**Bloqueio por proxy é inerte.**
`@remotion/renderer@4.0.479/dist/browser/open-browser.js:103-105` lança o Chromium
com `--no-proxy-server`, `--proxy-server='direct://'` e `--proxy-bypass-list=*`, e
**não existe `--offline`** em nenhum ponto do renderer ou do CLI. Confirma o ADR:
`HTTP_PROXY`/`HTTPS_PROXY` não bloqueiam nada.

**O alvo é mensurável:** 229 faces / 106 URLs em `fonts.gstatic.com`, mais os 193 MB
do Chrome Headless Shell em container frio.

### 7.2 NÃO PROVADO: o aceite propriamente dito

*"Render offline reproduz hash aprovado e não abre conexão externa"* exige
**executar** um render com a rede desligada e comparar hash. **Não executei nenhum
render.** Os três caminhos estão fechados:

| Caminho | O que exigiria | Por que está fechado |
|---|---|---|
| (a) Renderizar no parque | `npx remotion still` em `/Users/mac/volc-factory/remotion` | Grava bundle e saída **dentro do parque**. O parque é READ-ONLY por regra da missão. |
| (b) Renderizar na worktree | `npm install --save-exact remotion@4.0.479 @remotion/cli @remotion/google-fonts @remotion/fonts` | Regra 5 da missão proíbe instalar dependências. Não há `node_modules` de remotion aqui. |
| (c) Copiar o parque | copiar 624 MB de `node_modules` | É instalação com outro nome; e o primeiro render ainda precisaria dos 193 MB do Chrome Headless Shell. |

E mesmo vencido o (a)/(b)/(c), **desligar a rede de verdade** não se faz com
variável de ambiente — a prova do `--no-proxy-server` acima mostra por quê.
Exigiria `pf`/`pfctl` com **sudo**, ou um namespace de rede, que o macOS não oferece
como o Linux. O monitor de `lsof` que o ADR usou em 29/08 é **amostragem**: prova
presença de conexão, não prova ausência.

### 7.3 As três autorizações que fechariam o aceite

1. **Escrever numa cópia do parque fora dele** (ex.: `/private/tmp/remotion-hermetico-poc`),
   com permissão de rodar `npm install --save-exact` das 21 versões mais
   `@remotion/fonts`.
2. **Obter e versionar as 8 famílias ausentes** com licença conferida na tabela
   `name`, mais o itálico do Cormorant e o Regular 400 do IBM Plex Mono. **Sem isto
   o render hermético nem sobe** — 8 de 11 famílias não existem nesta máquina.
   É pré-requisito de arquivo, não de arquitetura.
3. **`sudo` para `pf`/`pfctl`**, ou um Linux com `netns`, para provar "zero conexão
   externa" por bloqueio real em vez de monitor por amostragem.

Sem as três, o honesto é o que está escrito aqui: **hermetismo é viável e
mensurado, e não está provado.**

---

## 8. Onde esta medição toca o ADR

Este documento **não edita** `ADR-REMOTION-RUNTIME-STORAGE.md`, que segue proposto e
é decisão do dono.

**Confirmo:** lockstep íntegro em 4.0.479 sustentado pelo lockfile e não pela
declaração; falha de fonte dura e sem artefato; proxy por variável de ambiente
inerte; fontes da PRENSA não cobrem as 11; `/docs/license/pricing` sem números;
nenhuma composição com Zod.

**Atualizo:** são **21** pacotes em lockstep, não 6 — pinar 6 deixa 15 flutuando;
são **32** chamadas `loadFont` no bundle, não 34 (duas estão num `.bak` que ninguém
importa); o teto de rede é **229 faces / 106 URLs**, não ~290 requisições; "todos os
pesos e 5 subsets" vale para **3 famílias das 11**; são **15** composições e **14**
não conferidas no upgrade, não 11.

**Contradigo, em quatro pontos:**

1. **"As fontes da PRENSA não têm par com as 11."** Têm par **parcial**: Archivo
   cobre por inteiro; Cormorant cobre o peso mas **não o itálico** que
   `Esoterico.tsx:180` pede; IBM Plex Mono cobre o 700 mas **não o 400**. Saldo: 8
   sem arquivo, 1 coberta, 2 parciais — e as parciais são o risco, porque parecem
   resolvidas e falham sem acusar.
2. **Hermetismo não é só fonte.** A maior dependência de rede é o **Chrome Headless
   Shell 149.0.7790.0, 193 MB, fora do `package-lock.json`**. Embutir as 11 fontes e
   esquecer o navegador não produz worker hermético.
3. **"Preview no Player não conta"** é verdadeiro para contagem de render e
   insuficiente como conclusão: **embutir o Player num site é automação** pela FAQ
   oficial de hoje, e exige Company License Automators com mínimo de **US$ 100/mês**.
   A Decisão 4 do ADR tem preço, e ele não foi atribuído.
4. **Adotar Zod não é configuração.** Hoje **12 das 15** composições têm props
   obrigatórias ausentes de `defaultProps` (5 delas com deref sem guarda). Declarar
   `schema` quebra o build dessas 12 no primeiro dia. É o resultado certo, e é
   trabalho a orçar.

**Novo, que o ADR não registra:** Oswald é pedido em **800 e 900** e o Google publica
Oswald só **até 700** — o que se vê hoje é negrito sintetizado, e vendorizar exige
conferir esse pixel por hash em vez de assumir equivalência.
