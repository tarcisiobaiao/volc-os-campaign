# Proposta de curadoria — negativas tipadas no Search

Entrega de 27/08/2026, commits `f4cf128..HEAD`.

## ⚠️ Por que isto é um documento e não um commit na curadoria

`docs/volc-os-graph/curadoria-operacional.json` é a única camada do Mapa Vivo
editável à mão — e no momento desta entrega ela está **modificada e não
commitada por outra frente de trabalho** (verificado: o arquivo já aparecia como
`M` no `git status` antes do primeiro commit desta missão, e nenhum commit desta
entrega toca `docs/volc-os-graph/`).

Aplicar o delta abaixo exigiria `git add` num arquivo com trabalho alheio
dentro. Isso varreria o WIP de outra pessoa para dentro de um commit meu — que é
exatamente o que o protocolo da casa proíbe, e o que o commit `8363c98`
("desfaz o trabalho de outra frente que eu varri para dentro dos meus commits")
já custou uma vez.

**Quem aplica é o dono da curadoria**, depois de commitar o que já tem lá. O
conteúdo abaixo está pronto para colar e foi validado contra o schema do
gerador (clusters e estados existentes, IDs sem colisão, referências resolvíveis).

---

## 1. `capabilities` — `cap_search_birth`

Estado **não muda** (`implemented`). Só a evidência, e ela nomeia os limites.

```json
"evidence": "Cockpit /trafego/nova/:opportunityId e engine Google Ads v25. Em 27/08/2026 o contrato Criterio (volc_ads/campanha/criterio.py) substitui a keyword solta: match type por keyword, negativa de campanha vira CampaignCriterion, negativa de ad group vira AdGroupCriterion sem vazar entre grupos, e GrupoEscolhido.negativas — campo do contrato HTTP que nenhum caminho lia — chega ao engine via _criterios_do_corpo. Mesa das Palavras (src/components/trafego/MesaDeCriterios.tsx) expõe a revisão no cockpit. 97 provas novas. Provado contra a conta real: validate_only na 8017851692 aceitou 20 operações com match types individuais, negativa de campanha e de ad group — nada criado, trava fechada. PARCIAL DENTRO DO IMPLEMENTADO: a porta HTTP força conjunto_unico=True (doutrina P7), então a campanha nasce com UM ad group e a negativa por grupo, embora provada no engine, não se manifesta hoje; os N ad groups recebem o mesmo RSA; não há agenda de anúncios no contrato; nada persiste motivo/origem/evidência do critério (nem payload, nem selo, nem recibo, nem a linha de campaigns); search_term_view → NEGATIVAR_TERMO/PROMOVER_TERMO (F6 do PRD) não está implementado. MATRIZ-COBERTURA-V25.md refuta a premissa registrada de meta_conversao_id: Campaign.selective_optimization é campo de campanha de APP na v25, não de Search."
```

## 2. `concepts` — `channel:SEARCH`

Estado **não muda** (`implemented`).

```json
"evidence": "Único construtor de grafo: volc_ads/campanha/search.py. CORRIGIDO em 27/08/2026: match type deixou de ser um brief.match_type único para o brief inteiro e passou a ser por keyword; negativas deixaram de nascer fixas em BROAD; os achados das negativas entram no Resultado principal, não num Resultado() descartável; e os avisos passaram a sobreviver ao caminho FELIZ (Preparo.avisos_locais) — antes só o recusa_local os carregava, e ele só é preenchido quando algo barra. NÃO MUDA nesta entrega: a porta HTTP ainda força conjunto_unico=True; os N ad groups recebem o mesmo RSA; não há agenda de anúncios; a rede de parceiros de pesquisa (target_search_network=True, volc_ads/campanha/comum.py:167) segue ligada sem o operador ver ou escolher."
```

## 3. `concepts` — dois nós novos, cluster `acquisition`

```json
{
  "id": "concept:typed_criteria_contract",
  "label": "Contrato tipado de critério de keyword",
  "cluster": "acquisition",
  "state": "partial",
  "summary": "Texto, match type, nível, grupo, origem, motivo e evidência (medida ou hipótese) viajam juntos num objeto imutável, do cockpit até o payload da API — substitui a keyword solta como str.",
  "evidence": "volc_ads/campanha/criterio.py, com de_lista (adaptador de compatibilidade), deduplicar, deduplicar_por_emissao, conflitos e por_nivel. 44 provas em testes_criterio.py. Consumido por search.py e exposto na porta HTTP via CriterioEntrada/EvidenciaEntrada. PARCIAL: só Search consome o contrato — Display recebe as negativas e AVISA que não as aplica; origem=SEARCH_TERM exige evidência MEDIDO por construção, mas nenhum produtor real desse tipo de evidência existe ainda (é o F6); e a procedência não é persistida em lugar nenhum depois da prova."
},
{
  "id": "concept:keyword_review_table",
  "label": "Mesa das Palavras",
  "cluster": "acquisition",
  "state": "partial",
  "summary": "Superfície do cockpit onde o operador revisa correspondência por keyword e exclusões antes de lançar — a regra fora do componente, o componente só desenha.",
  "evidence": "src/lib/trafego/criterios.ts (regra) e src/components/trafego/MesaDeCriterios.tsx, montada em /trafego/nova/:opportunityId. 47 provas no frontend, incluindo uma que falha se um enum cru da API vazar para o texto renderizado. PARCIAL: a doutrina P7 (conjunto_unico=True) força um único ad group, e a tela recua da escolha de grupo em vez de prometê-la (NASCE_COM_UM_CONJUNTO)."
}
```

## 4. `risks` — um nó novo

```json
{
  "id": "risk:rede_parceiros_oculta",
  "label": "Rede de parceiros de pesquisa ligada sem escolha do operador",
  "cluster": "acquisition",
  "state": "risk",
  "summary": "Toda campanha Search nasce com target_search_network=True fixo no código — o operador nunca vê nem escolhe se distribui para os parceiros de pesquisa do Google.",
  "evidence": "volc_ads/campanha/comum.py:167 (ramo canal=='SEARCH' de op_campanha), sem campo correspondente em ProvarEntrada nem controle em nenhuma tela de /trafego/nova. Display desliga o campo equivalente em comum.py:190 — o risco é específico de Search. Não é regressão desta entrega: é comportamento herdado que a matriz da API v25 tornou visível."
}
```

## 5. `documents` — a matriz

```json
{
  "id": "doc:matriz-cobertura-v25",
  "label": "Matriz de cobertura Google Ads API v25",
  "cluster": "acquisition",
  "documenta": "channel:SEARCH",
  "summary": "29 capacidades comparadas contra a v25 real, com duas provas medidas contra a conta e a premissa refutada de meta_conversao_id.",
  "evidence": "volc_ads/google_ads_api/MATRIZ-COBERTURA-V25.md."
}
```

## 6. Arestas

```json
{"source": "concept:typed_criteria_contract", "target": "channel:SEARCH", "relation": "corrige_premissa_de"},
{"source": "concept:typed_criteria_contract", "target": "cap_search_birth", "relation": "sustenta"},
{"source": "concept:keyword_review_table", "target": "concept:typed_criteria_contract", "relation": "expoe_no_cockpit"},
{"source": "concept:keyword_review_table", "target": "cap_search_birth", "relation": "materializa_em"},
{"source": "risk:rede_parceiros_oculta", "target": "channel:SEARCH", "relation": "afeta"},
{"source": "doc:matriz-cobertura-v25", "target": "channel:SEARCH", "relation": "documenta"}
```

## 7. `volc-os-workbook/ROADMAP-VIVO.json` — tarefa nova em P05

Status **`partial`**, não `done` — cinco lacunas nomeadas, nenhuma cosmética.

```json
{
  "id": "P05-T07",
  "title": "Tipar negativas e match type por keyword no Search",
  "status": "partial",
  "proof": "Contrato Criterio chega ao engine, à porta HTTP e ao cockpit. 97 provas novas; validate_only aceitou o payload tipado contra a conta real (20 operações, nada criado). FALTA para done: negativa por grupo não se manifesta (P7 força conjunto_unico); RSA idêntico nos N grupos; sem agenda de anúncios; procedência do critério não é persistida; F6 (search_term_view → NEGATIVAR_TERMO/PROMOVER_TERMO) não implementado; meta_conversao_id com destino documentado errado."
}
```

## 8. O que NÃO entra, e por quê

- **Nenhuma prioridade nova (rank 15).** Os três candidatos (rede de parceiros
  visível, redesenho do `meta_conversao_id`, tribunal lexical) são dívidas
  dentro de capacidades já rastreadas, não frentes do tamanho das 14 iniciativas
  existentes. Inflar a lista dilui a ordenação que ela serve para carregar.
- **Nenhum nó para o tribunal lexical do F6.** Não existe código: `search_term_view`
  não é lido em lugar nenhum do produto. Criar um nó "planejado" e ligá-lo por
  aresta forte ao contrato tipado inventaria uma relação que ainda não existe.
- **Nenhuma mudança de `state`.** `cap_search_birth` e `channel:SEARCH`
  continuam `implemented`: o laço origem→keyword→copy→conta→lance→prova→pausada
  →recibo já fechava antes. O que mudou foi a qualidade interna da keyword, e
  "mais implementado que antes" não é um estado.
