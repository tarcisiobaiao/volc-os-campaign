# Ciclo econômico entre compra de tráfego e monetização

**Estado:** proposta preservada; implementação e atuação financeira não autorizadas.  
**Data:** 14/10/2026. **Dono do aceite:** operador VOLC.  
**Próxima tarefa executável:** P07-T02, definição de evento e valor elegíveis.

## Direção

Conectar o custo de aquisição ao valor econômico da visita, com sinais rápidos de monetização e reconciliação posterior. A prioridade é aumentar contribuição financeira observada, não apenas CTR, volume ou ROAS aparente. Um sinal rápido pode antecipar diagnóstico; não vira receita contábil por ter chegado antes.

A proposta original fica preservada integralmente em [PROPOSTA-ORIGINAL-2026-10-14.txt](../reference/buy-sell-loop/PROPOSTA-ORIGINAL-2026-10-14.txt). Os rótulos "validada", "exata" e "100%" daquele texto são alegações da fonte, não aceite do VOLC. A conferência das capacidades está em [AVALIACAO.json](../reference/buy-sell-loop/AVALIACAO.json).

Não criar outro engine, banco ou controlador para começar. Reutilizar as peças abaixo, provando os pontos de ligação.

## O que o VOLC já oferece

| Peça existente | Uso nesta proposta | Limite observado nesta leitura |
|---|---|---|
| `volc_ads/inteligencia_google/coletor.py`, `campaign_simulation` | Coletar cenários nativos de custo, clique, orçamento e metas | Não prova disponibilidade de curvas na conta nem otimizador marginal produtivo |
| `supabase/migrations/v17_04_arbitragem_reconciliada.sql` | Evitar somar GAM e JoinAds como receitas independentes sem prova | Código não prova aplicação em produção; campanha-dia não é sessão; maturidade e as-of ainda são pendências registradas |
| P06-T03 e P06-T04 | Receita, moeda, fuso, impostos e revshare | Não há leitura de banco nesta rodada; não assumir resolução das lacunas do roadmap |
| P07-T01 a P07-T05 | Captura de clique, elegibilidade, fila, envio e recibo | O roadmap mantém elegibilidade/fila/envio em `todo`; capturar GCLID não prova conversão enviada |
| P14-T02 e P14-T09 | Replay/shadow e cenários read-only | Não transformar simulação ou hipótese em ação financeira |
| `docs/architecture/GADS-AUTONOMIA-ESTADO.md` | Limites de atuação e aprovação | Não habilitar autonomia pelo simples acréscimo deste documento |

O inventário foi de código e memória operacional, não uma auditoria remota de conta, site ou banco. Nenhum suporte a Prebid, GAM 360, AFS ou API do parceiro está presumido.

## Os cinco motores preservados com seus limites

### 1 Sinal rápido de receita e correção posterior

Preservar a coleta de eventos Prebid/GPT ligada à origem da visita e o estudo de upload seguido de `RESTATEMENT`. Antes: identificar o que o publisher controla, se `pbjs` é acessível, se há iframe/SSP/partner intermediário e qual moeda/base líquida os valores usam.

`bidWon` fornece o lance informado pelo Prebid, não liquidação final sem taxas ou IVT. `getHighestCpmBids` retorna vencedores do leilão Prebid e não inclui bids já renderizados; não é uma API do maior lance perdedor final do GAM. A inferência `receita AdX >= max(bid Prebid, floor)/1000` não está demonstrada na instalação real e não deve alimentar valores de conversão.

`impressionViewable` informa visibilidade, não CPM, faturamento final ou prova de usuário humano. Distinguir eventos de renderização, visibilidade, refresh e leilão por impressão para não somar o mesmo anúncio duas vezes.

`RESTATEMENT` é uma capacidade real, condicionada ao tipo de ação, owner, identificação e reconhecimento da conversão original. A documentação de ajustes distingue GCLID/GBRAID de WBRAID; não generalizar a mesma trajetória de correção para os três. Ele não dá ao VOLC a receita exata por sessão quando o parceiro só exporta total campanha-dia.

Registrar separadamente sinal observado, estimativa e receita reconciliada. Se o dado só existe por coorte, manter esse grão: não distribuí-lo por sessão e chamar a distribuição de receita exata. Envio a ação Secondary e eventual uso em bidding são etapas e aprovações distintas. Não prometer aprendizado do Smart Bidding em cinco minutos.

### 2 Custo marginal de expansão

Prioridade alta para análise em sombra: comparar lucro incremental estimado, não apenas CPC e EPC médios.

```text
delta_clicks = clicks[j] - clicks[i]
marginal_cpc_estimado = ((cost_micros[j] - cost_micros[i]) / 1_000_000) / delta_clicks
delta_contribuicao_estimada = delta_receita_liquida_estimada - delta_custo_estimado
```

Calcular somente com moeda, período e cenário compatíveis e `delta_clicks > 0`. Preservar curvas não monotônicas e pontos faltantes como diagnóstico, sem ordenar valores para fabricar uma curva conveniente. As simulações são projeções históricas, não derivada observada de um leilão futuro. O EPC incremental pode mudar com audiência/dispositivo/posição; não assumir que equivale ao EPC médio.

**Preferência já declarada pelo operador:** CPC estimado de SERP, DataForSEO ou Keyword Planner não determina lance, orçamento ou ROI. É dado de pesquisa. Uma curva nativa de simulação também é cenário, não autorização de mudança. Decisões financeiras se apoiam em custo observado, receita compatível, incerteza e limite aprovado.

### 3 Experimentos de pisos no sell-side

Preservar pisos Prebid e a hipótese de testar segmentação por custo de aquisição. Um piso maior pode aumentar preço, reduzir preenchimento ou apenas perder demanda; não obriga compradores a pagar seu custo.

Primeiro comprovar controle e suporte da rede/parceiro. `setTargeting` aceitar uma chave não prova que uma UPR da conta possa usá-la como proposto. Registrar a origem da faixa de aquisição: CPC por coorte não é custo exato daquele clique. Não enviar identificadores pessoais para key-values publicitárias.

Começar com controle e variante simples, alterando uma alavanca por vez; bandit e holdout de 10% não são defaults. Resultado é receita líquida por sessão e contribuição por clique adquirido, acompanhando fill, latência, consumo de anúncios e deduções posteriores. Taxa de visibilidade isolada não define receita de todas as impressões.

### 4 Relevância e valor de termos RSOC

Preservar a investigação de Keyword Planner, diversidade semântica e termos relacionados. Lances históricos são estatísticas do lado comprador, não RPC do feed nem lucro do publisher. A fórmula `high_bid * competition_index` é uma hipótese de ranking, não valor econômico validado.

Similaridade por embedding pode ajudar a selecionar e diversificar; não garante conformidade e não vira bloqueador lexical universal. Confirmar contratação/ativação AFS, parâmetros permitidos e termos efetivamente exibidos. O Google pode rejeitar termos fornecidos. Guardar a congruência anúncio → conteúdo → termo → resultado; não mudar o assunto do artigo para perseguir CPC alto.

### 5 Qualidade e proteção contra deduções

Preservar sinais de ASN, visibilidade, sessão e deduções para diagnóstico de IVT. Nenhum deles isoladamente prova bot ou humano. Usuário sem scroll pode ser legítimo; bot pode simular interação. Recusar todo datacenter/proxy ou exigir pointer cegamente pode cortar tráfego bom e enviesar o valor enviado.

O recurso account-level `CustomerNegativeCriterion.ip_block` existe na referência v25; limites, CIDR e suporte do canal devem ser conferidos na operação. Não bloquear IP/ASN/placement automaticamente a partir desta proposta. Medir falsos positivos, dados faltantes e maturidade dos ajustes antes de propor exclusão reversível.

Endpoint first-party reduz algumas perdas, mas não é imune a bloqueadores, consentimento, rede ou falha de entrega. `sendBeacon()` não prova ingestão durável; receiver e recibo idempotentes fazem parte da evidência.

## Separações que mantêm o lucro legível

- Custo observado, custo projetado e CPC de pesquisa permanecem distintos.
- Receita do lance, receita estimada, receita informada pelo parceiro e receita reconciliada permanecem distintas, com moeda, fuso, grão, fonte, data do fato e data da observação.
- Não somar GAM e parceiro intermediário sem prova de não sobreposição. Valor ausente não é zero.
- `contribuicao = receita_liquida_comparavel - custo_de_midia_comparavel`. Chamar de lucro líquido só depois de declarar os demais custos relevantes; não inventar câmbio, imposto ou revshare.
- Nenhuma mudança simultânea de bidding e floor no primeiro experimento: isso impediria atribuir o efeito.
- `BiddingSeasonalityAdjustment` trata mudanças de taxa de conversão, não um multiplicador genérico de RPM. Não usá-lo como atalho de yield.

## Fila de execução pequena

1. **P07-T02 — inventário e evento elegível.** Um site e uma origem de compra. Enumerar eventos acessíveis e os grãos reais de custo/receita. Identificar consentimento, owner da ação e se o mecanismo viável é Data Manager, upload Ads ou somente diagnóstico. Entrega: amostra sanitizada e uma decisão sobre valor observado/estimado, sem criar pipeline paralelo.
2. **P06-T03/P06-T04 — prova de reconciliação.** Reconstituir uma coorte com revisões as-of, moeda/fuso e deduções. Medir diferença entre sinal inicial e receita madura. Se faltar atribuição por sessão, não abrir a trajetória de restatement por sessão.
3. **P14-T02/P14-T09 — decisão em sombra.** Reutilizar o coletor de `campaign_simulation`; produzir uma proposta de contribuição incremental sem mutate. Curva ausente produz diagnóstico de indisponibilidade, não motivo para comprar tráfego extra.
4. **P07-T03/P07-T04 — transmissão controlada.** Só após aceite do evento e fonte: fila idempotente, validação suportada pelo endpoint, leitura de falhas por operação e reconciliação. Dados sintéticos não entram em aprendizado de produção. Eventual teste externo requer autorização própria.
5. **Pisos, RSOC e exclusões.** Preservados no mapa, mas não são dependências para concluir o primeiro ciclo econômico. Cada experimento exige acesso do parceiro, hipótese, limite, controle, resultado e rollback próprios.

O próximo implementador deve iniciar no item 1, mostrar o que já existe e emitir proposta mínima antes de acrescentar serviço/lib. Esta documentação não substitui uma execução nem garante prazo futuro; faz a ideia permanecer na fila e nos critérios de aceite.

## Critério de promoção

Não marcar ciclo como entregue por ter instalado SDK ou recebido `validate_only`. É preciso provar origem → evento → valor no grão correto → recibo → revisão posterior, sem dupla contagem. ROI e redução de IVT exigem tráfego, observação e contabilização maduros; não podem ser certificados pelo documento ou por teste hermético.

## Fontes primárias conferidas em 14/10/2026

- [Simulações de lance](https://developers.google.com/google-ads/api/docs/bid-simulations/overview).
- [Importação offline](https://developers.google.com/google-ads/api/docs/conversions/upload-offline) e [ajustes](https://developers.google.com/google-ads/api/docs/conversions/upload-adjustments).
- [Prebid onEvent](https://docs.prebid.org/dev-docs/publisher-api-reference/onEvent.html), [getHighestCpmBids](https://docs.prebid.org/dev-docs/publisher-api-reference/getHighestCpmBids.html) e [Price Floors](https://docs.prebid.org/dev-docs/modules/floors.html).
- [GPT e eventos de visibilidade](https://developers.google.com/publisher-tag/reference#googletag.events.ImpressionViewableEvent).
- [Keyword Planner histórico](https://developers.google.com/google-ads/api/docs/keyword-planning/generate-historical-metrics).
- [RSOC e termos fornecidos pelo parceiro](https://support.google.com/adsense/answer/10233819?hl=en).
- [IP block em conta](https://developers.google.com/google-ads/api/reference/rpc/v25/CustomerNegativeCriterion) e [IpBlockInfo](https://developers.google.com/google-ads/api/reference/rpc/v25/IpBlockInfo).
- [Ajustes sazonais](https://support.google.com/google-ads/answer/10369906?hl=en).

Rever o suporte da plataforma antes de executar. A página genérica de pricing GAM não comprovou nesta pesquisa o targeting UPR por `acq_bucket`; a capacidade permanece não demonstrada.
