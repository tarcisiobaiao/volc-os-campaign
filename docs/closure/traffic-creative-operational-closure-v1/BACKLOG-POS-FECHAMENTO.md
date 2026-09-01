# Backlog pós-fechamento — tráfego + criativos

Dívida conhecida ao fim da missão. Nada aqui bloqueia o que foi entregue; tudo
aqui é verdadeiro hoje e tem cenário de falha nomeado.

Ordenado por quanto custa deixar como está.

---

## 1. Lavagem de procedência pela pasta do operador

**Onde:** `volc_ads/criativo_ponte.py:876-884` (`lote_de_pasta`), aceito em
produção por `NATUREZAS_ACEITAS[Destino.PRODUCAO]` (`:155-168`).

`lote_de_pasta` reconstrói o `Asset` sem informar `natureza`, e o default de
`Procedencia.natureza` é `NAO_DECLARADA` (`volc_ads/criativo/contrato.py:166`) —
que é aceita em destino de produção.

**Cenário concreto** (achado pelo Codex, verificado por mim): um PNG produzido
pelo motor de ensaio, que declara `LOCAL` (`adaptadores/png_local.py`), é salvo
na pasta `marketing/` do operador. `lote_de_pasta` o recria como
`NAO_DECLARADA`. `imagens_de_display` o admite em `Destino.PRODUCAO`. **A peça
de ensaio vira payload de produção.**

O marcador `LOCAL` é lavado ao passar pelo disco.

**Por que não bloqueou esta entrega:** o caminho exige que uma pessoa copie
manualmente um arquivo de ensaio para a pasta de produção. Não há caminho
automático — os dois produtores programáticos (`catalogo.py:99` e
`bancada/servico.py:453`) propagam `natureza_do_motor(motor)` corretamente, e um
asset `LOCAL` que chegue por eles **é recusado**. Verifiquei os dois.

**Por que ainda importa:** a garantia que a missão pede é "nenhum asset falso ou
fixture é apresentado como produção". Ela vale para o caminho programático e
**não** vale para o caminho do disco. A diferença precisa estar dita.

**Remédio:** `lote_de_pasta` deveria marcar `NaturezaDaProcedencia.NAO_DECLARADA`
explicitamente **e** o destino de produção deveria recusá-la assim que os
produtores legados declararem. Enquanto `NAO_DECLARADA` for aceita, esta porta
fica aberta por construção.

---

## 2. Papel obrigatório pode ficar abaixo do mínimo sem reprovar

**Onde:** `volc_ads/criativo_ponte.py:636-640`, payload devolvido em `:673-675`.

A lista `faltando` testa apenas se o papel **esvaziou**
(`not getattr(imagens, papel)`), não se ele ainda satisfaz `quantidade_minima`.

**Cenário concreto** (achado pelo Codex): uma exigência pede 2 imagens de um
papel obrigatório. As 2 passam na validação. Uma é descartada depois por bytes
ausentes ou hash divergente. Sobra 1. `faltando` continua vazio, e `entrega.ok`
sai `True` — **plano inválido apresentado como válido**.

**Por que não bloqueou esta entrega — e esta é a parte que o Codex não podia
saber:** verifiquei `volc_ads/criativo/requisitos.yaml` e **todos** os mínimos de
papel de imagem hoje são `min: 1` ou `min: 0`. Com mínimo 1, "esvaziou" e "ficou
abaixo do mínimo" são a mesma condição. **O defeito é latente, não ativo.**

**O que o ativa:** o primeiro canal que exigir 2 ou mais de um papel obrigatório.
Nesse dia o defeito passa a produzir plano inválido silenciosamente, e nada no
código avisa que a mudança de YAML acordou um bug.

**Remédio:** trocar o teste de vazio por comparação com `quantidade_minima`.

---

## 3. `smart_bidding_eligible` é uma constante, não uma computação

**Onde:** `backend/app/trafego/prontidao.py:121-165`, consumido em `:203` e `:224`.

Nenhum ramo atribui `meta_status = PRONTO`; os únicos valores atribuídos são
`INDETERMINADO`, `PARCIAL` e `NAO_PRONTO`. Logo `medicao == PRONTO` é
inalcançável e `elegivel` é a constante `False`.

Falha na direção segura — nunca pinta verde sem prova. Mas apresenta um portão
que diz avaliar elegibilidade e que não tem como abrir. `contrato_canais.py:286`
já documenta isso honestamente e `:301` declara o default.

**Remédio:** ou tornar o portão alcançável com leitura real, ou renomeá-lo para
o que ele é — "não avaliado" — para que ninguém leia `False` como veredito.

---

## 4. Colapsos de estado dentro de `prontidao.py`

**Onde:** `:163` `list(fontes_de_sinal_observadas or ())` colapsa `None` ("não
li") em `[]` ("li, e está vazio"); `:125` `metas_da_conta.get("primaria")`
ausente cai no `else` "a conta não tem ação primária", ignorando `acoes[]`;
`:205` o ramo `sinal == INDETERMINADO` é **código morto** por consequência.

Os três levam a `NAO_PRONTO`, que é conservador. Eu os classifiquei como
bloqueadores durante a missão e **estava errado**: falha-fechado não é prontidão
falsa, e o critério existe para impedir prontidão falsa. São dívida.

Continuam sendo dívida real porque o cockpit passa a afirmar "não pronto" sobre
algo que ninguém mediu.

---

## 5. `prontidao.py:145` — `len(primarias) or 1` imprime 1 para 0

Nota textual que pode contradizer `conversion_actions_primarias: []` no mesmo
objeto. Só relato; não afeta decisão.

---

## 6. `volc_ads/entrega.py:263-267` — `try/except` devolvendo `[]`

Ausência lida como zero num caminho de **alerta**. Pré-existente e **fora do
ownership desta missão**; registrado para o Roadmap, não para este diff.

---

## 7. `MotorTipografico` se registra e falha depois

**Onde:** `backend/app/criativo/bancada/adaptadores/tipografico.py`.

Importa Pillow dentro de `produzir()` e de `versoes_congeladas()`. Numa máquina
sem Pillow ele **aparece na lista de motores** e só estoura no meio do render —
o pior modo de falha possível. Pillow não está em `backend/requirements.txt`.

Foi por causa disto que o motor local novo (`png_local`) foi escrito só com
`zlib` e `struct` da stdlib, sem pré-requisito nenhum.

**Remédio:** ou declarar Pillow como dependência, ou fazer o motor não se
registrar quando o import falha.
