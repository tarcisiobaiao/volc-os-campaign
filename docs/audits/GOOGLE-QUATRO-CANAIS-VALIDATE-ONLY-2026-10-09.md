# Quatro canais Google: prova real sem escrita

Em 09/10/2026, os builders oficiais de Search, Display, Demand Gen e
Performance Max foram aceitos pela Google Ads API v25 em `validate_only`.
Nenhuma campanha, anúncio, imagem ou orçamento foi criado ou alterado.

Conta: 5478096539. MCC: 6016739364. A conta foi relida como habilitada,
BRL, America/Sao_Paulo. Tema da prova técnica: guia Senac, com a URL pública
existente `https://creditoup.com.br/r/guia-cursos-senac/`.

| Canal | Operações | Resultado real | Request ID |
| --- | ---: | --- | --- |
| Search | 15 | gRPC OK, sem falha | xUsAh6AUPU_1FrNlaKXfvw |
| Display | 9 | gRPC OK, sem falha | EqfdKLSt8Rq9Ne8alvKYEg |
| Demand Gen | 9 | gRPC OK, sem falha | evcTANUKWqQckLlytFXcig |
| Performance Max | 25 | gRPC OK, sem falha | yMAhcaR7LNAAkf_AG0Rm0A |

## O que foi conferido

Os quatro `validar()` existentes montaram os próprios protos e fizeram a
requisição real. Um interceptor de auditoria não substituiu a rede: exigiu
`validate_only=true` e `partial_failure=false`, gravando somente horário,
quantidade, SHA-256 do request e request ID do Google. O SDK instalado estava
em 31.3.0, abaixo da dependência já declarada; foi alinhado a 33.0.0, que
expõe os campos de AssetGroup v25 usados pelo código. Nenhuma versão do
contrato foi trocada para contornar a API.

Display, Demand Gen e PMax usaram três banners locais em dimensões nativas,
produzidos por HTML/Chromium, medidos e recebidos pela ponte de criativos
existente. A procedência é `LOCAL`, o destino é `ENSAIO`; **não são criativos
aprovados para produção**. Os bytes só participaram das requisições
descartadas de validação. Não houve upload persistente separado.

Search e Demand Gen inicialmente foram recusados localmente por campos do
payload de teste: Search exigia dois callouts e dois sitelinks; Demand Gen
multi-asset não aceita a long headline do formato de vídeo. Foram ajustados
os dados por canal, sem relaxar o contrato. Só os dois canais ainda não
enviados foram retomados. Display e PMax não foram repetidos.

## Delta mínimo no engine

`pmax.validar()` agora distingue conferência técnica de autorização para
lançamento. Os impedimentos operacionais da mensuração ficam como avisos
**somente nessa função**. Recibo ausente, adulterado ou de outra conta/MCC
continua impedindo a chamada. `construir()` e `planejar()` continuam com os
bloqueios de lançamento; `/subir`, autorização financeira e publicação não
foram abertos. O ramo técnico é privado, sem novo interruptor público no
construtor operacional.

A leitura real das metas da conta também foi guardada. A meta WEBSITE/PURCHASE
está não-biddable; APP/DOWNLOAD está biddable. As ações primárias de website
divergem do campo legado `include_in_conversions_metric`. Essa constatação
**não autoriza otimizar a campanha para instalação de aplicativo**, nem
prova receita, volume de conversão ou prontidão do PMax para investir.

Testes: suite `volc_ads`, com os padrões `test_*.py testes_*.py`, passou
1.502 testes, zero falhas (25 avisos antigos de testes que retornam valores);
o recorte final novo passou 7/7. Os testes preservam o bloqueio de construção/planejamento e
recusam recibos adulterados antes da API. O teste completo não substitui a
prova remota acima.

## O que isto não prova

- Revisão/qualificação de política futura do Google. `validate_only` descarta
  operações, não transforma os anúncios em anúncios aprovados.
- Todas as combinações possíveis de lance, formato e segmentação: são quatro
  payloads base, um por canal.
- O fluxo cockpit → oportunidade → mídia de produção → campanha. A prova
  chamou os builders reais diretamente, não fingiu dados no HTTP. O conjunto
  pago do Search, o vínculo correto projeto/conta, a identidade do destino,
  a mídia aprovada e a governança de escrita continuam pendências separadas.
- O FGTS gerado pelo redator nessa mesma rodada: é um canário separado, vindo
  de uma oportunidade real; não é a página pública usada nesta prova Google.

## Evidência e continuidade

Os recibos, scripts locais e banners de ensaio ficam fora dos commits em
`canarios/google-quatro-canais-real-20261009/` no diretório do projeto-pai.
Preservar `resultado-google.json`, as quatro entradas de request ID, hashes,
mensuração e metas. Antes de qualquer lançamento, construir o payload de
produção pela porta governada e repetir a prova **desse payload exato**.

Roadmap: P04-T04, P04-T07 e P04-T09 recebem esta prova sem promover o estado
operacional para `done`. Nó operacional relacionado: `cap_search_birth`.
As evidências de `channel:SEARCH`, `channel:DISPLAY`, `channel:DEMAND_GEN`
e `channel:PERFORMANCE_MAX` foram reconciliadas: as afirmações antigas de
ausência de builder/prova não representam esta rodada. Demand Gen passou de
`todo` a `partial`; nenhum canal recebeu autorização de criação.

Fonte do comportamento de validação: [Google Ads — bulk mutate](https://developers.google.com/google-ads/api/docs/mutating/bulk-mutate).

## Revisão independente (09/10/2026, mesma data)

**Recibos.** `resultado-google.json` traz uma chamada por canal com
`validate_only=true`, `partial_failure=false`, gRPC `OK`, request ID lido dos
metadados da resposta do Google e SHA-256 do request; as contagens (15/9/9/25)
batem com as operações montadas. O interceptor chama a `continuation` real e
falha se o pedido não for `validate_only`. As metas relidas confirmam
PURCHASE/WEBSITE sem `biddable` e DOWNLOAD/APP `biddable=true`.

**Separação do PMax.** `pmax.validar` só é chamado pela porta de prova
(`perfil.PERFORMANCE_MAX.validador`), e nenhuma rota do backend o invoca:
`trafego.py` usa `resolver_provador` só para resolver o canal. O selo nasce
apenas em `subir.preparar`, que monta por `perfil.montar` → `pmax.construir`
(estrito). Regressão nova:
`testes_pmax_validate_only.py::test_porta_do_selo_continua_recusando_pmax_sem_mensuracao`
(sem ação na métrica, `preparar` não chama a API e não emite selo).

**Cadeia oportunidade → recibo no cockpit**, com o que falta:

| elo | estado |
|---|---|
| oportunidade real | existe (65, 73, 74, 106) |
| conjunto pago | **falta**: 106 sem cluster; 65/73/74 com cluster do n8n → 409 `N8N_PAID_ELIGIBILITY_CONTRACT_UNSUPPORTED`. Nasce só da mineração Python (prospector LLM, chamada paga) + aprovação humana gravada (`POST /conjunto-pago/aprovar`) |
| destino | LP Senac bloqueada só por exigências da casa (`basis` interna/interpretação) |
| mídia | nenhuma aprovação criativa com finalidade Google (as 2 existentes são `meta_ads`) |
| payload | builders aceitos (acima); cascata de copy gera 6 sitelinks; DG recebe copy estrita do corpo |
| validate_only | provado nos builders; pelo `/provar` só chega após conjunto pago + destino |
| recibo no cockpit | o selo volta na resposta do `/provar`; `/subir` o exige |

Teste ajustado: `backend/tests/test_trafego.py::test_provar_sem_copy_reprova_e_diz_por_que`
(ambiente real) esperava 200 e passou a receber o 409 do portão de elegibilidade
paga, posterior ao teste. Aceita agora essa recusa nomeada, exigindo `codigo`,
`autoridade` e `nada_foi_criado`.
