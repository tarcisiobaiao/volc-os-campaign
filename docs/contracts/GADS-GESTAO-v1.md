# GADS-GESTAO v1 — gestão de campanhas no ar (Google Ads)

Contrato HTTP de `/api/trafego/gestao`, para quem faz o front. Backend:
`backend/app/routers/trafego_gestao.py` → casos de uso em
`backend/app/trafego/gestao/application/` → ledger v10_02
(`supabase/migrations/v10_02_autogestao.sql`, com a exceção declarada da
`v17_03_gestao_operacoes_sem_delta.sql`) + motor `volc_ads/gestao/`.

Ciclo: **propor → aprovar (humano) → aplicar → verificar → (reverter)**.
Nada é escrito no Google sem uma aprovação humana gravada (T1). Autonomia
(aplicar sem humano) **não existe** nesta versão — ver o fim do documento.

---

## 1. Autenticação, permissão e escopo

| Situação | HTTP | Corpo |
|---|---|---|
| Sem `Authorization: Bearer <jwt>` ou token inválido | 401 | `{"detail": "Credencial ausente."}` |
| Rota de admin chamada por não-admin | 403 | `{"detail": "Esta operação exige papel administrativo."}` |
| Conta fora da árvore do MCC da casa (6016739364) | 403 | `{"detail": {"codigo": "fora_do_escopo", ...}}` |
| Servidor sem configuração de auth | 503 | `{"detail": "Autenticação indisponível..."}` |

Papel por rota:

| Rota | Papel |
|---|---|
| `GET /propostas`, `GET /recomendacoes` | usuário |
| `POST /propostas`, `POST /campanhas/importar`, `POST /aplicacoes/{id}/verificar` | usuário |
| `POST /propostas/{id}/aprovar`, `POST /propostas/{id}/recusar` | **admin** (autoriza gasto) |
| `POST /propostas/{id}/aplicar`, `POST /aplicacoes/{id}/reverter` | **admin** (escreve no Google) |

O escopo é conferido no servidor **antes** de qualquer leitura no Google ou
escrita no ledger — inclusive nas rotas por id (a conta vem da proposta).
`customer_id` aceita hífen (`547-809-6539`); o servidor normaliza para dígitos.

---

## 2. Formato de erro

Toda recusa da gestão vem como:

```json
{"detail": {"codigo": "antes_divergiu", "mensagem": "texto para humano", "detalhe": {...}}}
```

Decida pela `codigo`, nunca pela `mensagem`. `detalhe` é opcional e serve a tela.

| HTTP | `codigo` | Quando |
|---|---|---|
| 404 | `nao_encontrado` | proposta/aplicação/campanha inexistente |
| 422 | `acao_invalida` | payload não monta a ação (campo faltando, tipo errado, valor fora da faixa) |
| 422 | `estado_nao_permite` | a conta lida agora não permite (orçamento compartilhado sem ciência, já está no valor, estratégia mudou, recomendação expirou…) |
| 422 | `sem_motivo`, `recusa_sem_motivo`, `sem_diff_apresentado` | campo obrigatório de decisão ausente |
| 422 | `google_recusou` | o Google recusou no validate_only ou na escrita; a aplicação foi registrada como `erro` |
| 409 | `regra_ausente` | não há versão vigente da regra pedida (ver §4) |
| 409 | `campanha_nao_importada` | proposta de nível campanha sem identidade — chame `POST /campanhas/importar` |
| 409 | `evidencia_insuficiente` | métricas da janela da regra não cobrem os `dados_obrigatorios`; `detalhe.faltantes` |
| 409 | `regra_exige_delta` | ação sem tamanho numérico que a regra **não lista** em `operacoes_sem_delta`, ou operação monetária sem delta (§5.1); `detalhe.operacao`, `classe`, `operacoes_sem_delta_da_regra` |
| 409 | `teto_sem_delta` | a regra lista a operação, mas a proposta passa do teto próprio dela (itens, escopo, status, estratégia, modificador, tipo de recomendação); `detalhe.teto`, `motivo`, `classe` |
| 409 | `limite_pct`, `limite_absoluto`, `teto_orcamento`, `moeda_do_teto`, `antes_velho` | a proposta estoura a regra |
| 409 | `diff_divergente` | o diff que a tela mostrou não é o gravado — recarregue |
| 409 | `ja_decidida` | a proposta já tem decisão (única, imutável) |
| 409 | `proposta_expirada` | passou de `expira_em`; proponha de novo |
| 409 | `exige_aprovacao_humana` | aplicar sem aprovação `aprovada` |
| 409 | `em_carencia` | a regra está em cooldown sobre o alvo; `detalhe.ate` |
| 409 | `antes_divergiu` | a conta mudou desde a proposta; `detalhe.campos`, `aprovado`, `lido_agora`; **nada foi enviado** |
| 409 | `verificar_antes` | há tentativa `em_voo`/`sem_resposta`: verifique antes de reaplicar; `detalhe.aplicacao_id` |
| 409 | `aplicacao_em_andamento` | outra requisição acabou de abrir a aplicação |
| 409 | `escrita_bloqueada` | trava de escrita fechada no servidor (FORGE_PERMITIR_ESCRITA); nada enviado |
| 409 | `nada_a_reverter`, `irreversivel`, `estado_mudou_depois`, `reversao_ja_existe` | ver §3.7 |
| 409 | `banco_recusou` | um gatilho/CHECK da v10_02/v17_03 recusou; `detalhe.sqlstate` |
| 409 | `estado_invalido`, `campanha_removida`, `regra_invalida`, `plataforma` | estado não permite o pedido |
| 503 | `indisponivel`, `escopo_indisponivel`, `sdk_ausente`, `motor_ausente` | banco/Google/motor não responderam — **não** é recusa |
| 503 | `sem_resposta` | a escrita saiu e não voltou: a conta PODE ter mudado; vá para verificar |
| 503 | `desfecho_nao_gravado` | o Google respondeu e o ledger não gravou o desfecho; verifique |

---

## 3. Rotas

Base: `/api/trafego/gestao`.

### 3.1 `GET /propostas?customer_id=&estado=&limite=`

Lê a view `trafego_proposta_painel` da conta, mais recentes primeiro.
`estado` ∈ estados da §6; `limite` 1–200 (padrão 50).

```json
{"propostas": [{
  "proposta_id": "uuid", "volc_campaign_id": "uuid", "alvo_nivel": "campanha",
  "alvo_chave": "google_ads:5478096539:campanha:24278665189",
  "operacao": "orcamento.diario",
  "valor_atual": {"verba_diaria_micros": 30000000, "budget_id": 15886629542, "...": "..."},
  "valor_proposto": {"verba_diaria_micros": 33000000, "budget_id": 15886629542},
  "valor_atual_lido_em": "2026-10-08T21:30:00+00:00",
  "delta_pct": 10.0, "delta_absoluto_micros": 3000000, "moeda": "BRL",
  "estado": "aguardando_aprovacao", "criada_em": "...", "expira_em": "...",
  "regra_chave": "gestao_manual_google", "regra_versao": 1, "regra_objetivo": "...",
  "regra_responsavel": "...", "nivel_autonomia": "T1", "condicao_rollback": "...",
  "sintoma": "pedido humano: orcamento.diario", "explicacao": "<motivo de quem propôs>",
  "confianca": null, "severidade": null,
  "evidencia_colhida_em": "...", "evidencia_suficiencia": "suficiente",
  "janela_inicio": "2026-10-01", "janela_fim": "2026-10-07",
  "aprovacao_decisao": null, "aprovacao_por": null, "aprovacao_em": null,
  "aplicacao_id": null, "aplicacao_desfecho": null, "aplicacao_enviada_em": null,
  "vencida": false, "proximo_passo": "aguardar_humano"
}], "total": 1}
```

`proximo_passo` é o que a tela deve oferecer: `aguardar_humano` (aprovar/recusar),
`aplicar`, `verificar` (há tentativa em voo/sem resposta — **nunca** ofereça
reaplicar), `acompanhar`, `expirar`, `nada`.

### 3.2 `POST /propostas` → 201 (nova) | 200 (já existia)

```json
{"customer_id": "5478096539",
 "acao": {"tipo": "orcamento.diario", "campaign_id": "24278665189", "amount_micros": 33000000},
 "motivo": "CPA estável há 14 dias; verba limita entrega",
 "regra_chave": "gestao_manual_google",
 "validade_horas": 24}
```

`regra_chave` (opcional, padrão `gestao_manual_google`) e `validade_horas`
(opcional, 1–168, padrão 24). O servidor: confere escopo → monta a ação (§5) →
lê a regra vigente → lê o "antes" na conta → recusa se a regra recusaria (§2) →
lê as métricas da janela da regra → grava `trafego_evidencia` (com veredito de
suficiência) → `trafego_diagnostico` (explicação = `motivo`) → `trafego_proposta`.
**Não escreve no Google.**

```json
{"proposta": {"proposta_id": "uuid", "estado": "aguardando_aprovacao", "idempotency_key": "gestao:orcamento.diario:…", "...": "..."},
 "evidencia_id": "uuid", "diagnostico_id": "uuid", "ja_existia": false}
```

Idempotência: a chave deriva de (tipo, alvo, antes, proposto). O mesmo pedido
sobre o mesmo estado devolve a proposta existente com `ja_existia: true` (200).

### 3.3 `POST /propostas/{id}/aprovar` (admin)

```json
{"diff_apresentado": {"valor_atual": {...}, "valor_proposto": {...}, "delta_pct": 10.0},
 "motivo": "opcional"}
```

`diff_apresentado` é **o que a tela mostrou** e é gravado como está
(`trafego_aprovacao.diff_apresentado`). `valor_proposto` é obrigatório; se
`valor_proposto` ou `valor_atual` diferirem do gravado → 409 `diff_divergente`.
Resposta: `{"aprovacao": {...}, "proposta": {"estado": "aprovada"}, "ja_existia": false}`.
Repetir a mesma decisão é idempotente (`ja_existia: true`); decisão contrária → 409 `ja_decidida`.

### 3.4 `POST /propostas/{id}/recusar` (admin)

`{"motivo": "obrigatório", "diff_apresentado": {...opcional}}` → `estado: "recusada"`.

### 3.5 `POST /propostas/{id}/aplicar` (admin) — sem corpo

1. já há aplicação `sucesso` (ou a verificação confirmou o efeito) → 200 com `ja_aplicada: true`, **sem chamar o Google**;
2. tentativa `em_voo`/`sem_resposta` não verificada → 409 `verificar_antes`;
3. exige aprovação `aprovada`, proposta não vencida, sem carência;
4. relê o "antes" na conta; diferente do aprovado → 409 `antes_divergiu` (nada gravado, nada enviado);
5. grava `trafego_aplicacao` `em_voo` (com `valor_anterior` = estado relido);
6. `validate_only` → recusado: aplicação `erro`, 422 `google_recusou`;
7. escrita real pelo lote, atrás da trava de dois fatores → desfecho.

```json
{"aplicacao": {"aplicacao_id": "uuid", "tentativa": 1, "desfecho": "sucesso",
               "valor_anterior": {...}, "request_id": "...",
               "resposta_bruta": {"desfecho_gestao": "ok", "criados": [], "validate_only": {"desfecho": "ok", "erros": []}}},
 "proposta": {"estado": "aplicada"}, "desfecho": "sucesso", "ja_aplicada": false}
```

`recomendacao.*` não tem validate_only na API v25: chamar é aplicar.

### 3.6 `POST /aplicacoes/{id}/verificar` — sem corpo

Relê a conta e compara com o proposto → `trafego_acompanhamento`
(`momento: "verificacao"`). `confere` é tri-estado: `true`, `false`, `null`
(não dá para saber pela leitura — sempre com `motivo`).

```json
{"acompanhamento": {"acompanhamento_id": "uuid", "confere": true, "motivo": "verba lida 33000000, pedida 33000000", "valor_observado": {...}},
 "confere": true, "motivo": "...", "aplicacao": {...}, "proposta": {...}}
```

Efeitos: `confere: true` numa proposta `aprovada` → vira `aplicada` (sem
reenviar). Tentativa `em_voo` com mais de 5 min é fechada pela verificação
(`sucesso` se confere, senão `sem_resposta`). `confere: false` depois de
`sem_resposta` libera nova tentativa (`tentativa + 1`).

### 3.7 `POST /aplicacoes/{id}/reverter` (admin)

`{"motivo": "obrigatório", "acompanhamento_id": "uuid opcional (o que disparou)"}`

Restaura `trafego_aplicacao.valor_anterior` (capturado no envio, não o "antes"
da proposta). Recusas: `nada_a_reverter` (aplicação sem sucesso), `irreversivel`
(recomendação aplicada/dispensada, troca para estratégia não regravável),
`estado_mudou_depois` (a conta não está mais como a aplicação deixou — reverter
apagaria a mudança de outra pessoa), `reversao_ja_existe` (a v10_02 admite UMA
reversão por aplicação; para desfazer de novo, nova proposta). O reverso é
ensaiado (validate_only) antes de gravar a reversão `pendente`.

```json
{"reversao": {"reversao_id": "uuid", "desfecho": "sucesso",
              "valor_restaurado": {"reversivel": true, "motivo": "", "passos": [{"operacao": "orcamento.diario", "valor": {"verba_diaria_micros": 30000000, "budget_id": 15886629542}}]}},
 "proposta": {"estado": "revertida"}, "ja_revertida": false}
```

### 3.8 `POST /campanhas/importar` → 201 | 200

`{"customer_id": "5478096539", "campaign_id": "24278665189"}`

Cria a identidade em `trafego_campanha` para campanha que **não nasceu pelo
VOLC** (procedência `descoberta`, declarada por `humano:<email>`). Exigida
antes de qualquer proposta de nível campanha. Idempotente; se a identidade já
existia como `desconhecida` (varredura), a procedência é declarada uma vez
(`procedencia_resolvida: true`). Campanha `REMOVED` → 409 `campanha_removida`.

```json
{"campanha": {"volc_campaign_id": "uuid", "customer_id": "5478096539", "campaign_id": "24278665189", "procedencia": "descoberta"},
 "google": {"nome": "...", "status": "ENABLED", "canal": "SEARCH", "moeda": "BRL"},
 "ja_existia": false, "procedencia_resolvida": false}
```

### 3.9 `GET /recomendacoes?customer_id=`

Recomendações não dispensadas (GAQL `recommendation`). Cada item já traz as
duas ações tipadas que a tela pode mandar para `POST /propostas`:

```json
{"recomendacoes": [{"recurso": "customers/…/recommendations/…", "tipo": "SITELINK_ASSET",
  "campanha": "customers/…/campaigns/…", "orcamento": null, "grupo": null, "dispensada": false,
  "impacto": {"base": {...}, "potencial": {...}},
  "acoes": [{"tipo": "recomendacao.aplicar", "recurso": "…"}, {"tipo": "recomendacao.dispensar", "recurso": "…"}]}],
 "total": 4}
```

Para recomendação de orçamento/alvo, prefira montar `orcamento.diario`/`lance.alvo`
com o valor recomendado: há validate_only e reverso exato.

---

## 4. Pré-requisito: a regra vigente

Toda proposta cita uma regra vigente de `trafego_regra_otimizacao` — os limites
são dela, e o gatilho `trafego_proposta_respeita_regra` os impõe. **Não existe
regra publicada hoje**; publicá-la é decisão do dono (responsável, teto, limite
e cada teto por operação).

A regra limita as ações de dois jeitos:

- **Monetárias** (`orcamento.diario`, `lance.alvo`): pelas colunas da v10_02 —
  `limite_alteracao_pct`/`_absoluto_micros` sobre o delta e
  `teto_orcamento_micros` sobre a verba. Sempre exigem delta; nenhuma
  declaração as dispensa (a CHECK recusa listá-las abaixo).
- **Sem delta** (os outros 13): pela coluna `operacoes_sem_delta` (v17_03),
  `{operacao: {tetos}}`. **Operação ausente = não autorizada** (409
  `regra_exige_delta`). Listada, a proposta tem de caber no teto dela (senão 409
  `teto_sem_delta`). A coluna é imutável: para mudar, publica-se a versão
  seguinte da regra.

| classe | operação | tetos (`*` = obrigatório) |
|---|---|---|
| status | `status` | `*status_permitidos` ⊆ {ENABLED, PAUSED} (REMOVED nunca), `niveis` |
| estrategia | `lance.estrategia` | `*estrategias`, `teto_micros` (tCPA/teto de CPC que vier junto) |
| ajuste | `ajuste.dispositivo`, `ajuste.horario` | `*modificador_min`, `*modificador_max` (0 ≤ min ≤ max ≤ 10) |
| segmentacao | `negativa.keyword` | `*max_itens`, `escopos` ⊆ {campanha, grupo} |
| segmentacao | `exclusao.placement`, `exclusao.ip` | `*max_itens`, `escopos` ⊆ {campanha, conta} |
| segmentacao | `programacao.anuncios` | `*max_itens` (criar + remover), `modificador_min`/`_max` das janelas |
| estrutura | `lista.criar` | `*max_itens`, `max_campanhas` |
| estrutura | `lista.adicionar`, `lista.anexar` | `*max_itens` (no anexar, campanhas) |
| recomendacao | `recomendacao.aplicar` | `*tipos_permitidos` — nenhum tipo monetário (`*BUDGET*`, `*TARGET_CPA*`, `*TARGET_ROAS*`, `MAXIMIZE_*`, `ENHANCED_CPC*`, tarifas) |
| recomendacao | `recomendacao.dispensar` | `tipos_permitidos` (opcional) |

`max_itens` vai de 1 a 1000. Chave desconhecida é recusada pela CHECK (teto com
nome errado é teto que não vale). Recomendação monetária é recusada mesmo que
alguém tente listá-la: para ela, monte `orcamento.diario`/`lance.alvo`.

Regra de referência cobrindo os 15 tipos (o usado nas provas; os números são
EXEMPLO conservador — quem decide é o dono):

```sql
INSERT INTO public.trafego_regra_otimizacao
  (chave, versao, titulo, objetivo, plataformas, canais, janela_minima_dias,
   atraso_conversao_dias, frescor_maximo_horas, amostra_minima_impressoes,
   dados_obrigatorios, teto_orcamento_micros, teto_orcamento_moeda,
   limite_alteracao_pct, cooldown_horas, confianca_minima, condicao_rollback,
   rollback_janela_horas, responsavel, nivel_autonomia, deteccao, acao,
   declarada_por, fonte, vigente_desde, operacoes_sem_delta)
VALUES
  ('gestao_manual_google', 1, 'Gestão manual de campanhas Google Ads',
   'Limitar e registrar ajustes pedidos por humano em campanhas no ar',
   ARRAY['GOOGLE_ADS'], ARRAY['*'], 7, 0, 6, 0,
   ARRAY['impressoes', 'custo_micros'], 500000000, 'BRL',
   30, 24, 0.5, 'o operador declara piora no acompanhamento',
   72, '<dono>', 'T1', '{"tipo": "pedido_humano"}', '{"tipo": "gestao_manual"}',
   '<quem publica>', 'humano', now(),
   '{
     "status":                 {"status_permitidos": ["PAUSED", "ENABLED"],
                                "niveis": ["campanha", "grupo", "anuncio", "asset_group"]},
     "lance.estrategia":       {"estrategias": ["MANUAL_CPC", "TARGET_SPEND",
                                                "MAXIMIZE_CONVERSIONS",
                                                "MAXIMIZE_CONVERSION_VALUE"],
                                "teto_micros": 50000000},
     "ajuste.dispositivo":     {"modificador_min": 0.5, "modificador_max": 1.5},
     "ajuste.horario":         {"modificador_min": 0.5, "modificador_max": 1.5},
     "negativa.keyword":       {"max_itens": 50, "escopos": ["campanha", "grupo"]},
     "exclusao.placement":     {"max_itens": 50, "escopos": ["campanha", "conta"]},
     "exclusao.ip":            {"max_itens": 20, "escopos": ["campanha", "conta"]},
     "programacao.anuncios":   {"max_itens": 42, "modificador_min": 0.5,
                                "modificador_max": 1.5},
     "lista.criar":            {"max_itens": 100, "max_campanhas": 10},
     "lista.adicionar":        {"max_itens": 100},
     "lista.anexar":           {"max_itens": 10},
     "recomendacao.aplicar":   {"tipos_permitidos": ["SITELINK_ASSET", "CALLOUT_ASSET",
                                                     "CALL_ASSET",
                                                     "RESPONSIVE_SEARCH_AD_ASSET"]},
     "recomendacao.dispensar": {}
   }'::jsonb);
```

A evidência de uma proposta humana é a métrica real da janela da regra
(`janela_minima_dias` dias inteiros terminando antes do atraso de conversão),
medida no nível do alvo (conta, campanha, grupo, anúncio ou asset group).

---

## 5. As ações — 9 grupos, 15 tipos

`acao.tipo` é `trafego_proposta.operacao`. IDs podem ir como número ou string
de dígitos. Dinheiro sempre em **micros inteiros** múltiplos de 10.000 (0,01).

### 5.1 O que a regra deixa propor

A regra precisa declarar limite de alteração (CHECK da v10_02), e o gatilho
recusa proposta **sem delta** (trava 4a) — a menos que a regra liste a
operação em `operacoes_sem_delta` (v17_03, §4):

| Tipos | Propõe quando |
|---|---|
| `orcamento.diario`; `lance.alvo` (`tcpa`/`teto_cpc` com delta % e absoluto; `troas` só %) | sempre que o delta couber em `limite_alteracao_*` e a verba no teto |
| os outros 13 | a regra vigente lista a operação **e** a proposta cabe no teto dela |
| qualquer um dos 13 não listado | ⛔ 409 `regra_exige_delta` |

O backend confere a mesma coisa antes da primeira escrita
(`application/sem_delta.py`, espelho de `trafego_proposta_sem_delta_defeito`),
para a recusa sair com `codigo` estável em vez de linha órfã. Regra sem a
coluna (v17_03 não aplicada) vale como `{}`: nada sem delta passa.

### 5.2 Payloads

**1. status** — `{"tipo":"status","nivel":"campanha|grupo|anuncio|asset_group","ident":"<id>","status":"ENABLED|PAUSED"}`.
Anúncio: `ident = "<ad_group_id>~<ad_id>"`. `REMOVED` não é gestão (422).

**2. orçamento diário** — `{"tipo":"orcamento.diario","campaign_id":"…","amount_micros":33000000,"budget_id":"opcional","compartilhado_ciente":false}`.
Sem `budget_id`, o servidor usa o orçamento que a campanha usa hoje. Orçamento
compartilhado exige `compartilhado_ciente: true` (muda a verba de N campanhas).

**3. alvo de lance** — `{"tipo":"lance.alvo","campaign_id":"…","alvo":"tcpa|troas|teto_cpc","valor":25000000,"estrategia":"opcional"}`.
`troas` é razão (`4.5` = 450%); os outros em micros. Sem `estrategia`, vale a
lida na conta; alvo não troca estratégia; portfólio é recusado.

**4. troca de estratégia** — `{"tipo":"lance.estrategia","campaign_id":"…","nova":"MANUAL_CPC|TARGET_SPEND|MAXIMIZE_CONVERSIONS|MAXIMIZE_CONVERSION_VALUE|PORTFOLIO","tcpa_micros":0,"troas":0,"teto_cpc_micros":0,"portfolio":"customers/…/biddingStrategies/…"}`.
Só o campo da estratégia nova. Reinicia aprendizado.

**5. negativas e listas**
- `{"tipo":"negativa.keyword","escopo":"campanha|grupo","alvo":"<id>","termos":[{"texto":"grátis","correspondencia":"PHRASE|EXACT|BROAD"}]}`
- `{"tipo":"lista.criar","tipo_lista":"NEGATIVE_KEYWORDS|NEGATIVE_PLACEMENTS","nome":"…","itens":[…],"campanhas":["…"]}`
- `{"tipo":"lista.adicionar","shared_set_id":"…","tipo_lista":"…","itens":[…]}`
- `{"tipo":"lista.anexar","shared_set_id":"…","campanhas":["…"]}`

Itens de `NEGATIVE_KEYWORDS` são termos `{texto, correspondencia}`; de
`NEGATIVE_PLACEMENTS`, placements `{tipo, valor}`. Duplicata existente é recusada.

**6. exclusão de placement** — `{"tipo":"exclusao.placement","escopo":"campanha|conta","campaign_id":"só se campanha","itens":[{"tipo":"site|app|youtube_canal|youtube_video","valor":"exemplo.com.br"}]}`.

**7. exclusão de IP** — `{"tipo":"exclusao.ip","escopo":"campanha|conta","campaign_id":"só se campanha","ips":["203.0.113.7","198.51.100.0/24"]}` (IPv4 /24–/32, até 500).

**8. programação e ajustes**
- `{"tipo":"programacao.anuncios","campaign_id":"…","janelas":[{"dia":"MONDAY","inicio":"08:00","fim":"12:00","modificador":1.2}],"remover":[criterion_id],"substituir":false}` — grade de 15 min; `substituir: true` remove todas as janelas atuais.
- `{"tipo":"ajuste.dispositivo","campaign_id":"…","dispositivo":"DESKTOP|MOBILE|TABLET|CONNECTED_TV","modificador":1.3}` (0 = −100%; 0,1–10).
- `{"tipo":"ajuste.horario","campaign_id":"…","criterion_id":"…","modificador":0.8}`.

**9. recomendações** — `{"tipo":"recomendacao.aplicar|recomendacao.dispensar","recurso":"customers/…/recommendations/…"}` (sem validate_only; aplicar não tem reverso).

---

## 6. Estados

**Proposta** (`trafego_proposta.estado`):

```
aguardando_aprovacao ──aprovar──▶ aprovada ──aplicar (sucesso)──▶ aplicada ──reverter──▶ revertida
        │                            │   └─verificar confere (após sem_resposta)──▶ aplicada
        ├──recusar──▶ recusada       └─expira_em passou──▶ expirada
        └─expira_em passou──▶ expirada
```

`cancelada` existe no schema e não é produzida por esta API.

**Aplicação** (`trafego_aplicacao.desfecho`): `em_voo` (gravada antes da chamada)
→ `sucesso` | `erro` | `sem_resposta`. Fecha uma vez; nova tentativa = linha nova.
Um `sucesso` abre a carência da regra sobre o alvo (gatilho da v10_02).

**Reversão** (`trafego_atuacao_reversao.desfecho`): `pendente` → `sucesso` | `erro` | `sem_resposta`. Uma por aplicação.

---

## 7. Autonomia (aplicar sem humano) — não disponível

A v10_02 não tem T2. O ponto único no código é
`backend/app/trafego/gestao/application/autonomia.py` (vazio). A migration
necessária está proposta, **não aplicada**, em
`supabase/migrations/v17_02_autonomia_gestao.PROPOSTA.sql` (T2 por operação,
`trafego_aprovacao.decisor_tipo`, suspensão por conta). Até a decisão do dono,
todo `aplicar` exige aprovação humana.

A v17_03 é compatível com a v17_02 nas duas ordens: a v17_02 não reescreve
`trafego_proposta_respeita_regra`, e a v17_03 não toca `trafego_aprovacao` nem
`nivel_autonomia`. Uma operação sem delta só pode ser autônoma (`acao->
'operacoes_autonomas'`) se a regra também a listar em `operacoes_sem_delta` —
sem isso a proposta nem nasce.
