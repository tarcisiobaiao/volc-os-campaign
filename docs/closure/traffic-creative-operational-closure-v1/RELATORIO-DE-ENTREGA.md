# Relatório de entrega — fechamento operacional de tráfego + criativos

Branch `sprint/traffic-creative-operational-closure-v1`, worktree
`/private/tmp/volc-traffic-creative-operational-closure-v1`, sobre a base limpa
`3462b1407cb18c9f1fae3775d1db64608f56f3e9`.

**20 commits · 46 arquivos · 13.541 inserções · 104 remoções.**

---

## 1. Gates medidos

| Gate | Baseline | Final | Veredito |
|---|---|---|---|
| Pytest (`backend/tests volc_ads`) | 2319 passed · 53 skipped · 0 failed | **2529 passed · 45 skipped · 0 failed** | +210 testes, zero vermelho, 8 skips a menos |
| TypeScript (`-p tsconfig.app.json`) | 76 erros herdados | **76 erros** | zero erro novo |
| Vite build | — | **verde**, 15,03s | ok |
| Backend import | 112 rotas | **114 rotas** | +2: `/api/trafego/canais`, `/api/trafego/canais/{canal}` |
| `git diff --check` | — | **limpo** | ok |
| Superfície de mutação | 3 pontos guardados | **inalterada** | nenhum `mutate_*` novo |
| Credencial no diff | — | **zero** | ok |
| Árvore final | — | **limpa** | ok |

A suíte Python estava 100% verde na base. Não havia falha herdada onde uma
regressão pudesse se esconder: qualquer vermelho seria novo por definição, e
não houve nenhum.

---

## 2. O que passou a funcionar

### Motor criativo
Uma receita existente produz asset local reproduzível **sem rede e sem crédito**.
O motor (`volc_ads/criativo/adaptadores/png_local.py`) escreve PNG paletado real
com `zlib` e `struct` da stdlib — deliberadamente **sem Pillow**, porque Pillow
não está em `backend/requirements.txt` e o `MotorTipografico` da bancada tem
exatamente esse ponto cego: importa Pillow dentro de `produzir()`, então numa
máquina sem Pillow ele **se registra e falha depois**, no meio do render.

O asset carrega hash sha256, MIME, dimensões, procedência e recibo, e atravessa
`volc_ads/criativo_ponte.py` até o contrato de canal. A ponte ganhou uma
fronteira `Destino.PRODUCAO | ENSAIO`, com **produção como padrão** — porque o
erro caro tem uma direção só.

Um asset de natureza `LOCAL` é **recusado** em destino de produção, e o teste que
prova isso também separa um par que engana: `entrega.ok is False` **com**
`veredito.ok is True`. O lote é geometricamente bom e mesmo assim não sai
payload. Derivar "reprovado" de `entrega.ok` faria o operador caçar um defeito de
geometria que não existe.

### Search
Preservado. Só 29 linhas tocadas, para ganhar a entrada uniforme `planejar()`.
O canário `24195821946` foi reverificado ao vivo durante a missão: `PAUSED`,
`SEARCH`, `MANUAL_CPC`, R$ 10,00/dia, razões `[CAMPAIGN_PAUSED,
MOST_ADS_UNDER_REVIEW]`. `MANUAL_CPC` é a prova **positiva** do bloqueio de Smart
Bidding — escolha registrada, não campo vazio.

### Display
A lacuna literal de P04-T05 caiu. `ProvarEntrada` ganhou campo de imagem que
distingue `None` ("não declarei imagem") de `[]` ("declarei que não há nenhuma"),
e **as duas recusam Display, com frases diferentes**. `trafego.py` deixou de
passar `imagens_display=None` literal.

A ponte passou a emitir **recibo tipado também em Display** — antes só Demand Gen
emitia, e o mesmo asset atravessaria com prova por uma porta e sem prova pela
outra. Ganhou também guarda de canal: um lote `DEMAND_GEN` era antes mapeado com
a tabela de papéis do Display, onde `logo` é 4:1 e no DG nem existe, montando
payload que a API recusaria por proporção com o erro apontando para o anúncio.

### Demand Gen
Aceite 4 de P04-T09 (objetos v25 instanciados e serializados offline) exercitado.
Aceites 1 e 5 continuam provados desde `e0f05a1`. A tarefa **não pode ir a
`done`**: o aceite 5 dela mesma exige que a rota produtiva permaneça recusada e
que o estado máximo seja `partial`.

### Performance Max
Contrato próprio em `volc_ads/campanha/pmax.py` (1172 linhas), **reusando**
`PMAX_FIELD_REQUIREMENTS` e `evaluate_asset_group_coverage` da
`volc_ads/observabilidade_pmax/` que já existia — não duplicando.

`BUSINESS_NAME` e `LOGO` vão em `CampaignAsset` sob `brand_guidelines_enabled`
(ligado por default desde a v21), não em `AssetGroupAsset`. Colocá-los no lugar
errado geraria `CampaignError.REQUIRED_LOGO_ASSET_NOT_LINKED`.

50 provas em `testes_pmax.py`, das quais duas decidem a tarefa:
`test_mensuracao_inadequada_bloqueia_mesmo_com_canal_habilitado` e
`test_sdk_v25_real_instancia_e_serializa_o_grafo_pmax`.

### Contrato HTTP e frontend
`backend/app/trafego/contrato_canais.py` modela os quatro portões —
`planejavel`, `validavel`, `criavel_pausada`, `ativavel` — com ordem validada,
`bloqueadores[]` e **`origem`** por bloqueador (`operador`, `politica`,
`produto`, `manifesto`, `servidor`, `construtor`), que é o que diz ao operador
**a quem pedir**. 51 testes.

`src/lib/trafego/canais.ts` leva isso ao navegador **sem recalcular nada**.

---

## 3. O que NÃO foi feito, e por quê

### Nenhum `validate_only` foi executado
É a lacuna mais importante desta entrega e ela é declarada. A lacuna literal de
P04-T04 é "a prova contra a conta real", e ela continua aberta.

O Gemini afirmou que o payload de Display está "**100% completo e suficiente para
passar pelo `validate_only` em produção real**". **Descartado**: não é
verificável sem executar, é afirmação sem prova com a forma de prova, e aceitá-la
fecharia P04-T04 sem o único ato que a fecha.

### PMax fora do executor
Decisão registrada em `DECISAO-PMAX-FORA-DO-EXECUTOR.md`. Habilitar o construtor
derrubaria a rota HTTP dos **quatro** canais, porque `subir.py` levanta no import
quando a vista dele discorda do perfil.

### Frontend entregue pela metade
`src/lib/trafego/canais.ts` e o método no cliente da API existem. A **superfície
visual** de `/trafego` com os quatro canais não foi construída. O contrato chega
ao navegador; a tela que o desenha, não.

---

## 4. Revisões externas

**Gemini 3.7 Flash** — 11 afirmações julgadas: 1 procedente e útil (o segundo
caminho de mutação, `trafego.py:4051`), 5 achados reais, 2 procedentes mas lidos
do próprio repositório, **2 alucinações** (`Campaign.url_expansion_opt_out` não
existe na v25; `SearchTheme` obrigatório é inventado), 2 falsos achados de
recorte, 1 afirmação sem prova.

As duas alucinações teriam quebrado o builder de PMax. `url_expansion_opt_out`
num GAQL derruba a query inteira.

**Codex `gpt-5.6-sol/high`** — três rodadas. As duas primeiras **não produziram
veredito**: carregaram o skill `adversarial-review`, geraram sub-revisores e
estouraram explorando. A terceira, com escopo estreito e instrução explícita de
não carregar skill, respondeu — e achou duas coisas que eu não tinha pego, ambas
registradas em `BACKLOG-POS-FECHAMENTO.md`.

---

## 5. Correções que eu mesmo tive de fazer

**Minha varredura de mutação estava cega.** Usei `\.mutate\(`, que não pega
`mutate_campaigns(`. O Gemini encontrou o segundo caminho de mutação real em
`trafego.py:4051` — rota de remoção de campanha, corretamente guardada por
`modo.destravar` (motivo ≥10 chars + `FORGE_PERMITIR_ESCRITA=1`), que recusa
remover campanha `ENABLED` sem flag explícita. Não era furo; minha linha de corte
é que era estreita.

**Classifiquei dois defeitos como bloqueadores e estava errado.** Os colapsos de
`prontidao.py` (`:163`, `:125`) levam ambos a `NAO_PRONTO` — falham na direção
segura. O critério `ausente ≠ zero` existe para impedir **prontidão falsa**, e
falha-fechado não é prontidão falsa. Rebaixados a dívida.

**Marquei um alerta de campo v25 que não existia.** `campaign.start_date_time` é
o nome correto e o repositório já o usava; o erro foi meu ao montar a query.
