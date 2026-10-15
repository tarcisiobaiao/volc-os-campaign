# Harness Google Ads

## Modo canônico (`canonico.py`) — use este para o fluxo atual

Card com conjunto pago aprovado → Gemini escreve SÓ texto (RSA, sitelinks,
callouts) → `POST /api/trafego/provar` em processo → portão do conjunto pago,
política, builder, `validate_only`, destino e selo da própria rota. O schema
de saída não tem keyword, grupo, URL ou dinheiro. O pedido (`Pedido`) exige
verba, CPC, estratégia e rede declarados pelo operador, sem padrão.

```sh
cd backend && set -a && . ./.env && set +a && unset FORGE_PERMITIR_ESCRITA
PYTHONPATH=..:. .venv/bin/python -m volc_ads.harness.canonico PEDIDO.json PASTA \
  --modelo gemini-3.8-flash --preco-entrada-usd-mi 0.75 --preco-saida-usd-mi 3.75 \
  --fonte-preco "https://ai.google.dev/gemini-api/docs/pricing (data da leitura)"
```

- Recibo: request ID do aceite (agora devolvido pela própria rota em
  `preparo.prova_google`), hash do pedido e da copy, uso de tokens, custo
  ESTIMADO pelo preço declarado (sem preço: `null`), fotografia da conta antes
  e depois (campanhas/anúncios/orçamentos/estratégias) e o veredito do destino.
- Reparo: só quando o Google ou o portão criativo recusou o TEXTO, com
  `--reparar`, uma vez (teto de duas gerações). Recusa de conjunto, destino ou
  conta não é reparável por texto.
- Identidade: `exigir_usuario` é substituída por uma identidade declarada no
  recibo. Prova o motor e os portões, não a sessão do produto.

## Modo laboratório (`search.py`) — prova do builder

⚠️ Não é o caminho de campanha: não passa pelo portão do conjunto pago, pelo
destino nem pela doutrina P7 (a rota colapsa em um conjunto; aqui o modelo
pode propor N grupos com RSA próprio). Serve para provar o builder e o
`SubIntencao.rsa`, nunca para preparar campanha real.

Prova curta: LP pública + snapshot de keywords → proposta Gemini → builder
Search existente → Google `validate_only`. Não é outro executor, não gera
autorização de mídia, não tem ferramenta de shell para o modelo e não cria
campanha. A porta de criação e o ledger existentes continuam obrigatórios.

## Rodar

Da raiz do checkout oficial, use o ambiente de desenvolvimento:

```sh
backend/.venv/bin/python -m pip install -r volc_ads/harness/requirements.txt
backend/.venv/bin/python -m volc_ads.harness.capture CAMINHO_DO_RUN \
  --customer-id CUSTOMER_ID --login-customer-id MCC_ID \
  --url https://site.example/guia/ --tema 'Tema do guia' --slug tema \
  --budget VALOR_DECLARADO --cpc VALOR_DECLARADO
backend/.venv/bin/python -m volc_ads.harness.search \
  CAMINHO_DO_RUN/input.json CAMINHO_DO_RUN/proof --modelo MODELO_DISPONIVEL
```

A captura é somente leitura. Usa keywords já habilitadas na conta: não minera
nem aprova um conjunto novo. Seu recorte e o snapshot precisam fazer sentido
para a LP escolhida. `Entrada` também pode ser fornecida pelo chamador com
outro snapshot explícito; isso continua sem autorizar publicação/criação.

Orçamento e CPC são entradas explícitas do operador, não decisão do Gemini,
SERP ou Keyword Planner. Nesta prova Search: MANUAL_CPC, PHRASE, só Google
Search, sem parceiros ou expansão Display; campanha montada PAUSED.

## Contrato e limites

- O modelo recebe contexto de página/keywords, não a chave, IDs de conta ou
  parâmetros financeiros. Gera grupos e RSA específicos. Não gera negativas.
- Cada keyword do snapshot aparece exatamente uma vez. O schema declara os
  limites reais de caracteres; não há truncamento automático de copy.
- `SubIntencao.rsa` é opcional. Chamadores antigos mantêm a copy compartilhada.
- Uma chamada Gemini por tentativa, sem fallback ou retry/continuação ocultos.
  Um reparo explícito (`--reparar`) permite a segunda tentativa, nunca terceira.
- Resposta guardada antes de interpretar. Queda não zera contagem. `.lock`
  impede dois escritores no mesmo run; um lock após crash exige inspeção,
  não remoção automática. Recibo concluído é reutilizado só com hashes válidos.
- Só `GoogleAdsService.mutate(validate_only=True, partial_failure=False)`.
  Nenhum `mutar`, `/subir`, escrita Supabase, troca de RSA ou verba.
- Sucesso guarda request ID real, payload e hashes. Não comprova revisão de
  política do Google, serving, lucro, ROI nem percurso HTTP autenticado.
- Os sitelinks herdam a URL final porque esse é o contrato atual do builder.
  Não afirmar que caminhos independentes ou elegibilidade de serving foram provados.
- A chave é resolvida pelo carregador existente e não entra em logs/artefatos.
  Custo sem preço/usage de faturamento informado fica `null`, nunca “grátis”.

## Evidência de 14/10/2026

Leia `docs/audits/GOOGLE-HARNESS-GEMINI-WEBGO-2026-10-14.md`. A prova Google
passou após quatro ajustes locais explícitos da copy real. Isso NÃO é prova
de que toda proposta futura será aceita sem revisão. O output original,
o erro anterior e as mudanças foram preservados; não houve terceira geração.

```sh
backend/.venv/bin/python -m pytest volc_ads/harness/test_search.py \
  volc_ads/campanha/testes_search.py -q
```
