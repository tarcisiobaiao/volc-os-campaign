# PRD mestre — Tráfego como Operação

**Estado:** ✅ **aprovado e congelado** · **Data:** 24/08/2026
**Porta de entrada:** [TRAFEGO.md](./TRAFEGO.md) · **Fatos:** [ledger](./EVIDENCIAS-TRAFEGO.md) · **Decisões:** [ADRs](./ADR-TRAFEGO.md)

> **Marcação:** **[F]** fato comprovado (com `E-nn`) · **[I]** inferência ·
> **[DA]** decisão aceita · **[DP]** decisão pendente · **[R]** risco · **[DE]** dependência externa.
> Números vivem no ledger; este documento aponta para eles.

---

## 1. O problema, em uma frase

O VOLC O.S. sabe **fazer nascer** uma campanha com prova real, e não sabe **saber que ela existe**.

## 1.1 A visão norte — Hub de Controle de Mídia

O destino não é consertar duas campanhas: é transformar a camada de Tráfego no **Hub de
Controle de Mídia** do VOLC O.S. — um lugar onde toda mídia comprada é inventariada,
reconciliada, diagnosticada e atuada sob governança, **qualquer que seja o canal**.

**[DA]** O princípio é **núcleo comum de operação + perfil/adaptador por canal** (ADR-17).
O núcleo — conta, campanha, linhagem, projeto, funil, canal, estado, snapshot, vínculo,
procedência, evento, incidente, proposta, autorização, execução, política, auditoria — não
conhece keyword nem asset group. Cada canal injeta a sua semântica por contrato tipado.

**Search é a primeira implementação concreta, não o limite arquitetural.** A estratégia é:
construir o núcleo horizontal correto → prová-lo com Search → estabilizar o ciclo completo →
adicionar cada canal como adaptador e perfil, sem tocar nas fundações.

**[DA]** Isso **não** significa telas vazias nem abstração especulativa: um ponto de extensão
só entra no P0 se Search o exercitar hoje (ADR-19).

## 2. A evidência que define o escopo

- **[F]** Duas campanhas existem na conta, ambas ligadas há cinco dias sem gastar ([E-01](./EVIDENCIAS-TRAFEGO.md#e-01)).
- **[F]** O banco conhece uma; a FGTS não está em `campaigns` ([E-02](./EVIDENCIAS-TRAFEGO.md#e-02)).
- **[F]** A FGTS tem funil e cluster ([E-03](./EVIDENCIAS-TRAFEGO.md#e-03)), e por isso seu cartão exibe **"montar campanha"** — a tela convida ao segundo lançamento do mesmo termo ([E-04](./EVIDENCIAS-TRAFEGO.md#e-04)).
- **[F]** A FGTS já foi lançada três vezes, duas delas declaradas como teste ([E-05](./EVIDENCIAS-TRAFEGO.md#e-05)).
- **[F]** Não existe memória operacional: nenhuma tabela de alerta, incidente, proposta ou recibo ([E-06](./EVIDENCIAS-TRAFEGO.md#e-06)).
- **[F]** A leitura da conta acontece no caminho de renderização, em 23 das 28 páginas ([E-07](./EVIDENCIAS-TRAFEGO.md#e-07)).
- **[F]** O vocabulário de canal diverge em cinco lugares e **PMax não é executável** ([E-21](./EVIDENCIAS-TRAFEGO.md#e-21)).

### 2.1 O lance de R$ 0,12 — hipótese operacional registrada

**[DA]** O lance inicial de R$ 0,12 foi **hipótese operacional de teste**, não teto
permanente nem aceitação de não entregar: em campanhas brasileiras de benefícios sociais
esse valor já havia gerado entrega, e foi usado como partida de risco controlado. O operador
**esperava alguma entrega**; cinco dias com cinco impressões ([E-01](./EVIDENCIAS-TRAFEGO.md#e-01)) não era o resultado
previsto. **[I]** A evidência sugere que o vertical financeiro tem dinâmica de leilão
diferente — e é isso que o P0-A existe para verificar.

**[DA]** O P0-A permanece **somente leitura**: diagnostica, fundamenta e recomenda. Não
altera lance, orçamento ou campanha, nem automaticamente nem como efeito colateral.

## 3. Quem é servido, e a decisão que cada um toma

Um operador, três decisões distintas — nenhuma com superfície própria hoje:

| decisão | pergunta | onde vive hoje |
|---|---|---|
| **inventariar** | "o que eu tenho, e em que estado?" | em lugar nenhum |
| **priorizar** | "o que quer algo de mim hoje?" | a mesma lista, duplicada em duas superfícies |
| **diagnosticar e agir** | "por que esta campanha está assim?" | cockpit legado, com fonte parada ([E-20](./EVIDENCIAS-TRAFEGO.md#e-20)) |

## 4. Escopo

### 4.1 Dentro

Inventário reconciliado contra a conta; identidade de instância e de linhagem (ADR-02);
prevenção de duplicidade por composição de sinais (ADR-03); reconciliação campanha ↔ funil
com confirmação humana (ADR-09); estados de presença honestos (ADR-13); evento operacional
mínimo (ADR-14); snapshot com frescor (ADR-08); investigação e contenção dos executores
legados (ADR-06, ADR-15); reaproveitamento do cockpit existente com troca de fonte (ADR-07).

### 4.2 Fora, e por quê

| fora | motivo |
|---|---|
| motor de decisão automático | **[DP]** nenhuma regra de bidding, graduação ou automação está aprovada (ADR-11) |
| graduação em 30 conversões | **[F]** o gatilho não tem sensor ([E-15](./EVIDENCIAS-TRAFEGO.md#e-15)) |
| núcleo completo de Ocorrência/Incidente | **[DA]** é do P1; o P0 entrega evento operacional (ADR-14) |
| ingestão própria de custo e receita | onda posterior |
| remoção de campanhas de teste | **[DA]** permanecem pausadas (ADR-12) |
| desativação de qualquer workflow | **[DA]** P0-S investiga e contém; não desliga (ADR-06) |
| PMax, Display, Demand Gen | Search precisa fechar o ciclo |
| notificação externa (e-mail, push) | onda de saúde sistêmica |

## 5. Princípios

1. **A conta é a verdade sobre existência e status** (ADR-01); o banco é memória governada.
2. **Cada estado tem um dono de escrita declarado.**
3. **Leitura da conta fora do caminho de renderização** (ADR-08).
4. **Dado velho aparece com a idade visível**; ausência de leitura não vira ausência de problema.
5. **Prova antes de escrever** — vale para criar campanha e para prevenir duplicidade.
6. **Nada silencioso**: falha de persistência vira evento registrado, não aviso volátil.
7. **Preservar antes de substituir** (ADR-07).
8. **Fronteira, não expulsão** (ADR-05).

## 6. Métricas de sucesso

| métrica | hoje | alvo da onda P0 |
|---|---|---|
| campanhas da conta invisíveis no produto | 1 de 2 ([E-01](./EVIDENCIAS-TRAFEGO.md#e-01), [E-02](./EVIDENCIAS-TRAFEGO.md#e-02)) | 0 |
| campanhas sem procedência registrada | 1 de 2 | 0 não sinalizadas |
| convites a lançamento duplicado | 1 ativo ([E-04](./EVIDENCIAS-TRAFEGO.md#e-04)) | 0 |
| tempo até detectar campanha parada | "quando o operador olhar" ([E-07](./EVIDENCIAS-TRAFEGO.md#e-07)) | ≤ 1 ciclo de sincronização |
| consultas GAQL por carregamento de página | ~17 ([E-07](./EVIDENCIAS-TRAFEGO.md#e-07)) | 0 |
| falha de persistência que deixa rastro | 0 % | 100 % |
| endpoint crítico indeterminado sem prazo | 2 ([E-12](./EVIDENCIAS-TRAFEGO.md#e-12)) | 0 (ADR-15) |

## 7. Backlog por ondas

Esforço: S < 1 dia · M = dias · L = 1–2 semanas, uma pessoa.

### 7.1 P0-A · Diagnóstico operacional (somente leitura) — começa já

| item | esforço | aceite | depende |
|---|---|---|---|
| A1 · Bateria de leitura sobre as duas campanhas | M | parecer que responde "é lance, é relevância ou é política", com o dado que sustenta cada hipótese | — |
| A2 · Parecer de decisão | S | recomendação escrita, sem execução | A1 |

**Fora:** alterar lance, verba ou status. Detalhe em [P0-A](./P0A-PLANO-DIAGNOSTICO.md).

### 7.2 P0-S · Segurança dos executores legados — em paralelo

| item | esforço | aceite | depende |
|---|---|---|---|
| S1 · Inventário das superfícies | S | 7 gatilhos com dono, alcance e escopo ([E-12](./EVIDENCIAS-TRAFEGO.md#e-12)) | — |
| S2 · Evidência de uso | M | cada superfície classificada usado / não usado / **indeterminado**, com a fonte | **[DE]** histórico de execuções do n8n |
| S3 · Contenção proposta | M | por superfície: autenticação real, allowlist, rotação coordenada ou desativação aprovada — com dono e janela | S2 |
| S4 · Registro de aceitação de risco | S | todo endpoint crítico indeterminado tem aceite nominal, prazo, controle compensatório e data de reavaliação (ADR-15) | S2 |

**Fora:** desativar. Detalhe em [P0-S](./P0S-PLANO-SEGURANCA.md).

### 7.3 P0-T · Inventário real

| item | esforço | aceite | depende |
|---|---|---|---|
| T1 · Identidades interna e de linhagem | M | toda campanha conhecida tem `volcCampaignId`; linhagem atribuída no lançamento (ADR-02) | — |
| T2 · Sincronizador no backend | M | snapshot por conta, com carimbo, duração e resultado | T1 |
| T3 · Inventário na tela | M | as duas campanhas aparecem com estado, lance, verba, entrega e idade do dado | T2 |
| T4 · Estados de presença | S | os seis estados do ADR-13; as três linhas de fevereiro nascem `legado não reconciliado` | T2 |
| T5 · Degradação honesta | S | conta não lida aparece como `sincronização falhou`, nunca como "sem alertas" | T2 |

### 7.4 P0-R · Reconciliação

| item | esforço | aceite | depende |
|---|---|---|---|
| R1 · Sugestão de vínculo | S | FGTS sugerida ao funil run 9, com a regra que casou visível | T3 |
| R2 · Confirmação e auditoria | M | vínculo registra quem, quando, regra, evidência e vínculo anterior; desvincular funciona | R1 |

**[DA]** Confirmação humana obrigatória na fase inicial (ADR-09).

### 7.5 P0-D · Prevenção de duplicidade

| item | esforço | aceite | depende |
|---|---|---|---|
| D1 · Prova de equivalência por composição | M | subir equivalente da FGTS **bloqueia** se compuser dois sinais fortes na mesma conta; **adverte** se só a URL casar (ADR-03) | T2 |
| D2 · Contrato de persistência | M | vazio recusado no identificador de conta; procedência da aplicação sobrevive ao trigger (ADR-10) | investigação de ADR-10 |
| D3 · Evento operacional mínimo | S | falha de registro vira evento append-only, promovível a Ocorrência no P1 (ADR-14) | — |

### 7.6 P0-F · Frescor

| item | esforço | aceite | depende |
|---|---|---|---|
| F1 · Carimbo por fonte | S | toda superfície mostra a idade do dado | T2 |
| F2 · Atualização manual limitada | S | escopo de uma conta, com limite e custo declarado | T2 |

### 7.7 Ondas seguintes

**P1** monitoramento (promoção do evento a Ocorrência, agregação em Incidente, sincronização
agendada, sino como projeção, cockpit com fonte trocada) · **P2** propostas e aprovação ·
**P3** migração do conhecimento legado · **P4** atuação automatizada **[DP]** · **P5** outros canais.

## 8. Riscos

| risco | prob. | impacto | mitigação |
|---|---|---|---|
| **[R]** vínculo campanha↔funil errado contamina receita | média | alto | confirmação humana, auditoria, reversibilidade (ADR-09) |
| **[R]** conter executor legado quebra consumidor desconhecido | média | alto | evidência antes de contenção; aceitação com prazo (ADR-06, ADR-15) |
| **[R]** o mecanismo que produziu a linha divergente sobrescreve o conserto | alta | médio | investigação precede backfill (ADR-10) |
| **[R]** parecer do P0-A cria pressão por atuação sem porta governada | alta | médio | parecer separado de execução (ADR-11) |
| **[R]** chave de agrupamento mal escolhida no evento do P0 contamina a agregação do P1 | média | médio | chave opaca, sem semântica embutida (ADR-14) |
| **[R]** o módulo de tráfego não está versionado ([E-19](./EVIDENCIAS-TRAFEGO.md#e-19)) | alta | alto | rastrear antes de mudança estrutural |
| **[DE]** histórico de execuções do n8n | — | bloqueia S2 | o dono autoriza ou executa a consulta |
