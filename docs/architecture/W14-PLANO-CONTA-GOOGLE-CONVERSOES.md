# W14 — Plano de mudança na conta Google: valor de conversão e primárias

**Conta:** Portal Mundo Mais, `547-809-6539` (`5478096539`), MCC `601-673-9364`. Site: creditoup.com.br.
**Quem executa:** só o Tarcisio, na UI do Google Ads (ou pela API com autorização própria).
**Estado:** plano. **Nada aqui foi executado.** A nuvem não muta Ads.
**Data:** 15/10/2026. Código correspondente: `backend/app/trafego/conversao_offline/`.

## Por que mexer

O ROAS nativo do Google nessa conta é falso. As leituras que temos (GAQL de
01/09/2026 em `docs/closure/traffic-creative-operational-closure-v1/verificacao/VALIDATE-ONLY-CANAIS.md`
e releitura de metas de 09/10/2026 no `ROADMAP-VIVO.json`, P04-T07) mostram:

| Ação | id | tipo | primária | valor |
|---|---|---|:--:|---|
| `adView` | 7466949251 | WEBPAGE | sim | **R$ 10 sempre** (09/10) |
| `Compra` | 7467141090 | WEBPAGE | sim | R$ 1 (09/10) |
| `AdClick`, `adViewInterstitial` (7466930854), `adViewRewarded` (7467141321), `adviewinterstitial - Programa Pé de Meia` (7495780528), `- RG Digital` (7495808852), `- Cursos Senai` (7495947978) | | WEBPAGE | sim | não lido por ação |
| `Android installs (all other apps)` | 7498530235 | ANDROID_INSTALLS | não | — |

- Meta da conta PURCHASE/WEBSITE: **não biddable** (09/10). DOWNLOAD/APP: biddable.
- As campanhas usam **metas personalizadas por evento de anúncio** (ex.: Senac, custom goal `6456287716`), que o VOLC ainda não lê.
- Efeito medido: na Senac `24278665189` o Google mostra valor de conversão de R$ 2.380 na janela em que a receita JoinAds foi R$ 40,79 (ROAS real 0,0735). O lance que persegue esse valor persegue um número inventado.

⚠️ Essas leituras têm de 6 a 45 dias. O passo 0 relê tudo antes de qualquer mudança.

## O que o código do W14 faz e o que ele exige da conta

O VOLC passa a mandar, pela Data Manager API, **uma conversão por clique pago**
com valor = receita medida da coorte campanha-dia (JoinAds), convertida pela
cotação versionada (W12) para a moeda da conta e dividida pelas sessões da
coorte. É **estimativa** (rateio), e a proveniência de cada evento diz isso.
Sem receita, sem câmbio ou com receita imatura o clique é pulado e registrado;
nunca vai 10 nem 0.

O valor medido vai para **uma ação nova do tipo importação de cliques
(`UPLOAD_CLICKS`)**, e nunca para a tag `adView`. Misturar tag e upload na mesma
ação contaria a mesma sessão duas vezes.

## Passo 0 — Ler antes de mudar (somente leitura)

Rodar no Mac (`volc_ads.gads.client.buscar`, login `6016739364`) e guardar a
saída como retrato "antes" (é ele que o rollback restaura):

```sql
SELECT conversion_action.id, conversion_action.name, conversion_action.type,
       conversion_action.status, conversion_action.category, conversion_action.origin,
       conversion_action.primary_for_goal, conversion_action.counting_type,
       conversion_action.value_settings.default_value,
       conversion_action.value_settings.default_currency_code,
       conversion_action.value_settings.always_use_default_value,
       conversion_action.click_through_lookback_window_days
FROM conversion_action WHERE conversion_action.status != 'REMOVED'

SELECT customer_conversion_goal.category, customer_conversion_goal.origin,
       customer_conversion_goal.biddable FROM customer_conversion_goal

SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
       campaign.bidding_strategy_type,
       conversion_goal_campaign_config.goal_config_level,
       conversion_goal_campaign_config.custom_conversion_goal
FROM conversion_goal_campaign_config

SELECT custom_conversion_goal.id, custom_conversion_goal.name,
       custom_conversion_goal.conversion_actions, custom_conversion_goal.status
FROM custom_conversion_goal

SELECT customer.currency_code, customer.time_zone FROM customer
```

(Os campos foram conferidos no catálogo GAQL v25 do repo. Se a API recusar os
campos de `campaign` na consulta de `conversion_goal_campaign_config`, leia
`campaign` numa consulta separada e junte pelo id.)

Saída esperada para seguir: a moeda da conta (o VOLC só converte para ela), o
valor e o estado reais de `adView`, e a lista de campanhas cujo lance usa uma
meta (padrão ou personalizada) que contém `adView` ou `Compra`. **Essa lista é
o raio de impacto dos passos 3 e 4.**

## Passo 1 — Criar a ação de importação, como Secondary

UI: **Metas → Conversões → Resumo → + Nova ação de conversão → Importar →
Outras fontes de dados ou CRMs → Rastrear conversões a partir de cliques**.

| Campo | Valor |
|---|---|
| Nome | `VOLC — Receita medida (offline)` |
| Categoria | Compra |
| Valor | "Usar valores diferentes para cada conversão" (o VOLC sempre manda o valor) |
| Contagem | Todas |
| Janela de conversão após clique | 90 dias (o VOLC **não** lê este campo: a janela é declarada à mão no perfil de mensuração com o mesmo número; se divergir, vale a do Google e o evento fora dela é descartado lá) |
| Atribuição | Baseada em dados |
| Meta | **Secondary** (ação secundária: não entra em "Conversões", não move o lance) |

Anotar o **id numérico** da ação (Metas → Conversões → coluna id, ou a leitura
do passo 0). É ele que entra em `plano_para_acao_offline(plano, acao_id)`.

Conferir na leitura do passo 0, já com a ação criada:
`value_settings.always_use_default_value = false` nela. Se for `true`, o Google
ignora o valor enviado e usa o padrão, que é exatamente o defeito do `adView`.
O código do W14 não lê `value_settings` (lacuna conhecida), então esta
conferência é humana e fica no recibo.

- **Impacto no lance:** nenhum. Secondary só aparece em "Todas as conversões".
- **Rollback:** remover a ação. Enquanto nada foi enviado, não há resíduo.

## Passo 2 — Pré-requisitos do envio (fora da UI do Ads, no Mac)

Nenhum destes é feito pela nuvem.

1. Projeto Google Cloud com a **Data Manager API** ativada e credencial OAuth com
   escopo `https://www.googleapis.com/auth/datamanager`, de um usuário com acesso
   à conta 547-809-6539. A credencial nunca entra no repositório nem na nuvem.
2. Aplicar no Supabase oficial, em janela autorizada e nesta ordem: W4 (v19,
   v19_10) → W12 (v23_01) → **W14 (v25_01)**. Sem v23_01 não há receita datada
   nem câmbio; sem v25_01 não há registro de envio.
3. Ligar a coleta PTAX do W12. Sem cotação, todo clique sai como `sem_cotacao`.
4. **Consentimento do visitante:** `site_visits` não tem coluna de consentimento.
   Hoje todo clique é pulado como `sem_consentimento_do_usuario`. É preciso
   capturar o consentimento do visitante no tracker do creditoup.com.br (CMP /
   Consent Mode) e expô-lo na porta de cliques. Até lá, nenhum evento é enviado.
5. Decidir a política de valor (código: `PoliticaDeValor`): fonte `joinads`,
   maturidade mínima (sugestão: 3 dias, porque a JoinAds reescreve D-1 a D-3),
   defasagem máxima de câmbio (sugestão: 3 dias) e **aceite explícito do rateio
   por coorte** (`aceitar_rateio_de_coorte=True`). Sem esse aceite, todo clique é
   pulado como `rateio_de_coorte_sem_aceite`.

## Passo 3 — validateOnly real e o primeiro envio (com aprovação)

1. No Mac: `preparar_lote` → `validar_no_google` (validateOnly). O Google
   confere e descarta. Ler o resumo: elegíveis, pulados por motivo, avisos.
2. Se aceito, o Tarcisio aprova **a impressão exata do envelope validado**
   (`AprovacaoDeEnvio`). Só então `enviar_de_verdade`, com
   `FORGE_PERMITIR_ESCRITA=1` e `modo.destravar(motivo)` no script do envio.
3. Após 30 min, `reconciliar` (o Google pede até 24 h). Ler `warningInfo` mesmo
   em SUCCESS.
4. Deixar a ação **Secondary por 14 dias** e comparar, na coluna "Todas as
   conversões (valor)", o valor importado com a receita JoinAds do mesmo período.

- **Impacto no lance:** nenhum (Secondary).
- **Rollback:** a Data Manager **não retrata** conversão. Dá para corrigir valor,
  não para apagar: pela página de migração da Data Manager, o mesmo
  `transactionId` na mesma ação substitui o valor e não conta de novo. O VOLC
  não usa isso por conta própria (`ajuste_de_valor_nao_autorizado`); o único
  reenvio automático permitido é o do MESMO envelope que ficou sem resposta. Por isso o envio real é
  pequeno, aprovado por envelope, e começa em ação Secondary. Se algo sair
  errado, a saída é pausar o envio e deixar a ação Secondary (ou removê-la).

## Passo 4 — Revisar as primárias do PMax (e de qualquer lance automático)

Decisão do Tarcisio, por campanha, com a lista do passo 0. Recomendação:

1. **Não mexer na meta padrão da conta.** Para cada campanha que vai otimizar
   por receita (PMax incluída), usar **meta específica da campanha** (ou meta
   personalizada) que contenha **só** `VOLC — Receita medida (offline)`.
   UI: Campanha → Configurações → Metas → "Usar metas específicas desta
   campanha". Assim as campanhas que hoje usam `adView`/metas personalizadas
   por evento não mudam junto.
2. Tornar `VOLC — Receita medida (offline)` **primária** (Metas → Conversões →
   ação → Editar → Meta da ação: Primária). Conferir na releitura que ela ficou
   biddable para a meta da campanha.
3. Na mesma campanha, as ações de tag (`adView`, `Compra`, `adView*`) saem da
   meta da campanha. **Não** é preciso desligá-las na conta.
4. Para PMax: o portão do VOLC (`volc_ads/campanha/pmax.py`) só libera PMax com
   uma ação ENABLED, primária e com valor. A ação de importação primária e com
   valor medido é o que destrava a recusa `MENSURACAO_INADEQUADA`.

- **Impacto no lance:** a campanha passa a perseguir receita estimada em vez de
  `adView` a R$ 10. Espere período de aprendizado (de 1 a 2 semanas), queda
  aparente de "Conversões" (passa de vários `adView` por sessão para no máximo
  um por clique) e um ROAS muito menor que o mostrado hoje, porque o de hoje é
  inventado. **Recalibrar alvos:** um tROAS calculado com o valor de 10 vai
  estrangular a entrega. Sugestão: 2 semanas em "Maximizar valor de conversão"
  sem alvo, depois tROAS a partir do ROAS medido. A receita chega com 3 dias de
  atraso (maturidade), então o lance vê os dias recentes incompletos.
- **Atenção:** a doc da Data Manager cita 14 dias de período de teste para ação
  nova, em que as conversões aparecem no relatório mas não entram no lance.
- **Rollback:** restaurar o retrato do passo 0 (a ação offline volta a
  Secondary, as metas da campanha voltam às de antes, o alvo de lance volta ao
  anterior). O que já foi enviado continua contado (sem retratação).

## Passo 5 — Remover o valor fixo de 10 de `adView`

Só depois do passo 4 nas campanhas que importam, porque sem isso o lance por
valor dessas campanhas perde o único sinal que tinha de uma vez.

UI: Metas → Conversões → `adView` → Editar configurações → Valor → **"Não usar
um valor para esta ação de conversão"** (e o mesmo para `Compra`, R$ 1). Ou,
alternativa mais conservadora: torná-las **Secondary**, mantendo a contagem
para observação.

- **Impacto no lance:** campanhas que ainda tenham `adView` numa meta com
  estratégia por valor (tROAS, maximizar valor) passam a ver valor 0 daqui para
  frente: entrega cai bruscamente. Estratégias por contagem (maximizar
  conversões, tCPA) não mudam. Por isso a ordem: passo 4 antes do 5.
- **Rollback:** voltar para "Usar o mesmo valor para cada conversão: R$ 10".
  A mudança não é retroativa em nenhuma direção: o período intermediário fica
  com o valor que vigorou nele.

## Ordem, quem e o que cada passo precisa

| # | O quê | Quem | Precisa de |
|---|---|---|---|
| 0 | Releitura GAQL | Mac | nada novo (leitura) |
| 1 | Criar ação de importação Secondary | Tarcisio na UI | decisão dele |
| 2 | Credencial Data Manager, v23_01 + v25_01 em produção, PTAX, consentimento, política | Tarcisio + integrador | janela de migration, credencial, decisão sobre rateio |
| 3 | validateOnly real; 1º envio aprovado; 14 dias Secondary | Mac + Tarcisio | aprovação por envelope |
| 4 | Ação offline primária nas campanhas escolhidas; recalibrar alvos | Tarcisio na UI | decisão por campanha |
| 5 | Tirar o valor fixo de `adView`/`Compra` | Tarcisio na UI | passo 4 feito |
