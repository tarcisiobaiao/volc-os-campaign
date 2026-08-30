# volc_ads — engine de campanha Google Ads

Extraído do `google_ads_forge` em 14/08/2026. **Não é o forge inteiro.** Veio só
o que funciona ponta a ponta e o que tem evidência medida por trás; o que era
esqueleto ficou para trás de propósito, e a lista está no fim deste arquivo.

Nada aqui escreveu em conta nenhuma até hoje. A trava de `gads/modo.py` é de dois
fatores — `destravar()` no código **e** `FORGE_PERMITIR_ESCRITA=1` no ambiente — e
`validate_only` é deliberadamente isento dela, porque validar é leitura.

## As duas metades

### 1 · Subir campanha Search

```
gads/         client (buscar · validar_mutacoes · mutar) · errors · modo
campanha/     brief · comum · search · marcacao · taxonomia · validacao†
copy/         PROMPT.md · provar.py · REFERENCIA-n8n-sniper.md · prompt.py‡
policy/       spec.py · spec.json (validador de 3 camadas, com fonte citada)
referencia/   geo.py — 219 países × 151 idiomas, do arquivo oficial
briefs/       fgts_saque_aniversario.py — o exemplo trabalhado

google_ads_api/   a documentação da API, organizada — CONSULTE ANTES DE SUPOR
```

**`google_ads_api/` não é anexo, é fonte.** A v25 tem 2.133 entidades e nomes que
não se adivinham. Todos estes custaram uma chamada recusada antes de virar linha
em algum lugar:

| supõe-se | é |
|---|---|
| `campaign.start_date` | não existe |
| `LAST_90_DAYS` em `DURING` | inválido — use datas explícitas |
| `TargetCpaSimulationPoint.conversions` | `biddable_conversions` |
| `SeasonalityEventScope.CUSTOMER` | só `CHANNEL` |
| `ContentLabelType.TRAGEDY_AND_CONFLICT` | `TRAGEDY` |

`api_reference_v25.md` (452 KB) e `api_codes_formats.md` (880 KB) respondem sem
gastar chamada. `topics.md` (196 KB) traz os tópicos de política — é o vocabulário
que `dados/corpus/politica.jsonl` usa. `structured_snippets.md` tem os headers
oficiais que `campanha/validacao.py` valida. O zip de geotargets é a fonte que
`referencia/geo.py` lê: **não duplique** — já houve uma cópia dele em
`referencia/dados/` e ela foi eliminada.

`campanha/search.py` monta a campanha inteira num **mutate atômico** — orçamento,
campanha, geo, idioma, ad group, keywords, RSA, sitelinks, callouts, snippets. O
flow n8n que ele substitui fazia 13 chamadas HTTP em sequência; se a sétima
falhava, sobrava meia campanha na conta.

‡ **`copy/prompt.py` é o gerador ANTIGO, não o renderizador do `PROMPT.md`.** Ele
termina com *"Prefira morno a reprovado"* — exatamente a instrução que o
`PROMPT.md` §4.4 declara revogada e aponta como causa dos 0,0% de verbo e 0,0% de
pergunta medidos. Plugar um cliente de LLM nele automatiza o defeito. Apague-o ao
escrever `render.py`; não o mantenha como fallback.

### 2 · Prever ouro de pauta (a coluna "em validação" do kanban)

```
pautador/prompts/classificador_eixos.md    ← o único arquivo novo
```

**O motor NÃO mora aqui.** Ele é `backend/app/motor_pautas/` — `psique.py`,
`espaco.py`, `iab.py`, `grafo/`, `dados/`, `sensores/`, `testes/`. Uma cópia foi
trazida para cá no empacotamento e depois removida: era a **terceira** cópia de um
motor já validado, e duas cópias divergem. Importe do backend, nunca duplique.

E `sensores/dataforseo.py` (15,6 KB) já traduz `volume`, `spread`, `vacuo` e
`reposicao` para este vocabulário fechado. Leia antes de escrever qualquer
integração de medição — ver `DATAFORSEO-MEDIDO.md`.

`espaco.posicionar()` recebe os 10 eixos declarados e devolve a **posição do tema
no espaço**, não uma nota. `indice` é média geométrica ponderada e vale **zero**
se qualquer portão disparar — porque portão é decisão binária, e ordenar tema
morto entre temas mortos não informa nada. `ordenar()` **remove** da fila quem
disparou portão ou não atinge cobertura mínima, em vez de mandar para o fim.

`prompts/classificador_eixos.md` é o prompt que preenche os 10 eixos, para
qualquer país e qualquer língua, com vocabulário fechado.

## Como rodar

```bash
# provar uma copy: forma determinística + validate_only na conta real + corpus
python -m volc_ads.copy.provar copy.json

# extrair o corpus de política (SELECT puro, nada é escrito)
python -m volc_ads.scripts.extrair_corpus_politica --mcc 8696453882,6084143056,1081900905
```

## O que está VALIDADO, e como

**Copy.** O `PROMPT.md` foi escrito por quatro autores independentes, cada um
executado de verdade, e a copy que cada um produziu passou por três juízes:
forma determinística, `validate_only` contra a conta real e comparação com
**6.651 headlines APROVADOS** das contas da operação. Notas 74/79/86/86. A versão
final gerou copy que passou em FORMA e GOOGLE na primeira rodada.

O defeito que ele cura tem nome e número. A copy anterior, escrita à mão:

| marcador | copy à mão | aprovados reais |
|---|---:|---:|
| verbo de execução | 0,0% | 12,2% |
| marcador de leitura | 60,0% | 29,9% |
| pergunta | 0,0% | 7,2% |
| número | 40,0% | 14,1% |

Sem verbo, sem pergunta, o dobro de explicação. E o `validate_only` **aceitava** —
ou seja, o problema nunca foi política, era mornidão. Mornidão não aparece em
`validate_only`; só aparece comparando com o que a operação de fato publica. É
para isso que existe o terceiro juiz de `copy/provar.py`.

**Classificador de pauta.** Validado ponta a ponta contra `posicionar()`: dois
mercados sem canal (NG, PH) saíram da fila com índice zero, e as duas agulhas
(MX 0,769 · CL 0,692) foram ranqueadas na ordem certa. Zero falso positivo.

## Duas coisas que a medição derrubou — não as reintroduza

**A blocklist de palavras.** `campanha/limites.yaml` proíbe `empréstimo`,
`crédito`, `antecipação`. Medido nos 6.651 aprovados e servindo: `crédito`
aparece **54×**, `préstamo` 9×, `saque` 12× — e **nenhum** deles nos punidos.
`empréstimo` e `antecipação` não aparecem em anúncio nenhum da operação, ou seja
a proibição nunca impediu nada; só nos limitou. A lista foi copiada do bloco
`❌ PROIBIDO` do prompt do n8n (preservado em `copy/REFERENCIA-n8n-sniper.md`).

O critério que a substitui é o **papel do site** — "o artigo explica como emitir"
contra "o site emite" — e ele atravessa idioma, que é o requisito real de uma
operação em 7 países.

† `campanha/validacao.py` continua aqui **só porque `search.py` o importa**. Ele
é 100% pt-BR: copy em espanhol com os análogos exatos de todos os termos
proibidos passa com zero achados e o runner diz "ok". Ele deve morrer, e o
substituto (`policy/spec.py`, que sabe pt/es/en e tem portão país × vertical) já
está nesta pasta — desconectado, esperando ser ligado.

**O DKI do n8n.** O prompt antigo mandava DKI em 5 dos 15 títulos (33%). Medido:
DKI aparece em **86 de 6.651 aprovados — 1,3%**. E o formato que passa é
invólucro nominal (`Guia {KeyWord:…}`), nunca imperativo (`Consulte {KeyWord:…}`).

## O que NÃO veio, e por quê

| ficou | motivo |
|---|---|
| `beast/` | 3 defeitos reproduzidos. O pior: dia sem gasto vira ROAS 0 e dispara corte de orçamento — 20 dias com `spend=0` cortam de 100 para 70. Campanha nova é punida por não ter entregado. Laço degenerativo esperando um executor. |
| `sentinela/` | observa um JSON estático de 64 eventos; nenhuma rede, nenhuma métrica, nenhum laço |
| `descoberta/`, `harvest/` | úteis, mas fora do caminho de subir campanha |

## O que falta para a campanha subir

1. **Cliente de LLM + parser.** Não existe cliente de LLM no pacote. O
   `PROMPT.md` está pronto e ninguém o chama.
2. **Segundo ad group** PHRASE + BROAD-MINING. O n8n tinha (`4b. Cria AdGroup
   Discovery`); este pacote cria um só. É o ad group que gera os termos de busca
   que a rotina diária de colheita precisa.
3. **`subir.py`.** É o `copy/provar.py` trocando `validar_mutacoes` por `mutar()`
   dentro de um `destravar()`. A campanha nasce `PAUSED` (`comum.py`), então
   lançar custa zero e já produz o veredito real de política do Google.
4. **Preservar a evidência de política em `gads/errors.py`.** Ele lê só
   `error_code`, `field_path` e `message[:400]`; `err.details` — onde vivem
   `policy_violation_details.is_exemptible` e a `PolicyViolationKey` — nunca é
   tocado. Consequência: num mutate atômico de ~40 operações não se sabe **qual**
   item violou, e pedir isenção de política é estruturalmente impossível. É o
   pré-requisito de qualquer autocorreção.

## Decisão aberta, e ela não é de código

O brief do FGTS declara `vertical="informativo"`. A página de destino, medida em
14/08/2026, diz outra coisa: title *"Como Antecipar Seu Dinheiro Hoje"*,
`antecipar` 16×, `pix` 8×, `dinheiro hoje` 2×, e quatro bancos parceiros
nomeados (Bmg, Santander, Nubank, meutudo). **A página intermedeia crédito.**

E o próprio brief negativa `meutudo`, `nubank`, `bmg`, `santander` — as quatro
marcas que a página usa como argumento.

Ou a LP vira mesmo informativa, ou o brief assume `vertical="financeiro"` e o
portão de habilitação (país × vertical) passa a valer. É a mesma congruência que
o engine de funil resolve do outro lado — motivo pelo qual esta pasta veio para
cá em vez de continuar isolada.
