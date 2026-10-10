# FunnelForge: fechamento do motor de funis (10/10/2026)

- **Tarefa:** P10-T22 (`partial`). **Nó:** `cap_funnel`.
- **Execução:** uma execução real controlada pelo caminho canônico. Comando:
  `run-volc` + card com o esqueleto aprovado + perfil, em `--canario` (sem
  publicação e sem imagem paga). Mesmo tema e mesmo esqueleto de 09/10.
- **Retomadas:** três, cada uma de uma única etapa, registradas à parte.
- **Nada publicado.**
- **Artefatos fora do Git:** `producao/funil-final-20261010/`. O lote de
  homologação está em `lote-homologacao/` (rascunho, não aplicado).
- **Continuação de:** `FUNNELFORGE-BUCKET-PESQUISA-UNICA-2026-10-10.md`
  (commit `1ec4cf76`).

## O que mudou no motor

### Pesquisa guiada pelo esqueleto aprovado

- Com plano aprovado válido, a pesquisa antecipada pelo PAA não roda
  (`pesquisar=False`). O PAA só alimenta intenção e linguagem.
- A primeira pesquisa é a do dossiê, pelos requisitos das páginas: pergunta,
  resposta prometida, dados das ferramentas, ações e destinos oficiais.
- Requisitos iguais de páginas diferentes viram um só (`_agrupar`). Fato de
  requisito declarado chega a toda página que declara o mesmo id.
- Há no máximo uma rodada complementar agrupada.
- Redator e revisor não pesquisam.

### Fatos por contexto, não por coincidência

- Um número só se apoia num fato sobre o mesmo assunto. Para isso o motor usa:
  - o valor estruturado do fato;
  - ou a quantia escrita na frase do fato, fora de rótulos entre aspas.
- O mesmo número de outro assunto vira `numero_fora_do_contexto_do_fato`.
  Número sustentado só por fonte regional vira `fonte_so_regional`. Os dois são
  ajustes do revisor: o sentido é dele.
- Número sem nenhum fato continua bloqueando.
- O escopo (nacional ou regional:UF) vem do documento ou da declaração, nunca é
  presumido. O prompt de pesquisa define "subnacional".
- A instrução de lacuna restringe só o que não está nos fatos.

### Pacotes pequenos e revisão com índice factual compartilhado

- O revisor recebe os textos finais e um índice factual único do lote, com ids
  resolvíveis. As políticas vão uma vez por lote.
- O widget de orientação entra no que o revisor vê. Antes, a regex `vw-` o
  escondia.
- O revisor pode corrigir o texto do widget por patch localizado (`campo:
  widget`). A troca refaz leitura, render, sanitização e lastro factual.
- Tokens em cache passam a ser gravados por chamada (`cached_tokens`).

### Sniper único: botões, primeira dobra e entrega ajustada

- Uma chamada devolve:
  - os rótulos de todas as arestas;
  - o título (até 45 caracteres) e o subtítulo (até 160) da primeira dobra da
    LP;
  - a entrega ajustada de cada página cuja promessa central ficou sem fonte.
- O código confere tudo e reaproveita por assinatura.
- O ajuste vira delta registrado em `ctas_do_funil.json`. Ele não substitui o
  plano em silêncio.
- A LP aplica a dobra aprovada por código, antes do recibo.

### Saída oficial e prints

- Canais em ordem: emissor nacional, depois a fonte da própria página.
- Não há consolidação do dossiê depois de congelar os pacotes: ela reordenava
  os links e mudava a saída da p4 depois da redação.
- `recongelar_paginas` refaz só os pacotes pedidos e confere os outros.
- O print oficial só entra ao lado do link que ele mostra. Destino que o texto
  não linka não sobe para a mídia.

### Portão de HTML e retentativas

- O verificador de HTML reconhece a calculadora do motor: campo numérico sem
  `name`, id derivado e JS idêntico ao gabarito.
- `numero_fora_do_contexto_do_fato` e `fonte_so_regional` entram como
  patcháveis.

## Execução real (do zero, esqueleto aprovado)

As três colunas não são equivalentes:

- **09/10:** chamou o arquiteto, gerou 4 imagens e foi retomada depois.
- **10/10 bucket:** fez pesquisa antecipada pelo PAA.
- **10/10 final:** não fez pesquisa antecipada e não gerou imagem.

| | 09/10 | 10/10 bucket | 10/10 final |
|---|---|---|---|
| Pesquisa | 8 chamadas | 4 (2 antecipadas + 1 rodada) | 4 (1 rodada pelo esqueleto + 1 complementar agrupada) |
| Fatos no dossiê | 26 | 21 | 36 |
| Cobertura das páginas | — | 2 prontas / 5 em revisão | 6 prontas / 1 em revisão (p2) |
| Arquiteto | 1 chamada | 0 | 0 |
| Ferramentas + sniper | — | 2 chamadas | 2 chamadas |
| Redação | 9 tentativas (2 retentativas) | 10 (3) | 13 (6) |
| Revisão global | 1 chamada, 77 mil tokens, 31 s | 1 chamada, 310 mil tokens, 216 s | 1 chamada, 94 mil tokens, 164 s |
| Chamadas de texto | 19 | 17 | 20 |
| Tokens de entrada / saída | 401 mil / 46 mil | 611 mil / 43 mil | 370 mil / 43 mil |
| Tokens em cache | 16 mil | 8 mil | 19 mil |
| Parede | 1.159 s | 758 s | 804 s |
| Faturado | US$ 0,49 (imagens) | US$ 0 | US$ 0 |
| Resultado | 4 aprovadas, 3 em revisão humana | 4 aprovadas, p2 reprovada, 2 em revisão humana | **7 aprovadas**, gate OK nas 7 |

**Totais do run final.** Vêm de `log.jsonl` e de `pesquisa_dossie.json`, não
de `step_status`, que guarda só a última chamada de cada etapa.

- Pesquisa: 117 mil tokens de entrada (8 mil em cache) e 11 mil de saída.
- Redação: 151 mil tokens de entrada (11 mil em cache).
- Autenticação: plano ChatGPT em todas as chamadas de texto. Nenhum fallback
  faturado.
- Complemento: 13 lacunas, 11 pesquisadas e resolvidas.
- Bucket: 42 leituras pedidas, 15 idas à rede (7 falharam por WAF ou
  transporte) e 4 do cache compartilhado. A sonda de anúncio teve 69 pedidas e
  11 abertas.

**Tempo por etapa (s).** O tempo de pesquisa total é parecido nos dois runs de
10/10 (307 s e 324 s). No final, ele saiu da inteligência e foi para o dossiê.

| Run | inteligência | dossiê global | complemento | pacotes, ferramentas e CTAs | redação (3 em voo) | revisão | acabamento |
|---|---|---|---|---|---|---|---|
| bucket | 140 | 22 | 145 | 61 | 139 | 216 | 28 |
| final | 0,03 | 202 | 122 | 93 | 173 | 164 | 42 |

### Do zero, reaproveitamento e retomada, separados

- **Do zero:** 804 s de parede e 20 chamadas, com esqueleto aprovado. Nenhuma
  imagem.
- **Reaproveitamento dentro do run:**
  - PAA do cache;
  - 4 documentos do cache compartilhado de 24 h;
  - 27 leituras repetidas e 58 sondas evitadas pelo bucket.
- **Retomadas, cada uma de uma única etapa** (recibos em `recibos/`):

| Retomada | Causa | Chamadas | Tokens (entrada/saída) | Tempo |
|---|---|---|---|---|
| Gate da LP e da p2 | defeitos do validador e do verificador de HTML (abaixo) | 0 | 0 | 0,03 s |
| Saída oficial da p4 | canal ordenado com dossiê velho: notícia do governo da Bahia | 2 (sniper só da aresta + revisão da p4) | 25,5 mil / 1,4 mil | 44,5 s |
| Dobra da LP, 1ª tentativa (**desperdiçada**) | subtítulo de 150 caracteres recusado pelo limite de 140; a LP foi revisada sem mudar | 2 | 22,5 mil / 1,5 mil | 44,2 s |
| Dobra da LP | título de 60 caracteres virava 3 linhas no celular; limites 45/160 | 2 | 22,5 mil / 1,2 mil | 36,2 s |

O script da dobra agora pula a revisão quando a dobra não muda.

### Retentativas da redação

O run final teve 6 retentativas: p1 ×1, p2 ×1, p6 ×2 e p7 ×2. Todas tiveram o
código `ungrounded_critical_claim`.

- O motor grava só o código por tentativa, não a mensagem nem o número citado.
  A causa de cada retentativa não pode ser provada uma a uma.
- O que está provado:
  - o gate da LP reprovou "100%" de um fato de condição, lido pela data
    05/07/2025;
  - os widgets da p6 e da p7 foram recusados por "100%" e "0%" do mesmo fato;
  - a LP, a p6 e a p7 recebem esse fato.
- Com o validador atual, a LP passa e as duas afirmações dos widgets passam.
  Ver `test_numero_de_fato_de_condicao_e_o_valor_estruturado_nao_a_data`.
- Para a p2, a causa não ficou registrada.

## Primeira dobra e CTAs, antes e depois

| | Título | Subtítulo | Botões da LP |
|---|---|---|---|
| 09/10 | Tarifa Social de Energia | Entenda qual desconto está em questão e escolha entre critérios, fatura e valor da conta. | Ver quais critérios se aplicam · Conferir o desconto na fatura · Ver como a cobrança é formada |
| 10/10 bucket | Tarifa Social de Energia | Entenda o desconto na conta de luz e escolha entre conferir os critérios, a fatura ou o valor cobrado. | Ver quem pode ter direito à Tarifa Social · Procurar o desconto na conta de luz · Entender por que ainda pode haver valor a pagar |
| 10/10 final | Tarifa Social: desconto na conta de luz | Para residências elegíveis, a Tarifa Social desconta 100% da tarifa nos primeiros 80 kWh por mês; consumo excedente e outras cobranças podem permanecer. | Conhecer os critérios para ter Tarifa Social (hero, para a pré-sell) · Procurar a indicação da Tarifa Social na fatura · Entender por que ainda pode haver valor na conta |

- Antes, o subtítulo descrevia a navegação. Agora ele responde com o fato
  central e o limite dele.
- São 14 botões no funil (10 internos e 4 oficiais), com 14 rótulos distintos.
- O primeiro botão da LP vai à pré-sell. A navegação do topo segue.
- A p4 e a p7 não têm botão interno por desenho do plano: são as pontas dos
  caminhos.

## Ferramentas

- **p2, calculadora de renda por pessoa:**
  - no Chromium, 1518 ÷ 4 = 379,50;
  - "2,5" pessoas é recusado; "1.518,00" era recusado até o fechamento
    localizado (abaixo) e agora é aceito;
  - o aviso sem JS fica oculto.
- **p3, p4 e p5, navegadores de jornada:** respondem à escolha no Chromium.
- **p4:** o revisor corrigiu o texto do widget por patch localizado na
  retomada.
- **p6 e p7:** os widgets foram recusados pelo defeito do "100%", já corrigido.
  As páginas saíram sem widget, com tabela. Recuperar exige retomar ferramentas,
  redação e revisão das duas.

## Destino oficial por tarefa

| Página | Tarefa | Saída oficial |
|---|---|---|
| LP, pré-sell | — | nenhum link externo no corpo (regra) |
| p3 | obter o benefício | ANEEL, Tarifa Social (regras de acesso). O corpo cita também o Cadastro Único (gov.br) |
| p4 | achar o atendimento | ANEEL, "Fale com a sua distribuidora". Antes da retomada: notícia do governo da Bahia |
| p5 | conferir na conta | MME, perguntas frequentes (a quem pedir confirmação) |
| p6 | entender o valor | sem botão de saída; o corpo cita a ANEEL |
| p7 | comparar os descontos | ANEEL, Tarifa Social (faixa de consumo) |

**Casos reais pedidos:**

- **p2:** revisada e aprovada. A entrega foi ajustada (sem definição da renda
  por pessoa e sem o limite em reais) e registrada como delta.
- **p5:** o revisor tirou do corpo três afirmações de variação sem fato
  comparativo. O widget não afirma variação.
- **p7:** os 4 requisitos ficaram verificados pela pesquisa guiada (antes, 3
  indisponíveis). Não precisou mudar a entrega.
- **p6:** o fato dos 80 kWh chega ao texto e à tabela.
- **LP:** dobra nova (tabela acima).

## Defeitos reproduzidos sobre artefatos gravados

Reproduzidos sobre o run bucket em `recibos/reproducao-defeitos.json`:

- **p2:** os 3 bloqueios gravados viram 1 ajuste de atribuição para o revisor.
- **p5:** o widget passa a ser visto pelo revisor.
- **p6:** a instrução de lacuna deixa de proibir os 80 kWh.
- **Saídas oficiais das 5 soluções:** da Cemig para a ANEEL.

Achados pela execução final, todos corrigidos e retomados só na etapa
afetada:

1. **"100%" de fato de condição lido pela data.** Reprovou o gate da LP e
   recusou os widgets da p6 e da p7. A correção usa o valor estruturado ou a
   quantia escrita no fato. Ela tinha uma regressão: um rótulo entre aspas
   ("saque 100% digital") sustentava número. Foi corrigida antes do commit.
2. **Calculadora do motor recusada pelo verificador de HTML** (p2).
3. **Consolidação depois dos pacotes reordenou os canais.** A saída congelada
   da p4 virou notícia regional. Na composição, isso deu "página mudou depois
   do congelamento".
4. **Título da dobra longo demais no celular** (3 linhas sobre a imagem).
5. **Print oficial solto.** O print de um destino que a página não linka ia
   para depois do 2º título (a Bahia na p4).

## Testes e limites da prova

- **Testes:** suíte do motor com 1.693 passaram e 7 pulados. Testes novos:
  - `test_fatos_por_contexto.py` (8);
  - `test_pesquisa_pelo_esqueleto.py` (3);
  - casos novos em sniper, widgets, índice factual, fatos compartilhados,
    ordem de canais, calculadora e print.
- **Chromium:**
  - a auditoria do motor passou a 390 e 1440 px nas 7 páginas, depois da
    recomposição;
  - numa de quatro medições, a p7 mobile deu CLS 0,158. O HTML é idêntico, e
    as três repetições deram 0. A causa era as `<img>` inseridas pelo motor
    irem sem largura e altura; corrigido no fechamento localizado (abaixo).
- **Limites:**
  - **Imagens:** foram reaproveitadas na composição (p1, p2, p3 e p6 de 09/10;
    p4, p5 e p7 de 10/10). O run não gerou imagem.
  - **Prévia:** não é WordPress. O CSS do MU-plugin não está no site, e a rota
    HTTP não foi executada.
  - **Links com parâmetro de sessão** vindos da pesquisa (MME
    `?_authenticator=…`; Neoenergia `?doAsUserId=…`): trocados no fechamento
    localizado (abaixo).
  - **Pré-sell:** a definição da renda por pessoa e o salário-mínimo vigente
    seguem sem fonte. A entrega foi reduzida, não resolvida.
  - **Prints repetidos:** o mesmo print da ANEEL aparece na p3, na p6 e na p7.
    É o mesmo destino.
  - **Retentativas:** a causa por tentativa não é gravada (só o código).
  - **ROI e CTR:** nenhuma afirmação. Nada foi publicado nem medido com
    tráfego.

## Fechamento localizado, depois da homologação (10/10)

Pedido do dono: sem nova arquitetura, sem pesquisa nova e sem reescrever
páginas. Foi uma retomada só das etapas afetadas, registrada à parte:
`retomada_fechamento`, 2 chamadas, 60 mil/5 mil tokens, 176 s.

### Links públicos

As três URLs com parâmetro de sessão viraram a URL canônica que o próprio site
declara. A troca só foi feita depois de baixar a versão pública pelo leitor do
motor e conferir o trecho de cada fato nela:

- **MME:** texto idêntico.
- **Coelba:** texto idêntico.
- **Neoenergia:** a página `/en/` declara a canônica pt-BR, e a frase do fato
  está nela.

Foram atualizados fatos (com `url_substituida`), fontes, canais, rota e botão
da p5, rascunhos, prints (com `url_capturada`), pacotes, índice de evidências
e metadados. O dossiê foi de `468673eb…` para `e17a33b0…`. Telemetria,
briefings e revisões antigas ficaram como histórico.

### Espaço das imagens

- O wp:image do motor passa a levar o id da mídia (`"id":N`,
  `class="wp-image-N"`), como o Gutenberg salva.
- O WordPress (7.1.3 no site) acrescenta largura e altura ao renderizar.
- Largura e altura no `<img>` gravado deixariam o bloco inválido no editor:
  o `save` do core/image não as salva (conferido no código publicado do
  `@wordpress/block-library`).
- **Prova na prévia, que emula esse filtro:** com as imagens pendentes, a
  altura reservada foi de 0 px para 235 a 538 px no celular. CLS 0 em 4 de 4
  auditorias.

### Calculadora

- Python (gabarito) e JS (navegador) usam as mesmas duas expressões. Aceitam
  ponto de milhar em grupos de três e vírgula decimal; o ponto decimal vale
  quando não pode ser milhar.
- No Chromium, "1.518,00", "1518,00", "1.518" e "1518" ÷ 4 dão 379,50. "2,5"
  e "2.5" pessoas e "1,518.00" são recusados.
- Um teste antigo tratava "1.234,56" como ambíguo. Ele foi trocado pelo
  formato americano.

### Rótulos genéricos

- Rótulo que abre com "Entender/Conhecer/Saiba/Descobrir…" não é mais
  reaproveitado e é recusado quando o modelo o devolve. O prompt pede a
  resposta que o destino dá.
- Voltaram ao sniper só 3 botões:

| Botão | Antes | Depois |
|---|---|---|
| LP → pré-sell | Conhecer os critérios para ter Tarifa Social | Quando CadÚnico ou BPC dão acesso à Tarifa Social |
| LP → p6 | Entender por que ainda pode haver valor na conta | O que ainda pode ser cobrado com a Tarifa Social |
| Pré-sell → p3 | Entender como a Tarifa Social chega à conta | O que fazer se o desconto não aparecer na conta |

**Defeito achado pela execução a seco:** numa nova congelada, a entrega
ajustada da pré-sell era reaproveitada, mas o prompt do sniper ainda mostrava a
promessa original. O botão novo para ela seria escrito contra o que ela não
entrega. Agora a entrega ajustada entra no contexto antes do prompt (teste
`test_botao_repedido_para_pagina_com_entrega_ajustada_ve_a_entrega_ajustada`).

### Promessa da pré-sell

- **Antes:** "O acesso depende de hipóteses legais e dados cadastrais vigentes.
  Ter NIS, receber Bolsa Família, ser aposentado ou ter 60 anos, isoladamente,
  não confirma o direito."
- **Depois:** "Apresenta as hipóteses de acesso […]; não estão confirmados os
  parâmetros de cálculo da renda por pessoa nem o valor em reais do limite de
  renda."
- **Os textos combinam:** o texto aprovado traz as três hipóteses e os limites
  "expressos em salários-mínimos". O botão da LP anuncia as hipóteses, sem
  limite em reais e sem confirmar direito.
- **A mudança depende do aceite do dono.**

### Revisão e gate

- Só as páginas cujo conteúdo mudou (LP, p2, p5 e p7) foram revisadas, numa
  chamada. As 4 foram aprovadas sem patch.
- Gate OK nas 7.
- Composição local e Chromium a 390 e 1440 px OK, sem erro de JS.

### Entregas prometidas que continuam ausentes

- **Pré-sell:** definição dos termos da renda por pessoa e limite em reais.
- **p6:** o "exemplo" do esqueleto. A página traz um passo a passo de
  comparação de faturas, sem conta de exemplo.
- **p6 e p7, widgets:** não eram promessa do esqueleto e não foram
  restaurados.

### Testes

1.724 passaram, 7 pulados. São 29 casos novos de calculadora e imagem, 2 do
sniper e o ajuste de 1 teste antigo.

