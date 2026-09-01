# Backlog do Worker 2 — dívida não bloqueante, com o caminho de saída

*Nada aqui impede o fechamento desta rodada. Tudo aqui é fato medido, com o
próximo passo nomeado — não é lista de desejos.*

---

## 1. `BUDGET_BELOW_PER_DAY_MINIMUM` não vira bloqueio legível

**Medido** em 01/09/2026 (ver `verificacao/VALIDATE-ONLY-CANAIS.md` §2.1): Demand
Gen tem mínimo de orçamento por dia que Display não tem. A API devolve o número
exato em `budget_per_day_minimum_error_details` — nesta conta, em BRL,
**25.400.000 micros (R$ 25,40)**.

Hoje o operador que pede R$ 10,00 em Demand Gen recebe um `FalhaGads` cru com o
texto em inglês da API. Não há bloqueio local nem código de plano.

**Por que não foi resolvido agora:** o número é POR MOEDA. Gravar `25.40` em
`limites.yaml` valeria no Brasil e mentiria nos outros cinco países da operação
— o mesmo defeito que a nota dos `snippet_headers_es` documenta no mesmo arquivo.

**Caminho:** traduzir a falha da API em `plano.Achado` com código próprio
(`ORCAMENTO_ABAIXO_DO_MINIMO`), carregando `currency_code` e
`budget_per_day_minimum_micros` que a própria API devolveu. Isso exige que
`validar()` projete a falha no plano — hoje ele devolve `FalhaGads` cru ao
chamador, e `planejar()` não chama a API.

---

## 2. Search constrói o cliente antes de validar quase tudo

`search.construir()` chama `cliente(login_customer_id)` na terceira linha. Só a
conferência de `estrategia_lance` (adicionada nesta entrega) acontece antes.
Display e Demand Gen adiaram o cliente para depois de toda a validação local, e
documentaram a razão: autenticar para depois recusar o brief faz um pedido já
inválido renovar OAuth, e transforma "Google fora do ar" em "contrato
incompleto".

**Por que não foi resolvido agora:** mover essa linha é reordenar o caminho que
foi provado num canário real (campanha `24195821946`). A missão diz para
preservar o caminho provado de Search, e reordenar não é preservar.

**Caminho:** mover `c = cliente(...)` para depois do portão de política, no
mesmo lote em que `testes_search.py` ganhar um teste de ordem (cliente não é
construído quando o brief é inválido) — como `testes_display.py` já tem.

---

## 3. Performance Max fora do executor

Decisão de 01/09/2026, ratificada. `perfil.PERFORMANCE_MAX.construtor` e
`validador` continuam `None`; `planejador` aponta para `pmax.planejar`.

**Por que:** promover `construtor` mudaria `perfil.canais_que_provam()`, e
`volc_ads/subir.py:133-148` levanta no import quando `PROVADORES_POR_CANAL`
diverge do perfil — derrubaria a rota HTTP dos QUATRO canais.
`backend/tests/test_trafego_canal_de_criacao.py` exige 422 para `canal=PMAX`.

**Caminho, quando for a hora — e é um lote só, coordenado:**
1. `volc_ads/subir.py`: entrar em `PROVADORES_POR_CANAL` (não em
   `CONSTRUTORES_POR_CANAL`, que é mutate real);
2. `perfil.PERFORMANCE_MAX`: `construtor=pmax.construir`, `validador=pmax.validar`,
   `provas_obrigatorias=_PROVAS`, `permite_mutacao_real=False`;
3. `backend/app/trafego/plataforma.py` e `contrato_canais.py`: o manifesto passa
   a oferecer "provar";
4. `backend/tests/test_trafego_canal_de_criacao.py`: o 422 de PMAX vira 200 com
   plano, e o teste muda de fato, não de regra;
5. `pmax._prontidao`: `pode_provar=True`, e o bloqueio `PMAX_FORA_DO_EXECUTOR`
   sai do plano.

⚠️ O portão de mensuração NÃO participa desse lote e continua valendo depois
dele — `testes_pmax.py::test_mensuracao_inadequada_bloqueia_mesmo_com_canal_habilitado`
existe exatamente para que essa independência não se perca na mudança.

---

## 4. PMax monta um asset group, e a API aceita até 100

O builder emite exatamente um `AssetGroup`. A faixa de id temporário
(`comum.T_ASSET_GROUP_BASE`, −300 para baixo) já reserva 100, que é o teto real
da API.

**Por que não N:** cada asset group tem público e criativo próprios. N cópias do
mesmo conteúdo repartiriam a verba por sorteio — o mesmo motivo pelo qual
Display monta um ad group só. O brief ainda não tem como expressar "este
criativo para este sinal".

**Caminho:** um contrato de partição em `ConfiguracaoPMax` (lista de
`(nome, sinais, imagens, copy)`), quando houver operação que peça.

---

## 5. `marcacao.BUSCA` inclui `PERFORMANCE_MAX`

`campanha/marcacao.py:76` declara `BUSCA = {"SEARCH", "PERFORMANCE_MAX"}`, o que
faz `{keyword}`, `{matchtype}` e `{adposition}` entrarem no `final_url_suffix`
de PMax. Em PMax não existe keyword positiva, então `utm_term` e `vc_match`
tendem a chegar vazios.

**Não é defeito comprovado:** PMax serve em Search e o Google pode popular a
macro pelo termo de busca que casou. Não medi. E parâmetro vazio é ruído, não
erro.

**Caminho:** medir com um clique real depois do primeiro lançamento PMax, e só
então decidir se a macro sai da lista. Codificar agora seria escolher no
cara-ou-coroa.

---

## 6. `conversoes_ultimos_30d` nunca é preenchido

`pmax.ler_mensuracao()` lê `conversion_action` e deixa o volume como `None` —
que o plano reporta como "ninguém mediu", nunca como zero.

**Por que:** o volume vem de `metrics.conversions` sobre `conversion_action`,
que é outra consulta, com `segments.date`. Uma consulta a mais por plano, para
um dado que hoje só produz aviso.

**Caminho:** segunda consulta GAQL em `ler_mensuracao`, com a janela de 30 dias
explícita, preenchendo o campo. O tri-estado já está pronto para receber o
número — `AcaoDeConversao.conversoes_ultimos_30d` e `ReciboDeMensuracao.
volume_30d` distinguem `None` de `0.0` desde o primeiro commit.

---

## 7. Ponte criativa ainda não emite recibo de PMax

`volc_ads/criativo_ponte.py` (Worker 1) tem `imagens_de_display()` e
`imagens_de_demand_gen()`. Não há `imagens_de_pmax()`, e `ReciboAssetAprovado`
é emitido com `canal="DISPLAY"` ou `"DEMAND_GEN"`.

`campanha/brief.conferir_asset_aprovado(..., canal=...)` já é parametrizado, e
PMax exige `canal="PERFORMANCE_MAX"` — um recibo de Demand Gen **não** vale em
PMax, e há teste para isso
(`testes_pmax.py::test_recibo_de_outro_canal_nao_vale_em_pmax`).

Consequência: hoje só um chamador que emita o recibo pela fábrica privada
consegue montar PMax com asset. Os testes fazem isso; o caminho de produção
não existe ainda.

**Caminho:** pedido registrado em `PEDIDO-PONTE-channel-builders.md`.
