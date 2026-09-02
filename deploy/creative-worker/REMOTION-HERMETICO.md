# Creative worker — o que um render hermético exigiria

**Data:** 01/09/2026 · **Estado em 02/09/2026:** parcialmente CUMPRIDO — ver adendo no fim

⚠️ Este documento foi escrito antes de existir runtime neste diretório, e o
"nada implantado" do cabeçalho original deixou de ser verdade. O texto abaixo
permanece como foi medido; o adendo diz o que mudou.
**Medição de origem:** `docs/architecture/REMOTION-HERMETICO-P17-T07.md` e `docs/architecture/remotion-hermetico.json`

O `README.md` deste diretório diz que ele é território reservado e que nada aqui
representa um worker disponível. **Isso continua verdade.** Este arquivo não muda
esse estado: ele registra o que a medição de P17-T07 provou que um worker
precisaria, para que ninguém desenhe a imagem em cima de suposição.

Nenhum item abaixo está feito. A ordem é de bloqueio: **1 e 2 impedem o worker de
existir**; 3 a 6 impedem que ele seja hermético; 7 impede que ele seja faturável.

---

## 1. As fontes — bloqueio de arquivo, não de arquitetura

A fábrica usa **11 famílias**, todas carregadas de `fonts.googleapis.com` em tempo
de render. **8 delas não existem em nenhum lugar desta máquina** e 2 das 3 presentes
cobrem só parte do que o código pede:

| Estado | Famílias |
|---|---|
| Presente e cobre | Archivo |
| Presente e **não** cobre | **CormorantGaramond** (sem itálico; `Esoterico.tsx:180` pede itálico) · **IBMPlexMono** (tem 700 e 300; o código usa 700 e **400**) |
| Sem arquivo algum | Limelight, Oswald, SpecialElite, Anton, Creepster, VT323, Cinzel, ArchivoBlack |

**Enquanto isso não for resolvido, um worker hermético não sobe.** Não é escolha de
runtime; é falta de arquivo. Cada fonte obtida entra pela forma de
`backend/app/criativo/bancada/fontes/PROCEDENCIA.md`: arquivo versionado, sha256
registrado, e copyright/licença **lidos da tabela `name` do próprio arquivo**.

⚠️ Duas armadilhas que a imagem precisa evitar, porque **falham sem acusar**:
substituir o itálico do Cormorant por romano inclinado, e substituir o Regular 400
do IBM Plex Mono pelo Light 300. Nos dois casos o pixel muda e o `sha256` do arquivo
de fonte continua estável — a assinatura determinista **não pegaria**.

⚠️ Terceira: **Oswald é pedido em 800 e 900, e o Google publica só até 700.** O
negrito de hoje é sintetizado pelo Chrome. Ao vendorizar, esse pixel tem de ser
conferido por hash, nunca assumido.

## 2. Tocar 15 arquivos da fábrica, que é repositório de outra frente

São **32 chamadas `loadFont()`** de `@remotion/google-fonts` espalhadas por 15
módulos. Hermetismo exige trocá-las por `@remotion/fonts`
(`loadFont({family, url: staticFile(...)})`). Não dá para fazer numa composição só:
`Root.tsx` importa as 15 no topo e cada módulo chama `loadFont()` no seu topo, então
**toda composição paga o custo das 11 famílias**. Enquanto uma única chamada de
Google Fonts sobreviver no bundle, o render inteiro continua pedindo rede.

## 3. Assar o navegador na imagem — o item que a discussão de fontes escondeu

| | |
|---|---|
| Binário | **Chrome Headless Shell 149.0.7790.0** |
| Tamanho | **159.972.320 bytes** (193 MB com a pasta) |
| Onde vive | `node_modules/.remotion/chrome-headless-shell/` |
| Está no `package-lock.json`? | **Não.** Não é pacote npm |
| De onde baixa | `remotion.media`, `storage.googleapis.com`, `playwright.azureedge.net` |

**Um container frio que embuta as 11 fontes e nada mais continua baixando 193 MB
antes do primeiro quadro.** As fontes somam 106 URLs; o navegador é um download
único maior que todas elas.

A parte boa: a versão **não flutua**. `TESTED_VERSION = '149.0.7790.0'` é constante
compilada em `@remotion/renderer@4.0.479` — pinar o renderer pina o navegador. Basta
pré-assar o binário na imagem no passo de build (com rede) para que o passo de
render (sem rede) não precise dele.

**Restrições da imagem base, medidas no código:**
- **glibc ≥ 2.35** para os binários de `remotion.media` (`MINIMUM_GLIBC_FOR_REMOTION_MEDIA`,
  `get-chrome-download-url.js:59`). Ubuntu 24.04 serve; Alpine/musl vai por outro caminho.
- O **compositor é por plataforma** (`optionalDependencies` do renderer). Esta
  máquina tem `@remotion/compositor-darwin-arm64`; um worker Linux resolve
  `@remotion/compositor-linux-x64-gnu` ou `-musl`.

⚠️ **Equivalência de pixel entre macOS e Linux é NÃO PROVADA.** O "hash aprovado" do
aceite tem de ser gerado **na mesma plataforma do worker**. Comparar hash de macOS
com render de Linux é colapsar *local ≠ produção*.

## 4. Pinar 21 pacotes, não 6

Todos os `@remotion/*` publicam a mesma versão no mesmo dia e misturar versões
quebra de modo difícil de diagnosticar. Estão instalados **21 pacotes, todos em
`4.0.479`** — o `package.json` declara `^4.0.0` para seis, e os outros 15 entram por
resolução transitiva. **O lockstep é sustentado pelo `package-lock.json`.** A imagem
do worker precisa de `npm ci` sobre lockfile versionado, nunca `npm install`.

Faltam dois pacotes que o plano exige: `@remotion/fonts` (é o que troca Google Fonts
por arquivo local) e `@remotion/rough-notation` (exige ≥ 4.0.490; a fábrica está em
4.0.479).

## 5. Orçamento de timeout — sem rede o render não falha rápido

Medido em `@remotion/google-fonts@4.0.479/dist/cjs/base.js`: cada face abre
`delayRender(..., {timeoutInMilliseconds: 60000})` (linha 96) e o `catch` faz
`throw err` **sem `continueRender(handle)`** (linhas 117–123). Cada tentativa espera
**18.000 ms** (linha 22) e são **2 tentativas**.

**Um blackhole de rede estaciona ~36–60 s antes de abortar.** Um worker com timeout
de 30 s reportaria "timeout" onde a causa é "sem rede", e o operador caçaria o
defeito errado. O timeout do worker tem de ser maior que 60 s, e o erro de fonte
precisa aparecer como erro de fonte.

A propriedade boa a preservar: **sem a fonte, o render aborta e não gera arquivo.**
Nunca sai peça errada com recibo dizendo "mesmas versões". Isso é comportamento de
4.0.479/4.0.518 e **tem de ser reconferido a cada bump maior** — se uma versão
futura adotar fallback tolerante, o hermetismo deixa de ser garantia e vira
esperança.

## 6. Bloqueio de rede: variável de ambiente não serve

`@remotion/renderer/dist/browser/open-browser.js:103-105` lança o Chromium com
`--no-proxy-server`, `--proxy-server='direct://'` e `--proxy-bypass-list=*`, e **não
existe `--offline`** no renderer nem no CLI. `HTTP_PROXY`/`HTTPS_PROXY` apontando
para porta morta **não bloqueiam nada**.

O bloqueio precisa ser da infraestrutura: container sem egresso, `netns`, ou regra
de firewall. E a prova de "zero conexão externa" precisa ser **bloqueio real** —
monitor de `lsof` por amostragem prova presença de conexão, nunca ausência.

## 7. Licença — decidida antes de faturar vídeo

Consultado em **01/09/2026** (`remotion.dev/license` → `LICENSE.md`,
`remotion.pro/license`, `remotion.dev/docs/license/faq`):

- **Grátis até 3 pessoas.** A partir de 4, Company License paga.
- **Contratados somam.** A FAQ diz que terceiros e estúdios contratados para o mesmo
  projeto agregam headcount ao limiar de 4. A VOLC é agência: a contagem não é a
  folha de pagamento.
- **Automators:** US$ 0,01/render, **mínimo US$ 100/mês**. **Creators:** US$ 25/mês
  por assento.
- **Embutir o `<Player>` num site é automação** e exige Automators no mínimo de
  US$ 100/mês, **mesmo sem renderizar nada no mês**. Preview não conta como render;
  embutir conta como automação. São coisas diferentes.

Um worker de render automatizado cai em **Automators**. Isso é decisão do dono do
produto e é a metade do aceite de P17-T07 que **não depende de código** — depende de
uma pessoa responder quantas pessoas a VOLC tem para efeito da licença.

---

## Fronteira: por que nada disto foi executado

A medição foi feita **lendo** o parque `/Users/mac/volc-factory/remotion`, que é
READ-ONLY. **Nenhum render foi executado.** Renderizar exigiria escrever no parque
(proibido), instalar dependências na worktree (proibido) ou copiar 624 MB de
`node_modules` (instalação com outro nome). Desligar a rede de verdade exigiria
`sudo pfctl` ou um Linux com `netns`.

Portanto: **o hermetismo está medido e não está provado.** Este diretório continua
sem imagem, sem manifesto e sem processo implantável, exatamente como o `README.md`
declara.


---

# Adendo de 02/09/2026 — o que passou a existir

`deploy/creative-worker/remotion-runtime/` é um runtime Remotion **do VOLC O.S.**,
e não a fábrica externa. A diferença é o custo do hermetismo: a fábrica tem 15
composições e 11 famílias de fonte não licenciadas aqui; este runtime tem UMA
composição e UMA família — a Inter, já versionada sob OFL 1.1.

| Requisito deste documento | Estado |
|---|---|
| fontes locais, licenciadas e mínimas | **cumprido** — Inter (OFL 1.1), sha256 no recibo |
| nenhuma conexão externa durante o render | **cumprido e PROVADO** — `sandbox-exec` com `(deny network-outbound)`; o kernel devolve `EPERM`, e a sonda que confirma isso roda dentro do processo do render |
| versões em lockstep | **cumprido** — 16 pacotes `@remotion/*` em 4.0.479 exatos, lidos do lockfile |
| isolamento por processo e diretório | **cumprido** — diretório exclusivo por reivindicação, grupo de processos próprio, `killpg` no timeout |
| hash reprodutível | **cumprido** — 4 execuções do mesmo pedido dão o mesmo sha256 do container (`scripts/provar-render-hermetico.sh`) |
| orçamento de timeout | **cumprido** — `CRIATIVO_REMOTION_TIMEOUT_S`, com a árvore de processos derrubada |
| bloqueio de rede por infraestrutura | **cumprido em macOS**; em Linux exige container sem egresso ou netns, e o gate REPROVA sem prova de bloqueio |
| imagem / manifesto / processo implantável | **NÃO cumprido** |
| equivalência de pixel macOS ↔ Linux | **NÃO PROVADA** |
| decisão de licença do Remotion | **pendente, e do dono** |

⚠️ A propriedade "sem a fonte o render falha duro e não deixa artefato" continua
valendo para 4.0.479 e é reconferida a cada execução do script (DEGRAU 6). Se uma
versão futura adotar fallback tolerante, o hermetismo deixa de ser garantia e
passa a ser esperança — re-testar a cada bump maior.
