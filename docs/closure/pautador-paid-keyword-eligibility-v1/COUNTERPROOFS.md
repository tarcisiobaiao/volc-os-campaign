# Contraprovas — antes e depois, medidos

Cada bloco abaixo foi executado. Nenhum é reconstruído de memória: o "antes"
saiu de `git show 34dc7b4:backend/app/agents/mining/*.py` rodando num
diretório separado, e o "depois" do HEAD desta branch, com a mesma entrada.

Suíte: `backend/tests/test_pautador_paid_keyword_counterproofs.py` — 49 testes,
todos vermelhos no primeiro commit da sprint (`ed37cb5`), todos verdes agora.

---

## A · B · N — o conjunto exportado é o conjunto selecionado

Funil BPC/LOAS, uma sub-intenção, oito keywords.

**Antes**
```
selecionadas : 5  ['meu inss login', 'inss telefone 135',
                   'bpc loas quem tem direito', 'bpc loas valor 2026',
                   'bpc loas como dar entrada']
exportadas   : 8  (as cinco acima + 'bpc loas prazo analise',
                   'bpc loas negado o que fazer',
                   'bpc loas advogado x concorrente')
lista_google_ads: 8 linhas
stats: {'total_keywords': 8, 'total_volume': 985200, 'avg_cpc': '1.53'}
```
Três termos entraram na campanha sem passar por escolha nenhuma:
`all_keywords_for_campaign` era alimentada de `deduped`, não de `selected`.

**Depois**
```
selecionadas : 3  ['bpc loas quem tem direito', 'bpc loas valor 2026',
                   'bpc loas como dar entrada']
exportadas   : 3  (idênticas)
lista_google_ads = derivar_lista_google_ads(conjunto)  — uma função só
stats: {'total_keywords': 3, 'total_volume': 190000, 'avg_cpc': '1.10',
        'avg_cpc_estado': 'measured', 'avg_cpc_n': 3}
```

## C — volume não compra intenção

**Antes**: `meu inss login` (480.000) e `inss telefone 135` (300.000) eram os
dois PRIMEIROS da própria seleção, ordenada por volume, e empurravam a
intenção de elegibilidade para fora do topo. `lista_clickup` os rotulava
`ELEGIBILIDADE`, que é a sub-intenção em que foram minerados.

**Depois**: os dois vão para `HUMAN_REVIEW` com
`intencao_navegacional_ou_suporte` + `navegacional_para_entidade_publica`, e
`bpc loas quem tem direito` — com 1/5 do volume — está no conjunto.

É o mesmo defeito que `validacao/orquestrador.py` já documentava do lado
editorial: *"73% do eixo `volume` era gente procurando o telefone do Banco
Pan."* Do lado pago ninguém tinha olhado.

## D — CPC ausente não é CPC barato

O MESMO termo, mudando apenas se o CPC foi medido:

**Antes**
```
'ipva tabela fipe' sem CPC   -> APROVADA   "Good Volume + Affordable CPC"
'ipva tabela fipe' CPC 4,20  -> DESCARTADA
```
Não medir saía estritamente melhor que medir: `float(k.get("cpc") or 0)` dava
0,00, e 0,00 passa em `cpc <= max_cpc_scale`.

**Depois**: a regra de preço exige preço. Sem CPC medido ela não dispara, e o
termo não entra por ela.

## D3 · D4 — a média e a tela

**Antes**, funil IPVA: `stats.avg_cpc = "0.26"`, calculado com dois CPCs que
nunca existiram lidos como 0. E a linha que a pessoa lia era
`ipva 2026 tabela | Vol: 0 | CPC: R$0.00 | VALOR`.

**Depois**: `avg_cpc` sai só dos CPCs MEDIDOS e viaja com `avg_cpc_estado` e
`avg_cpc_n`. A tela escreve `s/ dado`.

## E — `absent`, `unknown` e `confirmed_zero` são três estados

**Antes**, no PRIMEIRO salto do pipeline:
```
sem keywordIdeaMetrics   ->  volume 0, cpc 0.0, competition_index 0
zeros MEDIDOS pela API   ->  volume 0, cpc 0.0, competition_index 0
```
Byte a byte idênticos. E `data_reliability`, o campo que R3 do Gold Miner lia
para dizer "vol=0 confirmed", nunca foi ESCRITO por nenhum produtor do
repositório — a regra nunca distinguiu nada.

**Depois**: `gold_extractor` grava `<campo>_estado` da PRESENÇA da chave (é a
única camada que esteve na fonte), `merger` propaga com default `unknown` e
nunca `measured`, e `Sinal.de_bruto` prefere o estado declarado ao seu próprio
palpite.

## F — as duas decisões são independentes

Tema editorial `apto: true` com TODAS as keywords retidas é um estado válido e
testado (`test_F`). E `OpportunityEditorialDecision` falha o teste se qualquer
campo de economia paga (`cpc`, `spread`, `avg_cpc`, `bid`, `lance`,
`orcamento`) aparecer nele (`test_F2`) — `app.validacao` declara `spread` como
o eixo que ninguém mede porque "CPC é comprável".

## G — marca e concorrente

`bpc loas advogado x concorrente` → `HUMAN_REVIEW`, fora do conjunto. E
`negative_keywords` é `[]` em todo caminho: negativa exige search-term evidence
e revisão de overblocking, e as duas moram fora deste motor.

## H — normalização não funde intenções

**Antes**: `bpc loas` (ELEGIBILIDADE, vol 100) e `BPC LOAS ` (NAVEGACIONAL, vol
900) viravam UMA linha rotulada NAVEGACIONAL. A intenção de elegibilidade
sumia da campanha sem aparecer em `keywords_removidas`.

**Depois**: a dedup entre sub-intenções saiu. Dentro da sub-intenção ela fica —
lá os dois termos são de fato o mesmo.

## I · O · J — a impressão e o congelamento

`impressao_de_decisoes` = SHA-256 do JSON canônico de
`{policy, sorted(set((termo_normalizado, match_type, subintencao)))}`.

- muda se o termo muda (`test_I`), se o match type muda (`test_I2`), se a
  sub-intenção muda (`test_I3`);
- NÃO muda com a ordem (`test_O`) — semântica de conjunto, decidida e testada;
- `aprovar()` recusa hash divergente (`test_J2`) e, depois de aprovar,
  `acrescentar()` levanta `ConjuntoCongelado` (`test_J`);
- sem `approved_set_sha256`, `para_criterios_de_campanha` recusa converter.

## K — prior de baixa confiança não vira regra

Todo `PriorDeBenchmark` carrega `confianca` e `bloqueia`/`autoriza`. O teste
exige que nada abaixo de "alta" bloqueie ou autorize; na prática NENHUM prior,
de qualquer confiança, faz uma coisa ou outra. O único prior de confiança alta
sobre conteúdo afirma uma AUSÊNCIA: o benchmark não contém teste de desfecho no
nível de keyword.

## L — evidência pós-lançamento

`decidir_keyword` levanta `VazamentoDeDesfecho` quando uma `Evidencia`
`pos_lancamento` da MESMA campanha é oferecida a uma decisão `pre_lancamento`.
Limitação declarada: a guarda depende de `campanha_ref` estar preenchido dos
dois lados — é contrato de honestidade do chamador, não prova.

## M — desconhecido não abre o portão

Sem teto econômico declarado, `ready_for_campaign_plan` é `False` com
`teto_economico_desconhecido`. Sem congruência avaliada, `congruencia_nao_avaliada`.
E `portoes_externos_pendentes` devolve `nao_avaliado_aqui` para conta, destino
pago, mensuração e aprovação humana — declarados em vez de omitidos, porque
campo ausente se lê como "sem pendência".

---

## O CASO REAL — `pautador_keyword_clusters` id=7, opportunity_id=104

Lido SOMENTE-LEITURA do Supabase self-hosted. Tema: `bpc loas idoso inss`.
Três keywords persistidas, TODAS com `volume: 0` e `cpc: 0` literais.

**Antes**
```
lista_google_ads:
   bpc loas para idoso requisitos
   bpc loas para idoso idade
   bpc loas idoso inss
lista_clickup:
   bpc loas para idoso requisitos | Vol: 0 | CPC: R$0.00 | ELEGIBILIDADE
   bpc loas para idoso idade      | Vol: 0 | CPC: R$0.00 | ELEGIBILIDADE
   bpc loas idoso inss            | Vol: 0 | CPC: R$0.00 | INFORMACIONAL
stats: {'total_keywords': 3, 'total_volume': 0, 'avg_cpc': '0.00'}
metrics.valid_keywords: 3
```

Três keywords marcadas **válidas**, com média de CPC publicada em **0,00**,
numa lista pronta para colar no Google Ads — e nenhuma evidência medida atrás
de nenhuma delas.

**Depois**
```
selecionadas    : []
retidas         : as três, HOLD, motivo 'volume_unknown'
lista_google_ads: ''
stats           : {'total_keywords': 0, 'avg_cpc': 's/ dado',
                   'avg_cpc_estado': 'absent', 'avg_cpc_n': 0}
ready_for_campaign_plan: False
blockers        : ['teto_economico_desconhecido',
                   'nenhuma_keyword_elegivel_selecionada']
```

O caso real é o argumento mais forte da sprint, e ele não é uma fixture: é o
que estava gravado. O motor antigo entregaria três keywords sem demanda medida
para uma campanha; o novo diz que não sabe, e diz por quê.

---

## Separação semântica entre nichos

BPC/LOAS e IPVA produzem conjuntos disjuntos, com impressões diferentes e
arquétipos diferentes (`elegibilidade` vs `valor_preco`). Isso é prova de que
os dois nichos não colapsam no mesmo cluster — **não** é autorização de
lançamento para nenhum dos dois.

---

## Emenda de escopo, declarada

`test_D4` foi escrito antes de a superfície de exibição existir e afirmava
sobre `keywords_text`. Depois da correção o termo retido deixou de aparecer
ali (a lista passou a ser só de selecionados) e passou a viver em
`keywords_retidas_text`. A asserção foi ampliada para varrer TODAS as
superfícies legíveis do item e exigir que (a) o termo apareça em pelo menos
uma e (b) nenhuma o escreva como `Vol: 0` / `0.00`. A contraprova ficou mais
forte, não mais fraca: antes ela olhava um campo, agora olha três.

---

# Revisão adversarial Codex (gpt-5.6-sol, effort high) — veredito BLOCK

Onze achados, todos REPRODUZIDOS antes de qualquer correção, todos fechados,
todos travados por teste (`test_X*`). A revisão foi read-only e não editou nada.

| # | achado | entrada que reproduz | o que saía de errado |
|---|--------|----------------------|----------------------|
| 1 | o hash cobria `termo_normalizado` e a exportação lê `termo` | aprovar `advogado trabalhista`, depois `decisao.termo = "cassino online"` | `approved_set_sha256` intacto, campanha recebe `cassino online` |
| 2 | `aprovar()` não congelava a lista | `conjunto.selected_keywords.append(retida)` depois de aprovar | `congelado` seguia `True` e a exportação incluía termo não aprovado |
| 3 | `derivar_lista_google_ads` apaga match type e sub-intenção | mesmo termo em `EXACT/elegibilidade` e `PHRASE/transacional` | hashes diferentes, texto exportado idêntico |
| 4 | `montar_conjunto` descartava seleção fantasma em silêncio | `montar_conjunto([], [decisao])` | conjunto vazio com o motivo ERRADO, escondendo bug do chamador |
| 6 | o funil copiava números e descartava `<campo>_estado` | `volume_estado="failed"` na entrada do funil | volume voltava a `measured`, decisão virava `INCLUDE` |
| 7 | `Sinal.de_bruto` honrava só três estados declarados | `{"volume": 1000, "volume_estado": "failed"}` | `Sinal(1000.0, "measured")` — leitura que FALHOU entrava como medida |
| 8 | `_medido` tratava só `absent` como sem número | `{"volume": 0, "volume_estado": "unknown", "data_reliability": "HIGH"}` | descarte rotulado `(vol=0 confirmed)` — medição afirmada sobre lacuna |
| 10 | a guarda de vazamento falhava ABERTO | evidência `pos_lancamento` com `campanha_ref=None` | nenhuma exceção; a decisão pré-lançamento carregava evidência pós |
| 11 | valor negativo aceito como medido | `{"volume": -100, "cpc": -0.5}` marcados `measured` | `INCLUDE` com `viabilidade="cabe_no_teto"` — CPC negativo cabe em qualquer teto |
| 12 | marca casava por substring | `telefone panasonic assistencia` com `marcas_proprias=["pan"]` | `"pan"` dentro de `"panasonic"` desligava o bloqueio de suporte |
| 13 | léxico de suporte não cobria `ligar para` | `ligar para o inss no 135` | `INCLUDE` — um pedido de telefone entrando como keyword paga |
| 14 | `negative_keywords` era lista pública mutável | `conjunto.negative_keywords.append(...)` após aprovar | a negativa viajava serializada num conjunto "congelado" |

O achado 5 (o payload JSON é um snapshot que não acompanha mutações
posteriores do conjunto vivo) é inerente a produzir um snapshot, e a direção
perigosa dele passou a ser barrada por `conferir_congelamento`. O achado 3 foi
respondido documentando o que `lista_google_ads` é — texto plano de colagem,
não o portador da semântica aprovada, que é `para_criterios_de_campanha`.

Na afirmação 6 do pacote (priors de benchmark) o revisor não encontrou defeito:
todos têm `bloqueia=False` e `autoriza=False` e só aparecem no snapshot de
evidência, sem participar de ramo decisório nenhum.

## As duas correções mais importantes desta rodada

**O congelamento passou a ser verificado no USO, não só na escrita.**
`aprovar()` sozinho não congela nada — Python não dá congelamento profundo de
graça, `CampaignKeywordSet` é dataclass mutável e `selected_keywords` é lista.
`conferir_congelamento()` roda em toda saída e recusa entregar qualquer coisa
quando a impressão atual difere da aprovada. Foi o que transformou a promessa
em invariante.

**A guarda de vazamento passou a falhar FECHADO.** Antes ela só levantava
quando as duas `campanha_ref` batiam; evidência pós-lançamento sem campanha
declarada passava direto. Numa guarda contra vazamento, "não sei de qual
campanha isto veio" é exatamente o caso que precisa ser barrado — só a menção
EXPLÍCITA de outra campanha a libera, e isso continua testado
(`test_X10b`).

## Rodada final — o corpo HTTP alterava o conjunto já aprovado

Reprodução anterior à correção:

```text
approved_match=PHRASE
body_match=EXACT
positive_count=4
duplicate_count_for_term=2
```

O conjunto possuía três positivas, mas `/provar` e `/subir` concatenavam
`criterios_do_conjunto` com `_criterios_do_corpo`, que também aceita positivas.
O mesmo envelope ainda podia reduzir três para duas por `keywords_fora`.

As contraprovas M1–M12 cobrem a recusa de positiva adicional, troca de match
type, retirada por `keywords_fora`, negativa legítima, igualdade exata do
multiconjunto final, colapso de grupo somente quando explicitamente declarado,
as duas funções reais de rota e a ordem anterior a qualquer rede. Resultado:
**33/33 verdes** no arquivo do caminho real.
