# UI do Estúdio — auditoria de estados honestos (P17)

Auditoria de `src/components/criativos/**`, `src/pages/criativos/**`,
`src/hooks/useCriativos*.ts`, `src/lib/criativosApi.ts` e `src/types/criativos.ts`,
feita **antes** de qualquer mudança de código, contra a regra dura da missão:

> Ausência é ausência, falha é falha, zero é zero, WARN não é PASS.
> Nunca use traço (`-`) ou `0` para esconder ausência ou falha.

## O que já estava certo, e não foi tocado

A base é boa, e isso precisa ser dito antes das correções, porque a maior parte
do trabalho de honestidade **já existe**:

- `comum/formato.ts` devolve **frase**, nunca traço: `não medido`, `não
  informado`, `custo não apurado`. Não há um único `?? 0` em medida.
- `comum/leitura.ts` separa os quatro estados de lista (carregando, erro, vazio,
  vazio-depois-do-filtro) e o erro vem antes do vazio — leitura que falhou não
  sabe se há zero ou mil.
- `comum/Estados.tsx` desenha os quatro diferentes, mais um quinto (`SemArquivo`)
  que não é erro nem vazio, e um sexto (`Indisponivel`) para indisponibilidade
  declarada.
- `comum/Selo.tsx` tem consulta tolerante (`doMapa`) para estado desconhecido,
  `SeloDeGate` trata `null` como "não executado" e distingue `WARN` (Ressalva)
  de `PASS` (Passou) com glifo, palavra e tom diferentes.
- `job/pecas.ts` recusa achatar `partial` em booleano e olha `permanente` antes
  de oferecer retry.
- `AtivoPage` distingue "uso não apurado" de "sem uso"; `video/Inspecao.tsx`
  distingue `[]` de "sem fontes" e `usoComercialOk: null` de "não permitido".
- `laboratorio/Producao.tsx` lê `vivo` do **lease**, não do estado, e escreve a
  frase certa quando o batimento vence: *"o trabalho volta para a fila; ninguém
  garante que ele esteja rodando"* — o **LEASE PERDIDO** da missão existe e é
  honesto.

## A armadilha que permite que o resto passe

`tsconfig.app.json` tem `"strict": false`, portanto **`strictNullChecks` está
desligado**. Todo `T | null` do contrato é, para o compilador, apenas `T`. Isso
significa que a disciplina de ausência do `types/criativos.ts` **não é
verificada por `tsc`**: passar `ProcedenciaDeExecucao | null` para uma prop
tipada `ProcedenciaDeExecucao` compila em silêncio, e a tela imprime a
afirmação errada. Os defeitos D1 e D3 abaixo só sobreviveram por causa disso.

Consequência prática: nesta área, honestidade de ausência é **obrigação de
runtime e de teste**, nunca do compilador.

## Inventário por estado exigido

| Estado / campo | Existe? | Onde | Honesto? |
|---|---|---|---|
| loading | sim | `Estados.Carregando`, esqueleto com altura de linha | sim |
| vazio | sim | `Estados.Vazio` | sim |
| vazio depois do filtro | sim | `Estados.VazioAposFiltro` | **não** — D5 |
| sem permissão | **não** | `criativosApi` trata só 401 | fronteira: 403 cai na frase genérica; ver "precisa de terceiro" |
| falha de leitura | sim | `Estados.ErroDeLeitura`, com ressalva de idade | sim |
| falha de motor | sim | `resumo.motorConfigurado`, `Producao` (motor que a máquina não roda) | sim |
| cancelado | parcial | `SeloDoJob('cancelled')`, `ofertaDeCancelamento` | **não** — D6: `canceladoPedidoEm` nunca é renderizado |
| LEASE PERDIDO | sim | `Producao.tsx`, `trabalho.vivo` | sim |
| STORAGE NÃO VERIFICADO | **não existe no contrato** | — | fronteira: nenhum campo de verificação de storage chega ao browser; ver "precisa de terceiro" |
| MISMATCH | parcial | `Rendition.largura` vs `larguraPedida`; `Enquadramento.nao_normalizado` | **não** — D4 |
| QA FAIL / WARN | sim | `SeloDeGate`, `video/Inspecao.tsx` | sim — WARN é "Ressalva", tom `atencao`, glifo próprio |
| aprovado | sim | `SeloDaAprovacao`, `null` = "Aguardando revisão" | sim |
| concluído | sim | `SeloDoJob('succeeded')` | sim |
| modo / engine | sim | `job.motor`, `job.motorVersao`, `recibo.motorSlug` | sim |
| provider / modelo | parcial | só no parque (`MotorRegistrado.provider`) | fora do ownership desta lane |
| formato / destino | sim | `FORMATOS_DE_IMAGEM`, `destinoLegivel` | sim |
| progresso | sim | `PainelDeFase` — sem barra quando `percentual === null` | sim |
| claim / lease | sim | `Producao.tsx` | sim |
| tentativa | sim | `job.tentativa`, `trabalho.tentativa` de `maxTentativas` | sim |
| custo | sim | `custoLegivel`, `null` = "custo não apurado" | **não** — D2 e D7 |
| procedência | sim | `SeloDeProcedencia`, `Procedencia` | **não** — D1 |
| hashes | sim | `hashCurto`, com valor inteiro no `title` | sim |
| recibo | sim | `Producao.tsx` | sim |
| erro | sim | `FalhaCriativa` tipada, com `permanente` | sim |
| retry | sim | `ofertaDeRetry` com motivo sempre presente | sim |
| indisponibilidade | sim | `Estados.Indisponivel`, `CatalogoDeVideos.disponivel` | sim |

## Os defeitos provados

### D1 — a ficha do ativo afirma autoria que ninguém apurou

`types/criativos.ts` declara `AssetMaster.procedenciaExecucao:
ProcedenciaDeExecucao | null`, com o comentário:

> `null` significa **não apurada** … a interface não pode preencher o silêncio
> com uma afirmação de autoria. O default anterior era exatamente isso, e fazia
> a ficha de um build OBSERVADO dizer "Produzida pelo motor do VOLC O.S.".

O contrato foi corrigido; **a tela não**. `AtivoPage.tsx` faz
`asset.procedenciaExecucao === 'observado' ? … : 'Produzida pelo motor do VOLC
O.S.'` — o `null` cai no `else` e a frase que o contrato existe para impedir
volta inteira. `SeloDeProcedencia` tem o mesmo desenho (`=== 'observado' ? … :
'Produzido aqui'`), e `AtivoPage` lhe passa o valor possivelmente nulo.

É a colisão exata proibida pela missão: **ausência ≠ afirmação**.

### D2 — custo estimado apresentado como se fosse apurado

`JobPage.tsx` e `home/Linhas.tsx` fazem
`custoLegivel(job.custoRealUsd ?? job.custoEstimadoUsd)`. O contrato guarda os
dois campos separados de propósito; o `??` os funde numa frase única
`US$ 0,0400` sem dizer qual dos dois é. Quem lê o cabeçalho de um job ainda em
execução acredita estar lendo gasto realizado. **Estimativa não é apuração.**

### D3 — estado de job desconhecido derruba a tela

`job/Acompanhamento.tsx` faz `ROTULO_DO_JOB[job.estado]` cru e logo em seguida
lê `rotulo.palavra`. `Selo.tsx` criou `doMapa` justamente porque "valor novo do
servidor não pode apagar a tela inteira" — `PainelDeFase` ficou de fora. Um
oitavo estado no servidor troca a tela de acompanhamento por tela branca, que é
a pior representação possível de "não sei".

### D4 — MISMATCH de dimensão não tem representação

Dois furos no mesmo fato:

1. `Enquadramento` inclui `'nao_normalizado'` — literalmente "a peça ficou na
   dimensão que o provider entregou, diferente da pedida". `formato.ts` não tem
   esse caso no mapa, então a tela imprime o slug cru `nao_normalizado` com a
   descrição "Enquadramento declarado pelo motor que esta versão da tela não
   conhece". A tela conhece; o mapa é que não foi atualizado, e o resultado
   rebaixa um MISMATCH declarado a "estado desconhecido".
2. `PecaDoJob` mostra "Pedido 1080 x 1080", "Medido no arquivo 1024 x 1024" e
   "Entregue pelo motor …" em três linhas de dicionário, **sem nunca afirmar que
   divergem**. Ler divergência de três números alinhados é trabalho do operador;
   uma peça fora da dimensão pedida é fato operacional e precisa de frase.

### D5 — "a biblioteca tem 0 ativos" quando ninguém contou

`BibliotecaPage` passa `universo={universo ?? 0}` para `VazioAposFiltro`, que
escreve *"A biblioteca tem 0 ativos. O filtro atual é que não alcança nenhum
deles."* — duas afirmações que se contradizem, e a primeira é falsa: `universo
=== null` é "o servidor não informou o total". `classificarLeitura` documenta
explicitamente que esse caminho é alcançável com universo desconhecido.

Na mesma tela, a contagem do painel de filtros é montada com
`total = consulta.data?.total ?? 0`; **quando a leitura falha**, `isLoading` já é
falso e a tela afirma *"0 ativos neste recorte"* logo acima do próprio alerta de
erro de leitura. Zero medido e leitura que não chegou viram a mesma frase.

### D6 — "pedi para parar" e "parou" são a mesma tela

`CreativeJob.canceladoPedidoEm` existe com este comentário no contrato:

> PEDIDO de cancelamento, e não confirmação. … A SPEC §16 exige que a interface
> distinga os dois, porque "pedi para parar" e "parou" não são a mesma notícia
> para quem está olhando o custo.

`rg canceladoPedidoEm src/` encontra o campo **apenas no contrato e em
fixtures de teste**. Nenhum componente o lê. Um job com cancelamento pedido e
ainda `running` mostra "Em execução — o motor está produzindo. Você pode sair
desta tela", e o botão "Interromper" continua oferecido como se nada tivesse
sido pedido.

### D7 — a ficha do recibo diz duas vezes "Custo apurado", e a segunda inventa

`laboratorio/Producao.tsx` monta a `Ficha` com **duas** entradas de rótulo
`Custo apurado`. Como `Ficha` usa `key={item.rotulo}`, são duas linhas com a
mesma chave React. Pior que a chave: a segunda entrada escreve, para
`custoRealUsd === null`, *"Não apurado. Este motor roda nesta máquina e não
cobra por peça."* — a primeira metade é verdade, a segunda é uma afirmação de
custo que ninguém apurou. `null` é ausência de apuração; concluir "não cobra"
dela é exatamente `custo não apurado → custo zero`.

## Fronteiras — o que esta lane não pode provar aqui

- **STORAGE (local / remoto / verificado).** Não existe no contrato do browser:
  `Rendition` tem `previewUrl` e `contentHash`, e `storageChave` fica no backend
  por decisão de segurança. A UI hoje sabe dizer "arquivo indisponível nesta
  leitura" (`SemArquivo`) e nada mais — e isso é o honesto disponível.
  A máquina de estados existe do lado de dentro: uma lane irmã escreveu
  `backend/app/criativo/bancada/armazenamento_verificado.py` com
  `LOCAL → UPLOADED_UNVERIFIED → VERIFIED_OK | VERIFIED_MISMATCH`. Ela **não
  chega ao DTO**: `rg verificad backend/app/routers/criativos_execucao.py` não
  encontra nada. Enquanto o DTO não carregar esse estado e o motivo, desenhar
  "STORAGE NÃO VERIFICADO" na tela seria inventar uma leitura que o servidor não
  fez — o mesmo defeito, do outro lado.
- **Trilha do trabalho.** O depósito da bancada expõe `trilha(trabalho_id)`
  append-only, mas `backend/app/routers/criativos_execucao.py` **não publica rota
  HTTP** para ela, e `_trabalho_dto` não a inclui. A UI não pode mostrar a
  história de tentativas/devoluções sem essa rota. Não foi criada aqui por
  instrução explícita da missão.
- **Sem permissão (403).** `criativosApi.falhaDaResposta` trata `401` com frase
  própria; `403` cai em `{codigo, mensagem}` do servidor ou na frase genérica.
  Distinguir "não autenticado" de "autenticado e sem permissão" depende de o
  backend emitir um código estável; inventar a distinção no cliente a partir do
  status seria adivinhação.
- **`terminadoEm` do trabalho da bancada.** Chega ao `Recibo`, mas
  `TrabalhoDaBancada` (em `src/types/parqueCriativo.ts`, **fora do ownership
  desta lane**) não o carrega. Não alterado.

## Correções aplicadas

Todas com contraprova vermelha registrada em
`src/components/criativos/__tests__/procedencia-nao-apurada.test.tsx` e
`src/components/criativos/__tests__/ausencia-nao-e-zero.test.ts`.

| # | Arquivo | O que mudou |
|---|---|---|
| D1 | `comum/Selo.tsx`, `pages/criativos/AtivoPage.tsx` | `SeloDeProcedencia` aceita `null` e vira "Procedência não apurada" (tom `atencao`); a ficha do ativo escreve a terceira frase |
| D2 | `comum/formato.ts`, `JobPage.tsx`, `home/Linhas.tsx` | `custoDoJobLegivel(real, estimado)` diz **qual** dos dois está na tela |
| D3 | `job/Acompanhamento.tsx` | consulta tolerante ao mapa, igual à de `Selo.tsx` |
| D4 | `comum/formato.ts`, `job/Acompanhamento.tsx` | `nao_normalizado` no mapa de enquadramento; `divergenciaDeDimensao()` e a frase de MISMATCH na peça |
| D5 | `comum/Estados.tsx`, `biblioteca/filtros.ts`, `BibliotecaPage.tsx` | `VazioAposFiltro` aceita universo `null`; `fraseDaContagem()` separa carregando / erro / universo desconhecido / medido |
| D6 | `job/pecas.ts`, `JobPage.tsx` | `estadoDoCancelamento(job)` com os três estados (nenhum, pedido e não confirmado, confirmado) |
| D7 | `laboratorio/Producao.tsx` | a linha duplicada que inventava "não cobra por peça" saiu; fica a que usa `custoLegivel` |
| D5b | `aprovacoes/regras.ts`, `AprovacoesPage.tsx` | `fraseDaFila()` não afirma "0 peças aguardam decisão" quando a leitura falhou |
