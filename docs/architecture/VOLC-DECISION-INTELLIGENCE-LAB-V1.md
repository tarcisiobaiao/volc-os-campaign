# VOLC Decision Intelligence Lab v1

Status desta entrega isolada: **partial**. O corte é navegável e hermético, mas
não está integrado ao ledger operacional, não lê contas reais e não autoriza
ação.

## Escopo e autoridade

O laboratório prova uma cadeia única de decisão sobre contratos existentes. Ele
não é uma segunda engine e não substitui o Hub, o diagnóstico canônico, o schema
v10_02 ou o executor de campanhas.

Autoridades reutilizadas:

- `backend/app/trafego/intencao.py`: `RegraDeOtimizacao` e
  `avaliar_suficiencia`;
- `supabase/migrations/v10_02_autogestao.sql`: vocabulário de regra, evidência,
  diagnóstico, proposta, aprovação, aplicação, follow-up, reversão e cooldown;
- `src/types/diagnostico.ts`: contrato de diagnóstico e caixa;
- `EscadaDeEntrega`, `CaixaDePropostas`, `PropostaDeAcao` e
  `MolduraDePrototipo`: superfícies existentes;
- recibo existente: permanece `null` porque nenhuma aplicação ocorreu. Uma
  ação futura deve produzir o recibo canônico, nunca outro formato paralelo.

A migration v10_02 não foi aplicada nem modificada. A projeção deste corte é
compatível com o seu ciclo, mas vive somente em memória sobre JSON sintético.

## Arquitetura

```text
JSON sintético versionado
  -> validação, frescor e anti-futuro
  -> features anuláveis em Python
  -> RegraDeOtimizacao versionada
  -> eventos tipados e deduplicados
  -> conflitos e health gate
  -> diagnóstico canônico
  -> proposta T1 bloqueada e idempotente
  -> replay e comparação dourada
  -> projeção HTTP autenticada
  -> laboratório React sem cálculo decisório
```

Fronteiras:

| Camada | Caminho | Responsabilidade |
|---|---|---|
| domínio | `volc_ads/inteligencia_decisao` | validação, features, políticas, arbitragem, diagnóstico, proposta e replay |
| Search | `volc_ads/inteligencia_search` | normalização e conflito reverso de negativas |
| aplicação | `backend/app/trafego/inteligencia_lab.py` | catálogo e projeção do dataset, sem integração externa |
| HTTP | `backend/app/routers/trafego.py` | GET autenticado por `scenarioId` |
| apresentação | `src/pages/trafego/DecisionIntelligenceLabPage.tsx` e componentes | estado, navegação e leitura da projeção |

O endpoint é
`GET /api/trafego/laboratorio/inteligencia/{scenario_id}`. Ele não aceita
`volcCampaignId`, customer enviado pelo cliente ou qualquer corpo. O portão de
identidade já pertence ao `APIRouter` de Tráfego. A resposta declara zero
chamadas externas, zero mutações e exclusão das contagens reais.

## Linhagem preservada

Nenhum código dos repositórios externos ou workflows privados foi copiado.

- NEXUS vira a política `nexus_guardiao_72h`: campanha nova sem entrega é
  indeterminada quando a causa não foi observada. As versões históricas v3.0 e
  v4.9 não são portadas.
- ORAKUL vira `orakul_escala_com_guardas`: demanda pode favorecer revisão de
  verba, mas margem, cooldown e saúde arbitram antes da proposta.
- ARBA inspira a separação entre perda por orçamento, perda por rank, Quality
  Score e componentes. Nenhum fator vira score mágico.
- Ads Monitor inspira ocorrência com severidade, chave de deduplicação,
  resolução e health gate para `cost_spike` e `routine_stale`.
- If This Then Ad inspira `EventoDeDecisao -> PropostaTipada`. O runtime v14 e
  qualquer mutate direto ficam fora.
- Search Terms ganha o caminho inverso: negativa existente que bloqueia termo
  explicitamente valioso produz proposta de revisão, nunca remoção automática.

O commit histórico `28d2540f3375079726358c3583f56ab1bfa45bf3` foi inspecionado
sem cherry-pick. Foram reaproveitados os invariantes de fonte explícita, janela,
`lido_em`, métricas anuláveis e ausência separada de falha. Foram recusadas as
rotas por identidade de campanha e a coleta real de Google Ads/Supabase, pois
contradizem o isolamento desta missão.

## Dataset

Fonte: `volc_ads/inteligencia_decisao/dados/cenarios_dourados.json`.

O arquivo usa um retrato base e overrides completos por cenário. Ele é um
**contrato sintético normalizado**, ainda não um `GoogleAdsRow` capturado. O
manifesto `VOLC-DECISION-LAB-RAW-MAPPING.json` registra a fronteira que deverá
ser atravessada antes do shadow mode. O loader
materializa uma observação determinística com:

- `customer_id`, `campaign_id`, `ad_group_id`, `criterion_id`,
  `resource_name`, `date`, `status`, `channel` e `bidding` no grão aplicável;
- impressões, cliques, custo, conversões e valor de conversão anuláveis;
- impression share, lost budget e lost rank consultados no grão campanha +
  janela, sem `segments.date`; os percentuais diários nunca são promediados;
- Quality Score, relevância do anúncio, experiência da landing page e CTR
  esperado;
- search terms, keywords e negativas com `criterion_id` e match type;
- receita externa com fonte separada; o RPC estimado é `receita total / cliques`,
  nunca média de RPCs diários;
- fonte, estado de cobertura, janela e `lido_em`;
- rotina, último sucesso, action anterior e cooldown.

`null` significa ausente. Zero só aparece quando foi medido como zero. A soma
anulável devolve `null` se qualquer linha necessária está ausente. Datas fora
da janela, posteriores ao `as_of`, duplicadas ou declaradas para outra entidade
invalidam a fotografia e bloqueiam toda proposta.

### Cenários dourados

| ID | Prova dominante |
|---|---|
| `new-no-delivery` | campanha nova sem entrega, causa indeterminada |
| `budget-limited-healthy` | lost budget com qualidade saudável |
| `rank-limited-low-quality` | lost rank com Quality Score ruim |
| `valuable-term-blocked` | termo valioso bloqueado por negativa |
| `mature-margin-cooldown` | demanda existe, margem e cooldown vetam escala |
| `cost-spike-routine-stale` | spike de custo e heartbeat de rotina velho |
| `partial-read` | métricas ausentes permanecem nulas |
| `stale-read` | fotografia antiga não recomenda |

Estados adicionais navegáveis: vazio confirmado, falha com último bom, falha
sem fotografia e versão desconhecida. Loading é o estado transitório do hook e
tem skeleton próprio. Atual, stale e parcial usam a projeção do pipeline.

## Políticas e conflitos

As cinco regras referenciam o perfil fechado
`lab-calibracao-sintetica-v1`, definido em código versionado — a fotografia
não injeta thresholds. Elas usam
`RegraDeOtimizacao`, têm owner, versão, fonte, limites, rollback e autonomia T0
ou T1. Todas declaram `publicavel=false`. Seus predicados e parâmetros efetivos
viajam no contrato para auditoria humana. Eles existem para provar o
replay, não são regra universal nem tradução de literal histórico.

A ordem é invariável:

1. avaliar suficiência;
2. emitir evento tipado quando a condição foi observada;
3. avaliar conflitos;
4. fechar health gate;
5. emitir diagnóstico;
6. emitir proposta somente se os vetos permitirem.

Conflitos de margem, cooldown, frescor, leitura parcial, cost spike e rotina
stale vencem antes do veredito. Toda proposta inclui regra e versão,
`idempotency_key`, evento originador, evidências, antes/depois e bloqueios. A
aprovação fica `nao_submetida`, a aplicação `nao_executada` e o recibo `null`.

## Porta crítica opcional

`PortaCritica` recebe somente a allowlist:

`scenario_id`, veredito, health gate, fatores, políticas, conflitos e evidências
publicáveis.

A resposta aceita somente resumo, questões e campos considerados. Timeout,
exceção ou excesso de tamanho torna a crítica `indisponivel` sem derrubar o
kernel determinístico. Campo extra,
incluindo veredito, diff, autorização ou aplicação, rejeita a resposta inteira.
O fake determinístico não usa rede ou chave. A crítica é anexada depois da
decisão e não participa do cálculo, do conflito ou da autorização.

## Replay e avaliação

`executar_replay()` fixa o relógio em `2026-08-28T12:00:00Z`, materializa cada
fotografia, executa o pipeline e compara quatro saídas com o esperado:

- estado da leitura;
- tipo do veredito;
- estado do health gate;
- quantidade de propostas.

Comando hermético:

```bash
PYTHONPATH=backend:. python3 -c "from volc_ads.inteligencia_decisao import executar_replay; print(executar_replay())"
```

O endpoint inclui o resumo do replay para a UI. “Zero chamadas externas” vale
para o domínio do laboratório; o portão HTTP de identidade é uma fronteira
separada e pode consultar a fonte de autorização. Ele não executa shadow contra
conta real. Isso permanece requisito de integração antes de qualquer canário.

## Google Ads API

A verificação desta missão é local, sem rede, conforme a proibição de chamadas
externas:

- `docs/growth-engine/matriz-api/comum.md` e `fontes.json` registram namespace
  v25 e minor v25.1 publicada em 19/08/2026;
- o SDK local documentado cobre o namespace v25, com lacunas nas adições v25.1;
- a resposta do laboratório declara `namespace=v25`,
  `minor_documentada_localmente=v25.1` e `v25_2=nao_afirmada`.

Nenhuma afirmação de publicação da v25.2 é feita.

## Curation handoff

- tarefas: `P05-T06`, `P05-T07`, `P05-T08`, `P05-T09`, `P06-T06`,
  `P09-T08`, `P09-T09`;
- nós: `cap_decision`, `cap_health`, `cap_execution`,
  `concept:campaign_onboarding_guard`, `concept:orakul_policy_kernel`,
  `concept:ads_health_monitor`, `concept:search_intelligence`,
  `concept:search_terms_workbench`, `concept:decision_timeline`;
- estado proposto: `partial`;
- prova: pipeline puro, 8 cenários dourados, endpoint autenticado, rota
  navegável e estados explícitos;
- lacunas: grafo híbrido ausente nesta worktree, v10_02 não aplicada, nenhum
  `GoogleAdsRow` atravessando o normalizador produtivo, nenhuma persistência,
  shadow, aprovação, canário ou recibo de aplicação.
