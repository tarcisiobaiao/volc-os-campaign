# P0-A — Plano de diagnóstico das campanhas sem entrega

**Estado:** ✅ **aprovado e congelado** · **Natureza:** SOMENTE LEITURA · **Data:** 24/08/2026
**Porta:** [TRAFEGO.md](./TRAFEGO.md) · **Fatos:** [ledger](./EVIDENCIAS-TRAFEGO.md) · **Decisões:** [ADRs](./ADR-TRAFEGO.md)
**Regra desta faixa:** nenhuma alteração de lance, verba, status, keyword ou anúncio. `validate_only` e `search()` são permitidos; qualquer `mutate` de escrita, não.

> **Marcação:** **[F]** fato (com `E-nn`) · **[I]** inferência · **[DA]** decisão aceita ·
> **[DP]** decisão pendente · **[R]** risco · **[DE]** dependência externa.

---

## 1. O fato que motiva

**[F]** As duas campanhas, seus números e o histórico de alteração de lance estão no ledger:
**[E-01](./EVIDENCIAS-TRAFEGO.md#e-01)** (estado, lance, verba, entrega) e **[E-14](./EVIDENCIAS-TRAFEGO.md#e-14)** (o lance baixado de R$ 1,00 para R$ 0,12
pelo operador, via painel, em 19/08 22:39).

**[F]** As duas estão aprovadas e veiculando pelo próprio Google e somam cinco impressões em cinco dias, sem razões de bloqueio declaradas ([E-01](./EVIDENCIAS-TRAFEGO.md#e-01)) — o Google não está dizendo que há impedimento.

**[I]** Aprovado + veiculando + quase zero impressão aponta para **não vencer o leilão**, não para bloqueio. Mas isso é hipótese, e este plano existe para separá-la das outras.

## 2. Hipóteses, e o que cada uma prevê

| # | hipótese | o que ela prevê que veremos | como distinguir |
|---|---|---|---|
| H1 | **lance muito abaixo do leilão** | impression share perdido por rank alto; lance ≪ estimativas de topo de página | `search_top_impression_share`, `search_rank_lost_impression_share`, estimativas de primeira página |
| H2 | **volume de busca real menor que o estimado** | poucas impressões disponíveis; termos com volume real baixo | volume de impressões elegíveis por keyword; status de keyword |
| H3 | **keywords com problema de qualidade ou status** | keywords `LOW_QUALITY`, `RARELY_SERVED` ou pausadas | status por critério e motivo |
| H4 | **restrição de segmentação** | geo, idioma, agendamento ou rede excluindo o público | configuração de segmentação da campanha |
| H5 | **limitação de política não bloqueante** | anúncio `APPROVED_LIMITED` em algum tópico | resumo de política por anúncio |
| H6 | **verba irrelevante** | verba R$ 10 com lance R$ 0,12 = teto de 83 cliques/dia — **[I]** não é o gargalo com 0 cliques | descartável por aritmética |
| H7 | **campanha nova ainda em aprendizado** | **[I]** 5 dias é tempo suficiente para sair disso | descartável pelo tempo |

**[I]** H6 e H7 já podem ser descartadas com o que está medido; ficam registradas para não voltarem como palpite.

## 3. Bateria de leitura

Todas as consultas são `search()` na API do Google Ads, escopo restrito à conta `8017851692`, sem escrita.

| # | o que ler | responde |
|---|---|---|
| L1 | impression share da campanha: total, perdido por rank, perdido por verba, topo e topo absoluto | H1 vs H6 — **é o primeiro e o mais decisivo** |
| L2 | por keyword: status, motivo do status, lance efetivo e métricas do período | H1, H2, H3 |
| L3 | estimativas de lance de primeira página e topo por keyword | H1 — dá a distância entre R$ 0,12 e o leilão |
| L4 | termos de busca acionados no período | H2 — se há demanda chegando |
| L5 | segmentação: geo, idioma, rede, agendamento, dispositivo | H4 |
| L6 | resumo de política por anúncio, incluindo tópicos limitantes | H5 |
| L7 | histórico de alterações dos 14 dias | contexto: o que mudou e quem mudou |
| L8 | ad strength e itens de ação | qualidade do anúncio, insumo de H3 |

**[F]** L6, L7 e L8 já existem no código e podem ser reusadas sem nada novo ([E-17](./EVIDENCIAS-TRAFEGO.md#e-17) para o inventário de capacidades de leitura). **[I]** L1–L5 exigem consultas novas, todas de leitura.

**[R]** L3 devolve **estimativa do Google**, não fato da conta. Ela entra no diagnóstico com essa etiqueta e **não** vira número de tela. **[F]** É a mesma disciplina que o módulo de entrega já adota ao recusar comparar o lance com CPC estimado de terceiro.

## 4. Sequência

1. **L1 primeiro.** Se o impression share perdido por rank for alto e o perdido por verba for baixo, H1 vira a hipótese dominante e L3 quantifica a distância.
2. **L5 e L6 em seguida**, porque são baratas e eliminam causas categóricas.
3. **L2 e L4** para o detalhe por keyword.
4. **L7 e L8** para contexto.

## 5. Entregável

Um parecer com quatro seções, e nada além disso:

1. **O que foi medido** — cada número com a consulta que o produziu.
2. **Qual hipótese sobrevive** — e por que as outras caíram.
3. **O que seria preciso mudar** — com a faixa de valores e o efeito esperado.
4. **O que NÃO recomendo** — explicitamente.

**[DA] O parecer não executa nada.** A ação que ele recomendar depende de porta governada (onda P2) ou de ato manual do operador, com registro.

**[R]** Um diagnóstico que conclua "é lance" cria pressão para agir imediatamente, e **[F]** não existe caminho governado de atuação hoje ([E-15](./EVIDENCIAS-TRAFEGO.md#e-15)). Se o operador agir pelo painel, isso é legítimo e deve ser **registrado como decisão**, não como conserto silencioso.

## 6. Perguntas que o parecer não pode responder sozinho

**[DP]** Se R$ 0,12 foi teto de risco deliberado. **[F]** [E-14](./EVIDENCIAS-TRAFEGO.md#e-14) mostra o operador baixando de R$ 1,00 para R$ 0,12 pelo painel — se foi intencional, "não entregar" é resultado esperado e o alerta de entrega vira ruído que precisa de silenciamento por decisão, não de conserto.

**[DP]** Qual é o teto de gasto aceitável para descobrir o leilão. Sem isso, "suba o lance" não tem limite superior.

## 7. Fora de escopo

Alterar qualquer coisa; propor regra de bidding permanente (**[DP]** nenhuma está aprovada — ADR-11); tocar nas campanhas de teste (**[DA]** permanecem pausadas — ADR-12); estender a análise às outras duas contas da casa antes de fechar esta.
