# LIMITATIONS — o que esta lane NÃO prova

Escrito para ser lido por quem for continuar, não para fechar a missão com
aparência de completude.

---

## DIVIDA-DESCOBERTA-SCORE · o LLM ainda recebe a fórmula, a montante

**O defeito é real e foi confirmado no código:**

- `backend/app/entities/prompts.py:131-133` **ensina a fórmula de pontuação ao
  modelo**: *"A nota do card é `volume·0,25 + RPM·0,40 + competição_invertida·0,35`"*.
  É exatamente o anti-padrão que `motor_pautas/prompts/classificador_eixos.md:27`
  nomeia: *"Um classificador que conhece a aritmética vira otimizador."*
- `backend/app/entities/prompts.py:263` pede `"score": 140.63` diretamente.
- `backend/app/entities/prompts.py:270-276` pede `ignorancia_level`,
  `engajamento_level` e `opacidade_level` como **rótulos ordinais** — os mesmos
  três eixos que o Validador deriva por aritmética.
- `backend/app/entities/scoring.py:69-72` tem, literalmente,
  `# fallback: trust the LLM score`, devolvendo proveniência `"llm"`.

**Adjudicação desta lane: NÃO ALCANÇÁVEL.**

A missão autorizou ampliar ownership para `prompts.py` e `scoring.py` **somente
se** esses contratos alcançassem a validação/ranking entregues aqui. Eles não
alcançam, e a prova está em `backend/tests/test_llm_score_sem_autoridade.py`
(36 testes), em três pernas independentes:

| perna | o que prova | como |
|---|---|---|
| valor | `score` arbitrário não muda a tese | 17 valores (`None`, `0`, `-1`, `inf`, `-inf`, string, dict, list, `999999`) → tese byte-idêntica |
| valor | 13 campos ordinais da descoberta não movem a tese | `score_source`, `roi_signal`, `gold_tier`, `*_level`, incl. os três psicológicos |
| valor | `score` não reordena o ranking | tema de `score=999999` e evidência pior continua abaixo |
| transporte | a rota não carrega o campo | `POST /entity-opportunities/teses` não inclui `score` no `select` |
| transporte | defesa em profundidade | mesmo se o banco devolver `score`, a resposta é idêntica |
| código | a Camada 2 não referencia o identificador | AST: `score` não aparece como literal, atributo ou nome |
| código | a Camada 2 não importa a descoberta | AST: nenhum import `app.entities.*` |

**Portanto o ownership NÃO foi ampliado. `prompts.py` e `scoring.py` não foram
tocados nesta branch.**

**A dívida continua de pé e é independente.** O que ela ainda contamina:

1. `pautador_entity_opportunities.score` é gravado com `score_source` podendo
   ser `"llm"` (`entities/orchestrator.py:76,114`).
2. `EntityKanbanBoard.tsx:280` renderiza esse `score` como o número dominante
   do card, colorido por `scoreColor()` — **quatro faixas por cor de texto**,
   sem rótulo, com o significado num `title`, e `score || 0` faz `null`
   sombrear como nota baixa.
3. `types/pautadorEntity.ts:174` declara que o índice de 10 eixos "é texto e
   **NÃO ordena o board** (ordenação segue por `score`)".

Ou seja: **o card do Kanban ainda exibe com destaque um número que pode ter
vindo do LLM, sem proveniência visível.** Isso não contamina a decisão desta
lane, mas contamina a leitura do operador na mesma tela.

Não foi corrigido aqui **por disciplina de escopo**: a instrução foi explícita
— *"Não amplie ownership além disso"* — e a condição que autorizaria a
ampliação (alcançabilidade) foi refutada com prova. Corrigir o badge seria
ampliar ownership com base numa condição que não se verificou.

`test_a_divida_da_descoberta_existe_e_esta_declarada` falha se alguém apagar
este registro sem consertar a descoberta, ou consertar sem atualizar aqui.

---

## O benchmark Webgo não sustenta peso — e isso foi verificado, não assumido

O run `20260903T010510Z` é honesto e traz errata própria. O que ele **não**
sustenta:

| # | verificado rodando os dados | consequência |
|---|---|---|
| 1 | 46 pares de controle, **só 10 são de vencedora** (20 perdedora + 16 deterioração = 78,3% não são) | `pattern_shares.csv` compara vencedoras contra um pool majoritariamente de perdedoras |
| 2 | `refinement-v2/scripts/gh_portfolio.py:122` faz `{...} & set()` | interseção com literal vazio: o `0` publicado é artefato de código |
| 3 | SEARCH 28,1% (`profit_90`) vs DISPLAY 33,0%; SEARCH 36,5% (`profit_180`) vs 18,7%; SEARCH 43,9% (`profit_all`) vs 32,5% | **o sinal de canal não é identificável**: a direção depende da janela de lucro escolhida |
| 4 | medianas por grupo — palavras 894/927/902, CTAs 6/6/6, formulários 1/1/1 | estrutura de página não discrimina vencedora de controle |
| 5 | **14 de 18 domínios servem mais de um grupo** de desempenho | o mesmo template produz vencedora, perdedora e controle; as páginas não são observações independentes |

Reportado pelos investigadores, coerente com o que li, **não reverificado linha
a linha por mim** (declarado como tal):

- a janela de 30 dias de eventos de mudança está **dentro** da janela de 90 dias
  que rotula vencedora/perdedora — circularidade não registrada em nenhuma errata;
- 0 dos 122 episódios "legíveis" tem controle pareado utilizável;
- 35 de 35 playbooks com `tem_contraprova=False` e `n_legiveis=0`;
- o pareamento é feito **na própria variável testada** (canal entra nos três
  estratos), então a comparação de canal não pode produzir sinal por construção;
- 1 par vencedora-controle é **literalmente a mesma página** servindo as duas.

### A correção que eu mesmo tive de fazer

Minha primeira leitura da densidade de anúncio usou **mediana** (5/5/8) e
concluiu que ela não separava vencedora de controle. Estava **errada**: a
mediana esconde a cauda. Por proporção, o gradiente é real e monotônico:

```
vencedora   4/27 = 14,8%
controle   14/36 = 38,9%
perdedora  13/19 = 68,4%
```

É o **único** padrão do corpus com gradiente monotônico e comparação com
controle. Ainda assim **não vira peso**, por quatro razões independentes:

1. n efetivo ≈ 18 domínios, não 82 páginas (agrupamento por domínio);
2. é medida de DOM, não confirmável visualmente — a captura não rola a página;
3. o snapshot é do estado **atual** contra desfecho de 90-180 dias;
4. é propriedade de **monetização paga** — categoricamente fora da decisão
   editorial pré-lançamento.

Entra como `PRIORS_WEBGO["webgo/densidade-de-anuncio"]` com
`confianca: "baixa"` e `pode_decidir: False`.

---

## O que a Camada 2 não faz

- **Não recalcula a medição.** Lê `card.validacao` e cita. Se o Validador
  errou, a tese repete o erro com fidelidade — ela não é uma segunda opinião.
- **Não tem ground truth.** Não há desfecho limpo contra o qual medir se
  `aprofundar` acerta. Por isso não há accuracy, precision, recall nem uplift
  neste pacote: publicá-los seria inventá-los.
- **Não observa o passo 2 do funil.** O corpus Webgo não capturou nenhum
  destino dos blocos de escolha, então nenhuma afirmação sobre "sustenta
  sequência de páginas" pode citar o benchmark.
- **Não vê a página.** Nenhum observável visual entra
  (`OBSERVAVEIS_ACEITOS` exclui hero, CTA, selo, layout, template, design, cor),
  porque o corpus provou que elemento recorrente é template.

---

## Nondeterminismo que permanece

`llm/gemini.py:31` e `llm/openai_client.py:31` fixam `temperature: 0.9` em
código, sem setting, sem `seed`, e sem JSON Schema real (só
`responseMimeType`/`response_format`). O contrato da ficha **não é imposto pela
API**.

Isto **não foi corrigido** nesta lane: mexer na temperatura muda o
comportamento de todas as fichas já medidas e exigiria remedir a base para
comparar. O desenho já mitiga com 3 passadas e unanimidade
(`veredito_de_passadas`), e a instabilidade fica visível em
`comparacao.estavel`.

Consequência honesta: **`refazer=True` não é determinístico.** A Camada 2 é
determinística dada a mesma evidência; a evidência é que pode mudar.

Agravante registrado e não corrigido: a concordância entre passadas é medida
por **chave de string da pergunta**. O prompt pede cópia literal, mas nada
verifica — se o modelo reescrever a pergunta, as chaves não colidem e a
concordância sai `1,0` espúria.

---

## Custo do LLM continua fora da contabilidade

`custo_usd` soma apenas DataForSEO (`cliente.py:114-115`). As três chamadas de
LLM por lote não são contadas nem estimadas. `custo_individual_estimado_usd`
subtrai a base de chamadas lotáveis que **falharam** (custo 0), então pode
ficar abaixo do custo real; `economia_do_lote` usa `max(0, …)` e esconde isso.

---

## Código morto que continua vivo

- `motor_pautas/prompts/classificador_eixos.md` — **648 linhas**, zero
  referência em Python.
- `motor_pautas/prompts/portao_engajamento.md` — **155 linhas**, referenciado
  só por `validacao/portao.py:39`, cujas funções não têm chamador.
- `validacao/portao.py` — `carregar_prompt`, `entrada`, `perguntar`,
  `temas_de`, `avaliar` sem chamador; só quatro constantes são importadas.

Não removido: apagar prompt é apagar aprendizado, e a remoção pertence a uma
decisão de curadoria, não a esta lane.

---

## `psique.ler` continua inflando na ambiguidade

`psique.py:186-193`: com 2+ tensões casando 1 marcador cada, `confianca`
sai `"nenhuma"` mas `intensidade` sai **cheia** e `transferivel=True`
(`:167-170` não consulta confiança). Reproduzido: **82 de 91** pares de
vocabulário violam `confianca=="nenhuma" ⇒ intensidade==0`. O desempate
`max(…, key=(len, intensidade))` ainda **enviesa para cima**.

**Não corrigido nesta lane, e o motivo é escopo honesto:** `psique.ler` foi
aposentado do caminho do Validador (`orquestrador.py:295-305`). Os
consumidores vivos são `grafo/prescrever.py:28` e `grafo/construir.py:32` — e
a missão proíbe tocar o grafo nesta branch.

---

## Cobertura da interface

A validação de navegador cobriu desktop (1440) e mobile (390) nos estados
carregando, vazio, erro, pronto, retido e sem validação. **Não** foi testada
com leitor de tela real, nem em Safari/Firefox, nem com `prefers-reduced-motion`
ativo no sistema (a regra CSS existe e foi lida, não exercitada).
