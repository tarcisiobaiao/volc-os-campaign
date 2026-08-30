# SPEC — ORAKUL Decision Intelligence v1

- **Estado:** especificação proposta (missão Fable 5, 2026-08-28). Nada aqui foi
  aplicado: zero migrations, zero deploys, zero edições de workflow,
  `FORGE_PERMITIR_ESCRITA` ausente durante toda a missão.
- **Autoridades reutilizadas (não recriadas):** `RegraDeOtimizacao` +
  `avaliar_suficiencia` (`backend/app/trafego/intencao.py`); vocabulário do ledger
  v10_01/v10_02 (`supabase/migrations/`); kernel do Lab
  (`volc_ads/inteligencia_decisao/`); identidade v9_01 (`trafego_campanha`,
  aplicada); executor com recibo (`volc_ads/subir.py` + `canario.py`).
- **Documentos irmãos:** `REPORT-ORAKUL-DECISION-INTELLIGENCE-FABLE.md`
  (diagnóstico), `ADR-RUNTIME-ORAKUL-E-WORKERS.md` (runtime),
  `ORAKUL-DECISION-INTELLIGENCE-AUDIT.json` (achados),
  `PROPOSTA-CURADORIA-ORAKUL-DECISION-INTELLIGENCE.json` (handoff).

## 0. Pré-condição de segurança (bloqueia tudo o que vem depois)

Esta especificação **não deve começar a ser implementada** antes de duas coisas,
ambas descobertas na auditoria que a originou:

1. **Rotacionar o `JWT_SECRET` do Supabase de produção.** Ele é hoje o segredo
   demo público do `.env.example` do Supabase (verificado por comparação de
   hash, sem expor valor) — qualquer pessoa forja um token `service_role` e o
   banco inteiro fica aberto. Enquanto isso vale, RLS, grants, ledger e portões
   de aprovação são decorativos, porque um token forjado passa por cima de todos.
   Rotação implica reemitir `anon`/`service_role` e reiniciar a stack.
2. **Revogar o CRUD de `anon`/`authenticated`** nas seis tabelas legadas sem RLS
   (§5, migration `v12_05`), sob pena de qualquer política aprendida no futuro
   ser treinada sobre dados que um anônimo pode falsificar.

Nota de versão para todo o desenho abaixo: **a Google Ads API v21 sofreu sunset
em 05/08/2026** e responde 404. Nenhum componente novo pode nascer apontando
para ela; o alvo é **v25** (minor corrente v25.1). Os flows legados que ainda
apontam para v21 falham em silêncio — o que os torna, hoje, inofensivos e
enganosos ao mesmo tempo.

## 1. Princípios inegociáveis

1. **Um ledger só.** O ciclo evidência → diagnóstico → proposta → aprovação →
   aplicação → verificação → acompanhamento vive nas tabelas v10_01/v10_02 do
   Supabase oficial. Recibo em arquivo (`volc_ads/dados/recibos/`) vira espelho,
   nunca fonte. Nenhuma tabela nova que duplique esse papel.
2. **Ausência é `null`.** Zero só quando medido. Toda métrica carrega origem,
   grão, janela e `lido_em` (padrão já implementado no kernel do Lab).
3. **LLM nunca é autoridade numérica nem canal de mutação.** O padrão
   `PortaCritica` (allowlist de entrada, schema fechado de saída, rejeição por
   campo extra, timeout ⇒ `indisponivel`) é o único jeito de um modelo falar com
   o pipeline.
4. **Recomendação não vira mutação por acidente.** Só o executor
   (`volc_ads/subir.py`-linhagem) escreve no Google Ads, somente com
   `FORGE_PERMITIR_ESCRITA` presente, `validate_only` prévio, aprovação humana
   registrada (v10_02) e recibo em_voo→desfecho.
5. **Regra tem dono, versão, teste e teto.** Nenhuma régua nova nasce fora de
   `RegraDeOtimizacao` (que já obriga amostra mínima e limite de alteração).
6. **n8n agenda, não decide.** Qualquer flow remanescente vira gatilho de
   endpoint autenticado ou canal de notificação.

## 2. Arquitetura-alvo (visão)

```text
Google Ads API v25 (somente leitura na fase shadow)
        │ GAQL tipada (coletor Python, worker)
        ▼
trafego_evidencia (v10_02)  ←  receita externa (GAM/AdSense, ledger de coleta)
        │ normalização + carimbo (fonte, grão, janela, lido_em)
        ▼
volc_ads.inteligencia_decisao (kernel puro, sem I/O)
  validação/frescor → features anuláveis → políticas versionadas
  → eventos tipados → conflitos → health gate → diagnóstico → proposta T1
        │                                   │
        │ shadow: persiste proposta         │ crítica LLM (PortaCritica, opcional)
        ▼                                   ▼
trafego_diagnostico / trafego_proposta / trafego_cooldown (v10_02)
        │ revisão humana (frontend: caixa de propostas + portão)
        ▼
trafego_aprovacao (append-only, diff apresentado)
        │ somente decisão='aprovada' e proposta não expirada
        ▼
executor (volc_ads, FORGE_PERMITIR_ESCRITA + validate_only + mutate)
        │ recibo em_voo → sucesso/erro/sem_resposta (trafego_aplicacao)
        ▼
verificação remota (releitura GAQL) → trafego_acompanhamento
        │ momento='verificacao' (entrou?) e momento='acompanhamento' (ajudou?)
        ▼
avaliação posterior (novas tabelas §5: previsão vs realizado, acurácia)
```

## 3. Máquina de estados do pipeline operacional

Etapas, donos e contratos. Persistência sempre no ledger; nenhuma etapa lê o
futuro; toda etapa é reexecutável por idempotência.

| # | Etapa | Dono (runtime) | Input → Output | Persistência | Idempotência / retry | Falha fechada | Proibido |
|---|---|---|---|---|---|---|---|
| 1 | Coleta | worker (coletor GAQL) | conta+janela → linhas cruas tipadas | `trafego_evidencia` (avaliada por gatilho) | chave (conta, recurso, janela, grão); retry 3× backoff; timeout 120 s | sem dado ⇒ nada gravado + heartbeat de rotina ausente dispara `routine_stale` | mutate; validate_only; segments médios de share |
| 2 | Normalização | worker (mesmo job) | linhas cruas → observação canônica (contrato do Lab, `VOLC-DECISION-LAB-RAW-MAPPING.json`) | idem (campos derivados carimbados) | determinística (função pura) | identidade mista / data duplicada / futuro ⇒ observação `invalida`, nada segue | zero-fill; média de ratios diários |
| 3 | Validação + frescor | kernel (`_validar`) | observação → estado atual/parcial/stale/invalida | — (campo da observação) | pura | `invalida`/`parcial`/`stale` ⇒ zero eventos, zero propostas | promover parcial a atual |
| 4 | Features | kernel (`_features`) | observação → features anuláveis | — | pura | ausência propaga `null` | imputação silenciosa |
| 5 | Eventos | kernel (`_detectar_eventos`) | features → eventos tipados dedupados | `trafego_evento` (v9, append-only) | `dedup_key` = hash(tipo, entidade, janela) | sem perfil de política ⇒ zero eventos | evento sem evidencia_refs |
| 6 | Políticas | kernel (`avaliar_regras`) | features+observação → avaliações (suficiência, disparo) | `trafego_regra_otimizacao` (versões publicadas) | versão imutável; cooldown por chave | insuficiência ⇒ "evidência insuficiente", nunca disparo | regra sem amostra mínima/limite (CHECK já recusa) |
| 7 | Conflitos + health gate | kernel (`_conflitos`, `_health_gate`) | eventos+features → vetos | campo do diagnóstico | pura | qualquer veto ⇒ proposta bloqueada/retida | ranking que ignora veto |
| 8 | Diagnóstico | kernel (`_diagnostico`) | tudo acima → escada de degraus | `trafego_diagnostico` (append-only) | 1 por (campanha, janela, versão) | degrau não apurado permanece não apurado | inventar causa |
| 9 | Proposta | kernel (`_propostas`) | eventos não vetados → `PropostaTipada` | `trafego_proposta` (INSERT recusado se estourar regra) | `idempotency_key` canônica (hash de conteúdo) UNIQUE | expira (`expira_em`); diff igual recusado | proposta sem evento originador |
| 10 | Crítica LLM | serviço de crítica (worker, opcional) | contexto allowlist → resumo+questões | coluna/tabela de auditoria da crítica (§5) | por proposta+versão do prompt; timeout curto | timeout/campo extra ⇒ `indisponivel`, pipeline segue | alterar veredito, ver diff, ver segredo |
| 11 | Revisão humana | frontend (caixa de propostas) | proposta → decisão | `trafego_aprovacao` (append-only, guarda `diff_apresentado`) | UNIQUE por proposta | recusa exige motivo (CHECK) | aprovar em lote cego |
| 12 | Aplicação | executor (worker sob trava) | proposta aprovada → mutate | `trafego_aplicacao` (em_voo antes da chamada) | índice único parcial (idempotency_key, operacao) WHERE sucesso; retomada reconhece em_voo | processo morto ⇒ linha em_voo visível; `sem_resposta` exige verificação antes de retry | mutate sem aprovação (gatilho recusa); mutate fora da trava |
| 13 | Verificação | worker | releitura GAQL do alvo | `trafego_acompanhamento` momento='verificacao' | por aplicação | não achou ⇒ estado indeterminado, bloqueia repetição | assumir sucesso por ausência de erro |
| 14 | Recibo | executor | resposta da API → desfecho | `trafego_aplicacao.desfecho` + espelho em arquivo | mesma chave | `sem_resposta` nunca vira `sucesso` sem verificação | recibo "OK" sintético |
| 15 | Avaliação posterior | worker (job diário) | aplicação+janela pós → efeito medido | `trafego_acompanhamento` momento='acompanhamento' + §5 acurácia | por (aplicação, janela) | efeito não medível ⇒ `null`, nunca 0 | atribuir efeito sem contrafactual declarado |

Leitura / diagnóstico / recomendação / aprovação / aplicação / verificação /
aprendizado são runtimes distintos com credenciais distintas: o coletor não tem
scope de mutate; o executor não calcula regra; o frontend nunca vê segredo.

## 4. Decomposição do legado (capacidade → destino)

| Capacidade | Origem atual | Destino recomendado | Justificativa | Dependências | Risco | Critério de aceite |
|---|---|---|---|---|---|---|
| Régua de escala/lance (BEAST: ROAS 0.50/0.70/1.30/1.70, steps 30 %, histerese, maturidade EXPLORATION/CALIBRATION/PRODUCTION, floors/loss caps) | Code node Python 1.678 linhas, `orakul-vos-auto-adjust` (inativo) | Reimplementar como `RegraDeOtimizacao` versionadas em `volc_ads/` (P09-T08); thresholds entram como *hipóteses* a calibrar, não como verdade | Regras valiosas, mas com cooldown/redistribuição mortos por inputs nunca preenchidos e filtro silencioso de estratégia | kernel do Lab; perfis por conta (§6) | médio: portar bug junto | replay dourado + shadow comparando BEAST-réplica vs kernel sobre a mesma fotografia (P09-T09) |
| Validação de campanha nova (NEXUS v3.0/v4.9, 72 h) | `gads-new-campaign-validation` (inativo, 2 ramos divergentes) | Guardião 72 h canônico já esboçado (`nexus_guardiao_72h` no Lab) + coleta real | Dois ramos com thresholds e contas diferentes sem doc; escrever `aplicado_com_sucesso` sem confirmação é inaceitável | coleta real (etapa 1-2) | baixo | cenário dourado + caso real em shadow |
| Upgrade de termos → keywords + negativação | `gads-search-terms-upgrade-kw` (inativo; 3 nodes de mutate sem persistência de decisão) | Mesa de Termos de Busca: detecção no kernel (`search_negativa_bidirecional` já existe no caminho inverso); mutação só via etapa 12 | mutate sem idempotência nem decisão registrada | search_term_view (não cobre PMax) | médio | proposta tipada com termo, evidência e diff; zero mutate direto |
| Insights/orientação diária (Motor 2 Insights + Gerador de Orientação; AdSense idem) | `atuacao-orakul-ai-agent-webgo` (ATIVO, escreve `orientacao_*` no Supabase legado) | Substituir por diagnóstico canônico persistido (etapa 8) no Supabase oficial; desativar a escrita legada após corte | Split-brain de autoridade: produtor ativo escreve num banco que o produto não lê | corte de consumo do legado | alto (é o único produtor ativo) | diff de paridade orientação-legada vs diagnóstico novo por N dias em shadow; depois desligar |
| Aplicação de lance por webhook | `atuacao-apply-bidding-webhook-v2` (ATIVO; sem auth, payload de campo fixo) | **Aposentar.** Substituído pela etapa 12 (executor com trava+aprovação) | Mutação real sem autenticação/limite/validate_only é o maior risco vivo do sistema | dono desativar no n8n vivo | — | webhook removido/bloqueado; nenhuma rota de mutação fora do executor |
| Preditivo D+1 (Ridge/XGBoost re-treinado por execução, intervalos in-sample, boost_factor) | `bola-de-cristal-preditivo`, `orakul-predictive-integrado-v1` (inativos) | Não portar como está. Guardar como memória (P14-T01, feito). Reabrir só via §6 (previsto vs realizado persistido primeiro) | target leakage + validação in-sample = número que parece ciência | tabela de previsões (§5) | — | nenhuma reativação; qualquer preditivo novo nasce com backtest as-of |
| Motores 1/2 "Análise Quantitativa/Comportamental" | `orakul-02-analysis-engine` (placeholders não funcionais) | Descartar (não há código real) | scaffolding com retornos hardcoded | — | — | classificado como não-funcional no manifesto |

## 5. Modelo de dados (delta sobre v9/v10 — migrations propostas, NÃO aplicadas)

**Reutilizar como está (nada a criar):** `trafego_campanha`/`_espelho`/
`_snapshot_conta`/`_vinculo`/`_evento` (v9_01, vivas); todo o ciclo v10_01
(intenção/lote/recibo/verificação/rollback) e v10_02 (regra/evidência/
diagnóstico/proposta/aprovação/aplicação/acompanhamento/reversão/cooldown) —
**pré-requisito: aplicar v10_01+v10_02, decisão do dono.**

**Criar (novas migrations `v12_*`, esboço):**

| Objeto | Finalidade (não técnica) | Colunas essenciais | Identidade / PK-FK | Índices | RLS | Retenção | Rollback |
|---|---|---|---|---|---|---|---|
| `trafego_fotografia` | "O que o sistema sabia às X horas" — snapshot as-of da observação normalizada que alimentou uma decisão; replay honesto exige isso | fotografia_id uuid PK; volc_campaign_id FK→trafego_campanha; janela_inicio/fim date; lido_em timestamptz; as_of timestamptz; payload jsonb (contrato do Lab); payload_hash text UNIQUE; origem text; api_namespace text | interna uuid; externa (customer_id,campaign_id) via FK | (volc_campaign_id, as_of DESC); payload_hash UNIQUE (idempotência de captura) | forçada, zero policies, só service_role | 18 meses, depois arquivar | `DROP TABLE` (append-only, sem dependentes) |
| `trafego_previsao` | Registrar o que a política esperava que acontecesse, antes de acontecer — sem isso não existe medir erro de previsão/uplift | previsao_id uuid PK; proposta_id FK→trafego_proposta; fotografia_id FK; metrica text; valor_esperado numeric NULL; intervalo_baixo/alto numeric NULL; horizonte_dias int; declarada_em timestamptz | 1 previsão por (proposta, metrica, horizonte) UNIQUE | (proposta_id); (declarada_em) | idem | permanente (é a memória científica) | DROP |
| `trafego_realizado` | O que de fato aconteceu na janela do horizonte, medido com a mesma régua | realizado_id uuid PK; previsao_id FK UNIQUE; valor_observado numeric NULL; janela_inicio/fim date; lido_em timestamptz; fonte text | 1:1 com previsão | (previsao_id) | idem | permanente | DROP |
| `trafego_critica_llm` | Auditoria da crítica: o que o modelo viu, o que respondeu, quanto custou | critica_id uuid PK; proposta_id FK; contexto_hash text; modelo text; prompt_versao text; estado text CHECK (explicada/indisponivel/resposta_rejeitada/nao_configurada); resposta jsonb NULL; latencia_ms int; custo_estimado numeric NULL; criada_em | por (proposta, prompt_versao) | (proposta_id) | idem | 12 meses | DROP |
| `trafego_job` | Fila e heartbeat das rotinas (P02-T04): recibo de rotina, owner, idempotência | job_id uuid PK; tipo text; escopo text (ex.: customer_id); chave_idempotencia text UNIQUE; estado CHECK (pendente/rodando/sucesso/erro); iniciado_em/terminado_em; erro text NULL; owner text | chave por (tipo, escopo, janela) | (estado, tipo); parcial WHERE estado='rodando' | idem | 90 dias | DROP |
| `vw_decisao_central` (view) | Central de decisões do frontend: propostas + estado + campanha + veredito numa projeção só de leitura | join proposta×diagnóstico×aprovação×aplicação×campanha | — | — | security_invoker, service_role | — | DROP VIEW |

Regras transversais: toda coluna de métrica é NULLABLE (ausência ≠ zero); toda
linha carrega `lido_em` e janela; `origem` distingue conta/planilha/estimativa
(padrão v10_02 `trafego_evidencia`); versionamento de política referencia
`trafego_regra_otimizacao.regra_id` (a versão exata, não a chave).

**Correções no existente (migrations propostas, não aplicadas):**
1. `REVOKE ALL ... FROM anon, authenticated` nominal nas 6 tabelas legadas
   (`campaigns`, `daily_campaign_metrics`, `users`, `projects`,
   `operational_costs`, `user_campaigns`) + política de leitura explícita onde o
   front realmente precisa (BLOCKER confirmado ao vivo nesta missão).
2. FK (`NOT VALID` → `VALIDATE`) de `daily_campaign_metrics.campaign_id` →
   `campaigns.campaign_id` ou migração de leitura para `trafego_campanha`.
3. Corrigir cabeçalho defasado de `v9_01_trafego_inventario.sql` ("NAO APLICADO"
   → aplicado em 25/08, confirmado no banco).

## 6. Ciência de decisão

**O que o Lab já mede:** conformidade determinística (replay dourado 8/8 — 4
saídas: estado da leitura, veredito, health gate, nº de propostas) e contraprovas
fail-closed (28 testes).

**O que passa a ser mensurável com o delta §5 (e só com ele):**

| Métrica | Como | Pré-requisito |
|---|---|---|
| Falso positivo/negativo | proposta emitida × decisão humana × efeito verificado | v10_02 aplicada + rotulagem da recusa (motivo já obrigatório) |
| Erro de previsão | `trafego_previsao` × `trafego_realizado` | §5 |
| Uplift / mudança causada vs externa | comparação com contrafactual declarado: campanhas-controle da mesma conta OU janela pré/pós com ajuste sazonal simples; declarar o método na previsão | §5 + ≥1 conta com contas-espelho |
| Valor esperado / margem | previsão de margem_micros vs realizado (receita externa já anulável) | ledger de receita saudável (P06) |
| Drawdown | série de margem por campanha pós-aplicação | §5 |
| Tempo até efeito | primeira janela em que o realizado difere do baseline além do ruído | §5 |
| Regressão à média | efeito medido em janelas 7/14/28 d decaindo | §5 |
| Sazonalidade | baseline por dia-da-semana no contrafactual. **Correção obrigatória antes de qualquer uso real:** o `cost_spike` atual usa mediana simples e foi reproduzido gerando falso positivo — série 3,5M/3,5M/7,0M (fim de semana → segunda) dá ratio 2,0 ≥ 1,75, emite evento, fecha o health gate e bloqueia proposta legítima. Enquanto não houver ≥ 14 dias de histórico e baseline por dia-da-semana, esse evento deve nascer "não apurado", nunca como veto | histórico ≥ 4 semanas |
| Atraso de conversão | `atraso_conversao_dias` da regra × janela do realizado (campo já existe em `RegraDeOtimizacao`) | coleta com conversions por data de conversão vs clique |

**Replay as-of e shadow sem vazamento:** replay = reexecutar o kernel sobre
`trafego_fotografia` com `agora := as_of` da fotografia (o kernel já recebe
relógio explícito e recusa futuro). Shadow = worker roda o pipeline completo em
produção **sem executor**, persistindo proposta+previsão com marca `shadow=true`;
comparação com o que o humano fez de fato. Regra dura: nenhuma feature pode ler
tabela sem filtro `lido_em <= as_of` (revisão de código exigida em todo coletor).

**Thresholds:**
- *Universais:* invariantes estruturais — frescor máximo, janela mínima,
  amostra mínima, limite de alteração por passo, cooldown mínimo. Já são campos
  obrigatórios da `RegraDeOtimizacao`.
- *Por conta:* ROAS/margem-alvo, teto de orçamento, RPC de referência (arbitragem
  vive de spread por conta), loss caps.
- *Por canal:* tudo que depende de leilão — impression share, Quality Score
  (Search-only), CPC de referência; Demand Gen/PMax exigem perfis próprios
  (dados de search term de PMax nem saem em `search_term_view`).
- *Aprendidos (futuro, com §5):* cost_spike por dia-da-semana, histerese ótima,
  tamanho de passo.
- *Não decidíveis hoje:* qualquer número de T3, uplift mínimo para
  auto-aprovação, thresholds de pausa definitiva — faltam dados de acurácia.

## 7. Autonomia T0–T3

| Nível | Pode | Aprovação | Limites monetários | Reversibilidade | Cooldown | Canário | Recibo | Kill switch | Pré-requisitos |
|---|---|---|---|---|---|---|---|---|---|
| **T0 observar** | coletar, diagnosticar, emitir evento/ocorrência | — | 0 mutação | n/a | n/a | n/a | heartbeat de rotina | parar worker | v10_02 aplicada (para persistir) |
| **T1 recomendar** | tudo de T0 + proposta tipada com diff, teto e prazo | humano decide depois | proposta recusada no INSERT se estourar `limite_alteracao_pct/absoluto` ou teto da regra | proposta expira sozinha | por (regra, alvo) via `trafego_cooldown` | n/a | proposta+aprovação append-only | despublicar regra (`retirada_em`) | regras publicadas com owner/versão/teste |
| **T2 executar após aprovação** | aplicar exatamente o diff aprovado | **obrigatória, prévia, por proposta** (gatilho já exige) | passo ≤ limite da regra; teto por conta; orçamento nunca abaixo do floor | rollback pré-declarado (`condicao_rollback`, janela) + `trafego_atuacao_reversao` | idem + cooldown pós-aplicação | primeira aplicação de cada regra nova = 1 campanha, menor passo, releitura em 24 h | `trafego_aplicacao` em_voo→desfecho + verificação remota | `FORGE_PERMITIR_ESCRITA` removida ⇒ nada escreve | shadow ≥ N semanas com FP aceitável; **não autorizado nesta missão** |
| **T3 autonomia limitada** | aplicar sem aprovação prévia dentro de um envelope estreito pré-autorizado (ex.: reduzir lance ≤10 % com margem negativa 3 d) | envelope aprovado pelo dono por escrito; cada aplicação ainda gera aprovação retroativa auditável | envelope com teto diário e mensal por conta | idênticos a T2 + reversão automática se verificação falhar | dobro do T2 | obrigatório por regra e por conta | idem T2 | kill switch por conta e global | T2 estável + acurácia medida (§6) + **mudança de CHECK no banco (hoje T2/T3 são recusados pelo vocabulário — é proposital)**; **não autorizado nesta missão** |

## 8. LLM e Hermes/Bia

- **Contexto permitido (allowlist, já implementada):** `scenario_id`/campanha,
  veredito, health gate, fatores, políticas (id/versão/resultado), conflitos,
  evidências publicáveis. **Limite:** 48 KB (constante existente).
- **Campos proibidos:** diff bruto, autorização, aplicação, segredos, GAQL cru,
  payload de mutação, qualquer identificador de credencial. A resposta com campo
  extra é rejeitada inteira (comportamento testado).
- **Ferramentas da Bia/Hermes:** somente endpoints de leitura da projeção
  (`/trafego/...`), nunca Supabase direto, nunca Google Ads direto (P09-T06:
  gateway read-only é tarefa própria).
- **Output schema:** `{resumo, questoes[], campos_considerados[]}` — inalterado.
- **Timeout/fallback:** timeout curto (proposto: 10 s) ⇒ `indisponivel`; o
  veredito determinístico segue sem crítica. Fallback = `CriticoDeterministico`.
- **Prompt-injection boundary:** o contexto é dado, não instrução: search terms
  e nomes de campanha entram como valores JSON; instrução do sistema fixa; a
  resposta não executa ferramenta nenhuma; validador de schema é código, não
  modelo. Term "ignore previous instructions" num search term não tem para onde
  escapar — o pior caso é um resumo ruim, rejeitado por schema.
- **Auditoria/custo/telemetria:** `trafego_critica_llm` (§5) com hash do
  contexto, versão do prompt, latência e custo estimado.
- **Como a Bia explica:** botões contextuais no frontend chamam
  `POST /trafego/critica/{proposta_id}` (a criar) que roda a PortaCritica sobre a
  proposta persistida e devolve o resumo; a explicação exibida carrega o selo
  "explicação, não decisão" e **nunca altera** o veredito canônico (que é coluna
  do ledger, escrita só pelo kernel).

## 9. Frontend — experiência de operação assistida

**Estado atual (auditado):** Lab navegável com 6+ ramos de estado, selo
PROTÓTIPO triplicado, acessibilidade sólida (roles, focus, tokens); caixa de
propostas e portão de aprovação existem como componentes ricos mas `aoSubmeter`
não é conectado por nenhum caller de produção (aprovação é UI morta hoje);
jargão técnico vaza (v25/v25.1, `regra_id`, paths `daily_metrics.*`) sem teste
de sanitização equivalente ao do inventário.

**Mapa de informação (fato ≠ diagnóstico ≠ sugestão ≠ decisão ≠ execução):**

| Camada | Vocabulário visual | Fonte |
|---|---|---|
| Fato | número + origem + idade ("lido há 2 h") | evidência/fotografia |
| Diagnóstico | EscadaDeEntrega (degraus ok/limita/bloqueia/não apurado) | `trafego_diagnostico` |
| Sugestão | CaixaDePropostas com diff antes/depois + confiança + amostra | `trafego_proposta` |
| Decisão | PortaoDeAprovacao (quem, quando, o que foi mostrado) | `trafego_aprovacao` |
| Execução | CartaoDeRecibo (aceito/recusado/parcial + verificação) | `trafego_aplicacao` |
| Explicação | balão da Bia com selo "explicação" | crítica LLM |

**Rotas:**

```text
/trafego                                  Hub (existe) + fila "decisões aguardando você" (novo)
/trafego/campanhas/:id                    Cockpit (existe) + abas: Diagnóstico | Propostas | Timeline | Recibos
/trafego/decisoes                         Central de decisões (novo; vw_decisao_central)
/trafego/decisoes/:propostaId             Detalhe: evidência → diff → conflitos → aprovação
/trafego/politicas                        Regras publicadas: versão, owner, limites, cooldowns (novo, leitura)
/trafego/shadow                           Placar shadow: proposta × decisão humana × efeito (novo, fase shadow)
/trafego/laboratorio/inteligencia/:id     Lab sintético (existe; permanece rotulado PROTÓTIPO)
```

**Wireframe — central de decisões:**

```text
┌ Central de decisões ──────────────────────────────────────────────┐
│ [3 aguardando] [1 em cooldown] [shadow ativo: 2 contas]           │
├───────────────────────────────────────────────────────────────────┤
│ ▸ Portal Mundo Mais · Campanha FGTS                               │
│   SUGESTÃO  Revisar aumento de orçamento   confiança alta         │
│   R$ 10,00/dia → proposto: revisar (teto da regra: +20 %)         │
│   evidência: perda por verba 34 % · margem positiva · lido há 3 h │
│   conflitos: nenhum veto                     [ver e decidir →]    │
│ ▸ Crédito Up · Maquininha                                         │
│   BLOQUEADA  cooldown até 29/08 14:00 · margem não sustenta       │
├───────────────────────────────────────────────────────────────────┤
│ Decididas hoje: 2 aprovadas · 1 recusada (motivo registrado)      │
└───────────────────────────────────────────────────────────────────┘
```

**Wireframe — detalhe da proposta (aprovação):**

```text
┌ Proposta prop-4f2… · Revisar aumento de orçamento ────────────────┐
│ POR QUÊ (fatos)      │ O QUE MUDA (diff)      │ GUARDAS           │
│ • perda por verba 34%│ orçamento/dia          │ ✓ margem positiva │
│   (janela 3 d,       │  antes: R$ 10,00       │ ✓ sem cooldown    │
│    lido há 3 h)      │  depois: A DEFINIR     │ ✓ saúde liberada  │
│ • qualidade saudável │  teto regra: +20 %     │ ✗ passo é humano  │
│ [explicar ➜ Bia]     │ prazo: expira 30/08    │                   │
├───────────────────────────────────────────────────────────────────┤
│ [Recusar (motivo obrigatório)]        [Aprovar exatamente isto]   │
│ Sua decisão fica registrada com o que esta tela mostrou.          │
└───────────────────────────────────────────────────────────────────┘
```

**Estados obrigatórios por superfície:** loading (skeleton), vazio confirmado
("lido e não há nada" ≠ falha), parcial (mostra o que há + o que falta), stale
(idade visível + por que não recomenda), erro com última boa, indisponível sem
fotografia. O Lab já implementa o padrão; a central herda.

**Proibições:** GAQL, payload cru, stack trace, `idempotency_key` (mesmo
truncada), `regra_id` cru e namespace de API saem da superfície de operador
(ficam em "detalhes técnicos" colapsado ou só no modo calibrador); teste de
sanitização novo em `laboratorio/__tests__` espelhando
`erros-sanitizados.test.tsx`.

**Permissões:** operador (vê, decide com identidade), calibrador (vê parâmetros
de política), admin (publica/retira regra). Botão de aprovar exige sessão com
identidade real (`decidida_por` não vazio — CHECK já existe).

## 10. Observabilidade e segurança

- Heartbeat por rotina em `trafego_job` (§5) alimenta `routine_stale` (política
  existente) e o Ads Health Monitor (P06-T06).
- Logs JSON no worker com `job_id`/`chave_idempotencia`; nada de métrica de
  negócio em log (vive no ledger).
- Segredos: só no host (`.env` root-only) e no executor; coletor com credencial
  read-only própria; frontend nunca recebe service_role (o BLOCKER de grants do
  legado tem correção própria em §5).
- Kill switches em camadas: remover `FORGE_PERMITIR_ESCRITA` (nada escreve),
  retirar regra (`retirada_em`), parar timer do worker, e o CHECK do banco que
  recusa aplicação sem aprovação.

## 11. Critérios de aceite da v1 (fatia por fatia)

1. **Shadow-read (próxima fatia, sem trava aberta):** coletor GAQL read-only
   materializa `trafego_fotografia` de ≥1 conta real; kernel roda sobre ela; replay
   as-of reproduz o resultado byte a byte; nenhuma escrita fora do Supabase oficial.
2. **Ledger ligado:** v10_01+v10_02 aplicadas (autorização do dono) + writer
   Python testado para evidência/diagnóstico/proposta.
3. **Aprovação viva:** `aoSubmeter` conectado a endpoint que grava
   `trafego_aprovacao`; teste de contrato UI→banco.
4. **Paridade legado:** por N dias, diff diário orientação-legada vs diagnóstico
   novo; ao atingir paridade explicada, desligar produtor legado e migrar o que
   restar do Supabase hospedado.
5. **T2 só depois:** shadow com FP/FN medidos (§6) e canário de aplicação de
   menor passo — fora do escopo desta missão.
