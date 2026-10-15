# Núcleo operacional do engine Google Ads — execução de 14/10/2026

> **Errata (homologação de 14/10, run google-homologacao-20261014-01):** os "bloqueios" de CNPJ, contato e divulgação do card 106 foram emitidos sobre o HTML vazio de um 404. Não são fato sobre o site e são `interpretacao_volc`, não exigência do Google. O único bloqueio de plataforma é o destino indisponível (rascunho). A varredura foi corrigida.

Run `google-engine-nucleo-20261014-01` · checkout `volc-os-campaign-qg-real-20261007`,
`main` @ fb446595 + delta local · um integrador, três pesquisadores (A APIs, B economia, C dados).
Nenhuma mutação persistente no Google, nenhuma escrita no banco, migration, deploy ou push.

## 1. O que passou a funcionar

| Antes | Agora | Prova |
|---|---|---|
| `validate_only` aceito não deixava id da chamada (só a falha tinha `request_id`) | `/provar` devolve `preparo.prova_google` (request ID, versão, instante) nos 4 canais, fora do selo | validate_only real: `d-cek3xx80tm8NJ2Xj4IKg`, `SDeAi8SZ8xFRhKFHxNBWuQ`; 5 testes |
| Harness Gemini montava Brief próprio, fora do portão do conjunto pago, do destino e da doutrina P7 | `harness/canonico.py`: Gemini escreve só texto; o pedido passa pela rota `/provar` real | 1 geração `gemini-3.8-flash` (servido = pedido), 2.440 tokens, 6,06 s, ~US$ 0,0036 estimado; 40 operações aceitas; conta relida sem mudança; selo retido pelo destino |
| Escrita real de gestão reenviava às cegas `CONCURRENT_MODIFICATION` | escrita real não retenta concorrência (volta `falhou`, a próxima nasce de releitura); ensaio continua retentando | 2 testes |
| Exclusão de placement por campanha em PMax só falhava no Google, com erro genérico | `ExcluirPlacements` lê o canal e recusa PMax (só conta/lista) e campanha inexistente | 4 testes + catálogo v25 |
| Política: só `topic`/`type`; assets de campanha sem política | `evidences`/`constraints` preservados (restrição vazia vira contagem); `campaign_asset` traz a política do asset | leitura real: 734 linhas, 71 assets de campanha, 1 anúncio `FULLY_LIMITED` (documentos oficiais) com restrição declarada; 6 testes |

## 2. O que foi comprovado de verdade (por classe)

- **validate_only real**: replay da copy de 09/10 (42 ops) e copy Gemini (40 ops) pela rota canônica; atomicidade com `partial_failure=false` (uma operação adulterada derruba tudo; dependentes falham por ID temporário) e formato do erro parcial com `partial_failure=true` (RPC OK, 22/30 em erro, 8 assets sem erro — por isso criação fica atômica). Todas com releitura idêntica da conta.
- **Leitura real**: portão do conjunto pago em 6 clusters (só a oportunidade 106 passa); política da família `estado`; catálogo Gemini.
- **Sessão real do produto (leitura)**: operador logado em `localhost:8080`; a tela chamou 9 rotas autenticadas do backend com este delta, todas 200 (sem token: 401). Nenhum token lido.
- **Sintético rotulado** (pesquisa B): shrinkage, nowcasting e OPE — mecânica, não ganho.
- **Não comprovado**: `/provar` e `/subir` pela tela com a sessão (o assistente grava decisões no banco; fora da autorização), aprovação de política, serving, receita, lucro, ROI.

## 3. Cobertura dos três documentos

156 itens com origem e decisão em `INVENTARIO.json`/`INVENTARIO.md` (136 da semente + 20 descobertos):
integrar agora 4 · reutilizar 22 · extrair padrão 22 · sandbox 6 · adiar com pré-requisito 34 · rejeitar 63 · não verificável 5.
Vereditos sobre as alegações: 47 confirmadas, 56 parciais, 32 refutadas, 11 não verificáveis.

Correções do B3 sobre o B2: Tightlock (o "tightrope" não existe), Megalista arquivado e MCP oficial só leitura — **confirmadas**.
Data Manager "streaming" — **refutado** (RPCs unárias, todas com `validate_only`).
Continuam contestadas no próprio B3:
- "20.000 operações para AdGroupCriterion" não existe (o teto é 10.000 por request).
- "Retraction imediata" é falsa (a conversão precisa ter ≥24 h e ≤54 dias, e a retraction é terminal). Na Data Manager não há retraction.
- "Sem perda de histórico" ao promover não está na doc.
- O campo é `traffic_split`, não `traffic_split_percent`.
- Sazonalidade só altera taxa de conversão; o escopo por canal aceita só Display, Search e Shopping. Em Search, Shopping, Demand Gen e Display ela exige tCPA ou tROAS.
- Não se troca headline de RSA por "AdGroupAdOperation": a troca de texto é `AdService.MutateAds`, que reescreve a lista inteira, e headline não tem status pausável.
- M=20 não é universal (o ótimo é a dispersão real; com κ=500 o erro sobe 147%).
- Os fatores 65/90/95% não têm base nos dados da operação.
- `obp` 0.5.7 exige Python <3.11, e o pip recua sem avisar para a 0.4.1.

Refutados no B1/B2 (amostra):
- **Lances e lote:** BatchJob "obrigatório"; bid modifiers sob Smart Bidding; PID/scalper horário; "degrau de segundo preço".
- **Valor de conversão:** inflar o valor enviado (B27/B28); OfflineUserDataJobService para conversões de clique.
- **Infra e ferramentas:** ClickHouse/Redis/Ray/Bytewax para a escala real; a ferramenta "arf" de relevância de anúncios não existe; topic-mine foi descontinuado.
- **Política e dados:** página por clique no edge (cloaking e destino); "negativar a intenção inteira" por HDBSCAN (C: ARI 0,005, 9 de 176 termos valiosos marcados); o dataset do Transparency Center não cobre o Brasil.

## 4. Limites por canal

- **Search**: o caminho até `validate_only` + request ID está provado com dado real. O selo depende do destino. Hoje nenhuma oportunidade tem conjunto aprovado **e** LP publicada.
- **Display / Demand Gen / PMax**: o request ID vem pela mesma projeção, mas não houve prova real nova (falta mídia aprovada; PMax tem a barreira de mensuração).
  - Leitura de placement: PMax e adequação de conteúdo só trazem impressões.
  - Nenhuma doc oficial de placement cita Demand Gen.
  - PMax exclui placement só na conta ou por lista (agora com guarda).
- **Conversões / Data Manager**: nada enviado.
  - Não há identificador que ligue clique a receita: a ligação é UTM × campanha-dia.
  - O consentimento não é capturado.
- **Sazonalidade e experimentos**: só leitura/estudo. Nenhum foi criado.

## 5. Gemini, Google, custo e falhas

- Gemini: 1 geração de 4 permitidas. Preço oficial: US$ 0,75/1M de entrada e 3,75/1M de saída até 31/12/2026, e dobra em 2027. Custo estimado ~US$ 0,0036; o custo observado não foi informado pelo provedor (`null`).
- Google: 5 RPCs `validate_only` — 2 pela rota (aceitas), 1 recusada inteira (atomicidade, `partial_failure=false`) e 2 com `partial_failure=true` (a resposta da primeira se perdeu num import errado do meu script, depois do retorno da RPC; refeita) — mais leituras GAQL.
- Falhas:
  - meu script de atomicidade quebrou num import no ramo `partial_failure=true` (refeito);
  - o primeiro replay foi recusado pelo meu schema (sitelink de 36 caracteres na copy registrada em 09/10 — o builder já a descarta com aviso);
  - a primeira leitura de política não registrava restrição vazia (corrigido).

## 6. Lacunas que não são código

1. Publicar a LP 2477 (card 106) e as páginas de identidade do site (CNPJ, contato, divulgação de monetização) — sem isso nenhum selo vira `plano_impressao`.
2. Conjunto pago pelo motor Python nas oportunidades 65/73/74/104 (hoje vêm do n8n, sem contrato).
3. Snapshot "as-of" de receita e de custo, receita por `utm_content` (grupo), propensão e recompensa no ledger de decisão — impedimentos de nowcasting, shrinkage operacional e OPE.
4. Emenda da v17_04 (`receita_imatura` e checagem de fuso) antes de o dono aplicá-la. O câmbio continua congelado em 5,25 e há 5,50/5,35 fixos no front.

Pastas: `integrador/` (mapa, baseline, decisões), `recibos/` (sanitizados), `pesquisa-A-apis/`, `pesquisa-B-economia/`, `pesquisa-C-dados/`.
