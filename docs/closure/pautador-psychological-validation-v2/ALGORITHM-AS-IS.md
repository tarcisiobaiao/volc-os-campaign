# ALGORITHM-AS-IS — o Validador como ele é hoje

Base: `origin/volc-os-v2 @ b2af81f0a2018626c5d873574664991b16f7ce38`.
Reconstruído por leitura integral dos módulos e por **execução**, não por
comentário. Onde um comentário afirma algo que o código não faz, está marcado
`⚠️ COMENTÁRIO FALSO` com a prova.

---

## 1 · O caminho completo do arraste

```
Kanban (EntityKanbanBoard.tsx, @dnd-kit)
  └─ handleDragEnd :575-591 → onStatusChange(card, "validating")
       └─ useEntityPautador.moveEntity :496-503
            ├─ applyMove → PATCH /entity-opportunities/{id}/status      (1º update)
            └─ se !card.validacao → medirCard :393-452
                 ├─ loop de sondagem GET /{id}/axes a cada 1500 ms      :413-423
                 └─ POST /entity-opportunities/{id}/validate            :426
                      └─ routers/entities.py:1130-1141
                           ├─ update_entity_status(status="validating") (2º update)
                           └─ _medir_eixos([id], modo="individual")     :1200-1218
                                └─ validacao.Validador.validar(...)     orquestrador.py:266-323
```

O arraste dispara **dois** updates de status: o `PATCH` do front e o mesmo
`PATCH` repetido dentro da rota `/validate` (`entities.py:1140-1141`), que força
`status="validating"` ignorando qualquer `status` do corpo.

### Os passos do Validador, em ordem real (`orquestrador.py:266-323`)

| # | passo | fonte | eixos derivados | lote? |
|---|---|---|---|---|
| — | `_carregar` :327-370 | Supabase | — | — |
| — | `_marcar_ja_medidos` :372-386 (só se `refazer=False`) | Supabase | — | — |
| 0 | `_passo_cluster` :414-465 | DataForSEO `keyword_suggestions` | (semeia volume) | não, 1 semente/card |
| 1 | `_passo_historico` :467-524 | DataForSEO `historical_search_volume` | `volume`, `reposicao` | **sim** |
| 2 | `_passo_serp` :619-679 | DataForSEO SERP (2 fases) | `formato_consumo` | não |
| 3 | `_passo_trafego` :683-724 | DataForSEO `bulk_traffic_estimation` | `vacuo`, `densidade` | **sim** |
| 4 | `_passo_ficha` :728-905 | **LLM ×3 passadas sobre o lote** | `ignorancia`, `engajamento`, `opacidade` | **sim** |
| 5 | :315-318 | — | grava tudo | — |

---

## 2 · Os oito eixos, e de onde cada um vem

**Escopo real do Pautador = 8 eixos** (`espaco.py:ESCOPO_PAUTADOR`), não nove.

| eixo | proveniência | família | níveis | portão |
|---|---|---|---|---|
| `volume` | **medido** (API) | economia | 5 | `residual` (exige medição) |
| `reposicao` | **medido** (API) | demanda_humana | 4 | — |
| `vacuo` | **medido** (API) | posicao | 4 | — |
| `densidade` | **medido** (SERP) | economia | 4 | — |
| `formato_consumo` | **medido** (SERP) | economia | 4 | `video_social`, `voz_ou_humano` |
| `ignorancia` | **julgado** (aritmética sobre contagens do LLM) | demanda_humana | 6 | `nao_preciso_de_nada` |
| `engajamento` | **julgado** (idem) | demanda_humana | 2 | `dado_unico` |
| `opacidade` | **julgado** (idem) | demanda_humana | 4 | — |

Fora do escopo por **decisão declarada**: `spread` (razão receita/CPC — é decisão
de compra, pertence ao engine de Ads) e `producao` (restrição de equipe, não
sinal de mercado). `espaco.py:FORA_DO_ESCOPO_PAUTADOR`.

### O que o LLM faz, e o que ele não faz

`prompts/ficha_de_resposta.md` — o **único** prompt vivo no caminho de validação
(carregado em `julgamento.py:48`). Ele proíbe o rótulo explicitamente:

> "Você **não classifica nada**. Não existe nível, nota, tier, faixa nem
> recomendação nesta tarefa. Os eixos do motor são derivados das suas contagens
> por aritmética, fora daqui."

O LLM **conta 8 observáveis + 1 tensão de vocabulário fechado**, sobre uma
`resposta_literal` que ele mesmo acabou de escrever. Python deriva os níveis em
`ficha.py:derivar` (:253-336). A justificativa está medida: a versão anterior,
que pedia rótulo ordinal, teve **67% de estabilidade** entre execuções idênticas.

**Esta é a parte do motor que já cumpre a seção 7 da missão.** Não foi
"consertada" nesta sprint porque já estava certa.

---

## 3 · Os quatro estados do dado — e onde eles colapsam

O motor distingue corretamente três estados no cálculo, o que verifiquei
executando `espaco.posicionar`:

| situação | índice | efeito |
|---|---|---|
| `volume` **ausente** | 0,740 | eixo sai da conta; cobertura cai 1,00 → 0,88 |
| `volume=residual` **medido** | 0,000 | portão dispara |
| `volume=residual` **não medido** (palpite) | 0,580 | portão **não** dispara (`PORTOES_EXIGEM_MEDICAO`) |

Ausência não vira zero. Zero confirmado não vira ausência. Palpite não mata.
**Isto está correto e não deve ser mexido.**

### Onde colapsa

Existem **quatro** situações e só **duas** são representáveis:

- (a) `proveniencia="ausente"` + `motivo_ausencia` → linha gravada, rastreável;
- (b) eixo simplesmente **fora** de `card.eixos` → nenhuma linha, nenhum motivo,
  o eixo desaparece do resumo **sem deixar rastro**;
- (c) zero confirmado → vira `residual` (mata) ou `serie_curta` (falta de dado);
- (d) falha de rede/LLM → cai em (a) num caminho e em (b) noutro.

A exceção do passo da ficha (`orquestrador.py:749-756`) faz **todos** os cards
pendentes perderem os três eixos psicológicos sem gravar uma única linha
`ausente`. E um card sem os três eixos ainda sai `apto: true`, com índice
calculado sobre cinco eixos, porque `veredito is None` não barra nada (:947-951).

---

## 4 · Defeitos reproduzidos

### D1 · ⚠️ COMENTÁRIO FALSO — a gravação não é incremental, e a UI finge progresso

`_gravar_eixos` tem **exatamente dois** call sites: `orquestrador.py:316` (dentro
do laço do passo 5, **depois** de todos os passos) e `:391` (caminho sem
credencial). **Nada é gravado antes do fim.**

O docstring do módulo (`orquestrador.py:41-46`) afirma: *"Cada eixo grava assim
que é medido. Se a chamada morrer no passo 4, os passos 2 e 3 já estão salvos"*.
A rota `GET /{id}/axes` (`entities.py:1150-1157`) repete a falsidade e vai além:
*"a escrita é INCREMENTAL … para a tela ler esse progresso do banco em vez de
fingir um"*.

O front sonda essa rota a cada 1500 ms (`useEntityPautador.ts:413-423`) sobre uma
tabela que fica **vazia até o fim** (~2 min por lote). A barra de progresso é
exatamente o progresso fingido que o comentário diz não ser.

**Consequência real:** timeout em qualquer passo perde 100% da medição paga.

### D2 · Revalidar destrói a ficha psicológica (não é idempotente — é destrutivo)

Cadeia completa, verificada:

1. `_marcar_ja_medidos` :372-386 restaura de `pautador_entity_axes` **apenas
   eixos**. Não restaura `card.ficha`, `card.tensao`, `card.portao`,
   `card.cabeca_*` — esses só existem na coluna JSON `validacao`.
2. `_passo_ficha` :746-748 — `pendentes = [c … if any(e not in c.eixos …)]`;
   `if not pendentes: return`. Card já medido **pula a ficha inteira**.
3. `_resumir` :1005-1017 emite `"ficha": card.ficha or None` (idem `tensao`, `portao`).
4. `_gravar_resumo` :1040-1044 faz `patch(…, {"validacao": valores})` —
   **substituição total da coluna**, não merge.

Revalidar um card já medido grava `ficha: null, tensao: null, portao: null` por
cima de dados bons. O botão de lote manda a coluna inteira, incluindo já medidos.
**Contraprova #18 não vale hoje.**

### D3 · A medição nunca aparece no card do Kanban

`useEntityPautador.ts:395` grava `medindo`/`progresso` com `String(card.id)`
(`"42"`). `EntityKanbanBoard.tsx:501` lê com `entityKey(card)` = `` `ent-${id}` ``
(`pautadorEntity.ts:269-270`) → `"ent-42"`. `"42" !== "ent-42"`, logo
`medindoKeys.has(key)` é **sempre false** no board.

Os outros **18** sites de chave do hook usam `entityKey`; `:395` é o único
outlier, e seu próprio comentário confessa o alinhamento ao drawer.

### D4 · `economia` mistura construtos e o rótulo do quadrante mente

`FAMILIAS["economia"] = volume, spread, densidade, formato_consumo`
(`espaco.py:274-280`). Com `spread` fora do escopo do Pautador, sobra:

- `volume` — quantas pessoas buscam → **demanda**, não economia;
- `densidade` — "quantos setores **pagariam**" → economia, mas é palpite;
- `formato_consumo` — canal → **comportamento**, não economia.

`perfil()` (:532) rotula quadrantes com "mercado paga / não paga" a partir dessa
mistura. Executado, com demanda humana **idêntica**:

```
volume massivo + densa → índice 0,767  perfil "alvo"             E=1,000
volume medio   + densa → índice 0,713  perfil "alvo"             E=0,796
volume baixo   + rala  → índice 0,553  perfil "audiencia_pobre"  E=0,357
```

**Baixar o volume de busca faz o motor dizer "o mercado não paga".** É erro de
categoria, não de calibração.

### D5 · O board ordena por um número que o LLM pode ter inventado

`EntityKanbanBoard.tsx:280` renderiza `card.score` como o número dominante do
card, colorido por `scoreColor()` (:85-91) — **quatro faixas por cor de texto**,
sem rótulo textual, com o significado num `title`. `score || 0` faz `null`
sombrear como nota baixa.

A montante (**fora do ownership desta missão**), `entities/prompts.py:131-133`
**ensina a fórmula de pontuação ao modelo** e `:263` pede `"score": 140.63`;
`entities/scoring.py:71` tem literalmente `# fallback: trust the LLM score`,
devolvendo proveniência `"llm"`.

Enquanto isso `pautadorEntity.ts:174` documenta que o índice de 10 eixos
"é texto e **NÃO ordena o board** (ordenação segue por `score`)".

### D6 · Deriva de contrato no objeto `tensao`

Backend emite (`orquestrador.py:764-773`):
`{tensao, distribuicao, share_com_tensao, intensidade_prior, porque}`.
Frontend declara (`types/pautadorValidacao.ts:188`):
`{tensao, pergunta, confianca}`.

`pergunta` e `confianca` **nunca** são emitidos → `undefined` em runtime.
`confianca` é resquício do `psique.ler` aposentado. E `intensidade_prior` — o
prior contaminado por desfecho — trafega sem tipo.

### D7 · `psique.ler` infla na ambiguidade (raio limitado)

`psique.py:186-193`: com 2+ tensões casando 1 marcador cada, `confianca="nenhuma"`
mas `intensidade` sai cheia e `transferivel=True` (`:167-170` não consulta
confiança). O desempate `max(…, key=(len, intensidade))` **enviesa para cima**.
Prova: **82 de 91** pares de vocabulário violam
`confianca=="nenhuma" ⇒ intensidade==0`.

**Escopo honesto:** `psique.ler` foi **aposentado** do Validador
(`orquestrador.py:295-305` documenta a substituição pelo LLM). Consumidores vivos
são `grafo/prescrever.py:28` e `grafo/construir.py:32` — fora do caminho do card.

### D8 · Código e prompt mortos

- `prompts/classificador_eixos.md` — **648 linhas**, zero referência em Python.
- `prompts/portao_engajamento.md` — **155 linhas**, referenciado só por
  `validacao/portao.py:39`, cujas funções `carregar_prompt/entrada/perguntar/
  temas_de/avaliar` **não têm chamador**. O orquestrador importa de `portao.py`
  apenas constantes (:742-743, :945).

### D9 · Nondeterminismo estrutural

`temperature: 0.9` **hardcoded** em `llm/gemini.py:31` e `llm/openai_client.py:31`
— sem setting, sem override, sem `seed`. Sem JSON Schema real: só
`responseMimeType: application/json` e `response_format: {"type":"json_object"}`.
O contrato da ficha **não é imposto pela API**.

*Mitigação já existente:* `julgamento.ler_fichas` roda 3 passadas e
`veredito_de_passadas` exige unanimidade. O desenho já assume o ruído.

*Agravante:* a concordância entre passadas é medida por **chave de string da
pergunta**. O prompt pede cópia literal, mas nada verifica — se o modelo
reescrever a pergunta, as chaves não colidem e a concordância sai 1,0 espúria.

### D10 · Custo do LLM não é contabilizado

`custo_usd` soma apenas DataForSEO (`cliente.py:114-115`). As **três** chamadas
de LLM por lote não são contadas nem estimadas. `custo_individual_estimado_usd`
(:1083-1089) subtrai a base de chamadas lotáveis que **falharam** (custo 0), então
pode ficar abaixo do custo real; `economia_do_lote` usa `max(0, …)` e esconde isso.

### D11 · Falha silenciosa vira sucesso na tela

`_medir_eixos` **nunca levanta** (`entities.py:1216-1218`): qualquer falha vira
`{"cards":0,"custo_usd":0.0,"erros":[…]}` com HTTP 200. O front só trata erro
HTTP, então mostra o toast **"Card medido ✓"** (`useEntityPautador.ts:438-442`)
sobre uma medição que não aconteceu.

### D12 · Cabeçalho descreve um motor que não existe

`validacao/__init__.py:3-5` diz que o LLM lê "ignorancia · engajamento ·
opacidade · densidade · producao". No código `densidade` é **medida pela SERP**
(:714) e `producao` saiu do escopo. `orquestrador.py:32` diz que a cobertura
divide "pelos NOVE" — o escopo real tem **oito**, então todo raciocínio de
cobertura escrito no arquivo está calibrado no denominador errado.

---

## 5 · A lacuna que justifica a missão

Existe **Camada 1** (medição: eixos + ficha) e **Camada 3**
(`paid_eligibility.py`, com fronteira já testada por `test_F2`).

**Não existe Camada 2 — a tese de oportunidade.** Nada no motor responde:

- vale aprofundar?
- qual hipótese justifica a aposta?
- qual formato de funil, e **com base em quais observáveis**?
- o que é fato, o que é hipótese, o que é desconhecido?
- qual o menor experimento que reduz a incerteza?
- esta oportunidade é **comparável** com aquela?

`formatos_da_entidade` (`julgamento.py:257`) já classifica formato **por
pergunta**, mas é declarado "propriedade da PÁGINA, não da entidade" e não vira
tese. E **não existe UI de comparação** entre oportunidades — o board compara
pelo `score` da descoberta (D5), não pela medição.

---

## 6 · O que já está certo e NÃO deve ser mexido

1. Ausência ≠ zero ≠ palpite — provado por execução (§3).
2. O LLM conta, o Python deriva — `ficha_de_resposta.md`, com justificativa medida.
3. `ordenar()` (`espaco.py:651`) já barra cobertura < 0,5.
4. `_CALIBRACAO` vazio, com teste guardando.
5. Volume alto com intenção de suporte já morre (`dado_unico` é portão → 0,0).
6. `intensidade` é emitida mas **nunca entra em conta** — verifiquei os dois
   únicos consumidores (`ficha.py:711`, `julgamento.py:251`), ambos payload.
7. `spread` fora do escopo editorial por decisão declarada e argumentada.
8. `DECISOES.md` é um registro de refutações com números — 8 ideias plausíveis
   testadas e mortas, incluindo a regressão ajustada em lucro (AUC de `spend`
   sozinho = 0,971, viés de seleção). Nenhuma delas deve voltar.
