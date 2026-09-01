# Matriz de fechamento — item a item, com evidência ou sem ela

*Worker 4 · verification · read-only sobre código*
*Medida em `HEAD 5efd756`, com trabalho ainda não commitado na árvore.*
*Base da missão: `3462b14` · baselines do lead: pytest **2319 passed / 53 skipped / 0 failed**, tsc **76 erros**.*

---

## 0. Como ler

| Estado | Significa |
|---|---|
| **PROVADO** | Existe comando + saída, ou arquivo + linha, que sustenta o item hoje |
| **PARCIAL** | Parte do item tem prova; a parte que falta está nomeada |
| **NÃO** | Sem prova, ou medido como zero, ou o caminho não existe |
| **N/A declarado** | Não se aplica, **com motivo** — nunca por omissão |

⚠️ **Esta matriz não é o gate final.** A árvore estava suja quando a medi
(8 arquivos modificados, 4 não rastreados, incluindo `volc_ads/campanha/pmax.py`
recém-criado). Números de suíte medidos sobre árvore suja não são baseline: o
integrador precisa remedi-los sobre árvore limpa na convergência. O que **não**
muda com isso são os achados estruturais, que são leitura de código.

---

## 1. Motor criativo

| Item | Estado | Evidência | Quem entregou |
|---|---|---|---|
| Asset reproduzível (bytes reais, não sintéticos) | **PROVADO** | `backend/app/criativo/bancada/adaptadores/png_local.py` — PNG real por `zlib`+`struct`, sem Pillow, sem rede, sem credencial. O commit `fbb7f3e` registra o motivo: o `MotorFalso` produzia `sha256*4` declarando `mime=image/png`, e `medir_imagem.medir()` lia `(None,None,None)` — "um asset que parece produção e não é" | Worker criativo |
| Hash / MIME / dimensões conferidos contra os bytes | **PROVADO** | `volc_ads/subir.py:468-540` `_medidas_batem`: decodifica com `medir_imagem.medir(dados)` e corrobora `bytes_totais`, MIME normalizado (`image/jpg`→`image/jpeg`, caixa, parâmetro RFC) e largura/altura. Assinatura não reconhecida ⇒ não corrobora nada | herdado (base) |
| Divergência **rebaixa**, nunca promove | **PROVADO** | `volc_ads/subir.py:543-620` `_linhagem_do_payload`, três ramos para `Linhagem.desconhecida`: sem candidata; hash declarado ≠ bytes; linhagem **sem** hash. O terceiro existe porque omitir saía mais barato que mentir | herdado (base) |
| Procedência viaja no recibo | **PROVADO** | `Preparo.linhagem` (`subir.py:238-245`) fica **fora** do `Selo` de propósito — o selo é impressão do payload, e linhagem não é payload; acrescentá-la não invalida prova feita | herdado (base) |
| Ponte chamada em ordem, a partir de um motor | **PROVADO** | `fbb7f3e`: `producao.py` (`Receita` → pedidos → lote catalogado); os papéis saem da **régua**, não de tabela | Worker criativo |
| Falha explícita (nada de lote vazio silencioso) | **PROVADO** | `fbb7f3e`: os cinco erros da porta viram cinco `Falha` com `codigo` e `permanente` | Worker criativo |
| `/criativos` com procedência na tela | **PROVADO** | 10 rotas em `src/App.tsx:136-145`; `AtivoPage.tsx:97,138,170` mostra `SeloDeProcedencia`, `hashCurto(asset.contentHash)` e `hashCurto(p.insumoHash)`; `AprovacoesPage.tsx:65-75` mostra motor, versão, licença, disclosure. `JobPage.tsx:16,50` separa `procedenciaExecucao === 'observado'` de produzido | herdado + Worker frontend |
| **Sem fixture-como-produção** | **PARCIAL** | O controle existe e é fail-closed no default: `criativo_ponte.Destino.PRODUCAO` é o padrão das assinaturas públicas (`imagens_de_display`, `imagens_de_demand_gen`), e `NATUREZAS_ACEITAS` (`criativo_ponte.py:155`) recusa `LOCAL` e `FIXTURE`. **Mas `NAO_DECLARADA` é aceita em PRODUCAO** (`:168`) — dívida **declarada** no próprio código (`:158-168`), compensada por um aviso por asset | Worker criativo |

### 1.1 Achado — a compensação da dívida não chega a ninguém

`criativo_ponte.py:165` justifica aceitar `NAO_DECLARADA` em produção assim:
*"O que ELA ganha em troca é visibilidade: cada asset sem natureza sai [com aviso]"*.

**Essa troca não é feita no caminho HTTP.** Em `backend/app/routers/trafego.py:2074-2088`
a `Entrega` é consumida **só** por `entrega.ok` (bloqueio) e `entrega.imagens`.
**`entrega.avisos` e `entrega.naturezas` nunca são lidos**, e os `avisos` que
chegam ao `Plano` (`:2091-2097`) vêm de `cockpit.avisos`, que é outra fonte.

Consequência: um asset **sem procedência declarada** entra num plano Demand Gen
sem nenhum sinal visível ao operador. O raio de dano hoje é limitado, porque
Demand Gen não pode mutar — mas o mesmo descarte se aplicará a Display, que
**pode** criar, assim que o elo de imagem for ligado.

**Classificação: bloqueador de "sem fixture-como-produção", não dívida cosmética.**
Custo de correção: propagar `entrega.avisos` para `Plano.avisos`.

---

## 2. Search

| Item | Estado | Evidência | Quem entregou |
|---|---|---|---|
| Fluxo verde ponta a ponta | **PROVADO** | Canário criado por `POST /api/trafego/subir`, HTTP 200, executor ACEITO, 34 operações consumidas (`RECIBO-CANARIO-V10-24195821946.json`) | sprint anterior |
| Canário `24195821946` pausado | **PROVADO — e reverificado ao vivo pelo lead** | `campaign_status=PAUSED`, `SEARCH`, `MANUAL_CPC`, budget 10.000.000 micros; `primary=PAUSED razoes=['CAMPAIGN_PAUSED','MOST_ADS_UNDER_REVIEW']`. `campanhas_com_a_marca: 1`, conta 6→7, delta 1 | sprint anterior + lead |
| Canário **no H0** | **NÃO** | `RECIBO…json` → `pendencias_medidas.espelho_h0: 0`. Causa nomeada: "o coletor contínuo lê apenas ENABLED e uma campanha PAUSED some da observabilidade (P09-T14)". É o **aceite 6 de P05-T11**, medido como zero | ninguém — segue aberto |
| Meta efetiva lida | **NÃO** | `prontidao.py:125-165` lê `conversion_action`; **não** lê `customer_conversion_goal`, `campaign_conversion_goal` nem `conversion_goal_campaign_config.goal_config_level`. O próprio módulo declara isso em `:128-138`. Status sai `PARCIAL` com bloqueador nomeado — **não afirma prontidão falsa** | ninguém — é P05-T12 item 3 |
| Divergência de meta **aparece** no contrato | **PROVADO** | `contrato_canais.contrato_dos_canais()` devolve, no portão `ativavel` de SEARCH, os bloqueadores `meta_efetiva_divergente` e `meta_efetiva_nao_lida` — o achado DOWNLOAD/APP × oito PURCHASE virou código | Worker API/UI |
| Bloqueio de Smart Bidding | **PARCIAL** | `MANUAL_CPC` na conta é escolha registrada, e `prontidao.smart_bidding_eligible` é fail-closed. **Mas ver §2.1** | herdado |

### 2.1 Achado — o portão de Smart Bidding é hoje uma constante, não uma computação

Em `backend/app/trafego/prontidao.py` **não existe nenhum ramo que atribua
`meta_status = PRONTO`**. Os únicos valores atribuídos são `INDETERMINADO`
(`:121`), `PARCIAL` (`:137`) e `NAO_PRONTO` (`:151`). Logo:

- `medicao == PRONTO` (`:203`) é **inalcançável**;
- `elegivel = medicao == PRONTO and observacao == PRONTO` (`:224`) é **sempre `False`**;
- o ramo `medicao = INDETERMINADO` que depende de `sinal == INDETERMINADO`
  (`:205`) é **código morto**, porque `sinal` só recebe `PRONTO` ou `NAO_PRONTO`
  (`:174-181`).

**Isso está CERTO para hoje** — a meta efetiva não é lida, então declarar
`PRONTO` seria mentir, e o módulo é honestamente fail-closed.

**O que é achado:** enquanto o ramo `PRONTO` for inalcançável,
`smart_bidding_eligible=False` é **infalsificável**. Qualquer teste que afirme
"Smart Bidding está bloqueado" **passa com qualquer entrada**, inclusive com uma
conta perfeitamente medida — o anti-padrão *"teste que passa com qualquer
entrada"* que esta missão manda caçar. Quem fechar o item 3 de P05-T12 tem de
acrescentar o ramo `PRONTO` **e** um teste que prove o portão **virando**.

### 2.2 Achado menor — colapsos de estado dentro de `prontidao.py`

O mesmo módulo cujo docstring (`:104-108`) separa com cuidado "não li" de "não há"
para `metas_da_conta` **colapsa os dois** em outros dois pontos:

- `:163` `fontes = list(fontes_de_sinal_observadas or ())` — `None` ("não li") e
  `[]` ("li e está vazio") caem os dois em `NAO_PRONTO`;
- `:125` `metas_da_conta.get("primaria")` ausente cai no `else` "a conta não tem
  ação de conversão primária" (`:150`), **ignorando** `acoes[]` que pode estar
  cheio — ausência de chave virando zero medido;
- `:145` `f"{len(primarias) or 1} ação(ões)"` imprime **1** quando a contagem é
  **0**, podendo contradizer `conversion_actions_primarias: []` no mesmo objeto.

A direção dos dois primeiros é a segura (ambos bloqueiam), então **não há risco
operacional hoje**. Mas o `DEFINITION-OF-DONE.md` §1 trata colapso de estados
como reprovação de gate, sem cláusula de colapso benigno. **Dívida real, barata.**

---

## 3. Display

| Item | Estado | Evidência | Quem entregou |
|---|---|---|---|
| Brief de Display | **PROVADO** | `volc_ads/campanha/display.py`, construtor completo | herdado |
| Plano com budget / segmentação / anúncios / assets | **PROVADO** | `display.py:203-204` emite `comum.op_geo` e `comum.op_idioma`; cadeia budget → campanha → geo → idioma → ad group → RDA (`display.py:6,18`) | herdado |
| **Imagens chegam ao builder pelo HTTP** | **NÃO** | `backend/app/routers/trafego.py:2086` passa `imagens_display=None` **literal**, e `ProvarEntrada` (`:1311-1400`) **não tem campo de imagem**. É o F031 do `fable-global-v1`, ainda verdadeiro **para Display** | em curso (Workers 1/2/3) |
| v25 serializável offline | **PARCIAL** | Verificado por mim nos protos instalados: `Campaign.contains_eu_political_advertising`, `ai_max_setting`, `demand_gen_campaign_settings` **existem**. Não há para Display o equivalente ao `sondar_proto_v25()` que Demand Gen tem | herdado |
| `validate_only` real | **NÃO** | Nunca executado contra a conta. É a **única** lacuna que o Roadmap reconhece separar P04-T04 de `done`: *"FALTA a prova contra a conta real, que exige autorização"* | ninguém — exige autorização |
| Zero mutate | **PROVADO** | Ver §7.1: as três superfícies de mutação estão todas atrás de trava de dois fatores | — |

⚠️ **Não aceitar como prova**: Gemini afirmou que o payload de Display está
"100% completo e suficiente para passar pelo `validate_only` em produção real".
**Descartado** — é afirmação sem execução, com a forma de prova. Ver
`REVISAO-GEMINI-CONTRATOS.md` §1.2.

---

## 4. Demand Gen

| Aceite literal (P04-T09) | Estado | Evidência |
|---|---|---|
| 1. Relabelado como Search é recusado antes de trava, recibo e cliente | **PROVADO (antes desta missão)** | `volc_ads/subir.py:869-873`: `_exigir_selo` roda **antes** de `_recusar_canal_sem_mutacao`, que roda antes de `_exigir_motivo` e `_recusar_trava_ambiente`. O canal vem de `campaign_operation.create` via `_autoridade_das_operacoes`, **nunca do rótulo**. Roadmap: pago em `e0f05a1` |
| 2. Troca de canal / `login_customer_id` / hash / tipo invalida o selo | **PROVADO — os quatro eixos** | `subir.py:986-1044`: `customer_id` (`:977`), `login_customer_id` (`:984`), `canal` (`:991`), `n_operacoes` (`:1000`), `atual.canal` vs `selo.canal` (`:1014`), `tipos_operacoes` (`:1021`), `hashes_operacoes` (`:1028`), `impressao` (`:1038`). Era um dos três pendentes |
| 3. Asset remoto sem recibo tipado falha fechado | **PARCIAL** | `demand_gen.py:640-670` distingue `conteudo:{hash}` de `novo-sem-recibo:{nome}` e `remoto-sem-recibo:{canonico}`, e `:663` recusa "asset remoto em `str` [que] não carrega recibo tipado". Falta amarrar isso a uma contraprova executada nesta missão |
| 4. Objetos v25 instanciados e serializados **offline sem rede** | **PROVADO** | `demand_gen.sondar_proto_v25()` (`:94-292`) instancia e serializa os namespaces v25 e as folhas (`DemandGenMultiAssetAdInfo`, `AdImageAsset`, `AdTextAsset`); `construir()` (`:297`) **recusa** quando indisponível, com "capacidade Demand Gen rebaixada sem fallback". Exercitado em `volc_ads/campanha/testes_demand_gen.py:374`. **Medido por mim: 31 passed em 4,85s** |
| 5. Rota produtiva permanece recusada; estado máximo `partial` | **PROVADO, e é estrutural** | `perfil.py:122` — `permite_mutacao_real` tem **default `False`**; só SEARCH (`:213`) e DISPLAY (`:236`) o ligam. `subir.py:122` lista Demand Gen **fora** de `CONSTRUTORES_POR_CANAL` e **dentro** de `PROVADORES_POR_CANAL` (`:127`), e `:133-148` derruba o import se as duas vistas divergirem do perfil |

| Item extra da Definição de Pronto | Estado | Evidência |
|---|---|---|
| Selo carrega canal / MCC / operações / assets | **PROVADO** | `Selo` (`subir.py:170-190`): `customer_id`, `login_customer_id`, `canal`, `tipos_operacoes`, `hashes_operacoes`, `impressao`, `n_operacoes`, `carimbo` |
| `validate_only` de Demand Gen | **PARCIAL** | Porta existe (`PROVADORES_POR_CANAL`), mas nasce **desligada no servidor**: bloqueador `demand_gen_experimental_desligado` no portão `validavel` |
| Zero mutate | **PROVADO** | Ver aceite 5 |

> **Teto declarado:** o aceite 5 diz literalmente *"o estado máximo é partial"*.
> **P04-T09 não pode ir a `done` nesta missão** — promovê-la violaria o critério
> ao tentar cumpri-lo.

---

## 5. Performance Max

| Item | Estado | Evidência | Quem entregou |
|---|---|---|---|
| Observabilidade PMax existe | **PROVADO — mas é anterior à missão** | `volc_ads/observabilidade_pmax/` (2.580 linhas: `types`, `coverage`, `kernel`, `projector`, `queries`) + `docs/architecture/HANDOFF-PMAX-OBSERVABILITY-V25.md` | **anterior à missão — não creditar a ela** |
| Observabilidade **integrada** | **NÃO** | `grep -rn "observabilidade_pmax"` → o único importador é `backend/tests/test_observabilidade_pmax.py`. **Zero consumidores de produção**: sem router, sem coletor agendado, sem painel. Degrau 6 da escada do DoD ("funcionalidade integrada") não alcançado | ninguém |
| Painel no cockpit | **NÃO** | Nenhuma tela consome o módulo. O Roadmap (P04-T07) já dizia "não existe coleta PMax nem painel VOLC específico", e isso **continua verdadeiro** para o painel | ninguém |
| Contrato próprio de PMax | **EM CURSO** | `volc_ads/campanha/pmax.py` apareceu não rastreado em `5efd756`; não avaliado aqui | Worker canais |
| Decisão registrada de manter PMax fora do executor | **PROVADO** | `5bc9e82` + `DECISAO-PMAX-FORA-DO-EXECUTOR.md`: habilitar o construtor derrubaria a rota HTTP dos quatro canais, porque `subir.py` levanta no import quando a vista discorda do perfil | lead |
| Zero mutate | **PROVADO** | PMax não está em `CONSTRUTORES_POR_CANAL` nem em `PROVADORES_POR_CANAL`; `permite_mutacao_real` default `False` |
| **Mensuração inadequada bloqueia criação** | **NÃO** | **Ver §5.1 — é o achado que o lead pediu que eu fiscalizasse, e ele se confirma** |

### 5.1 Achado — PMax está bloqueado por motivo empilhado, e o motivo que a tarefa pede não está no portão certo

Rodei `contrato_canais.contrato_dos_canais()` com `papel="dono"` e
`escrita_permitida=True` (privilégio máximo, para isolar o que resta):

```
PERFORMANCE_MAX
  planejavel         BLOQUEADO  ['sem_campos_de_pedido']
  validavel          BLOQUEADO  ['sem_porta_de_prova']
  criavel_pausada    BLOQUEADO  ['sem_construtor']
  ativavel           BLOQUEADO  ['ativacao_fora_de_escopo', 'politica_nao_inclui_ativacao',
                                 'mensuracao_nao_lida', 'observabilidade_nao_provada']
```

Os três primeiros portões têm **a mesma causa literal** ("não há construtor de
campanha para Performance Max"), com `origem='construtor'`.

O título de **P04-T07 é "Definir observabilidade PMax ANTES de autorizar
criação"** — logo o portão que a tarefa governa é **`criavel_pausada`**. E o
único bloqueador de `criavel_pausada` é `sem_construtor`.

Mensuração e observabilidade só aparecem em **`ativavel`** — e não só para PMax:
`SEARCH`, `DISPLAY` e `DEMAND_GEN` também têm `criavel_pausada` **sem** nenhum
bloqueador de mensuração. Isso é decisão de produto coerente e defensável
(o canário pausado atravessa G0 sozinho; `prontidao.py:18-21` diz exatamente
isso), **mas para PMax ela não satisfaz o critério literal da tarefa.**

**Consequência concreta:** no dia em que `volc_ads/campanha/pmax.py` virar um
construtor registrado, `sem_construtor` desaparece dos três portões e
`criavel_pausada` fica **sem nenhum bloqueador de observabilidade**. Pior: PMax
hoje nem recebe `fora_da_janela_do_canario`, o bloqueador de política que Display
recebe — porque a avaliação já parou em `sem_construtor`.

**Correção pedida:** um bloqueador próprio no `criavel_pausada` de PMax, derivado
de observabilidade, que **se sustente sozinho** quando `sem_construtor` sair.
Enquanto não existir, P04-T07 **não pode passar de `todo`** para além de
`partial`, e nunca para `done`.

### 5.2 Verificado por mim contra os protos v25 (para quem escrever o builder)

| Objeto | Campos reais na v25 instalada |
|---|---|
| `AssetGroup` | `ad_strength`, `asset_coverage`, `campaign`, `final_mobile_urls`, `final_urls`, `google_local_services_info`, `id`, `name`, `path1`, `path2`, `primary_status`, `primary_status_reasons`, `resource_name`, `status` |
| `AssetGroupSignal` | `approval_status`, `asset_group`, `audience`, `disapproval_reasons`, `local_services_id`, `resource_name`, `search_theme`, `vertical_ads_item_group_rule_list` |
| `AssetGroupAsset` | `asset`, `asset_group`, `field_type`, `policy_summary`, `primary_status`, `primary_status_details`, `primary_status_reasons`, `resource_name`, `source`, `status` |

- **`Campaign.url_expansion_opt_out` NÃO EXISTE.** Gemini o apresentou como
  exigência de PMax; é alucinação, e o repositório já a tinha documentado como
  campo inexistente. Usá-lo derruba a query GAQL inteira.
- **`SEARCH_THEME` não é um `AssetFieldType`.** `search_theme` é campo de
  `AssetGroupSignal`. Confundir os eixos produz query inválida.
- Limites de asset do repositório (`docs/growth-engine/matriz-api/performance-max.md:87-119`)
  conferem com a doutrina oficial; e `:73`/`:134` registram que com
  `brand_guidelines_enabled` (**default desde a v21**) `BUSINESS_NAME` e `LOGO`
  vão para **`CampaignAsset`**, não `AssetGroupAsset` — bifurcação que Gemini
  **errou**.
- Estratégias de lance em PMax: só `MAXIMIZE_CONVERSIONS` e
  `MAXIMIZE_CONVERSION_VALUE`; **portfólio é proibido** (`:161-166`).
- PMax não-retail: `AssetGroup` + todos os `AssetGroupAsset` mínimos **no mesmo
  bulk mutate** (`:33-53`).

### 5.3 As queries GAQL de PMax não têm campo morto — conferido, não opinado

A revisão externa desta pergunta **não foi obtida** (a lane Gemini estourou duas
vezes; registrado em `REVISAO-GEMINI-CONTRATOS.md` §3.1). No lugar dela fiz a
conferência determinística, que é evidência mais forte:

extraí toda referência `recurso.campo` de `volc_ads/observabilidade_pmax/queries.py`
e resolvi cada uma contra o `DESCRIPTOR` protobuf da v25 instalada, descendo em
campos aninhados, sobre `campaign`, `asset_group`, `asset_group_asset`,
`asset_group_signal`, `asset` e `campaign_asset`.

**61 campos válidos, ZERO inexistentes.** Os dois suspeitos da primeira passada
eram defeito do meu extrator: `asset_group.path` é o meu regex truncando
`path1`/`path2` (`queries.py:285-286`), e `asset.type` (`:377`) é o nome de wire
correto em GAQL — no proto Python o campo é `type_`, porque `type` é reservado.

Importa porque uma query com campo inexistente falha **inteira**
(`UNRECOGNIZED_FIELD`) e não degrada: era o risco mais caro do módulo, e não se
materializa. **Não promove P04-T07** — contrato correto e desligado continua
desligado.

---

## 6. Frontend

| Item | Estado | Evidência | Quem entregou |
|---|---|---|---|
| Quatro canais | **PROVADO** | `contrato_dos_canais()` devolve SEARCH, DISPLAY, DEMAND_GEN, PERFORMANCE_MAX; `src/components/trafego/canal/jornada.ts:543-586` tem **seis** jornadas (as quatro + SHOPPING + VIDEO) | Worker API/UI |
| Quatro portões | **PROVADO** | `planejavel`, `validavel`, `criavel_pausada`, `ativavel` — com `estado`, `bloqueadores[]`, e **`origem`** por bloqueador (`operador`, `politica`, `produto`, `manifesto`, `servidor`, `construtor`), que é o que diz ao operador **a quem pedir** | Worker API/UI |
| `/criativos` com procedência | **PROVADO** | §1 desta matriz | herdado + Worker frontend |
| **Nenhum verde sem evidência** | **PROVADO** | Com nada lido, `mensuracao.lida=False` e todos os status saem `INDETERMINADO`, com causa literal ("ninguém contou quantas campanhas deste canal foram lidas de volta nesta sessão"). `observado_em=None` e `revalidacao=None` marcam o não lido. Nenhum portão sai `PERMITIDO` por ausência de bloqueador conhecido | Worker API/UI |
| Quinto estado (`não aplicável`) preservado | **PROVADO** | PMax: `Assets(estado='NAO_APLICAVEL', recursos=(), causa='Performance Max não tem construtor de campanha, então não há pedido para carregar assets.')` — distinto de ausência e de vazio | Worker API/UI |
| Sem leitura viva do Google na rota | **PROVADO** | `17ce44d`: "Nenhuma leitura viva do Google: a rota desenha um cockpit e gastaria quota da conta a cada navegação" |
| Sobe local (`./start-dev.sh`) | **NÃO VERIFICADO POR MIM** | Não executei; é gate do integrador | — |

Dois colapsos que `17ce44d` evitou explicitamente, e que confirmo pela saída:
`sem_construtor` **deixou de** cobrir Demand Gen (que tem construtor e é recusado
pelo **executor** — o bloqueador dele é `mutacao_real_recusada`, `origem='manifesto'`);
e a causa de cada portão deixou de ser `indisponibilidades[0]`.

---

## 7. Engenharia

| Item | Estado | Evidência |
|---|---|---|
| Commits atômicos | **PROVADO** | 6 commits em `3462b14..5efd756`, cada um com escopo próprio e mensagem que declara a decisão. Contrato antes do código em dois casos (`52c3345`, `99b4b51`) |
| Ownership respeitado | **PROVADO até aqui** | Não escrevi fora de `docs/closure/traffic-creative-operational-closure-v1/verificacao/`. Nenhum worker tocou `ROADMAP-VIVO.json`, `docs/volc-os-graph/**` ou `graphify-out/**` |
| Sem credencial no diff | **PROVADO** | `git diff 3462b14..HEAD` grep por `SUPABASE_SERVICE_ROLE|api key|secret|BEGIN RSA/OPENSSH|eyJ…|FORGE_PERMITIR_ESCRITA=1` → **2 ocorrências, ambas benignas**: uma é um teste que asserta que esses nomes são **proibidos**; a outra é a string da mensagem de erro da trava |
| `git diff --check` limpo | **PROVADO** | exit 0 |
| Árvore limpa | **NÃO (durante a missão)** | Medições feitas com trabalho em curso na árvore. Não é defeito; **mas o gate final é do integrador, sobre árvore limpa** |
| TS sem erro novo | **PROVADO** | `npx tsc --noEmit -p tsconfig.app.json` em `96fea91` → **76 erros**, exatamente o baseline. Zero erro novo |
| Suíte Python | **PROVADO** | `backend/.venv/bin/python -m pytest backend/tests volc_ads -q -p no:randomly` em `96fea91` → **2445 passed, 45 skipped, 0 failed** (75,08s). Baseline: 2319/53/0. **+126 testes, zero falhas** |
| Build verde | **NÃO VERIFICADO POR MIM** | gate do integrador |
| Mapa Vivo `--check` | **N/A declarado** | `UPDATE_STATUS.json` não existe nesta worktree (arquivo gerado, não versionado). `current:false, reason:"UPDATE_STATUS.json ausente"` é **estado inicial esperado**, não regressão — o lead reconstrói na convergência |

### 7.0 Um vermelho transitório, registrado para não virar lenda

Numa medição intermediária em `5efd756`, com a árvore no meio de uma edição, a
suíte devolveu **3 failed, 2413 passed**:
`test_canario_pedido_aprovado.py::test_4_identidade_do_pedido_bate_com_o_dossie`,
`::test_6b_carimbo_de_outra_execucao_invalida_o_selo` e
`test_criativo_bancada.py::test_a_maquina_declara_quais_motores_consegue_rodar`.

Os três **passavam isoladamente** na mesma árvore — reprodução:
`pytest <os dois primeiros> -q -p no:randomly` → `2 passed`. Ou seja, era estado
intermediário de arquivo, não defeito de produto. Em `96fea91` a suíte inteira
voltou a **0 failed**.

Registro porque um vermelho visto uma vez e não explicado vira dúvida
permanente — e porque os dois primeiros tocam a **identidade do canário**, que é
exatamente onde um vermelho não explicado seria grave.

### 7.1 Superfície de mutação — enumeração completa, e um erro meu corrigido

Minha primeira varredura usou `grep "\.mutate(\|mutate_campaigns"`. **No `grep` do
macOS, `\|` em BRE é um pipe literal, não alternância** — a busca não achou nada e
eu quase registrei "existe um único caminho de mutação". Refeita com `grep -E`, e
com o Gemini apontando independentemente o caminho #3:

| # | Local | `validate_only` | Guarda |
|---|---|---|---|
| 1 | `volc_ads/gads/client.py:170` | `True` (`:166`, fixo) | Nenhuma necessária — a API valida e descarta |
| 2 | `volc_ads/gads/client.py:201` | `False` (`:197`) | `modo.exigir_leitura_apenas()` na **primeira linha** de `mutar()` (`:191`), antes de o cliente ser construído |
| 3 | `backend/app/routers/trafego.py:3714` `svc.mutate_campaigns` | n/a (`CampaignService`) | `with modo.destravar(body.motivo)` (`:3713`); recusa `ENABLED` sem `remover_ativa: true` (`:3703`) |

`modo.destravar` (`gads/modo.py:49-69`) exige **motivo ≥10 chars E
`FORGE_PERMITIR_ESCRITA=1`** — dois fatores de verdade, verificado no código.
O caminho #3 é a **rota de remoção**, que é o rollback autorizado do canário
("reversão autorizada futuramente é `status REMOVED`").

**Residual declarado, não bloqueador:** `_destravado_no_codigo` é **global de
processo** (o próprio `trafego.py:3469` registra isso), e `/subir` roda em
`asyncio.to_thread`. `subir()` se protege com `_recusar_trava_ambiente()`
(`:975`), que recusa quando a trava já está aberta — falha na direção segura. A
rota de remoção **não** tem essa guarda, então uma remoção concorrente a um
`/subir` executaria sob a trava aberta pelo outro. Requer duas operações
autorizadas simultâneas; risco baixo, mas é o único ponto onde a trava não é
por-operação.

---

## 8. Veredito por bloco

| Bloco | Veredito |
|---|---|
| Motor criativo | **PARCIAL** — motor, bytes, linhagem e recusa provados; a visibilidade que justifica aceitar `NAO_DECLARADA` não chega ao HTTP |
| Search | **PARCIAL** — canário provado e reverificado ao vivo; H0 zero e meta efetiva não lida seguem abertos, ambos honestamente declarados |
| Display | **PARCIAL** — construtor e plano completos; imagem não atravessa o HTTP, `validate_only` real nunca executado |
| Demand Gen | **PARCIAL por teto próprio** — aceites 1, 2, 4 e 5 provados; 3 parcial. Não pode ir a `done` |
| PMax | **NÃO** — observabilidade existe e não está integrada; o bloqueio de criação não é o de mensuração |
| Frontend | **PROVADO** — quatro canais, quatro portões, origem por bloqueador, ausência renderizada, quinto estado preservado |
| Engenharia | **PARCIAL** — higiene e ownership provados; gates finais a remedir sobre árvore limpa |

### Bloqueadores REAIS

1. **PMax: mensuração não bloqueia criação** (§5.1) — contradiz o critério
   literal de P04-T07, e some sozinho quando o builder existir.
2. **Display não recebe imagem pelo HTTP** (§3) — `imagens_display=None` literal;
   critério literal de Display.
3. **`entrega.avisos` descartado pelo router** (§1.1) — a compensação da dívida
   de `NAO_DECLARADA` não existe na prática.
4. **Aceite 6 de P05-T11 medido como zero** (§2) — `espelho_h0: 0`.
5. **Meta efetiva não lida** (§2) — P05-T12 item 3, causa declarada do `partial`.

### Dívida cosmética (não bloqueia)

- `prontidao.py:145` `len(primarias) or 1` imprimindo 1 para 0.
- `prontidao.py:163` e `:125` colapsando "não li" em "vazio" (direção segura).
- `prontidao.py:205` ramo `sinal == INDETERMINADO` morto.
- `volc_ads/entrega.py:263-267` — `try/except` devolvendo `[]`, ausência lida
  como zero num caminho de **alerta**. **Pré-existente e fora do ownership desta
  missão**; registrado para o Roadmap, não para este diff.
