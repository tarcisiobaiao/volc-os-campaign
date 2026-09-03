# REMAINING-RISKS — o que continua aberto

Escrito para quem pega isto depois. Nada aqui é "pequeno detalhe": são os
motivos concretos pelos quais esta sprint fecha como **PARCIAL** e não como
aceite.

## 1. As rotas reais nunca foram vistas em navegador

`/trafego`, `/trafego/nova/:id`, `/trafego/campanhas/:id` e o laboratório estão
sob `ProtectedRoute` e exigem sessão Supabase. Sem credencial — e digitar senha é
proibido — o navegador só alcança `/login`.

**Todo o QA visual desta sprint foi feito na bancada de fixtures.** Ela monta os
componentes REAIS, e por isso vale; mas ela não prova integração: não exercita
`useCanais` contra o servidor, nem o Hub inteiro, nem o cockpit de lançamento.

**Risco concreto:** um defeito de composição — dois `card-volc` aninhados, um
cabeçalho duplicado, um layout que só quebra com dado real — passaria por aqui.

**Próximo ato:** alguém com sessão abre `http://127.0.0.1:8091/trafego?aba=criar`
e confere a aba Criar com dado real. Ambiente já sobe (`GATES.md`).

## 2. A revisão Gemini NÃO aconteceu

```
gemini 0.57.0
comando: gemini -m gemini-2.5-flash -p "<prompt de revisão de contratos v25>"
falha:   "Please set an Auth method in your /Users/mac/.gemini/settings.json or
          specify one of the following environment variables before running:
          GEMINI_API_KEY, GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_GENAI_USE_GCA"
```

Não substituí por outro modelo e não inventei resposta. **O que ficou sem
segunda opinião independente:** a conferência dos contratos v25, a semântica dos
rótulos de portão em português operacional, e a leitura das capturas por um olho
que não é o meu.

## 3. Uma falha de pytest herdada continua vermelha

`test_provar_sem_copy_reprova_e_diz_por_que` reprova com `409
N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED`. Reproduz na árvore intocada, no SHA
da base. Não foi consertada — está fora do escopo — mas também não foi escondida.

## 4. Lente 8 da revisão adversarial: aceita e NÃO corrigida

Na aba Criar são renderizadas em sequência a jornada do canal, os quatro portões
e as treze etapas. Em mobile não há disclosure nem modo compacto: três listas
longas empurram a próxima ação por várias telas.

As 104 capturas mostram **0 overflow horizontal** e **0 alvo abaixo de 40px** em
375px — mas comprimento não é overflow, e a crítica está certa. A captura de
`jornada__pmax-retido__375x812` tem mais de 4000px de altura.

**Próximo ato:** esconder a prévia de treze etapas atrás de um único disclosure
abaixo de `md`, mantendo a escada de portões sempre visível.

## 5. Curadoria e grafo NÃO foram reconciliados — de propósito

`docs/volc-os-graph/curadoria-operacional.json` ainda registra Performance Max
como inexistente, e o grafo não foi regenerado.

Isto é **instrução, não esquecimento**: o AGENTS.md determina que trabalhadores
paralelos não disputem Roadmap/curadoria/grafo e entreguem um delta; o integrador
único aplica e reconstrói uma vez após o merge. O delta está em
`CURATION-HANDOFF.json`.

⚠️ **O grafo está defasado e isso precisa ser dito:**
`graphify-out/UPDATE_STATUS.json` registra `built_at_commit
a539dbd7d7cb395ebc14986f0e1944d94f0aad26`, e a base desta sprint é `207e91f1`.
Ele nem existe dentro desta worktree (é gerado, não versionado).

## 6. O que esta sprint deliberadamente NÃO fez

- **Não reescreveu o cockpit de lançamento** (`NovaCampanhaPage`, 1014 linhas).
  Ele continua com as três verdades simultâneas para a etapa "copy", com
  `pendencias`/`podeLancar` montados no navegador, sem controle de releitura e
  sem carimbo de frescor — na única tela que gasta dinheiro.
- **Não implementou M1** (serializar `bloqueado`/`bloqueios` em
  `projecao.cockpit`). A síntese o nomeia como a mudança de maior alavancagem do
  backend, e ela continua por fazer.
- **Não tocou a tela canônica da campanha** além de torná-la navegável.
- **Não implementou a varredura de evidência (§8.4).** E aqui a razão importa:
  `POST /provar` é UMA requisição. Não existem sub-fases observáveis. Animar
  nove fases sobre uma chamada seria exatamente o "loader falso" que o briefing
  proíbe. Uma varredura honesta exige encadear atos REALMENTE sequenciais —
  validação local, leitura do destino, releitura dos portões, prova na conta — e
  isso é uma sprint própria.
- **Não corrigiu os defeitos herdados do Hub** listados no `AUDIT-BEFORE.md`
  (quinta consulta em toda aba, "Atualizar dados" incompleto, contador de atenção
  recalculado no cliente, docblock que diz três abas).

## 7. Riscos de contrato que continuam de pé

- `mensuracao.lida` é **sempre** `false` em `/canais`, e isso não é defeito: a
  rota não chama o Google Ads. Mas significa que a pergunta "esta campanha está
  medida?" continua **sem resposta honesta** nesta superfície.
- Cinco dos sete portões de `prontidao` são estruturalmente inalcançáveis porque
  quatro entradas de `pr.avaliar` estão fixadas em `False` em produção.
  `HEALTHY` é inalcançável para toda campanha.
- SHOPPING e VIDEO não têm manifesto. Qualquer afirmação de capacidade para eles
  seria invenção; a única descrição por canal é uma gramática do frontend.
