# CL-02 · Campanha Search lançável

**Horizonte**: A (núcleo do caixa) · **Resultado**: uma campanha Search nasce
pausada com intenção persistida, ledger, vínculo, reconciliação e veredito de
política — e a ativação continua impossível sem humano.

## Estado factual (F006, F009, F037)

- Canário real criado 28/08 (campanha 24183717006, PAUSED, Portal Mundo Mais);
  código do canário na main (`backend/app/trafego/canario.py`).
- Faltam os 5 gates de governança: ledger v10_01 ligado, intenção persistida,
  vínculo confirmado, ID reconciliado no inventário/H0, veredito de política.
- v10_01/v10_02 NÃO aplicadas (decisão D1); writer Python inexistente;
  aprovação da UI sem caller.
- P05-T04 (vínculo) está a um clique de operador autenticado do `done`.

## Missões

| ID | O quê | Onda | Portão |
|---|---|---|---|
| (ação humana) | Operador confirma os 2 vínculos (Maquininha/FGTS) na UI | qualquer | nenhum |
| M-W3-01 | Aplicar v10_01/02 no oficial (backup+preflight+rollback provado) | 3 | **D1** |
| M-W3-02 | Writer Python do ledger + caller do `aoSubmeter` + recibo em_voo | 3 | após M-W3-01 |
| M-W3-03 | Reconciliar ID externo do canário no inventário/H0 + veredito de política | 3 | após M-W3-02 |
| M-W3-04 | Gate humano de lançamento: D4 (credenciais/RLS) provado por smoke anônimo | 3 | **D4** |

## Regras invioláveis (do DoD CL-B)

- Timeout nunca oferece reenvio; conta-laboratório ≠ conta financeira;
  ativação permanece impossível sem novo ato humano explícito.

## Resultado observável

Cockpit da campanha canônica mostra recibo de lançamento, vínculo e estado do
ledger; `trafego_vinculo` > 0 linhas; P05-T11 promovível a done com prova.
