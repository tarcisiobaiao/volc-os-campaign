# GOLDEN DE IMAGEM — P17-T08

**Estado:** cadeia local atravessada e provada · duas divergências abertas, com
sentinela cada uma · aprovação humana e Postgres fora de alcance nesta fatia.
**Medido em:** 01/09/2026, nesta máquina (macOS, Python 3.14.6, Pillow 12.3.0).

Aceite da fatia:

> Uma peça aprovada para Google/Meta ou orgânico possui briefing, versão do
> motor, seed, hashes, validações, custo, recibo, armazenamento verificado e
> vínculo ao destino, **sem publicação automática**.

## O que roda, e onde

```
backend/tests/test_criativo_golden_imagem.py     a travessia e os sentinelas
backend/tests/goldens/criativo-imagem/           o golden versionado (JSON)
volc_ads/criativo/destinos.py                    envelopes, medidor, pacotes
volc_ads/criativo/testes_destinos.py             as regras do módulo, isoladas
```

Gate focal:

```bash
.venv-worker/bin/python -m pytest \
  backend/tests/test_criativo_golden_imagem.py volc_ads/criativo \
  -q -p no:cacheprovider
# 198 passed
```

Para regravar o golden depois de uma mudança **deliberada**:

```bash
CRIATIVO_REGRAVAR_GOLDEN=1 .venv-worker/bin/python -m pytest \
  backend/tests/test_criativo_golden_imagem.py -q
```

## A cadeia, e quem responde por cada elo

| Elo | Quem executa | O que o golden afirma |
|---|---|---|
| briefing | `BRIEFING` no teste | título, apoio, insumo, canal e intenção viajam nos `parametros` da `Encomenda` e reaparecem no recibo |
| modo | `Encomenda.modo_slug = "ensaio-local"` | entra na `chave_de_idempotencia` |
| engine | `bancada/adaptadores/tipografico.MotorTipografico` | motor **local**, sem rede e sem credencial; usa `fontes/Inter-Variable.ttf` vendorizada |
| fila | `bancada/deposito.DepositoDeTrabalhos` | trilha `claimed → running → validating → rendered`, sem pular estado |
| output | 5 PNG em disco | dimensão exata por envelope, MIME lido do *magic byte* |
| QA | `bancada/operario.Operario._validar` | `hash_confere`, `dimensao`, `arquivo_nao_vazio`, `contraste` — todos bloqueantes e PASS |
| recibo | `bancada/contrato.Recibo` | seed, `versoes` congeladas (Pillow + sha256 da fonte), artefatos, validações, `assinatura_determinista` |
| storage | `bancada/armazenamento_verificado.publicar_artefato` | `VERIFIED_OK` só depois de **reler** os bytes do armazenamento |
| aprovação | `criativo_ponte.Destino` | `ENSAIO` aprova os 5; `PRODUCAO` recusa quando a natureza é declarada |
| biblioteca | `criativo/catalogo.Catalogo` | 5 identidades distintas, dedup por conteúdo no replay |
| destino | `criativo/destinos.PacoteDeDestino` | 3 pacotes completos e verificados, **nenhum publicável**, `publicacao_automatica = False` |

## Os envelopes, e o que foi medido em cada um

Peça: *"Matricule-se ate 30 de setembro e garanta a bolsa"* · seed `20260901`.

| Envelope | Destino | Medida | Proporção | MIME (magic byte) | bytes | gate `dimensao` | adaptação | `fora_da_rampa` |
|---|---|---|---|---|---|---|---|---|
| `meta-feed-1x1` | meta | 1080×1080 | 1:1 | `image/png` | 46 085 | PASS | mestre | 0 |
| `meta-feed-4x5` | meta | 1080×1350 | 4:5 | `image/png` | 47 968 | PASS | **recomposição** | 0 |
| `google-display-191x1` | google | 1200×628 | 1.91:1 | `image/png` | 47 088 | PASS | **recomposição** | 0 |
| `google-logo-1x1` | google | 1200×1200 | 1:1 | `image/png` | 51 495 | PASS | **recomposição** | 0 |
| `organico-reels-9x16` | organico | 1080×1920 | 9:16 | `image/png` | 51 821 | PASS | **recomposição** | 0 |

sha256 (nesta máquina, com Pillow 12.3.0 e `Inter-Variable.ttf`
`29160a80ff49dd…`):

```
meta-feed-1x1         90a0c1b0e3503463f3f653a7e46210afc0494904fbfe66f3f455ff8b18fdc3d9
meta-feed-4x5         b3c2bb33b0586e63e82a12d4c43ed71d92dcba3168a130f65a798290b38afbe2
google-display-191x1  4fe8bb82b85940e75924a90eae17a802b687c20b9d3be2368eb5ea92388b1a41
google-logo-1x1       5d6174c0ce2b5722ac7dcb924017e6cee1f64dbb3048338082e5dcdb3c9a47bc
organico-reels-9x16   e801f96e39256a7a0dc801845974d86ee6452e5bc14edd369d61ce641a987f28
```

O logo 1:1 entrou no catálogo por uma razão de régua e não de estética:
`requisitos.exigencia_binaria_de("DEMAND_GEN")` exige `logo_quadrado` com
`quantidade_minima = 1`. Sem ele o lote reprova em `Q1.faltam` e a aprovação de
destino nunca acontece — o buraco estaria na encomenda, não na peça.

## Recompor ou recortar: como a diferença foi provada

O risco desta fatia não é a peça sair errada; é a peça sair **igual**. Recortar
uma imagem-mãe em quatro produz quatro arquivos com quatro dimensões e **uma**
composição, e todos os gates de geometria aprovam isso.

O discriminante usado é físico, não semântico. O motor tipográfico compõe com
duas cores — fundo e tinta —, e o antialias do desenho é uma mistura **convexa**
das duas: todo pixel cai no segmento `fundo → tinta`. Uma reamostragem LANCZOS
(que é o que `services/creative_engine/enquadramento.enquadrar` faz) tem lóbulos
negativos e produz *overshoot*: pixels na mesma reta, fora de `[0, 1]`.

Medido, comparando cada variante recomposta com o recorte do mesmo mestre:

| Envelope | recomposto: `fora_da_rampa` / cores | recortado: enquadramento, `fora_da_rampa` / cores |
|---|---|---|
| `meta-feed-4x5` | 0 / 254 | `cover_crop`, 8 525 / 2 076 |
| `google-display-191x1` | 0 / 254 | `cover_crop`, 7 221 / 1 965 |
| `google-logo-1x1` | 0 / 254 | `resize`, 7 221 / 1 965 |
| `organico-reels-9x16` | 0 / 254 | `cover_crop`, 12 460 / 2 289 |

Segunda medida, independente da primeira, e é a que dói — a **margem**:

| Peça | caixa da tinta | faixas (altura das linhas) | toca a borda |
|---|---|---|---|
| mestre 1:1 | (92, 391, 912, 728) | 60, 74, 59, 36 | não |
| **recomposto** 4:5 | (92, 526, 912, 863) | 60, 74, 59, 36 | não |
| recortado 4:5 | (0, 486, 1008, 913) | 81, 97, 79, 51 | **sim** |
| **recomposto** 9:16 | (92, 811, 912, 1148) | 60, 74, 59, 36 | não |
| recortado 9:16 | (0, 691, 1080, 1284) | 115, 138, 89, 58 | **sim** |

Leitura: a recomposição mantém o corpo do glifo que o canvas de 1080 de largura
pede e a margem de 92 px que o motor calcula; o recorte amplia tudo 25 % (4:5) e
78 % (9:16) e **corta a letra na borda esquerda**. No 1.91:1 o canvas tem 1200 de
largura, e a recomposição muda o corpo — faixas 66/80/64/39 contra 60/74/59/36 —
porque margem e corpo saem da largura, não de um fator de escala.

### Mutantes, para o teste não ser tautologia

| Mutante | Onde | Resultado |
|---|---|---|
| `classificar_adaptacao` nunca vê recorte (`if False`) | `destinos.py` | 2 falhas — o teste do recorte e o golden versionado |
| a fábrica **recorta** em vez de recompor (variantes trocadas por `enquadrar`) | fixture da travessia | 2 falhas: `…recomposicao_medida…` e `…come_a_margem…` |
| `PacoteDeDestino.verificado` sem a guarda de lista vazia | `destinos.py` | 1 falha |
| `armazenamento_verificado` colapsa `None` em `False` | `destinos.py` | 2 falhas |
| rótulo de proporção deixa de ser conferido | `destinos.py` | 1 falha |
| `publicavel` ignora a natureza | `destinos.py` | 1 falha |
| armazenamento grava um byte a menos | teste `LojaQueGravaMenos` | `VERIFIED_MISMATCH`, `exigir_verificado()` levanta |

## Determinismo

Duas travessias independentes (bancadas separadas, operários com nomes
diferentes), mesma semente:

```
assinatura A  4f228338339966d14cba4eda17f54a1b5ad410d2e7b2eb5423cc0d3d4ab08352
assinatura B  4f228338339966d14cba4eda17f54a1b5ad410d2e7b2eb5423cc0d3d4ab08352
sha256 das 5 saídas: idênticos par a par
produzido_por e terminado_em: DIFERENTES (e a assinatura não os vê — é isso que
a torna capaz de responder "o motor repetiu?")
```

Contraprovas do determinismo, para que "determinístico" não signifique
"constante":

* semente `20260901 + 1` → assinatura, chave de idempotência e **os cinco
  arquivos** mudam;
* título diferente, mesma semente → assinatura e os cinco arquivos mudam.

**Fronteira declarada.** O determinismo provado é *nesta máquina, neste
processo*. `versoes` do recibo registra `pillow=12.3.0` e
`fonte_sha256=29160a80ff49dd…` justamente porque os dois entram no pixel: em
outra máquina com outro Pillow ou outro FreeType a assinatura muda, e o recibo
diz onde. Por isso `sha256`, `bytes` e `assinatura_determinista` **não entram**
no golden versionado — congelá-los transformaria "outra máquina" em "regressão",
que é o jeito mais rápido de um golden ser desligado.

## Custo

`custo_estimado_usd = None` e `custo_real_usd = None`, no recibo e na
procedência de cada asset. O motor é local e não custa dinheiro, e **ainda assim
o sistema não afirma que a peça saiu de graça**: ninguém apurou. A distinção
está testada como distinção (`is None` *e* `!= 0.0`), porque um relatório de COGS
que soma zeros inventados fecha bonito e está errado.

Estado do custo no golden: **`nao_apurado`**, e não `0`.

## Sem publicação automática — três provas, nenhuma delas "não vi chamada"

1. `app/criativo/destino.py` continua sem implementação, e o golden confere que
   o módulo **não expõe nenhum invocável**;
2. `socket.socket` e `socket.create_connection` estão derrubados durante a
   travessia inteira e em todo teste do arquivo — um provider pago acrescentado
   por engano levantaria `RedeProibida` em vez de gastar;
3. `PacoteDeDestino.publicacao_automatica` é `ClassVar[bool] = False` e não
   aceita ser passado no construtor; os três pacotes o carregam.

Além disso, os três pacotes saem `publicavel = False`: a peça é de motor local, e
`NaturezaDaProcedencia.publicavel` só é verdadeira para `PRODUCAO`.

## Duas divergências abertas (sentinelas no teste)

### 1. O gate de dimensão do operário julga a DECLARAÇÃO, não os pixels

`Operario._validar` compara `Artefato.largura/altura` com
`SaidaPedida.largura/altura`. As duas são números que o **motor** escreveu; o
arquivo nunca é aberto. A mesma docstring conta que `bytes_` e `sha256` já foram
movidos para a medida do disco por esse exato motivo — a dimensão ficou para
trás.

Medido em 01/09/2026 com `MotorQueMenteNaDimensao` (grava 64×64, declara
1200×628):

```
estado:            RENDERED
gate dimensao:     PASS   {'pedido': [1200, 628], 'produzido': [1200, 628]}
medida real:       Medida(mime='image/png', largura=64, altura=64, bytes_totais=166)
```

O trabalho conclui, com recibo, apontando para um PNG que não serve a nenhum
canal. **Correção necessária, e ela não é desta lane** (`operario.py` pertence ao
integrador): medir `largura`/`altura` do arquivo — `medir_imagem.medir()` já faz
isso com stdlib — e comparar o MEDIDO com o pedido, deixando a declaração do
motor como terceiro número no `detalhe`.

Sentinela: `test_sentinela_o_gate_de_dimensao_do_operario_julga_a_declaracao`.
Ele **falha quando o defeito for corrigido**, e a docstring diz o que trocar.

Achado menor da mesma família: a `Validacao` de dimensão não carrega o `slot`.
Aqui o casamento por `detalhe["pedido"]` funciona porque as cinco geometrias são
distintas; com dois envelopes de mesma medida no mesmo pedido, nada diria qual
arquivo o gate julgou.

### 2. `MotorTipografico` não declara `natureza`

`MotorPngLocal` declara `NaturezaDaProcedencia.LOCAL`. `MotorTipografico` não
declara nada, então `servico.natureza_do_motor` devolve `NAO_DECLARADA` — que é a
resposta correta da função e a errada para este motor: ele é tão local quanto o
outro.

O custo aparece no portão de produção. `criativo_ponte.NATUREZAS_ACEITAS[Destino
.PRODUCAO]` aceita `NAO_DECLARADA` como dívida declarada, então:

```
natureza NAO_DECLARADA → Destino.PRODUCAO: ok=True, recusas=(), 5 avisos
natureza LOCAL         → Destino.PRODUCAO: ok=False, 6 recusas nomeadas
```

Ou seja: a peça de um motor 100 % local passa no portão de produção com aviso
onde o `png-local` recebe recusa. **Correção necessária, e ela não é desta lane**
(os adaptadores são de outro dono): acrescentar
`natureza = NaturezaDaProcedencia.LOCAL` a `MotorTipografico`.

Sentinela: `test_sentinela_o_motor_tipografico_nao_declara_natureza`. Ele afirma
as duas metades — a que está errada e o contraste com a declaração correta —
então quando alguém declarar a natureza, a metade errada falha e aponta para cá.

## O que este golden NÃO alcança

| Etapa | Por quê |
|---|---|
| Aprovação **humana** (`criativo_aprovacao`, gatilho `criativo_aprovacao_peca_pronta_tg`) | vive no Postgres, e o único Supabase operacional é o de produção — esta fatia não escreve nele |
| `DepositoPostgres` | o mesmo motivo; a travessia usa a fila SQLite |
| Armazenamento **remoto** (`ArmazenamentoSupabase`) | o bucket não existe no servidor (zero linhas em `storage.buckets`, 27/08/2026); a verificação provada aqui é contra `ArmazenamentoLocal` |
| Publicação em Google Ads / Meta | fora de escopo por aceite, e barrada por três provas acima |
| Motor de produção (`gemini-imagem`, prensa) | exige credencial e rede; **provider indisponível não é provider reprovado** — nada aqui diz nada sobre a qualidade deles |
| Determinismo entre máquinas | ver "Fronteira declarada" acima |

## Como estender o catálogo de envelopes

1. acrescente o `Envelope` em `volc_ads/criativo/destinos.py` com a **fonte do
   número** (a especificação da plataforma, com data);
2. o `__post_init__` confere o rótulo de proporção contra as dimensões — um
   rótulo errado recusa na importação, não na tela;
3. rode `CRIATIVO_REGRAVAR_GOLDEN=1` e **leia o diff** do JSON antes de commitar:
   `adaptacao` e `gate_dimensao` são o que se está afirmando sobre a peça nova;
4. se o envelope trouxer um `TipoDeAsset` que a régua do canal não conhece, a
   aprovação de destino vai reprovar — e isso é a régua funcionando, não um bug
   do catálogo.
