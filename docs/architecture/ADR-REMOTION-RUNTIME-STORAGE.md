# ADR — Remotion, runtime de render e storage do Estúdio Criativo

**Data:** 28/08/2026 · **Estado:** proposto · **Decide:** dono do produto
**Fontes:** somente `remotion.dev` (docs oficiais) e registry npm, verificados em 28/08/2026.
Onde a doc não confirmou, está escrito **NÃO CONFIRMADO** — não preenchi com o plausível.

## Contexto medido, não suposto

| Fato | Valor | Onde conferi |
|---|---|---|
| Remotion mais recente | **4.0.518** | `registry.npmjs.org/-/package/remotion/dist-tags` |
| Remotion **instalado** na fábrica VOLC | **4.0.479** | `/Users/mac/volc-factory/remotion/node_modules/remotion/package.json` |
| Range declarado na fábrica | `^4.0.0` em todos os pacotes | `remotion/package.json` |
| Distância | 39 patches, tudo dentro de 4.0.x | — |
| Zod nos props | **não existe** — `type Props` inline nas 15 composições | `grep` em `remotion/src/` |
| Backend VOLC | **função serverless Python na Vercel** | `backend/vercel.json`, `backend/api/index.py` |

A doutrina do legado (`motor-video/doutrina/MODELO.md:18`) afirma **"Remotion v7"**. Isso é
falso: v7 não existe. Um plano de runtime escrito sobre a doutrina miraria uma versão
inexistente. Este ADR usa o número medido no `node_modules`, não o declarado em prosa.

---

## Decisão 1 — Agent Skills sim, MCP hospedado não

O MCP hospedado está **depreciado por texto explícito** da própria Remotion, com
desligamento anunciado para **não antes de 31/08/2026** — três dias depois desta data.
O substituto declarado são as Agent Skills oficiais (`npx skills add remotion-dev/skills`,
12 skills) e `/remotion-docs`, que busca a doc e devolve markdown.

**Decisão:** adotar as skills; **não instalar** o MCP hospedado. Se houver qualquer
configuração do VOLC apontando para ele, ela morre nesta semana.

**WebMCP é outra coisa e não substitui nada disso.** Existe a partir de 4.0.518, expõe
20 ferramentas no Studio — `get_compositions`, `select_composition`, `get_sequences`,
`get_canvas_html`, `get_selection`, `seek_to_frame`, `play`/`pause`, guias, zoom da
timeline. Cobre exatamente o que a missão perguntou: seleção atual, tempo atual,
layers, HTML do canvas, controle remoto do laboratório.

**Mas não há uma única ferramenta de render na lista.** WebMCP é superfície de
inspeção e direção do Studio, não executor de produção. E hoje, entre os harnesses
principais, **só o ChatGPT Codex o suporta** — o que o torna irrelevante para uma
pipeline Claude Code neste momento. **Decisão: observar, não adotar.**

## Decisão 2 — `@remotion/rough-notation` é real e entra

Esta era a pergunta que travava o desenho de legendas, e a resposta é sim.

- Pacote oficial da Remotion (`author: Jonny Burger <jonny@remotion.dev>`), licença MIT.
- Nasce em **4.0.490**; latest 4.0.518.
- Sete componentes, cada um com página própria: `<Box>`, `<Bracket>`, `<Circle>`,
  `<CrossedOff>`, `<Highlight>`, `<StrikeThrough>`, `<Underline>`.
- Props comuns: `progress` (0–1, é o que anima), `seed`, `color`, `roughness`,
  `maxRandomnessOffset`, `bowing`, `disableMultiStroke`, `preserveVertices`.
  `<Highlight>` acrescenta `iterations`, `padding`, `rtl`.

**A fábrica está em 4.0.479 e precisa subir para usar.**

⚠️ **`seed` não é enfeite; é requisito de determinismo.** O fork existe porque o
RoughJS original não expunha a semente, e sem ela cada thread sorteia forma diferente.
A fábrica renderiza em paralelo (`--concurrency=8`, `motor/core.py:376`). Com `seed`
livre, o mesmo grifo treme entre chunks do mesmo vídeo. **O contrato Zod do VOLC deve
fixar `seed` explicitamente** — é o tipo de defeito que passa despercebido em preview
e só aparece no arquivo final.

⚠️ `https://www.remotion.dev/docs/rough-notation` (sem sufixo) devolve **404**, e é o
endereço que o campo `homepage` do npm aponta. O índice vivo é `/docs/rough-notation/api`.
Um 404 aqui **não** significa que o pacote não existe.

**`@remotion/paper` não existe como pacote.** É a função `paper()` de
`@remotion/effects`, a partir de 4.0.486, com backend **WebGL2**. E não é alternativa
ao rough-notation: papel é textura de fundo, rough-notation é anotação sobre texto.
São coisas diferentes, não um o fallback do outro.

## Decisão 3 — o contrato VOLC → fábrica é um objeto Zod JSON-serializável

A forma canônica atual de parametrizar é: `defaultProps` estáticos → input props que
sobrescrevem → `calculateMetadata()` que pós-processa e calcula duração/dimensão/fps.
Com `schema` Zod declarado na `<Composition>`, o Remotion **exige** `defaultProps`
compatíveis — a incompatibilidade vira erro de build, não surpresa no render.

Isso encaixa no que a fábrica já tem: existe `remotion/props.json`. Falta o schema
tipando-o. **Decisão:** o contrato de entrega VOLC O.S. → fábrica é esse objeto.

⚠️ **`calculateMetadata` só aceita JSON-serializável** (texto da doc). Serve para
resposta de API; **não** serve para asset binário. Um contrato que tentasse embutir
mídia quebra.

## Decisão 4 — Player sim no app; Studio não exposto

`@remotion/player` é componente React puro, roda em Vite/Next sem servidor. Cabe no
app Vercel hoje, sem tocar em backend, e é o caminho do preview do Laboratório.

O Studio é ferramenta de operador: Node + Chrome, porta 3000. A doc ensina a subir
numa VPS para "tornar a UI de render acessível ao time" e **não traz nenhum aviso de
segurança sobre isso**. Porta 3000 aberta é execução de render arbitrário por quem
alcançar a porta. **Decisão: Studio fica local ao operador. Se um dia for exposto, a
autenticação é responsabilidade do VOLC, não do Remotion.**

## Decisão 5 — executor de render pesado

### Por que a função Vercel curta está descartada, com número

Não é preferência do dono; é limite documentado. A doc oficial diz que **funções da
Vercel rodam até 800 s**, e por isso a própria Remotion usa a função apenas como
*disparador*, com `renderMediaOnVercel({detached: true})` + polling, jogando o trabalho
numa VM efêmera. Some-se: a função não tem disco persistente para um MP4 de 40 MB
(o `short_odete` real tem 43,8 s e 40,5 MB) e não tem as libs de sistema do Chrome
Headless Shell que o Dockerfile oficial instala. **A Remotion não a oferece como
executor.**

### Comparação

| Executor | Teto de tempo | Recursos | Distribuído | Estabilidade declarada | Adequação VOLC |
|---|---|---|---|---|---|
| **Vercel Sandbox** | 45 min (Hobby) / 5 h (Pro) | não especificado | não | "new… actively improving" | **Alta como primeiro passo** — mesmo provedor do app |
| **Cloud Run Job, imagem própria** | 60 min | ≤32 GB, 8 vCPU | não | cai em "Node.js APIs", que a Remotion sustenta a longo prazo | **Alta** — mais teto e isolamento |
| **Lambda** | **15 min** | ≤10 GB | **sim, único** | "committed long-term" | Média — traz AWS para um stack Vercel+Hetzner |
| **Worker no Hetzner atual** | sem teto | 4 GB, compartilhado com o Supabase | não | — | **Baixa** — ver abaixo |
| **Railway** | — | — | — | — | **NÃO CONFIRMADO** — ausente de toda a doc oficial |
| Função Vercel curta | 800 s | sem disco | não | — | **Descartada** |

⚠️ **Distinção que evita uma decisão errada:** o aviso *"Cloud Run está em alpha e não
está em desenvolvimento ativo"* é sobre o **pacote `@remotion/cloudrun`**, não sobre o
GCP Cloud Run como infraestrutura. Rodar imagem Docker própria num Cloud Run Job
**não** herda o risco do alpha. Usar `@remotion/cloudrun` herda — e a Remotion sinaliza
que pretende reescrevê-lo sobre o Lambda.

⚠️ **Por que o worker no Hetzner atual é a pior opção:** `renderMedia` usa por default
**metade das threads de CPU disponíveis**, e a caixa é a `ubuntu-4gb-ash-1` — a mesma
que roda o Supabase operacional do VOLC O.S. inteiro. Um render 1080×1920 competindo
com o Postgres de produção é risco de disponibilidade do sistema todo, não só do vídeo.
Se um worker permanente for o caminho, ele vai numa VM separada.

**Recomendação em sequência:** (1) skills + upgrade 4.0.479→4.0.518 + rough-notation +
schema Zod, zero infra nova; (2) `<Player>` no app para preview; (3) executor no Vercel
Sandbox ou Cloud Run Job. **Nunca na caixa do Supabase.**

## Decisão 6 — storage

O bucket `criativos` **não existe** (`storage.buckets` = 0, medido hoje). O adaptador
`ArmazenamentoSupabase` está **escrito e nunca instanciado**: `armazenamento_padrao()`
devolve `ArmazenamentoLocal` incondicionalmente. Trocar exige editar código, não config.

E há um problema maior que a ausência do bucket: **`ArmazenamentoLocal` grava em disco
de função serverless.** O disco de uma função Vercel não sobrevive à requisição. Criar
o bucket sem antes resolver o modelo de execução só move o problema de lugar.

**Decisão: não criar o bucket agora.** A ordem correta é (a) decidir o executor,
(b) ligar `ArmazenamentoSupabase` por configuração e não por edição, (c) criar o bucket,
(d) migrar os bytes já gravados localmente — que **não** atravessam sozinhos, porque
`storage_chave` é a mesma string nos dois adaptadores mas os bytes não são.

## Riscos que o ADR carrega para a decisão do dono

1. **Licença.** Free License cobre organização de **até 3 pessoas**; acima disso, Company
   License paga. "1 render" conta igual em local, Lambda ou Cloud Run; preview no Player
   e no Studio **não** conta. **NÃO CONFIRMADO:** os preços — a página de pricing renderiza
   por componente e não devolveu valores. Levantar antes de faturar vídeo.
2. **Subir o Remotion não desbloqueia "criar vídeo".** Os três impedimentos medidos são
   da fábrica, não do Remotion: 21 de 26 geradores escrevem em singletons compartilhados,
   os 4 que isolam não têm teste de concorrência, e a raiz está fixa no código
   (`/Users/mac/volc-factory`). Prometer o contrário no roadmap é prometer o que não entrega.
3. **Lockstep de versão.** Todos os `@remotion/*` publicam a mesma versão no mesmo dia.
   O `^4.0.0` da fábrica flutua para 4.0.518 em qualquer `npm install` sem lock, enquanto
   o `node_modules` está em 4.0.479. Instalação parcial mistura versões e quebra de um
   jeito difícil de diagnosticar. **Pinar exato antes de acoplar.**
4. **WebGL2 em headless.** `paper()` usa backend WebGL2. Nem Lambda nem Vercel Sandbox
   têm GPU. **NÃO CONFIRMADO:** requisitos de SwiftShader em container — a página
   `/docs/webgl` não foi auditada. Verificar **antes** de o produto depender de textura.
5. **Vercel Sandbox sem guarda-corpo.** O template oficial "não inclui rate limiting nem
   cache", e blobs "persistem indefinidamente". Endpoint de render público sem isso é
   conta aberta.

---

# Adendo de 28/08/2026, noite — o que foi MEDIDO, não lido

A primeira versão deste ADR foi escrita a partir da documentação oficial. Este
adendo vem de execução real contra a fábrica, sem alterá-la.

## Lockstep: íntegro hoje, frágil por construção

Os seis pacotes instalados estão todos em **4.0.479**:

```
remotion 4.0.479 · @remotion/cli 4.0.479 · @remotion/transitions 4.0.479
@remotion/google-fonts 4.0.479 · @remotion/renderer 4.0.479 · @remotion/bundler 4.0.479
```

Mas o `package.json` declara `^4.0.0` para todos. O lockstep está intacto **por
causa do lockfile**, não por causa da declaração. Um `npm install` sem lock leva
a 4.0.518 e, se atualizar só parte, mistura versões.

**Decisão: pinar exato antes de qualquer upgrade.** `"remotion": "4.0.479"` e
irmãos, e só então subir os seis juntos para a versão alvo.

## Determinismo: PROVADO

Dois `remotion still` independentes do mesmo quadro da mesma composição:

```
sha256  4d83af8c…cde4a   still-a.png   1080×1920   2.463.274 bytes
sha256  4d83af8c…cde4a   still-b.png   1080×1920   2.463.274 bytes
diferença de pixel: nenhuma (ImageChops.difference → bbox None)
```

## Concorrência: PROVADA, e a distinção importa

Dois renders simultâneos, composições diferentes, diretórios de saída diferentes:
ambos `exit 0`, hashes distintos entre si (correto — são composições diferentes),
e o hash do render **concorrente** de `Corta` é **idêntico** ao do render
**sequencial** da mesma composição.

⚠️ **Isto corrige um recorte impreciso do relatório anterior.** Eu havia tratado
"21 de 26 geradores escrevem em singletons compartilhados" como se fosse um
problema de concorrência *do Remotion*. Não é. O render do Remotion é isolado por
processo e por caminho de saída. Quem compartilha estado são os **wrappers Python
da fábrica** (`clips_registry.json`, `timings.json`, `props.json` na raiz), que
preparam a entrada antes de chamar o Remotion. O risco é real e continua real —
mas ele mora um andar acima, e a correção é lá.

## Achado novo: o render NÃO é hermético

O log de um único still traz:

```
Made 25 network requests to load fonts for Cormorant Garamond
Made 50 network requests to load fonts for Cormorant Garamond
Made 30 network requests to load fonts for Oswald
Made 27 network requests to load fonts for Archivo
Made 54 network requests to load fonts for Archivo
Made 35 network requests to load fonts for IBM Plex Mono
Made 70 network requests to load fonts for IBM Plex Mono
```

**~290 requisições de rede para produzir um quadro.** `@remotion/google-fonts`
busca as famílias em tempo de render.

Consequências, em ordem de gravidade:

1. **Sem rede, o render falha ou sai com fonte substituta** — e uma fonte
   substituta muda o pixel sem mudar nenhum parâmetro do contrato. O recibo diria
   "mesma seed, mesmas versões" sobre duas peças diferentes.
2. **Num Cloud Run Job ou container sem egresso**, isto quebra. Qualquer plano de
   executor precisa ou liberar egresso para o Google Fonts, ou **embutir as
   fontes** e trocar `loadFont()` por arquivo local.
3. O determinismo que acabei de provar vale **com rede e com o Google Fonts
   respondendo o mesmo**. É determinismo observado, não garantido.

**Decisão recomendada:** antes de mover o render para qualquer executor remoto,
embutir as fontes no bundle e registrar o sha256 de cada uma no recibo — que é
exatamente o que o motor tipográfico local do VOLC O.S. já faz
(`versoes.fonte_sha256`).

## `calculateMetadata` já está em uso

`remotion/src/Root.tsx` passa `calculateMetadata={meta as any}` nas 15
composições. O `as any` denuncia a ausência de tipagem: é o ponto exato onde o
schema Zod entra, e onde `@remotion/captions` daria o tipo `Caption` canônico no
lugar do formato próprio de legenda.

## O que continua NÃO provado

- **Render de vídeo completo** (não só still) sob concorrência.
- **`@remotion/rough-notation`**: exige 4.0.490 e a fábrica está em 4.0.479.
  Confirmado que existe; não exercitado.
- **Licença**: continua sem número. Free cobre até 3 pessoas.

---

# Adendo de 29/08/2026 — hermetismo investigado por execução

## Duas afirmações minhas caem

**1. "Sem rede o render falha OU usa fonte substituta" — a segunda metade é falsa.**

O adendo anterior dizia que uma fonte substituta mudaria o pixel sem mudar
parâmetro, e que o recibo mentiria dizendo "mesmas versões". Isso foi **refutado
por experimento**: corrompendo as URLs do `@remotion/google-fonts` numa cópia
isolada, o render falha **duro e visível** (`NetworkError: A network error
occurred`, `net::ERR_UNSAFE_PORT`) e **nenhum arquivo de saída é gerado**.

O motivo está no código: `@remotion/google-fonts/dist/esm/*.mjs` faz duas
tentativas por variante e, no `catch`, dá `throw err` sem chamar
`continueRender(handle)`. O handle veio de `delayRender(..., {timeoutInMilliseconds:
60000})`. O render trava e aborta; não troca de fonte.

Isso é **melhor** do que eu tinha escrito, e a correção importa: o risco real do
Remotion sem rede é **indisponibilidade**, não peça errada com recibo mentiroso.

⚠️ A garantia vale para 4.0.479/4.0.518. Se uma versão futura adotar fallback
mais tolerante, ela deixa de valer — vale re-testar a cada bump maior.

**2. O método de bloqueio de rede que eu sugeri não bloqueia nada.**

`HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` apontando para porta morta é **inerte**:
`@remotion/renderer/dist/open-browser.js:103-105` lança o Chromium com
`--no-proxy-server`, `--proxy-server='direct://'` e `--proxy-bypass-list=*`
embutidos. E não existe `--offline` em nenhum ponto do CLI ou do renderer.

A prova teve de vir por outro caminho: monitor de conexões ao vivo (`lsof -i`
a cada 50 ms durante o render). Com fontes locais, **235 amostras, 100% em
`127.0.0.1`/`[::1]`**. Numa execução de controle com o código original, o mesmo
monitor pegou `→ 172.217.30.67:443` (faixa Google) — o instrumento acusa rede
quando ela existe, então a ausência significa alguma coisa.

## O achado que muda o custo do hermetismo

**O download não é da composição pedida; é de todas as 15.**

`src/Root.tsx:3-17` importa as 15 composições no topo do módulo, e cada uma chama
`loadFont()` no topo do seu módulo. O bundle inteiro é avaliado a cada render.
Medido: um `still` de `Corta` (cujas fontes são Limelight, Oswald e SpecialElite)
baixa também CormorantGaramond (de `Esoterico.tsx`), Archivo (de `Arquivo.tsx`)
e IBMPlexMono (de `Holerite.tsx`).

São **34 chamadas `loadFont()` em 11 famílias**, e nenhuma passa `weights` ou
`subsets` — o default baixa todos os pesos e os 5 subsets, incluindo cirílico e
vietnamita para peças em português.

## Hermetismo: viável, provado, e não de graça

Numa cópia isolada, as 34 chamadas foram trocadas por `@remotion/fonts`
(`loadFont({family, url: staticFile(...)})`, oficial desde 4.0.164) apontando
para `.ttf` locais. Resultado: render sai, **zero conexão externa**, e dois
renders seguidos dão hashes idênticos entre si.

**O que ainda falta para adotar:**

1. **Fontes.** As 11 famílias em uso (Limelight, Oswald, SpecialElite, Anton,
   Creepster, VT323, Cinzel, ArchivoBlack, Archivo, IBMPlexMono,
   CormorantGaramond) **não têm par** nas 10 disponíveis no diretório da PRENSA.
   Adotar exige obter as 11, com licença conferida — como já foi feito para a
   Inter do motor tipográfico (`bancada/fontes/PROCEDENCIA.md`).
2. **As 15 composições** precisam ser tocadas, não uma.
3. **Custo medido, e contraintuitivo:** com rede boa e cache quente, o online foi
   **mais rápido** (2,7–2,9 s) que o hermético (3,7–4,8 s). Os `.ttf` variáveis
   locais são pesados (Cormorant 1,2 MB, Inter 876 KB) contra `.woff2` já
   subsetados, e `staticFile()` ainda faz round-trip no servidor estático local.
   O ganho do hermetismo não é velocidade: é eliminar a cauda — 290 requisições
   por quadro numa fila com rede compartilhada pode estourar o timeout de 60 s
   por handle e derrubar o render inteiro.

## Upgrade 4.0.479 → 4.0.518: testado

`npm install --save-exact` dos seis pacotes mais `@remotion/fonts` e
`@remotion/rough-notation`, tudo em 4.0.518, numa cópia. Quatro stills
renderizados sem erro, e `Corta` saiu com **hash idêntico ao baseline de
4.0.479** — o upgrade é visualmente equivalente para essa composição.
`@remotion/rough-notation` instala e exporta os sete componentes; é ESM-only.

**NÃO CONFIRMADO:** as outras 11 composições não foram renderizadas no upgrade.

## Achado colateral que vale para o CI

O cache de bundle do webpack **não invalida** quando só `node_modules` muda. Na
primeira tentativa de corromper as URLs, o render saiu com hash idêntico ao
baseline — não por fallback, mas porque o bundle antigo foi reusado. Um CI que
reaproveite cache entre builds pode mascarar exatamente esse tipo de regressão.

## Decisão

Hermetismo é **viável com trabalho**, e nenhum dos três custos é bloqueador. Mas
ele não entra nesta rodada: exige as 11 fontes licenciadas e tocar 15 arquivos da
fábrica, que é repositório de outra frente. Fica como pré-requisito declarado de
qualquer executor remoto — e não como pré-requisito do determinismo, porque a
falha sem rede é dura, não silenciosa.

---

# Decisão formalizada — produção hermética de vídeo

Cinco pontos, fechados. Não se resolve nenhum deles com download oportunista de
fonte no meio de uma fatia; cada um é pré-requisito declarado.

## 1. Produção hermética exige fontes versionadas e licenciadas

As 11 famílias em uso hoje (Limelight, Oswald, SpecialElite, Anton, Creepster,
VT323, Cinzel, ArchivoBlack, Archivo, IBMPlexMono, CormorantGaramond) precisam
entrar no repositório com licença conferida, como já foi feito para a Inter do
motor tipográfico (`backend/app/criativo/bancada/fontes/PROCEDENCIA.md`).

**As 10 fontes disponíveis no diretório da PRENSA não cobrem as 11.** Não há
sobreposição suficiente, e substituir família é mudar o pixel.

## 2. Carregar as 15 composições é custo estrutural atual

`remotion/src/Root.tsx` importa as 15 no topo, e cada uma chama `loadFont()` no
topo do seu módulo. Um `still` de `Corta` baixa fontes de `Esoterico`, `Arquivo` e
`Holerite`. Isto **não é defeito de configuração**: é como o bundle é montado, e
mudar exige `lazyComponent` ou carregamento por composição.

## 3. Otimização futura declara família, peso e subset por composição

As 34 chamadas usam o default, que baixa **todos os pesos e os 5 subsets** —
cirílico e vietnamita incluídos, para peça em português. `loadFont(style,
{weights, subsets})` existe e reduz volume; não elimina rede, mas corta a cauda.

## 4. Nenhuma fonte pessoal ou local pode ser requisito

Um caminho de máquina no runtime faz o mesmo pedido produzir **assinaturas
determinísticas diferentes** em máquinas diferentes, porque `fonte_sha256` entra
na assinatura. Isso já foi corrigido no motor tipográfico e vale igual aqui.

## 5. Falha de fonte permanece visível e sem artefato

Medido: sem a fonte, o render aborta com `NetworkError` e **não gera arquivo**.
Essa propriedade é **desejada** e precisa ser reconferida a cada bump maior de
versão — se uma versão futura adotar fallback tolerante, o hermetismo deixa de
ser garantia e passa a ser esperança.

## O que NÃO entra nesta fatia

Nada disso. O hermetismo é pré-requisito de **executor remoto**, não de
determinismo — porque a falha sem rede é dura, não silenciosa. E a fábrica é
repositório de outra frente: tocar 15 arquivos dela não cabe aqui.
