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
