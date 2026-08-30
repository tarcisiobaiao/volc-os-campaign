# Resgate da inteligência proprietária n8n, ORAKUL e preditivo

> Estado factual em 28/08/2026 · fonte operacional oficial:
> `https://database.agenciavolc.com.br` · nenhum workflow foi ativado, executado
> ou alterado durante esta análise.

## Decisão executiva

O legado não será descartado nem reativado por nostalgia. Cada workflow será
tratado como uma cápsula de conhecimento: preservamos a fonte e sua genealogia,
extraímos a inteligência defensável, provamos o comportamento em replay e só
então escolhemos o sucessor.

A divisão permanente é:

| Camada | Responsabilidade |
| --- | --- |
| n8n | agenda, chamada autenticada ao backend, retry de transporte, heartbeat e notificação |
| backend VOLC | coleta, features, políticas versionadas, predição, arbitragem e propostas |
| Supabase oficial | fatos, evidências, versões, previsões, aprovações, recibos e resultados |
| frontend | explicação, revisão, confirmação humana e acompanhamento |
| Google Ads | uma única porta backend-only, autenticada, idempotente e reversível |

As fórmulas e políticas proprietárias não devem morar no browser nem continuar
espalhadas em Code nodes. O n8n pode continuar sendo uma boa engrenagem, mas não
o cofre do cérebro.

## Correção de versão da Google Ads API

Em 28/08/2026, a versão publicada mais recente é **v25.1**, lançada em
19/08/2026. A **v25.2 ainda não foi publicada**; deve existir um gate de revisão
quando ela sair. Os workflows analisados usam v21 e não podem ser religados sem
revisão de campos, operações, paginação, erros e máscaras.

Fontes oficiais:

- <https://developers.google.com/google-ads/api/docs/release-notes>
- <https://developers.google.com/google-ads/api/docs/sunset-dates>
- <https://developers.google.com/google-ads/api/fields/v25/search_term_view>
- <https://developers.google.com/google-ads/api/fields/v25/campaign_search_term_view>

## Inventário dos nove fluxos

### 1. GOOGLE ADS — New Campaigns Validation

- **ID:** `pjItRZhP2yrNyrDs`
- **estado declarado:** inativo
- **tamanho:** 44 nós, 486 linhas de código
- **papel histórico:** ajuste fino e diagnóstico no início da vida da campanha
- **destino:** guardião canônico das primeiras 72 horas, somente diagnóstico e
  proposta

O mesmo JSON contém duas versões incompatíveis. O ramo agendado usa NEXUS v4.9,
abre tarefa no ClickUp e não altera o Google; o ramo manual usa NEXUS v3.0,
consulta cooldown, grava no Supabase legado e chama um webhook de bidding. As
duas versões discordam sobre passos, maturidade, CTR e tetos.

O que vale preservar é a pergunta: “esta campanha já possui dado suficiente e,
se não entrega, qual causa precisa ser conferida?”. Não vale preservar regras
universais como “zero impressão autoriza lance fixo” ou “CTR acima de 3% autoriza
aumento”. Data inválida precisa virar `indeterminado`, nunca campanha madura.

**Integração alvo:** evento `campaign_onboarding_due` → coletor v25.1 → política
versionada → diagnóstico/proposta no ledger → cockpit. A primeira versão não
executa mudança.

### 2. ORAKUL V.OS AUTO ADJUST

- **ID:** `Q6IunKtTI0gY0KgX`
- **estado declarado:** inativo
- **tamanho:** 21 nós, 2.254 linhas; motor central Python com 1.678 linhas
- **execução histórica:** há mutações bem-sucedidas registradas em fevereiro
- **destino:** kernel privado de políticas, replay, shadow e proposta assistida

As joias reais são:

1. maturidade `EXPLORATION → CALIBRATION → PRODUCTION`;
2. histerese em dias consecutivos;
3. piso de orçamento e teto de perda;
4. evento externo pelo desacoplamento compra × venda;
5. lance ancorado no RPC medido;
6. fila de ações com prioridade, permissão e motivo de bloqueio;
7. cenários pessimista, realista e otimista.

As constantes são memória de negócio, não lei universal. Precisam de `rule_id`,
versão, owner, procedência, janela, idade máxima do dado, limite, rollback e
replay. O workflow atual tem cooldown e redistribuição mortos por inputs nunca
preenchidos, filtra silenciosamente estratégias que não sejam
`MAXIMIZE_CONVERSIONS`, permite propostas concorrentes de orçamento e pode
registrar erro como sucesso. Ele não deve ser reativado.

### 3. Bola de Cristal preditiva

- **ID:** `i21UFesZCR3nkMfN`
- **estado declarado:** inativo e manual
- **tamanho:** 46 nós, 1.102 linhas
- **papel histórico:** três bancadas A/B/C para prever gasto e receita D+1
- **destino:** serviço Python de forecasting com lifecycle próprio

A tese é valiosa: prever spend/receita e simular `planned_spend`. A implementação
atual não é utilizável: campanha e datas hardcoded, nenhuma previsão persistida,
vazamento de alvo, validação desalinhada, avaliação in-sample e intervalo não
calibrado.

O serviço novo precisa de:

- dataset `as-of`, apenas com features disponíveis no instante da previsão;
- baseline ingênuo lado a lado;
- treino e avaliação temporal;
- versões `candidate/challenger/champion/retired`;
- previsão append-only por campanha, alvo, data e cenário;
- avaliação posterior com MAE, WAPE, RMSE, bias, cobertura e largura do intervalo;
- drift de schema, ausência, frescor, feature e residual;
- promoção explícita, nunca auto-promoção;
- fallback `indisponível` ou baseline, nunca zero inventado.

Um challenger não influencia a decisão. Mesmo um champion apenas informa ou
veta uma proposta até existir decisão posterior de governança.

### 4. Atuação ORAKUL / insights no Webgo

- **ID:** `dbpKlrxR6B2pqiAs`
- **estado declarado:** ativo, cron 06:30 + gatilho manual
- **tamanho:** 61 nós, 4.812 linhas
- **papel comprovado:** gerar `orientacao_*` determinística e gravar no Supabase
  hospedado legado
- **destino:** timeline canônica de evidência, diagnóstico, proposta e resultado

Correção de linhagem: o ramo preditivo copiado neste workflow **não é alcançável
pelo cron das 06:30**. Ele nasce apenas no gatilho manual. O schedule executa o
motor determinístico de métricas, lance, insights, arbitragem e orientação.

O frontend atual lê `orientacao_*` no self-hosted, enquanto o escritor grava no
projeto hospedado legado. Essa autoridade partida explica por que a inteligência
não chega de forma confiável à tela. Não foi encontrada function/RPC local que
gere a orientação; os RPCs de `campaign_highlights` apenas rotacionam destaques.

O resgate do projeto legado `txvvzpstquqmbhljudfn` deve ser somente leitura:
exportar schema, functions, triggers, policies e contratos sanitizados, comparar
com o self-hosted e decidir objeto por objeto. Nunca trocar URL às cegas.

### 5. Search Terms upgrade KW

- **ID:** `svJWqv5r1NSxB8MO`
- **estado declarado:** inativo
- **tamanho:** 23 nós, 636 linhas
- **papel histórico:** promover, negativar, preservar, despromover ou deixar em
  limbo
- **destino:** Mesa de Termos de Busca no backend e cockpit

O fluxo usa `search_term_view`, compara keywords ativas e podia mutar critérios
de campanha/ad group. As categorias são úteis; os limiares fixos não são. CPA
de R$ 5, três cliques, 50 ou 100 impressões não podem governar toda vertical.

O VOLC já possui `Criterio` tipado, negativa/positiva, match type, nível,
procedência, motivo e evidência. Falta coletar e persistir termos reais, usar
margem/RPC, detectar o caminho inverso — negativa existente bloqueando tráfego
relevante — e passar tudo por proposta, aprovação e recibo. Search usa
`search_term_view`; Performance Max precisa de fonte distinta, como
`campaign_search_term_view`.

### 6. GTM DATA SCROLL — Funil

- **ID:** `GHMVIgFAv6oytKuj`
- **estado declarado:** inativo
- **tamanho:** 18 nós, 888 linhas
- **papel histórico:** orquestrar agregações de comportamento e emitir alertas
- **destino:** políticas versionadas sobre o sensor/SQL canônico

Ele não é o sensor: chama RPCs de página e funil, agrega scroll, engagement,
viewability, CTA, dead/rage click e cria alertas/ClickUp. Parte dessa infraestrutura
já existe no banco e no sensor atual. Duas ramificações ainda carregam datas
fixas e algumas heurísticas confundem amostra com diagnóstico.

Preservar as heurísticas úteis, retirar datas fixas e provar o agregador por run
datado. O cron pode ficar no pg_cron ou n8n, mas deve ter owner, watermark,
heartbeat, replay, contagens e erro persistido.

### 7. CTA Optimization — congruência da página

- **ID:** `awNXK3BdPTplsmKy`
- **estado declarado:** inativo
- **tamanho:** 14 nós, 587 linhas
- **agenda real:** semanal, segunda às 06h; o rótulo “diário” é falso
- **destino:** laboratório de experimento de CTA, não automação de copy

O fluxo cruza termos de busca, tenta inferir landing page pelo nome da campanha,
baixa HTML, extrai CTAs e pede a um LLM seis alternativas. Ele cria tarefa no
ClickUp; não altera a página. A identidade é frágil, métricas se perdem no
mapeamento, o acumulador não é idempotente e parte da copy pode criar urgência
manipulativa.

A feature nova deve partir de `volc_campaign_id → funil → URL`, gerar hipótese
com `before`, janela, amostra e evidência, exigir aprovação, publicar controle e
variante e registrar outcome. Nunca fazer POST WordPress a partir do analisador.

### 8. RSA Darwin Optimizer — CTR

- **ID:** `RYmky2S9FCy2dVuz`
- **estado declarado:** inativo
- **tamanho:** 21 nós, 612 linhas
- **agenda real:** semanal, quarta às 08h; não “a cada 15 dias”
- **destino:** observação de assets e experimento controlado no copy engine

O fluxo lê RSAs, `ad_group_ad_asset_view` e termos, mas agrega o texto no nível da
campanha e perde a identidade de ad group, anúncio e asset. Classifica assets por
share de impressões, mistura isso com causalidade e podia mutar o Google Ads sem
`validate_only`, aprovação, recibo, idempotência ou rollback. Não deve ser
reativado.

O sucessor precisa preservar `campaign/ad_group/ad/asset/resource_name`, ler
`performance_label`, `ad_strength` e `action_items`, exigir suficiência, mostrar
diff e testar um eixo por vez. Toda mutação usa o executor canônico.

### 9. Recomendador Semântico P3+

- **ID:** `NlDpiKPIqHCDblto`
- **estado declarado:** ativo, mas funcionalmente quebrado
- **tamanho:** 33 nós, 256 linhas
- **papel histórico:** escolher URL complementar no sitemap e gerar LazyBlock
- **destino:** convergir com Redator/FunnelForge; nenhum segundo recomendador

O caminho ativo consulta um sitemap fixo, mas o ramo de match bem-sucedido não
persiste nem retorna ao loop. “P3+” significa apenas índice de array `>= 2`. Uma
cópia manual desabilitada contém escrita WordPress hardcoded.

O Redator/FunnelForge já possui base melhor: sitemap real, same-domain,
eliminação de self/redundância e `cross_funnel`. Se o LazyBlock continuar útil,
deve virar renderer determinístico da recomendação canônica, com preview,
aprovação, publicação e resultado de clique.

## Modelo de dados alvo

Reusar o ledger de autogestão da migration `v10_02_autogestao.sql` para regra,
evidência, diagnóstico, proposta, aprovação, aplicação, follow-up, reversão e
cooldown. Não criar outro ledger de decisão.

Complementos necessários:

- `pipeline_run`: source/version, owner, heartbeat, watermark, contagens, status e erro;
- `behavior_observation`: página/funil/campanha, métrica nullable, N, janela, fonte e `lido_em`;
- `asset_observation`: identidade campaign/ad group/ad/asset e leitura;
- `experiment`, `experiment_variant`, `experiment_outcome`;
- `semantic_recommendation`: origem, destino, sitemap hash, score, motivo, aprovação e resultado;
- `forecast_model_versions`, `forecast_predictions`, `forecast_evaluations` e `forecast_drift_events`.

Invariantes: observado ≠ declarado; `null` ≠ zero; toda medida tem tempo e fonte;
escritas são idempotentes; fatos não recebem opinião; políticas têm versão; RLS é
forçada; service role fica apenas no backend.

## Superfícies do produto

### Campanha / Inteligência

- fatos e frescor;
- diagnóstico de onboarding e escala;
- termos, negativas e conflitos;
- assets RSA e propostas de experimento;
- previsão, baseline, intervalo e cobertura;
- timeline `evidência → diagnóstico → proposta → aprovação → aplicação → follow-up`.

### Redator / Funil / Experimentos

- scroll, engagement, dead/rage click e CTA;
- hipótese de CTA com controle/variante;
- preview da recomendação semântica;
- aprovação e resultado observado.

### QG / Registro de rotinas

- workflow ou job;
- classificação, owner, versão e sucessor;
- schedule, heartbeat, watermark, último sucesso e último erro;
- worktree/tarefa responsável pelo resgate.

## Fases de implantação

1. **Congelar:** export sanitizado, hash, classificação, owner e sucessor.
2. **Reproduzir:** golden fixtures e replay temporal sem I/O nem mutate.
3. **Shadow:** legado e novo recebem a mesma fotografia; divergências são explicadas.
4. **Recomendar:** front mostra proposta, nenhuma ação externa.
5. **Aprovar:** humano vê diff, evidência, limite, validade e rollback.
6. **Canário:** ação pequena, reversível, em porta única e com recibo.
7. **Acompanhar:** comparar o previsto/proposto com o ocorrido e suspender em drift.

## Proteção do patrimônio intelectual

“Anti-cópia” absoluta não existe. A proteção defensável é reduzir exposição,
controlar acesso e provar autoria:

- exports sanitizados e imutáveis com SHA-256;
- manifesto versionado com ID, linhagem, classificação e sucessor;
- fórmulas, thresholds e prompts somente em módulos server-side privados;
- políticas com versão, owner, fonte e hash;
- DTO mínimo para browser e n8n;
- referências de credencial, nunca segredo em JSON;
- private schema, RLS, menor privilégio e auditoria append-only;
- backups cifrados, logs de acesso, CODEOWNERS e branch protection;
- licença e proveniência em cada artefato/modelo.

Preservar não é expor. O grafo e o workbook registram o que a capacidade faz e
onde está; não precisam publicar a fórmula completa.
