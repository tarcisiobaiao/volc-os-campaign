# HANDOFF-C — Identidade e atribuição

**Thread:** C · **Branch/worktree:** `lab/dil-fundacao-20261016-c` / `worktrees/dil-fundacao-20261016-c` · **Data:** 2026-10-16
**Estado:** `testado hermeticamente` + `testado com sintético`. Matriz cruzada com as leituras de produção do integrador
(RECIBO-LEITURAS-20261016 L3–L5). Nada rodando em shadow; nada calibrado além do que o recibo mediu.
Rede, produção, GTM, n8n, JoinAds, Google Ads: **não acessados** por esta thread. Nenhum `.env`/`~/.ssh` aberto.

## Arquivos

| Arquivo | Papel |
|---|---|
| `experiments/data-intelligence-lab/src/volc_dil/fundacao/identidade/__init__.py` | API pública |
| `…/identidade/normalizacao.py` | réplica fiel de `utmValue`/`clean`/`campaign()` (sensor v3), `safeValue` (wrapper v2), recorte do `cleanValue` (ingest) |
| `…/identidade/chave_campanha.py` | UTM/key-value → `campaign.id` ou recusa tipada |
| `…/identidade/resolvedor.py` | registro datado conta+id+nome+template; `Resolucao` com confiança |
| `…/identidade/graos.py` | matriz de grão como dado; `exigir_grao`, `receita_por_sessao`, `GraoNaoSuportado` |
| `…/identidade/colisao.py` | mesma UTM/duas campanhas, id em duas contas, renomeação, custom_key substituída, truncamento |
| `…/identidade/juncao.py` | `juntar_campanha_dia` custo × tráfego × receita com cobertura, null ≠ zero, sem rateio |
| `tests/data-intelligence/fundacao/test_identidade_{normalizacao,chave_e_resolvedor,colisao,ponta_a_ponta}.py` | 68 testes |
| `docs/data-intelligence/fundacao-20261016/03-MATRIZ-DE-ATRIBUICAO.md` | matriz, contradição, leituras externas, plano |
| `docs/data-intelligence/fundacao-20261016/receipts/identidade/gerar_vetores_sensor.mjs` | gera vetores executando o JS real (extraído do HTML) em Node |
| `…/receipts/identidade/vetores_utm_sensor_v3.json` | 65 nomeados + 3000 pseudoaleatórios (semente 20261016) + 11 cenários de `campaign()` |
| `…/receipts/identidade/RECIBO-IDENTIDADE.json` | recibo (fontes com sha256, comandos, contagens, mutantes) |

## Provas

- Vetores: Python × JS real = **0 divergências** em 65 + 3000 + 11. Comando de geração no cabeçalho do `.mjs` (Node v26.5.0, sem rede).
- Suíte: `OMP_NUM_THREADS=2 <venv>/python -m pytest tests/data-intelligence -q` → **240 passed** numa cópia do worktree com as
  fixtures de `backend/` que o checkout esparso não tem; no worktree esparso: **237 passed, 3 failed**, as 3 de
  `test_surrogate.py` por `FileNotFoundError` em `backend/app/trafego/shadow_experimentos/…/transformacao.csv` e
  `backend/tests/goldens/atribuicao-meta-adset-v1.json` (herdado do esparso; independente desta thread — no worktree do
  integrador as 172 herdadas seguem verdes).
- Mutantes: 10 aplicados, 10 mortos (lista no recibo).
- Contradição `utm_campaign`: P06-T09.`proof` (refs `043c77f5`, `4be92dfc`) × código `918e9571:measurement/gtm/volc-sensor-v3.html:73,107-125`
  × execução JS × produção L4. Veredito no doc 03 §5.

## Falhas e limites

- O mecanismo que leva o `campaign.id` cru à JoinAds **não foi identificado** (o wrapper v2 o descarta; hipótese: script
  `script.joinads.me`). Pendente: leitura L6 (GTM API) — consulta exata no doc 03 §6.
- Comprimento real de `ad_group.id` não lido (inferido ≥ 10 dígitos; vetor sintético de 12 dígitos cai).
- Formato de `land_uri`, fuso de fechamento JoinAds e existência de receita horária: não verificados.
- Não há versão versionada anterior do sensor/wrapper (v34 do GTM): `git log -S` só vê `918e9571`.
- `juntar_campanha_dia` assume que o chamador marca `EstadoMedida` honestamente nas entradas; um `0` vindo do legado
  `DEFAULT 0` entra como `medido`, nunca é promovido a `zero_confirmado`.
- Sessão = `sid` por aba (sem timeout); duas campanhas na mesma aba → `nao_atribuivel`. Tráfego aceita resolução
  probabilística (marcada em `confianca_sessoes`); receita só determinística.

## Riscos

- **Privacidade/PII:** o módulo não lê nem grava dado pessoal; os testes usam `sid` e `gclid` sintéticos
  (`CLIQUE_SINTETICO_NAO_REAL`) e um teste prova que o valor do gclid não chega ao `raw_events`. Os vetores incluem
  e-mails/CPF/telefone **fictícios** (`fulano@example.com`, `123.456.789-01`) para exercitar o filtro. O id de campanha
  `24278665189` e de conta `5478096539` aparecem (já públicos nos recibos do repositório; não são PII).
- **Proposta do passo 1 do plano** (isentar ids numéricos do filtro): 11 dígitos podem coincidir com um CPF; a isenção deve
  valer só para `utm_campaign`/`utm_content` e só para `^\d{6,20}$`, nunca para texto livre. Exige publicação de GTM
  (autorização do dono).
- O índice UNIQUE `(sid,pid,event_name,ts_sec)` colapsa eventos legítimos no mesmo segundo [P L3] — não afeta
  `volc_sensor_ready` (1 por pageview), afeta contagens de outros eventos.

## API pública (estável para as threads D/F/G)

```python
from volc_dil.fundacao.identidade import (
    normalizar_utm_sensor_v3, diagnosticar_utm_sensor_v3, normalizar_valor_wrapper_v2,
    utm_da_pagina_sensor_v3, UtmSessao, limpar_utm_ingest,
    interpretar_chave_campanha, interpretar_campanha_da_sessao, OrigemValor, MotivoRecusa,
    RegistroCampanhas, CampanhaRegistrada, TemplateCampanha, Resolucao,
    Confianca, Fonte, Grao, GraoTempo, MATRIZ, exigir_grao, receita_por_sessao, GraoNaoSuportado,
    detectar_colisoes_registro, detectar_custom_key_substituida, colisoes_de_normalizacao,
    CustoCampanhaDia, EventoSensorReady, ReceitaChaveDia, ReceitaDominioDia,
    juntar_campanha_dia, ResultadoJuncao, Cobertura, para_json,
)
```

## Delta de curadoria proposto (só proposta — o integrador aplica)

| Tarefa | Status proposto | Delta |
|---|---|---|
| **P08-T07** Versionar a telemetria comportamental | `partial` (mantém) | Acrescentar: "Sensor v3/wrapper v2/volc-ingest versionados só em `wip/historico-measurement-20261015` (`918e9571`), ausentes de `main`. Defeito provado: regex de PII ≥ 10 dígitos (`volc-sensor-v3.html:73,109`) descarta `utm_campaign={campaignid}` e `utm_content={adgroupid}`; produção 15–16/10: 0 de 28 sessões pagas com campaign (RECIBO-LEITURAS L4). Navegação/funil não junta com campanha; só `source/medium/term/paid`. Réplica testada em `volc_dil.fundacao.identidade` (0 divergências em 3076 vetores do JS real)." Lacuna: corrigir o filtro (GTM) e versionar o sensor em `main` |
| **P06-T07** Tracking Control Plane | `partial` (mantém) | Acrescentar: "Inventário de chaves ponta a ponta em `03-MATRIZ-DE-ATRIBUICAO.md`: Final URL suffix leva 13 parâmetros; o sensor preserva 3 (source/medium/term) + `paid`; o wrapper v2 não envia o id numérico ao GPT. Mecanismo do key-value numérico da JoinAds não identificado (L6 pendente). Drift detectável por vetores-ouro do JS (`receipts/identidade/`)." |
| **P05-T12** Plano canônico de mensuração no nascimento | `partial` (mantém) | Acrescentar critério: "o plano de mensuração de uma campanha Search deve declarar se `utm_campaign`/`utm_content` sobrevivem ao sensor (hoje não: id numérico é descartado); prontidão de sinal de tráfego por campanha = `nao_atribuivel` até a correção." Sem evidência nova de conversão |
| **P16-T05** Provisionar GTM/GA4 e validar o contrato de medição | `reserved` (mantém) | Registrar como insumo: "mudança proposta (isentar ids numéricos do filtro de PII só em `utm_campaign`/`utm_content`) exige publicação de GTM; teste de aceite = vetor-ouro novo + canário `payload->'utm'->>'campaign' ~ '^\d+$'` em `raw_events`." Nada autorizado/executado |
| **P13-T06** Provar uma oferta afiliada com atribuição | `todo` (mantém) | Acrescentar: "pré-condição de identidade: nenhuma fonte hoje liga clique/sessão a conversão (sem click id persistido; sensor só `paid=1`); atribuição afiliada exigiria subid por campanha (determinística só em campanha × dia) ou por sessão (decisão de privacidade)." |
| P06-T09 | `partial` (mantém) | Ver doc 03 §5.5 (mecanismo + L4 + L5) |

Nós afetados no Mapa Vivo (proposta): `concept:reconciliation`, `cap_attribution`, nó do sensor/telemetria (P08), JoinAds
(P06-T03). Arestas: `volc-sensor-v3 —descarta→ utm_campaign numérico`; `joinads key_value —liga→ google_ads campanha×dia`.
Trabalho só nesta branch: **não** marca fonte compartilhada como concluída.
