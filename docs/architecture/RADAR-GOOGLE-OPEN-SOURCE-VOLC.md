# Radar Google Open Source — decisão arquitetural VOLC O.S.

Data da revisão: 27/08/2026  
Fonte recebida: `VOLC-OS-Arbitragem-Radar-Google-Open-Source.docx`  
Escopo: transformar referências públicas do ecossistema Google em componentes proprietários coerentes com o VOLC O.S., sem instalar soluções inteiras por entusiasmo.

## Decisão em uma frase

O VOLC O.S. não será uma colagem de repositórios Google. Ele absorverá padrões comprovados em oito módulos proprietários: **registro de pipelines, saúde de mídia, inteligência Search, governança de tracking, radar de tópicos, governança criativa, laboratório de impacto e gateway agêntico somente leitura**.

Esses módulos obedecem ao mesmo fluxo:

```text
fontes reais
  → ingestão com recibo e frescor
  → fatos versionados
  → saúde e anomalias
  → diagnóstico explicável
  → experimento controlado
  → decisão humana
  → ação limitada, idempotente e reversível
```

Nenhum item deste radar autoriza instalação, credencial, migration, deploy ou mutação em campanha.

## O que já existe e não deve ser reinventado

- Inventário Google Ads real, com presença, ausência e frescor.
- Contrato de campanha, prova, criação pausada, recibo e trava de escrita.
- Critérios e negativas tipados no engine Search.
- Motor de diagnóstico e propostas assistidas em evolução.
- Inventário sanitizado dos workflows n8n.
- Engines próprios de imagem e vídeo, linhagem de asset e Estúdio Criativo em integração.
- Especificação da Data Manager API para o loop de conversão offline.
- Especificação do Meridian em `shadow mode`, sem autoridade operacional.

As referências abaixo devem fechar elos entre essas capacidades — não abrir produtos paralelos.

## Oito módulos proprietários resultantes

| Módulo VOLC | Estado honesto | O que incorpora | O que não incorpora |
|---|---|---|---|
| VOLC Data Pipeline Registry | planejado | jobs, runs, schedules, owner, heartbeat, retry, fonte, destino, recibo | instalação integral do CRMint |
| VOLC Ads Health Monitor | parcial | coleta padronizada, baseline, severidade, deduplicação, quiet-on-ok, histórico | Grafana/Prometheus como requisito imediato |
| VOLC Search Intelligence | parcial | escala, Quality Score, impression share, termos, negativas e conflitos de negativas | uma segunda engine de Search |
| VOLC Tracking Control Plane | planejado | inventário GA4/GTM, eventos, UTMs, conversões, drift e linhagem | alteração em massa sem proposta e aprovação |
| VOLC Topic Radar | parcial | Trends, Search Console, GA4, termos, RPM, sazonalidade e risco | duplicação do Pautador |
| VOLC Creative Governance | parcial | geração, adaptação, biblioteca, experimento, aprovação, linhagem e destino | substituição dos motores PRENSA/Imagem/Vídeo |
| VOLC Intervention Impact Lab | planejado | desenho experimental, MDE, controle, intervenção e efeito com intervalo | confundir pré/pós simples com causalidade ou MMM |
| VOLC Ads Agent Gateway | planejado | consulta contextual somente leitura para Bia/Hermes | MCP com mutate ou segredo no navegador |

## Veredito item a item

Legenda: **extrair agora** = incorporar padrão ao contrato atual; **spike** = prova isolada e comparativa; **referência** = não entra no runtime; **estacionar** = fora do foco atual.

| Projeto | Situação verificada | Veredito VOLC | Extração concreta | Encaixe |
|---|---|---|---|---|
| [ads-monitor](https://github.com/google-marketing-solutions/ads-monitor) | ativo; Google Ads API → gaarf exporter → Prometheus → Grafana/Alertmanager | **extrair agora** | catálogo de métricas, baselines, regras, severidade, deduplicação e resolução | Ads Health Monitor; P06 |
| [crmint](https://github.com/google-marketing-solutions/crmint) | ativo; UI para criar, executar e agendar pipelines | **extrair agora, não instalar** | contrato de source/job/run/schedule/log/owner/retry | Data Pipeline Registry; P10 |
| [arba](https://github.com/google-marketing-solutions/arba) | ativo; Ad Rank/Quality Score, BigQuery, Looker, Vertex/Gemini | **spike de consultas e regras** | causas de perda de escala por budget, rank, CTR esperado, relevância e landing | Search Intelligence; P05/P06 |
| [negative_keyword_cleaner](https://github.com/google-marketing-solutions/negative_keyword_cleaner) | ativo; detecta **negativas existentes que bloqueiam tráfego** | **extrair agora como auditor de conflito** | desnegativação proposta, evidência do bloqueio e aprovação; não é minerador de termos ruins | Search Intelligence; P05 |
| [ga4_dataform](https://github.com/google-marketing-solutions/ga4_dataform) | ativo; modelos Dataform para exportação GA4 no BigQuery | **spike condicionado** | modelo raw → sessão → landing → aquisição → qualidade | Tracking Control Plane; somente após export GA4/BQ real |
| [ga4-gtm-utilities](https://github.com/google-marketing-solutions/ga4-gtm-utilities) | ativo; Apps Script/Sheets lista e altera tags, parâmetros e variáveis | **extrair inventário; bloquear escrita** | drift, dependências, changelog e proposta de alteração | Tracking Control Plane; P06/P08 |
| [google-analytics-utilities](https://github.com/google-marketing-solutions/google-analytics-utilities) | ativo; inventário de configurações GA4 | **extrair agora em leitura** | contas, propriedades, streams, dimensões, eventos e vínculos Ads | Tracking Control Plane; P06/P08 |
| [topic-mine](https://github.com/google-marketing-solutions/topic-mine) | ativo; combina dados próprios/externos e Gemini para temas, keywords e copy | **gap analysis com Pautador** | sinais de tendência e ranking de oportunidade; manter um único motor de pauta | Topic Radar; P08 |
| [pMaximizer](https://github.com/google-marketing-solutions/pmax_best_practices_dashboard) | ativo; monitoramento de PMax/assets em Looker sobre Gaarf/BigQuery | **spike quando PMax existir** | manifesto de asset group, cobertura e qualidade de assets | PMax observability; P04 |
| [ml_toast](https://github.com/google-marketing-solutions/ml_toast) | arquivado | **referência** | clustering multilíngue e janelas; reimplementar apenas se necessário | Search Intelligence/Topic Radar |
| [Causmos](https://github.com/google-marketing-solutions/causmos) | ativo; Causal Impact para uma intervenção usando Ads/Analytics/Sheets/CSV | **spike isolado** | registro de intervenção, série contrafactual, efeito e intervalo | Intervention Impact Lab; P15 |
| [Meridian](https://github.com/google/meridian) | ativo; framework MMM | **já aceito, implementar depois** | contribuição, saturação e cenários agregados; nunca intradiário | P15 e SPEC Meridian |
| [FeedX](https://github.com/google-marketing-solutions/feedx) | ativo; experimentos de feed com potência, CUPED/crossover e grande número de itens | **referência de desenho experimental** | MDE, simulação, washout, controle/tratamento e outliers | Intervention Impact Lab; não usar para budget/bid |
| [fractional_uplift](https://github.com/google-marketing-solutions/fractional_uplift) | arquivado | **referência** | princípio de uplift condicionado a custo | laboratório futuro, sem dependência produtiva |
| [if-this-then-ad](https://github.com/google-marketing-solutions/if-this-then-ad) | ativo e capaz de alterar Google Ads/DV360 por eventos | **extrair padrão, não instalar** | regra de evento → recomendação → aprovação; alvo nunca é chamado diretamente | eventos operacionais; P09/P10 |
| [copycat](https://github.com/google-marketing-solutions/copycat) | ativo; geração de Search Ads alinhada à marca | **gap analysis** | consistência de marca, variações e revisão; comparar com engine Search atual | Search drafting; P05 |
| [adios](https://github.com/google-marketing-solutions/adios) | ativo; geração, biblioteca, associação e experimentos de image assets | **gap analysis prioritário** | ciclo asset → aprovação → biblioteca → vínculo → experimento | Creative Governance; P04/Estúdio |
| [vigenair](https://github.com/google-marketing-solutions/vigenair) | ativo; recrafting de vídeo em formatos/durações | **gap analysis com Motor de Vídeo** | variantes por inventário, duração, orientação e QA | Creative Governance; P04/Estúdio |
| [feedgen](https://github.com/google-marketing-solutions/feedgen) | ativo; otimização generativa de Shopping feeds | **estacionar** | scoring de título/descrição/imagem pode ser reaproveitado depois | Shopping não é frente operacional atual |
| [argon](https://github.com/google-marketing-solutions/argon) | arquivado/deprecated | **referência histórica** | arquitetura de relatórios CM360/DV360 → BigQuery | não instalar |
| [crystalvalue](https://github.com/google-marketing-solutions/crystalvalue) | ativo; pLTV em Vertex AI | **estacionar neste cérebro** | útil para lead/recorrência, não para arbitragem editorial imediata | portfólio VOLC futuro |
| [google/skills](https://github.com/google/skills) | ativo; skills para agentes/devs | **usar como referência de implementação** | Ads diagnostics, Data Manager, GA4 APIs, BigQuery, lineage, monitoring e segurança agêntica | engenharia e checklists; não é feature do produto |

## Correções e lacunas do documento recebido

1. `negative_keyword_cleaner` estava descrito como fonte para criar negativas. A finalidade declarada no repositório é encontrar negativas irrelevantes que **bloqueiam** tráfego. O VOLC precisa das duas direções, mas não deve misturá-las.
2. `gen-v` e `adspace_agent` aparecem sem URL ou identidade verificável. Permanecem na inbox e não ganham nó de sistema nem tarefa até a fonte ser informada.
3. Vários projetos de `google-marketing-solutions` declaram explicitamente que não são produtos Google oficialmente suportados. “Repositório de organização Google” não equivale a SLA, suporte ou adequação produtiva.
4. FeedX não é ferramenta geral de experimento de campanha. Ele foi desenhado para muitos itens de feed e não para orçamento/lance.
5. Causmos, Meridian e experimento randomizado respondem perguntas diferentes: intervenção pontual, contribuição agregada e teste controlado. O VOLC não os fundirá num único “score causal”.
6. Google skills são instruções para agentes. Devem melhorar nosso processo e nossos conectores, não aparecer como capacidades já implementadas.

## Ordem de execução orientada a caixa

### Agora — não bloquear o primeiro ROI

1. Consolidar custo, receita e frescor por conta/data.
2. Criar o contrato mínimo do Data Pipeline Registry e aplicar primeiro aos jobs que alimentam tráfego e monetização.
3. Entregar Ads Health Monitor mínimo: `delivery_stalled`, `data_freshness`, `cost_spike`, `click_drop` e rotina parada.
4. Levar Search Scale Diagnosis às campanhas Maquininha e FGTS: budget, rank, leilão, Quality Score, aprovação e volume.
5. Completar Search Terms Governance: termo candidato a negativa, conflito de negativa existente, decisão, recibo e reversão.

### Próximo — fechar aprendizado e escala

1. Fechar Data Manager API/event ingestion com fila idempotente e reconciliação.
2. Inventariar GA4/GTM em leitura e criar contrato de drift.
3. Confrontar Topic Mine com Pautador e incorporar apenas sinais ausentes.
4. Fazer gap analysis de Adios/Copycat/Vigenair contra engines proprietários.
5. Definir PMax observability antes de autorizar criação PMax.

### Depois — causalidade e agentes

1. Intervention Impact Lab com desenho de experimento, MDE e registro da intervenção.
2. Meridian com dataset semanal, EDA e `shadow mode`.
3. Google Ads MCP somente leitura atrás do backend/Hermes, com contexto filtrado e auditoria.
4. BigQuery/lineage quando volume e diversidade justificarem a nova infraestrutura.

### Estacionado conscientemente

- Argon, `ml_toast` e `fractional_uplift`: referência, não dependência.
- Feedgen e CrystalValue: válidos, mas fora do caminho atual para ROI de arbitragem.
- `gen-v` e `adspace_agent`: fonte ausente.

## Critério para qualquer spike

Todo spike deve terminar com cinco respostas registradas:

1. Qual pergunta operacional ele resolve que o VOLC ainda não resolve?
2. Qual padrão/código é reaproveitável sem criar um segundo sistema?
3. Qual dado, credencial e custo de infraestrutura exige?
4. Qual falha aberta, risco de política ou risco de mutação introduz?
5. O resultado é: incorporar, adaptar, apenas referenciar ou aposentar?

Sem essas respostas, o spike não muda status no grafo nem percentual no QG.

## Fontes e frescor

Metadados e READMEs foram conferidos nas páginas oficiais dos repositórios em 27/08/2026. O radar deve ser revisto quando um item for escolhido para spike; `ativo` aqui significa repositório não arquivado e com atividade observada, não maturidade ou suporte oficial.
