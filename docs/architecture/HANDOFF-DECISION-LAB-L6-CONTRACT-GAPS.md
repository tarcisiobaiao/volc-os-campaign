# Handoff — Decision Lab L6, lacunas reais do contrato

Sprint: superfície operacional Search (frontend e projeção).
Branch: `feat/decision-intelligence-ui-l6`
Worktree: `/private/tmp/volc-grok-decision-ui-l6`
Base: `b69969be724bd0ee6794c244650bb0903110756c`

O browser não improvisou campo. Onde a bancada L6 pedia um dado e o contrato
vivo não o envia, a tela declara a ausência e esta nota registra o gap.

## O que o contrato já entrega e a bancada projeta

- `health_gate`, `estado_da_leitura`, `estado_da_superficie`
- `veredito.titulo` e `veredito.resumo` como resposta executiva
- `fatores.favorece | limita | desconhecido`
- `politicas[].suficiencia`, `faltantes`, `motivo_suficiencia`
- `conflitos[]` na ordem do servidor
- `diagnostico.degraus[]` com `frase`, `impedimento` e `evidencias[]` (`EvidenciaDeCampo`)
- `propostas_tipadas[]` e `caixa_de_propostas.propostas[]`
- `execucao.mutacoes_executadas: 0`, `aplicacao: nao_executada`, `recibo: null`
- `isolamento.oferece_aplicar: false`
- `timeline[]` técnica de oito passos, agrupada visualmente em quatro estágios

## Lacunas — não improvisadas no frontend

### 1. Modo shadow

`isolamento.somente_sintetico` é sempre `true`. Não existe `modo: shadow` no
contrato vivo.

A prova local `prova-l6-shadow-futuro` usa `SHADOW FUTURO · FIXTURE SINTÉTICA · SEM AÇÃO EXTERNA`.
O selo `SHADOW READ · DADOS REAIS · CONTA TESTE · SEM AÇÃO` fica reservado a um
payload futuro do backend, com fonte, conta e carimbo. Fixture não o renderiza.

### 2. Estado da medida

`EvidenciaDeCampo.valor: string | null` distingue ausência de valor, mas não
carrega um enum para:

- ausente
- zero medido
- lista observada e vazia
- campo ausente
- falha de leitura
- não aplicável

A projeção infere zero medido só quando o valor literal é `0` / `0.0`.
Lista vazia, não aplicável e campo ausente só aparecem quando a fixture L6
anexa chaves extras (`itens: []`, `estado_da_medida`). O pipeline vivo não
as envia em `evidencias[]` públicas.

### 3. Famílias de evidência

`resultado.evidencias` pública traz só `source` e `campaign`. Não há família,
interpretação, ressalva, carimbo por métrica, nem lance como eixo próprio.

A bancada agrupa `diagnostico.degraus` por eixo para leitura. Isso é
organização visual, não um recálculo. Conversão/receita só aparece quando
`fatores` a envia. Lance sem evidência permanece "nenhuma evidência anexada".

### 4. Frase executiva dedicada

Não existe `frase_executiva`. A tela usa `veredito.titulo` + `resumo`.
Quando `tipo` é `nao_apurado` ou `indeterminado`, ou a leitura não está
`atual`, a insuficiência é colocada antes da hipótese com o texto do contrato.

### 5. Hipótese versus fato no payload

O veredito chega como objeto único, sem `hipotese: true` e sem
`hipoteses_secundarias`. A bancada rotula a hipótese na apresentação.
Hipóteses secundárias só renderizam se o contrato um dia enviar
`veredito.hipoteses_secundarias: string[]`.

### 6. Confiança do diagnóstico

Não há `veredito.confianca`. A tela diz "confiança não declarada neste contrato".
Confiança de proposta existe em `caixa_de_propostas` e em `propostas_tipadas`.

### 7. Efeito estimado

`diff.gasto_diario` no pipeline sai `null`. A bancada mostra "não estimado".
Não calcula delta.

### 8. `PropostaTipada` no TypeScript do cliente

`PropostaTipadaDoLab` omite `evidencias`, embora o Python as serialise.
A projeção lê `evidencias` só se vierem no JSON, sem alargar o tipo exportado.

### 9. Marcas

`marcas` está fechado em `['PROTÓTIPO', 'DADOS SINTÉTICOS']`. Não inclui
`LABORATÓRIO` nem `SEM AÇÃO EXTERNA`. A superfície L6 adiciona essas palavras
na apresentação, sem alterar o tipo.

### 10. Timeline operacional de quatro estágios

A timeline do contrato tem oito passos técnicos (`features`, `politicas`,
`replay_eval`, …). A bancada agrupa em observado → qualificado →
diagnosticado → proposto. Não reordena o array original; só o apresenta
em quatro estações.

### 11. Ação local "registrar que ainda falta confirmação"

Não existe no contrato. Não foi oferecida.

### 12. Features como evidência

`features` é um dicionário calculado em Python. A bancada não o usa como
métrica operacional, para não parecer recálculo no browser.

## Pedidos de contrato (próximo corte, backend)

1. Enum `estado_da_medida` em cada evidência.
2. Famílias, interpretação e ressalva na evidência pública.
3. `modo_da_superficie: sintetico | shadow` e marcas correspondentes.
4. `frase_executiva` em linguagem simples, já priorizando insuficiência.
5. `hipoteses_secundarias` e `confianca` no veredito.
6. Efeito estimado explícito, inclusive o valor sentinela "não estimado".
7. Alinhar `PropostaTipadaDoLab` com o JSON real (`evidencias`).
8. Timeline de quatro estágios operacionais, ou metadados de agrupamento.

Nada disto foi implementado nesta sprint. Zero backend, zero banco, zero
Google Ads, zero Roadmap Vivo, zero grafo.
