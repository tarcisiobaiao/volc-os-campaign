# O engine multicanal — como um segundo canal entra sem espalhar `if`

Estado: **Search e Display criam. Demand Gen e Performance Max só são inventariados.**
Última mudança: 26/08/2026 (primeira fatia vertical de Display).

---

## 1. O problema que este desenho resolve

Com **um** canal, tudo o que era "de Search" podia ficar implícito e nada quebrava:
`ai_max` era parâmetro de `preparar()` porque Search tem `ai_max`; a autocorreção de
política podava keyword porque Search tem keyword; o nome da campanha não marcava
canal porque só havia um canal para marcar. Nada disso estava errado — estava **não
declarado**.

Com **dois**, cada implícito vira um `if canal == …` em algum lugar. E `if` espalhado
é o desenho que obriga a varrer o produto inteiro quando o terceiro canal chegar.

A regra da missão é o contrário: *não criar condicionais espalhados; cada canal
possui manifesto/capability profile*.

---

## 2. A decisão de arquitetura: qual é a fonte única do perfil de canal

Havia duas declarações antes desta entrega, e a tentação era criar uma terceira.

| onde | o quê | público |
|---|---|---|
| `volc_ads/subir.py:CONSTRUTORES_POR_CANAL` | quem sabe criar | o engine |
| `backend/app/trafego/plataforma.py:ManifestoDeCanal` | o que a tela mostra | o Hub |

### A decisão

> **O engine declara. O Hub projeta. A coerência é provada, não combinada.**
>
> 1. Cada FATO de um canal é declarado **uma vez, no módulo do canal**
>    (`campanha/search.py`, `campanha/display.py`): `CANAL`, `LANCES_PERMITIDOS`,
>    `OPCOES`, `construir`, `validar`.
> 2. `volc_ads/campanha/perfil.py` é o **índice** — ele **referencia** esses objetos,
>    nunca os copia. `PERFIS["DISPLAY"].lances_permitidos is display.LANCES_PERMITIDOS`
>    é asserção de teste, com `is` e não `==`: cópia é o que diverge no primeiro ajuste.
> 3. `subir.CONSTRUTORES_POR_CANAL` continua existindo como **vista literal**, com uma
>    guarda que derruba o import se ela discordar do perfil.
> 4. `plataforma.ManifestoDeCanal` continua sendo a verdade dita para a **tela**, em
>    outro vocabulário, e é comparada com o engine por **dois testes de árvore
>    sintática**.

### Por que o backend não importa `perfil.py`

Seria o desenho mais direto — e está errado por dois motivos concretos:

* `perfil.py` referencia os construtores, que importam `google.ads.googleads`. O Hub
  **não** depende do SDK do Google em tempo de import hoje, e passar a depender
  significaria que o backend deixa de subir numa máquina sem a credencial.
* `backend/tests/test_trafego_plataforma.py:test_o_manifesto_nao_importa_o_engine`
  já proíbe isso, e a proibição é boa: o manifesto **descreve** o engine, e descrever
  não é depender.

Por isso a ligação é por **leitura de árvore sintática**, que não importa nada:

| prova | lê | compara com |
|---|---|---|
| `test_so_search_sabe_criar_e_isso_bate_com_o_engine` | `volc_ads/subir.py` (AST) | manifestos com `sabe_criar` |
| `test_o_manifesto_do_hub_bate_com_o_perfil_do_engine` | `volc_ads/campanha/perfil.py` (AST) | manifestos com `sabe_criar` |

As duas direções derrubam: manifesto que sobra faz a tela oferecer o que não existe;
manifesto que falta esconde capacidade real.

### Por que a vista literal em `subir.py` não é uma terceira verdade

Ela lista **nomes de canal**, não fatos, e não pode divergir em silêncio:

```python
CONSTRUTORES_POR_CANAL = {
    "SEARCH": perfil.SEARCH.construtor,
    "DISPLAY": perfil.DISPLAY.construtor,
}
if set(CONSTRUTORES_POR_CANAL) != set(perfil.canais_que_criam()):
    raise RuntimeError(...)     # o import falha, não a tela
```

O literal existe porque é ele que o teste do Hub lê por AST. A guarda o torna
derivado na prática: esquecer um canal aqui é um erro na hora do import, não um
sintoma na tela três dias depois.

---

## 3. O que o perfil declara

`volc_ads/campanha/perfil.py:PerfilDeCanal` — os campos que a missão pediu:

| campo | Search | Display |
|---|---|---|
| `hierarquia` | campaign → ad_group → responsive_search_ad → keyword → campaign_asset | campaign → ad_group → responsive_display_ad → ad_asset |
| `campos_operados` | keywords, sub_intenções, negativas, match type, copy completa | copy, título longo, nome do negócio, imagens por papel, vídeos |
| `construtor` / `validador` | `search.construir` / `search.validar` | `display.construir` / `display.validar` |
| `coletor` | varredura do Hub (`app/trafego/sincronizador.py`) | a mesma |
| `recursos_criativos` | texto, sitelink, callout, snippet | texto, imagem 1.91:1, imagem 1:1, logo, logo quadrado, vídeo |
| `lances_permitidos` | `MANUAL_CPC`, `MAXIMIZE_CONVERSIONS` | `MAXIMIZE_CONVERSIONS` |
| `opcoes` | `{ai_max}` | `{}` |
| `provas_obrigatorias` | política, duplicidade, selo | as mesmas |
| `acoes_permitidas` | montar, provar, subir | as mesmas |
| `acoes_indisponiveis` | — | quatro, ver §6 |

`__post_init__` recusa a construção de um perfil incoerente: canal que declara
construtor e não declara validador, lance permitido ou prova obrigatória não existe.

### Os dois `if canal ==` que o perfil comeu

1. **`ai_max`.** `preparar()` chamava `construir(..., ai_max=ai_max)` direto. Agora
   chama `perfil.montar(canal, ...)`, que filtra as opções pelo que o canal declara —
   e **recusa** a opção ligada num canal que não a tem, em vez de ignorar. Marcar uma
   caixa que não faz nada é pior que não poder marcá-la.
2. **Autocorreção de política.** Ela poda `brief.keywords`. Em Display a remontagem
   devolveria um payload idêntico e o diário registraria uma decisão sem efeito — pior
   que não autocorrigir, porque *afirma* ter feito algo. `perfil.autocorrige_keywords`
   decide.

---

## 4. A extração: o que saiu de `search.py`

`campanha/conteudo.py` é uma **extração**, não um módulo novo. Cada função saiu de
`search.py`, onde estava privada e portanto invisível para o segundo canal:

`LIM` · `SEVERIDADE_BARRA` · `SO_AVISO` · `CAMPO_POLITICA` · `chave()` ·
`nome_da_campanha()` · `forma()` · `politica()` · `registrar()` ·
`avisar_cobertura()` · `abrir_portao()`

Duas coisas **não** saíram, de propósito: `_checar_snippet_header` e `_vincular`.
Snippet e asset de campanha são recursos do Search hoje, e "shared" não é depósito de
utilitário sem dono — eles sobem quando existir o segundo consumidor real.

### A fachada que ficou em `search.py`

`copy/contrato._barra_o_lancamento` importa `_SEVERIDADE_BARRA` e `_SO_AVISO` **de
`campanha.search`**, e `copy/testes_juiz_semantico` prova por `inspect.getsource` que
ele os importa de lá — é assim que o portão do lançamento e o do runner usam um
critério só. `search.py` reexporta os dois de `conteudo.py`. **Condição de
aposentadoria:** somem no dia em que `volc_ads/copy/` (outro dono) importar de
`campanha.conteudo` diretamente.

### O `marcador` de canal no nome da campanha

`nome_da_campanha(brief, ts, *, marcador="")`. Search passa `""` — ele nasceu sem
marcador e mudar o nome do que já subiu quebraria o `taxonomia.analisar()` sem
consertar nada. Display passa `"Display"`, e o nome sai
`BR - 20260826_175002 / Saque Anual / https://… [Display]`.

Quem escolhe o marcador é o perfil, não um `if` dentro da função.

---

## 5. Faixas de id temporário — Display não abriu família nova

`comum.py` reserva: budget `-1`, campanha `-2`, ad groups `-3..-92`, vão vazio
`-93..-99`, assets `-100` para baixo.

Display usa `-1`, `-2` e `-3`. **A faixa de asset fica intocada**, porque Display não
cria asset: imagens e vídeos chegam como resource name de Asset **já criado**, vindo
do motor de criativo. Duas provas guardam isso:

* `test_display_nao_toca_na_faixa_de_asset_reservada_para_search` — nenhum
  `/assets/-N` aparece no payload;
* `_checar_resource_name()` **recusa id negativo** com mensagem explicando que ele
  invadiria a faixa de Search. É a colisão que não avisa, barrada onde é barata.

---

## 6. O que a primeira fatia de Display monta — e o que ela declara não montar

**Monta:** budget → campanha (`DISPLAY`, `PAUSED`, `maximize_conversions`, rede de
conteúdo só) → geo → idioma → ad group (`DISPLAY_STANDARD`) → responsive display ad
com títulos, título longo, descrições, nome do negócio, imagens por papel e vídeos do
YouTube.

**Recusa o que Search permite:** `MANUAL_CPC`, `ai_max` e DKI — as três com mensagem
que diz o que fazer.

**Declara não montar** (`perfil.DISPLAY.acoes_indisponiveis` e
`plataforma.DISPLAY.indisponibilidades`):

1. segmentação positiva (topic, listas, demografia) — confirmada `[alta]` na matriz,
   entra na próxima fatia;
2. **segmentação positiva por placement** — ver §7;
3. extensões de campanha (sitelink, callout, snippet);
4. lance manual.

### A regra que governa o que é emitido

> **Campo marcado `[NÃO CONFIRMADO]` na matriz do Agente A não é emitido, e nenhum
> limite dela é reafirmado por conta própria.**

Consequências concretas nesta fatia:

* `_checar_imagens()` conta e confere resource name, e **não afirma nada sobre bytes
  ou pixels** — peso de arquivo e dimensão recomendada estão `[NÃO CONFIRMADO]`
  (a doc remete ao Help Center). Reaproveitar os 5120 KB de PMax seria importar um
  limite de outro canal.
* `_checar_videos()` só conta (teto 5). Duração, proporção e resolução são de PMax.
* **`TARGET_CPA` avulso saiu.** `comum.op_campanha()` emitia
  `campaign.target_cpa` quando havia `tcpa`; a matriz §8 mostra que `TARGET_CPA` não
  aparece em lista nenhuma da tabela oficial de estratégias para Display —
  `MAXIMIZE_CONVERSIONS` é a única `[alta]`. O tCPA passou a viajar **dentro** do
  MaxConv (`maximize_conversions.target_cpa_micros`), que é como Search já o expressa.
* `call_to_action_text`, `main_color`/`accent_color`, `format_setting`,
  `allow_flexible_color`, `price_prefix`, `promo_text` e `control_spec` não são
  emitidos. Os defaults do proto são os corretos e afirmar um valor sem necessidade
  é assumir risco sem ganho.

---

## 7. Placement positivo: por que ficou de fora

Duas fontes **oficiais** se contradizem (matriz §7):

* a tabela de critérios marca Placement como positivo ❌ / negativo ✅ — conferido no
  HTML da tabela, não só no texto extraído;
* `Campaign.network_settings.target_content_network` descreve a rede como *"ads served
  on **specified placements** … specified using the Placement criterion"*, o que
  pressupõe o positivo. E `managed_placement_view` existe como recurso de relatório.

A matriz marca `[NÃO CONFIRMADO]` e recomenda resolver com `validate_only` num
`AdGroupCriterionOperation` com `placement` e `negative = false`. **Essa prova não foi
autorizada nesta rodada** (outro agente estava lendo a Crédito Up). Entre duas leituras
oficiais que se contradizem, codificar uma é escolher no cara-ou-coroa e descobrir no
lote.

A decisão está em três lugares, e nos três ela é verificável:

* `perfil.DISPLAY.acoes_indisponiveis` — com o termo técnico `placement` e a citação;
* `plataforma.DISPLAY.indisponibilidades` — na palavra do operador, **"posicionamento"**;
* provas: `test_a_fatia_nao_emite_criterio_de_segmentacao_nenhum`,
  `test_o_perfil_explica_por_que_placement_positivo_ficou_de_fora`,
  `test_display_declara_a_ausencia_de_segmentacao_por_posicionamento`.

> ⚠️ **Por que o Hub diz "posicionamento" e o engine diz "placement".** Não é
> inconsistência. `backend/tests/test_trafego_plataforma.py:test_o_nucleo_nao_manipula_conceito_de_canal`
> proíbe as palavras `placement`, `audience`, `match_type`, `ad_set` e `listing_group`
> no **código** dos módulos do núcleo — é o gate mecânico do ADR-17 §9.4 contra
> vazamento de conceito de canal para dentro do núcleo. Uma string de manifesto é
> código. E "posicionamento" é justamente o termo que o painel do Google Ads usa em
> pt-BR, então a restrição arquitetural e a clareza para o operador apontam para o
> mesmo lado.

---

## 8. A costura com o motor de criativo

`Brief.imagens: list[str]` não serve para Display, e o motivo é estrutural: um resource
name (`customers/123/assets/456`) **não carrega proporção**, e o RDA tem quatro campos
de imagem com geometrias diferentes. Adivinhar o papel pela ordem da lista subiria a
imagem quadrada no campo do banner — a API recusaria o mutate inteiro por proporção e
o erro apontaria para o anúncio, não para quem montou a lista.

Por isso o papel é **declarado**, em `Brief.imagens_display: ImagensDisplay`:

```python
ImagensDisplay(
    marketing=[...],            # 1.91:1, mín 600x314   ≥1 obrigatória
    marketing_quadrada=[...],   # 1:1,    mín 300x300   ≥1 obrigatória
    logo=[...],                 # 4:1,    mín 512x128   opcional (aviso)
    logo_quadrado=[...],        # 1:1,    mín 128x128   opcional
)
```

**Este é o contrato com `volc_ads/criativo/` (Agente D):** ele cria os assets e devolve
os resource names **já separados por papel**. `brief.videos` continua sendo lista
chapada porque vídeo tem um papel só (`youtube_videos`).

Logo ausente é **aviso, não erro** — e a diferença é medida: o proto escreve
"is required" para as duas famílias de marketing e não escreve para logo; a matriz
confirma ("logos são opcionais no proto"). Barrar aqui recusaria localmente um payload
que a API aceita, e portão que dá falso positivo é portão que alguém desliga.

---

## 9. Dependências de outros donos

| item | dono | o que falta |
|---|---|---|
| `volc_ads/criativo/` preencher `ImagensDisplay` | Agente D | a ponte que devolve resource names por papel |
| `montar_brief` do cockpit emitir brief de Display | dono do `pautador_ponte.py` / router | hoje ele sempre emite `estrategia_lance="MANUAL_CPC"`, que Display recusa com mensagem acionável |
| tela de Display | dono do `src/` | `manifesto.sabe_criar` de DISPLAY virou `true`; a tela deriva o botão daí |
| `volc_ads/testes_subir.py` | — | **tocado por mim**: `DISPLAY` saiu da lista de canais recusados e a mensagem esperada virou `"DISPLAY, SEARCH"`. Era a prova direta de `subir.py`; deixá-la vermelha seria declarar pronto o que não passa |
| `backend/tests/test_trafego_plataforma.py` | — | **não tocado**, e passa. Mas o nome `test_so_search_sabe_criar_e_isso_bate_com_o_engine` ficou desatualizado: o corpo compara conjuntos e continua sendo prova válida; só o nome diz "só Search" |
| `validate_only` contra a conta real | condutor | não autorizado nesta rodada. O caminho está implementado e provado com dublê |

---

## 10. O que falta para Demand Gen e Performance Max reaproveitarem

O que **já está pronto** para os dois:

* `comum.op_campanha()` já tem o ramo `DEMAND_GEN` e as faixas de id temporário valem
  igual;
* `marcacao.py` já monta o contrato de URL por canal para os quatro;
* `conteudo.py` julga texto sem saber de canal — `limites.yaml` já tem
  `headline_demandgen`, `long_headline` e `description_dgen`;
* `policy/spec.py` já aceita `long_headline` e `business_name` em `aplica_a`;
* `taxonomia.MODIFICADOR` já tem `GD` e `Pmax`;
* `perfil.py` já tem os dois perfis, declarando a ausência com explicação.

O que **falta**, por canal:

**Demand Gen** — o mais próximo. Precisa de: `campanha/demand_gen.py` com
`CANAL`/`LANCES_PERMITIDOS`/`OPCOES`/`construir`/`validar`; decidir entre os quatro
tipos de anúncio do canal; imagens em **quatro** orientações (a matriz aponta 20
combinadas, contra 15 de Display) — o que provavelmente pede um irmão de
`ImagensDisplay` com o campo 9:16; `channel_controls`. Depois: preencher
`perfil.DEMAND_GEN`, acrescentar a linha em `CONSTRUTORES_POR_CANAL` e mudar
`plataforma.DEMAND_GEN` **na mesma entrega** — os dois testes de AST cobram.

**Performance Max** — o mais distante, e a distância não é de esforço, é de forma. Ele
não tem ad group nem anúncio explícito: tem **asset group**, e `PerfilDeCanal.hierarquia`
já prevê o degrau. Ele exige brand assets no nível da campanha e não tem controle de
rede. Duas coisas que este desenho ainda não tem e que PMax vai exigir:

1. **uma família nova de id temporário** para `asset_group` — a ser declarada em
   `comum.py`, no mesmo bloco, com a mesma disciplina de verificação (`temp_adgroup()`
   levanta antes de emitir id fora da faixa; o equivalente vai precisar existir);
2. **atomicidade obrigatória** — a matriz registra que PMax **exige** o mutate atômico,
   ao contrário de Display. O engine já é atômico sempre, então isso é uma restrição
   que ele satisfaz por construção.

O que **não** precisa mudar em nenhum dos dois: `subir.py` (o perfil roteia),
`conteudo.py` (o julgamento de texto é o mesmo), a trava de escrita, o `Selo` e o
recibo.
