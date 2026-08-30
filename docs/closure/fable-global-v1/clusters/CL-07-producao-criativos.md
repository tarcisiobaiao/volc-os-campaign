# CL-07 · Estúdio Criativo — do laboratório à produção

**Horizonte**: B (não bloqueia o caixa) · **Resultado**: pedido aprovado
percorre contrato → motor → worker durável → storage verificado → recibo →
biblioteca → destino, sem depender do processo web.

## Estado factual (F030)

- v11_01/02 aplicadas; 10 páginas roteadas; bancada SQLite provada (234+226).
- v11_03 provada 129/129 em cluster descartável, NÃO aplicada (**D6**);
  sem writer Postgres; sem worker remoto; Remotion não-hermético (11 famílias
  de fontes baixadas em runtime; licença não decidida).
- 4 lacunas conhecidas (L1-L4 do handoff da bancada).

## Ordem de missões (após D6; sequência do próprio roadmap P17)

1. M-W4-01: aplicar v11_03 (gate humano, backup, rollback executável).
2. M-W4-02: porta única de depósito (SQLite local / Postgres por ambiente),
   mesmo contrato de claim/lease/heartbeat nos dois adapters.
3. M-W4-03: worker fora do processo web (interrompível sem perder/duplicar).
4. M-W4-04: storage remoto com verificação de bytes (releitura antes de
   "verificado"; divergência é terminal).
5. M-W4-05: Remotion hermético + decisão de licença (**pré-requisito de
   faturar vídeo**).
6. M-W4-06: primeira peça real com aprovação humana por destino.

## Regra dura

Linhagem por bytes (sha256), nunca por nome; estado LOCAL→UPLOADED_UNVERIFIED→
VERIFIED_* monotônico; nenhuma peça "verificada" sem releitura.
