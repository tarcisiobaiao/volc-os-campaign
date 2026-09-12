# Fechamento — implementação das prioridades Meta OP01/OP02

Data: 12/09/2026
Estado: `PARTIAL_PRODUCT_READY_FOR_AUTHENTICATED_QA`

## Resultado

Esta rodada deixou de ser apenas descoberta. O dashboard financeiro Meta agora
expõe o caminho observável entre compra de tráfego, chegada à landing page,
inventário GAM e receita. O backend preserva os campos já coletados pela Meta e
recalcula as pontes no grão canônico `adset/dia`, sem alterar a atribuição da
receita.

A contribuição exibida é deliberadamente chamada **contribuição observada**:
`receita GAM em BRL - mídia Meta`. Outros custos não são tratados como zero;
ficam declarados como não modelados. A resposta também informa se a evidência é
completa, provisória, divergente entre níveis ou incompleta.

## Contrato implementado

- `inline_link_clicks` e `landing_page_views` seguem da leitura existente para
  cada linha e para o total.
- Taxa de chegada, custo por chegada e impressões GAM por chegada são derivados
  do total, nunca somados.
- Ausência permanece `null`; zero medido permanece zero; denominador zero não
  produz razão.
- A densidade GAM não aparece se alguma parcela do período não tem a contagem
  de impressões, evitando apresentar uma soma parcial como total.
- Receita continua atribuída exclusivamente ao conjunto via
  `utm_campaign_value = adset_id`; nenhum valor desce ao anúncio ou criativo.
- O painel explica que impressões GAM podem representar múltiplos slots e
  refresh, não pessoas nem retenção.
- O estado de evidência é informativo e não altera aprovação, criação PAUSED ou
  ativação.

## Execução do harness

Run: `/private/tmp/volc-meta-adk-v2-20260912T125512Z`.

- modelo pedido e efetivo: `gemini-3.8-flash`
- thinking: `HIGH`
- grounding: ativo
- 6 chamadas; 111.959 tokens informados; custo monetário não informado
- resultado do harness: `partial_no_candidate`

O engenheiro de backend expirou com HTTP 504. A lane de interface produziu uma
proposta e consertou o próprio ambiente de testes, mas esgotou o orçamento antes
da crítica final. O patch não foi integrado cegamente: o lead rejeitou aliases
ambíguos e implementou no produto um único vocabulário canônico, usando a
proposta apenas como insumo.

## Provas

- `backend/tests/test_meta_financial_lineage.py`: 31 passed.
- suíte backend relacionada a atribuição, financeiro e anúncios: 88 passed
  antes da última guarda; a suíte financeira foi repetida e permaneceu verde.
- `conjuntos-financeiros.test.tsx`: 16 passed.
- suíte frontend Meta ampliada: 29 arquivos, 264 testes passed.
- contrato hermético do harness: 30 testes passed.
- build Vite: passed, apenas avisos herdados.
- TypeScript global continua com erros herdados fora dos arquivos alterados;
  nenhum diagnóstico apontou os arquivos desta rodada.
- `git diff --check`: passed.

## Limites honestos

- Não houve migration: os campos Meta já existiam no schema e no read model.
- Não houve chamada de criação/alteração na Meta, banco ou ativação.
- A tela protegida não foi inspecionada numa sessão autenticada; o navegador
  isolado chegou ao login. Portanto isto não é `VISUAL_VERIFIED`.
- A primeira linha real Meta + GAM ainda precisa comprovar o percurso completo.
- OP02 ainda não inclui contrato versionado de impostos, fees, revshare ou
  fechamento contábil.
- OP03 não foi implementada: associar contribuição a hipótese/criativo sem
  exposição temporal e coortes comparáveis inventaria causalidade.

## Próximo corte recomendado

1. QA autenticado do painel com uma campanha real e estados completo/incompleto.
2. Provar uma linha real com clique no link, LPV, impressão e receita GAM.
3. Modelar custos versionados com owner financeiro antes de chamar qualquer
   resultado de margem líquida.
4. Só então criar o lineage de hipótese criativa e exposição necessário à OP03.
