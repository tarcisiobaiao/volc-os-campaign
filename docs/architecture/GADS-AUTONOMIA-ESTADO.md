# Autonomia no Google Ads: o que existe, o que falta (09/10/2026)

**Correção do fechamento de 08/10:** foi dito que a v17_02 "permite gestão sem
aprovação humana". Isso está errado. A v17_02 é **uma** de várias peças, não
está aplicada, e sozinha não faz a máquina aplicar nada. Nesta rodada **nenhuma
autonomia financeira foi habilitada**.

Fatos verificados no código (branch integrada ao `main` local em 09/10/2026):

- `backend/app/trafego/gestao/application/autonomia.py`:
  `NIVEIS_QUE_APLICAM_SEM_HUMANO = frozenset()`. É vazio de propósito; o módulo
  diz que três peças precisam entrar juntas.
- Não existe teto acumulado por campanha nem por conta (busca por
  `teto_acumulado`, `acumulado_diario` e `gasto_acumulado`: nada). A v17_02 só
  limita **cada ação** (≤ 20%).
- Não existe job, worker ou agendador que proponha ou aplique sozinho. Toda
  proposta nasce de `POST /api/trafego/gestao/propostas`, e toda criação nasce de
  `POST /api/trafego/subir`.
- No banco de produção não há regra de gestão publicada, e a v17_03 e a v17_02
  não estão aplicadas.

## As cinco categorias, separadas

| categoria | hoje | o que falta para ser automática | risco |
|---|---|---|---|
| **1. Criar campanha PAUSADA** | `/subir` exige admin, `confirmar_criacao_pausada=true`, motivo ≥ 10 caracteres, canário (só a conta 547-809-6539 sob o MCC 6016739364, teto de orçamento e CPC do canário, rede declarada), trava de dois fatores (`FORGE_PERMITIR_ESCRITA=1` + `destravar`), canal em `CANAIS_COM_CRIACAO_AUTORIZADA` (**só SEARCH**), portão de destino com recibo de aprovação | (a) canário aceito por canal para Display, DG e PMax, registrado e com o canal incluído em `CANAIS_COM_CRIACAO_AUTORIZADA`; (b) uma identidade de serviço (não humana) aceita por `/subir`, com escopo e teto próprios; (c) quem chama: um job que monte o pedido a partir da pauta e chame `/subir`; (d) recibo de aprovação do destino emitido antes; (e) teto diário de **quantidade** de campanhas criadas por conta | baixo em gasto (nasce PAUSADA), alto em poluição da conta e em política (anúncio reprovado conta contra a conta) |
| **2. Ativar** (PAUSED → ENABLED) | não há rota de ativação no nascimento. Ativar é a ação de gestão `status`, que exige proposta e aprovação humana | tudo da linha 3 **mais** uma regra que liste `status` com `status_permitidos=[ENABLED]`. **Ativar é o primeiro gasto real**: não deve entrar em autonomia antes do teto acumulado (linha 4) | alto: começa a gastar |
| **3. Gerir campanha ativa** (sem dinheiro: pausar, negativas, exclusões, agenda, ajustes, recomendações não financeiras) | rotas prontas, **com aprovação humana obrigatória**. Sem regra publicada → 409 `regra_ausente`. Sem a v17_03 aplicada, só `orcamento.diario` e `lance.alvo` viram proposta | (a) aplicar a v17_03; (b) publicar a regra de gestão (os números são do dono); (c) aplicar a v17_02; (d) T2 em `NIVEIS_QUE_APLICAM_SEM_HUMANO`; (e) o ramo de `Gestao.aplicar` que grava a aprovação com `decisor_tipo='regra'`; (f) uma regra T2 publicada listando as operações autônomas; (g) **um proponente automático** (job que leia os fatos e o diagnóstico e chame `propor`), que não existe; (h) `FORGE_PERMITIR_ESCRITA=1` no ambiente desse job; (i) monitoramento da tabela de suspensão (`trafego_autonomia_suspensao`) e alerta por aplicação | médio: pausar no momento errado custa receita; negativa errada corta tráfego bom |
| **4. Alterar orçamento** (e alvo de lance) | proposta com delta e limite percentual da regra, aprovação humana | tudo da linha 3 **mais um teto ACUMULADO diário por campanha e por conta**, que não existe. O limite por ação não basta: 5 aumentos de 20% no mesmo dia somam +149%. Falta: tabela ou view que some os deltas aplicados no dia (por campanha e por conta, na moeda da conta) e um gatilho que recuse a aplicação que estoure o teto; o teto é número do dono | **alto — não habilitado nesta rodada, por instrução** |
| **5. Irreversíveis** (REMOVED, troca de estratégia que zera o aprendizado, aplicar recomendação sem reverso) | `/remover` exige admin, trava e diário; a v17_03 proíbe REMOVED como ação de gestão; recomendação de verba e lance é recusada | **não automatizar.** Ficam humanos por desenho | — |

## Ordem recomendada (quando o dono decidir)

1. Aplicar a v17_03 e publicar a regra de gestão manual (T1). Gestão com
   aprovação humana passa a funcionar para as 15 ações.
2. Aplicar a v17_04 (arbitragem reconciliada), para que as propostas se apoiem
   em lucro reconciliado e não em soma de fontes.
3. Implementar o **teto acumulado diário** (migration + gatilho + teste) e só
   depois discutir a v17_02.
4. A v17_02 com autonomia restrita à linha 3 **sem** orçamento, com o proponente
   automático e o botão de suspensão testado em produção.
5. A criação automática pausada (linha 1) depende do canário aceito em cada
   canal e da identidade de serviço.

## Prova operacional de 09/10/2026 (main integrado, sem dublês além da identidade)

`scripts/smoke_gads_fluxo_real.py`: backend em processo, Supabase de produção
(leitura), Google real, mensuração e portões reais. **Única substituição
declarada: a identidade** (admin de teste no lugar do login). Trava de escrita
fechada (`FORGE_PERMITIR_ESCRITA` ausente). Recibo:
`/tmp/volc-gads-blindagem/testes/smoke-fluxo-real.json`.

| passo | resultado real |
|---|---|
| `GET /trava` | `escrita_permitida=false` |
| `GET /canais/esquema` | 4 canais: SEARCH, DISPLAY, DEMAND_GEN, PERFORMANCE_MAX |
| `GET /escopo` | MCC 601-673-9364 alcança só 547-809-6539 |
| `GET /candidatos/106?run_id=28` | projeto 2 vinculado à conta **801-785-1692, cancelada** (`CUSTOMER_NOT_ENABLED`); `SEM_CLUSTER` |
| `POST /provar` SEARCH (opp. 65, run 9), MANUAL_CPC e MAXIMIZE_CONVERSIONS | **409 `N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED`**: o cluster veio do n8n e não carrega `conjunto_pago`. Nada foi ao Google |
| `POST /gestao/propostas` (+10% Senac) | **409 `regra_ausente`**, nada gravado |
| `GET /gestao/recomendacoes` | 4 recomendações lidas do Google |

O que isso prova: com os dados de produção de hoje, **nenhuma oportunidade
chega ao `validate_only` pelo caminho HTTP**. A 106 não tem cluster; a 65, a
73 e a 74 têm clusters do n8n, recusados pela autoridade de elegibilidade paga
(`app.agents.mining.paid_eligibility`). O `validate_only` aceito nos quatro
canais em 08/10 usou dublês de oportunidade, conjunto pago e brief (contrato de
criação, §7); a camada do motor está provada, a cadeia real está parada antes
dela, por portão correto.

## Campanhas reais PAUSADAS por canal: plano, mídias, limites, autorizações

Conta: 547-809-6539 sob o MCC 601-673-9364. Nenhuma foi criada.

| canal | plano | mídias exigidas | limites vigentes | falta autorizar / resolver |
|---|---|---|---|---|
| **SEARCH** | RSA a partir do `conjunto_pago`; MANUAL_CPC no canário; só Google Search (sem parceiros, sem expansão) | nenhuma | teto R$ 20/dia; CPC ≤ R$ 1,00; nasce PAUSED | (1) oportunidade com `conjunto_pago` do motor Python; (2) destino elegível com recibo de aprovação; (3) `FORGE_PERMITIR_ESCRITA=1` + `destravar`; (4) admin humano com `confirmar_criacao_pausada` |
| **DISPLAY** | RDA; lance MANUAL_CPC/CPM ou TARGET_SPEND | ≥ 1 imagem paisagem + ≥ 1 quadrada (≤ 15); logo opcional (≤ 5) | teto R$ 20/dia; nasce PAUSED | tudo de Search **mais** o canário Display aceito e `DISPLAY` em `CANAIS_COM_CRIACAO_AUTORIZADA`; mídia aprovada para Google (hoje há 0) |
| **DEMAND_GEN** | multi-asset ou vídeo responsivo (vídeo só aqui e no PMax) | multi-asset: ≥ 1 par paisagem+quadrada, 1..5 logos; vídeo: 1..5 ids do YouTube + exatamente 1 logo quadrado | teto R$ 20/dia; nasce PAUSED | idem Display, canal `DEMAND_GEN`; vídeo não passa pelo portão criativo (bytes ausentes) e sai com aviso |
| **PERFORMANCE_MAX** | 1..100 asset groups; vídeo opcional | imagens e logos por asset group (≤ 5 MB cada); crawl de vídeo só com direitos declarados | teto R$ 20/dia; nasce PAUSED | idem Display, canal `PERFORMANCE_MAX`; **e** mensuração: as 5 conversões primárias da conta estão fora da métrica, e o portão do builder recusa `MENSURACAO_INADEQUADA` até isso ser corrigido no Google |

Pendências comuns, fora do código:

- **Projeto 2 aponta para a conta errada** (801-785-1692, cancelada). A conta
  real é 547-809-6539. Corrigir é escrita no banco (decisão do dono).
- **Destino**: a página da Senac é bloqueada só por exigências da casa
  (`interpretacao_volc` e `interna_volc`), nenhuma com fundamento Google. A
  JoinAds não está em `adtech_declarada`. Verificação de anunciante financeiro
  só vale para a vertical `financeiro`; não se aplica a educação.
- A campanha Senac 24278665189 não tem `funnel_run_id`: a receita dela
  reconcilia (v17_04), mas não volta para um funil.
